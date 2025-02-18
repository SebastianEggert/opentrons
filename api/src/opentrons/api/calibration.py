import functools
import logging
from copy import copy

from opentrons.util import calibration_functions
from opentrons.config import feature_flags as ff
from opentrons.broker import Broker
from opentrons.types import Point, Mount, Location
from opentrons.protocol_api import labware
from opentrons.hardware_control import CriticalPoint

from .models import Container

log = logging.getLogger(__name__)

VALID_STATES = {'probing', 'moving', 'ready'}


# This hack is because if you have an old container that uses Placeable with
# just one well, Placeable.wells() returns the Well rather than [Well].
# Passing the well as an argument, though, will always return the well.
def _well0(cont):
    if isinstance(cont, labware.Labware):
        return cont.wells()[0]
    else:
        return cont.wells(0)


def _require_lock(func):
    """ Decorator to make a function require a lock. Only works for instance
    methods of CalibrationManager """
    @functools.wraps(func)
    def decorated(*args, **kwargs):
        self = args[0]
        if self._lock:
            with self._lock:
                return func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    return decorated


class CalibrationManager:
    """
    Serves endpoints that are primarily used in
    opentrons/app/ui/robot/api-client/client.js
    """
    TOPIC = 'calibration'

    def __init__(self, hardware, loop=None, broker=None, lock=None):
        self._broker = broker or Broker()
        self._hardware = hardware
        self._loop = loop
        self.state = None
        self._lock = lock

    def _set_state(self, state):
        if state not in VALID_STATES:
            raise ValueError(
                'State {0} not in {1}'.format(state, VALID_STATES))
        self.state = state
        self._on_state_changed()

    @_require_lock
    def tip_probe(self, instrument):
        inst = instrument._instrument
        log.info('Probing tip with {}'.format(instrument.name))
        self._set_state('probing')

        if ff.use_protocol_api_v2():
            mount = Mount[instrument._instrument.mount.upper()]
            assert instrument.tip_racks,\
                'No known tipracks for {}'.format(instrument)
            tip_length = instrument.tip_racks[0]._container.tip_length
            # TODO (tm, 2019-04-22): This warns "coroutine not awaited" in
            # TODO: test. The test fixture probably needs to be modified to get
            # TODO: a synchronous adapter instead of a raw hardware_control API
            measured_center = self._hardware.locate_tip_probe_center(
                mount, tip_length)
        else:
            measured_center = calibration_functions.probe_instrument(
                instrument=inst,
                robot=inst.robot)

        log.info('Measured probe top center: {0}'.format(measured_center))

        if ff.use_protocol_api_v2():
            self._hardware.update_instrument_offset(
                Mount[instrument._instrument.mount.upper()],
                from_tip_probe=measured_center)
            config = self._hardware.config
        else:
            config = calibration_functions.update_instrument_config(
                instrument=inst,
                measured_center=measured_center)

        log.info('New config: {0}'.format(config))

        self.move_to_front(instrument)
        self._set_state('ready')

    @_require_lock
    def pick_up_tip(self, instrument, container):
        if not isinstance(container, Container):
            raise ValueError(
                'Invalid object type {0}. Expected models.Container'
                .format(type(container)))

        inst = instrument._instrument
        log.info('Picking up tip from {} in {} with {}'.format(
            container.name, container.slot, instrument.name))
        self._set_state('moving')
        if ff.use_protocol_api_v2():
            with instrument._context.temp_connect(self._hardware):
                loc = _well0(container._container)
                instrument._context.location_cache =\
                    Location(self._hardware.gantry_position(
                                Mount[inst.mount.upper()],
                                critical_point=CriticalPoint.NOZZLE,
                                refresh=True),
                             loc)
                inst.pick_up_tip(loc)
        else:
            inst.pick_up_tip(_well0(container._container))
        self._set_state('ready')

    @_require_lock
    def drop_tip(self, instrument, container):
        if not isinstance(container, Container):
            raise ValueError(
                'Invalid object type {0}. Expected models.Container'
                .format(type(container)))

        inst = instrument._instrument
        log.info('Dropping tip from {} in {} with {}'.format(
            container.name, container.slot, instrument.name))
        self._set_state('moving')
        if ff.use_protocol_api_v2():
            with instrument._context.temp_connect(self._hardware):
                instrument._context.location_cache = None
                inst.drop_tip(_well0(container._container))
        else:
            inst.drop_tip(_well0(container._container))
        self._set_state('ready')

    @_require_lock
    def return_tip(self, instrument):
        inst = instrument._instrument
        log.info('Returning tip from {}'.format(instrument.name))
        self._set_state('moving')
        if ff.use_protocol_api_v2():
            with instrument._context.temp_connect(self._hardware):
                instrument._context.location_cache = None
                inst.return_tip()
        else:
            inst.return_tip()
        self._set_state('ready')

    @_require_lock
    def move_to_front(self, instrument):
        inst = instrument._instrument
        log.info('Moving {}'.format(instrument.name))
        self._set_state('moving')
        if ff.use_protocol_api_v2():
            current = self._hardware.gantry_position(
                Mount[inst.mount.upper()],
                critical_point=CriticalPoint.NOZZLE)
            dest = instrument._context.deck.position_for(5)\
                                           .point._replace(z=150)
            self._hardware.move_to(Mount[inst.mount.upper()],
                                   current,
                                   critical_point=CriticalPoint.NOZZLE)
            self._hardware.move_to(Mount[inst.mount.upper()],
                                   dest._replace(z=current.z),
                                   critical_point=CriticalPoint.NOZZLE)
            self._hardware.move_to(Mount[inst.mount.upper()],
                                   dest, critical_point=CriticalPoint.NOZZLE)
        else:
            calibration_functions.move_instrument_for_probing_prep(
                inst, inst.robot)
        self._set_state('ready')

    @_require_lock
    def move_to(self, instrument, container):
        if not isinstance(container, Container):
            raise ValueError(
                'Invalid object type {0}. Expected models.Container'
                .format(type(container)))

        inst = instrument._instrument
        cont = container._container
        target = _well0(cont).top()

        log.info('Moving {} to {} in {}'.format(
            instrument.name, container.name, container.slot))
        self._set_state('moving')

        if ff.use_protocol_api_v2():
            with instrument._context.temp_connect(self._hardware):
                instrument._context.location_cache = None
                inst.move_to(target)
        else:
            inst.move_to(target)

        self._set_state('ready')

    @_require_lock
    def jog(self, instrument, distance, axis):
        inst = instrument._instrument
        log.info('Jogging {} by {} in {}'.format(
            instrument.name, distance, axis))
        self._set_state('moving')
        if ff.use_protocol_api_v2():
            self._hardware.move_rel(
                Mount[inst.mount.upper()], Point(**{axis: distance}))
        else:
            calibration_functions.jog_instrument(
                instrument=inst,
                distance=distance,
                axis=axis,
                robot=inst.robot)
        self._set_state('ready')

    @_require_lock
    def home(self, instrument):
        inst = instrument._instrument
        log.info('Homing {}'.format(instrument.name))
        self._set_state('moving')
        if ff.use_protocol_api_v2():
            with instrument._context.temp_connect(self._hardware):
                instrument._context.location_cache = None
                inst.home()
        else:
            inst.home()
        self._set_state('ready')

    @_require_lock
    def update_container_offset(self, container, instrument):
        inst = instrument._instrument
        log.info('Updating {} in {}'.format(container.name, container.slot))
        if ff.use_protocol_api_v2():
            if 'centerMultichannelOnWells' in container._container.quirks:
                cp = CriticalPoint.XY_CENTER
            else:
                cp = None
            here = self._hardware.gantry_position(Mount[inst.mount.upper()],
                                                  critical_point=cp)
            # Reset calibration so we don’t actually calibrate the offset
            # relative to the old calibration
            container._container.set_calibration(Point(0, 0, 0))
            if ff.calibrate_to_bottom():
                orig = _well0(container._container).bottom().point
            else:
                orig = _well0(container._container).top().point
            delta = here - orig
            labware.save_calibration(container._container, delta)
        else:
            inst.robot.calibrate_container_with_instrument(
                container=container._container,
                instrument=inst,
                save=True
            )

    def _snapshot(self):
        return {
            'topic': CalibrationManager.TOPIC,
            'name': 'state',
            'payload': copy(self)
        }

    def _on_state_changed(self):
        self._hardware._use_safest_height = (self.state in
                                             ['probing', 'moving'])
        self._broker.publish(CalibrationManager.TOPIC, self._snapshot())
