import asyncio
import atexit
import logging
import optparse
import os
import subprocess

from opentrons import robot
from opentrons.config import infer_config_base_dir
from opentrons.drivers.rpi_drivers import gpio
from opentrons.drivers import serial_communication
from opentrons.system import nmcli

log = logging.getLogger(__name__)

RESULT_SPACE = '\t- {}'
FAIL = 'FAIL\t*** !!! ***'
PASS = 'PASS'

USB_MOUNT_FILEPATH = '/mnt/usbdrive'
DATA_FOLDER = str(infer_config_base_dir())
VIDEO_FILEPATH = os.path.join(DATA_FOLDER, 'cam_test.jpg')
AUDIO_FILE_PATH = '/etc/audio/speaker-test.mp3'


def _find_storage_device():
    if os.path.exists(USB_MOUNT_FILEPATH) is False:
        run_quiet_process('mkdir {}'.format(USB_MOUNT_FILEPATH))
    if os.path.ismount(USB_MOUNT_FILEPATH) is False:
        sdn1_devices = [
            '/dev/sd{}1'.format(l)
            for l in 'abcdefgh'
            if os.path.exists('/dev/sd{}1'.format(l))
        ]
        if len(sdn1_devices) == 0:
            print(RESULT_SPACE.format(FAIL))
            return
        try:
            run_quiet_process(
                'mount {0} {1}'.format(sdn1_devices[0], USB_MOUNT_FILEPATH))
        except Exception:
            print(RESULT_SPACE.format(FAIL))
            return
    return True


def _this_wifi_ip_address():
    loop = asyncio.get_event_loop()
    wifi_info = loop.run_until_complete(
        nmcli.iface_info(nmcli.NETWORK_IFACES.WIFI))
    assert wifi_info['ipAddress'], 'Not connected to wifi'
    return wifi_info['ipAddress'].split('/')[0]


def _erase_data(filepath):
    if os.path.exists(filepath):
        os.remove(filepath)


def _reset_lights():
    robot._driver.turn_off_rail_lights()
    gpio.set_button_light(blue=True)


def _get_state_of_inputs():
    smoothie_switches = robot._driver.switch_state
    probe = smoothie_switches['Probe']
    endstops = {
        ax: val
        for ax, val in smoothie_switches.items()
        if ax in 'XYZA'  # only test gantry axes
    }
    return {
        'button': robot._driver.read_button(),
        'windows': robot._driver.read_window_switches(),
        'probe': probe,
        'endstops': endstops
    }


def _set_lights(state):
    if state['windows']:
        robot._driver.turn_off_rail_lights()
    else:
        robot._driver.turn_on_rail_lights()
    red, green, blue = (False, False, False)
    if any(state['endstops'].values()):
        red = True
    if state['probe']:
        green = True
    if state['button']:
        blue = True
    gpio.set_button_light(red=red, green=green, blue=blue)


def run_quiet_process(command):
    subprocess.check_output('{} &> /dev/null'.format(command), shell=True)


def _get_unique_smoothie_responses(responses):
    """ Find the number of truly unique responses from the smoothie, ignoring

    - Responses that are only different because of interjected \r\n
    - Responses that are only different by \r or \n replacing a single char

    Both of these errors are results of race conditions between smoothie
    terminal echo mode and responses, and do not indicate serial failures.
    """
    uniques = list(set(responses))  # Eliminate exact repetitions
    # eliminate "uniques" that are really just the second \r\n racing
    # with the smoothie's return values
    true_uniques = [uniques[0]]
    for unique in uniques[1:]:
        if len(unique) != len(uniques[0]):
            true_uniques.append(unique)
            continue
        for a, b in zip(uniques[0], unique):
            if a in '\r\n':
                continue
            elif b in '\r\n':
                continue
            elif a != b:
                true_uniques.append(unique)
                break
    return true_uniques


def test_smoothie_gpio(port_name=''):
    def _write_and_return(msg):
        return serial_communication.write_and_return(
            msg + '\r\n',
            'ok\r\n',
            robot._driver._connection,
            timeout=1)

    print('CONNECT')
    if port_name:
        robot.connect(port_name)
    else:
        robot.connect()
    d = robot._driver
    # make sure the driver is currently working as expected
    version_response = _write_and_return('version')
    if 'version' in version_response:
        print(RESULT_SPACE.format(PASS))
    else:
        print(RESULT_SPACE.format(FAIL))

    print('DATA LOSS')
    [_write_and_return('version') for i in range(10)]
    # check that if we write the same thing to the smoothie a bunch
    # it works
    data = [_write_and_return('version') for i in range(100)]
    true_uniques = _get_unique_smoothie_responses(data)
    if len(true_uniques) == 1:
        print(RESULT_SPACE.format(PASS))
    else:
        log.info(f'true uniques: {true_uniques}')
        print(RESULT_SPACE.format(FAIL))

    print('HALT')
    d._connection.reset_input_buffer()
    # drop the HALT line LOW, and make sure there is an error state
    d.hard_halt()

    old_timeout = int(d._connection.timeout)
    d._connection.timeout = 1  # 1 second
    r = d._connection.readline().decode()
    if 'ALARM' in r:
        print(RESULT_SPACE.format(PASS))
    else:
        print(RESULT_SPACE.format(FAIL))

    d._reset_from_error()
    d._connection.timeout = old_timeout

    print('ISP')
    # drop the ISP line to LOW, and make sure it is dead
    d._smoothie_programming_mode()
    try:                                        # NOQA
        _write_and_return('M999')               # NOQA
        print(RESULT_SPACE.format(FAIL))        # NOQA
    except Exception:                           # NOQA
        print(RESULT_SPACE.format(PASS))        # NOQA

    print('RESET')
    # toggle the RESET line to LOW, and make sure it is NOT dead
    d._smoothie_reset()
    r = _write_and_return('M119')
    if 'X_max' in r:
        print(RESULT_SPACE.format(PASS))
    else:
        print(RESULT_SPACE.format(FAIL))


def test_switches_and_lights(port_name=''):
    print('\n')
    print('* BUTTON\t--> BLUE')
    print('* PROBE\t\t--> GREEN')
    print('* ENDSTOP\t--> RED')
    print('* WINDOW\t--> LIGHTS')
    print('')
    print('Next\t--> CTRL-C')
    print('')
    # enter button-read loop
    if port_name:
        robot.connect(port_name)
    else:
        robot.connect()
    try:
        while True:
            state = _get_state_of_inputs()
            _set_lights(state)
    except KeyboardInterrupt:
        print()
        pass


def test_speaker():
    print('Speaker')
    print('Next\t--> CTRL-C')
    try:
        run_quiet_process('mpg123 {}'.format(AUDIO_FILE_PATH))
    except KeyboardInterrupt:
        pass
        print()


def record_camera(filepath):
    print('USB Camera')
    # record 1 second of video from the USB camera
    c = 'ffmpeg -f video4linux2 -s 640x480 -i /dev/video0 -ss 0:0:1 -frames 1 {}'  # NOQA
    try:
        run_quiet_process(c.format(filepath))
        print(RESULT_SPACE.format(PASS))
    except Exception:
        print(RESULT_SPACE.format(FAIL))


def copy_to_usb_drive_and_back(filepath):
    # create the mount directory
    print('USB Flash-Drive')

    if _find_storage_device():
        # remove double-quotes
        filepath = filepath.replace('"', '')
        # move the file to and from it
        name = filepath.split('/')[-1]
        try:
            run_quiet_process(
                'mv "{0}" "/mnt/usbdrive/{1}"'.format(filepath, name))
        except Exception:
            print(RESULT_SPACE.format(FAIL))
            return
        if os.path.exists('/mnt/usbdrive/{}'.format(name)):
            try:
                run_quiet_process(
                    'mv "/mnt/usbdrive/{0}" "{1}"'.format(name, filepath))
            except Exception:
                print(RESULT_SPACE.format(FAIL))
                return
            if os.path.exists(filepath):
                print(RESULT_SPACE.format(PASS))
            else:
                print(RESULT_SPACE.format(FAIL))
        else:
            print(RESULT_SPACE.format(FAIL))


def start_server(folder, filepath):
    print('\nOPEN\t--> {0}:8000/{1}\n'.format(
        _this_wifi_ip_address(),
        filepath.split('/')[-1]
        ))
    print('\nQuit\t--> CTRL-C\n\n\n')
    try:
        run_quiet_process('cd {} && python -m http.server'.format(folder))
    except KeyboardInterrupt:
        print()
        pass


def get_optional_port_name():
    parser = optparse.OptionParser(usage='usage: %prog [options] ')
    parser.add_option(
        "-p", "--p", dest="port", default='',
        type='str', help='serial port of the smoothie'
    )
    options, _ = parser.parse_args(args=None, values=None)
    return options.port


if __name__ == '__main__':
    # put quotes around filepaths to allow whitespaces
    logging.basicConfig(filename='factory-test.log')
    data_folder_quoted = '"{}"'.format(DATA_FOLDER)
    video_filepath_quoted = '"{}"'.format(VIDEO_FILEPATH)
    atexit.register(_reset_lights)
    atexit.register(_erase_data, video_filepath_quoted)
    _reset_lights()
    _erase_data(video_filepath_quoted)
    port_name = get_optional_port_name()
    test_smoothie_gpio(port_name)
    test_switches_and_lights(port_name)
    test_speaker()
    record_camera(video_filepath_quoted)
    copy_to_usb_drive_and_back(video_filepath_quoted)
    start_server(data_folder_quoted, VIDEO_FILEPATH)
    exit()
