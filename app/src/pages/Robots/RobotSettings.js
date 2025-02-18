// @flow
// connect and configure robots page
import * as React from 'react'
import { connect } from 'react-redux'
import { withRouter, Route, Switch, Redirect } from 'react-router'

import {
  selectors as robotSelectors,
  actions as robotActions,
} from '../../robot'
import { CONNECTABLE, REACHABLE } from '../../discovery'
import {
  getBuildrootUpdateSeen,
  getBuildrootRobot,
  getBuildrootUpdateInProgress,
  getBuildrootUpdateAvailable,
} from '../../shell'

import { makeGetRobotHome, clearHomeResponse } from '../../http-api-client'

import { SpinnerModalPage } from '@opentrons/components'
import { ErrorModal } from '../../components/modals'
import Page from '../../components/Page'
import RobotSettings, {
  ConnectAlertModal,
} from '../../components/RobotSettings'
import UpdateBuildroot from '../../components/RobotSettings/UpdateBuildroot'
import CalibrateDeck from '../../components/CalibrateDeck'
import ConnectBanner from '../../components/RobotSettings/ConnectBanner'
import ReachableRobotBanner from '../../components/RobotSettings/ReachableRobotBanner'
import ResetRobotModal from '../../components/RobotSettings/ResetRobotModal'

import type { ContextRouter } from 'react-router'
import type { State, Dispatch, Error } from '../../types'
import type { ViewableRobot } from '../../discovery'
import type { ShellUpdateState } from '../../shell'

type WithRouterOP = {|
  robot: ViewableRobot,
  appUpdate: ShellUpdateState,
|}

type OP = {|
  ...ContextRouter,
  ...WithRouterOP,
|}

type SP = {|
  showUpdateModal: boolean,
  showConnectAlert: boolean,
  homeInProgress: ?boolean,
  homeError: ?Error,
  updateInProgress: boolean,
|}

type DP = {| dispatch: Dispatch |}

type Props = {|
  ...OP,
  ...SP,
  closeHomeAlert?: () => mixed,
  closeConnectAlert: () => mixed,
|}

export default withRouter<WithRouterOP>(
  connect<Props, OP, SP, {||}, State, Dispatch>(
    makeMapStateToProps,
    null,
    mergeProps
  )(RobotSettingsPage)
)

const UPDATE_FRAGMENT = 'update'
const CALIBRATE_DECK_FRAGMENT = 'calibrate-deck'
const RESET_FRAGMENT = 'reset'

function RobotSettingsPage(props: Props) {
  const {
    robot,
    homeInProgress,
    homeError,
    closeHomeAlert,
    showConnectAlert,
    closeConnectAlert,
    showUpdateModal,
    updateInProgress,
    match: { path, url },
  } = props

  const titleBarProps = { title: robot.displayName }
  const updateUrl = `${url}/${UPDATE_FRAGMENT}`
  const calibrateDeckUrl = `${url}/${CALIBRATE_DECK_FRAGMENT}`
  const resetUrl = `${url}/${RESET_FRAGMENT}`

  // TODO(mc, 2018-07-26): these routes are too complicated and mess with the
  // active state of the robot side-panel links. Remove in favor of a component
  // or redux state-based solution
  return (
    <>
      <Page titleBarProps={titleBarProps}>
        {robot.status === REACHABLE && !updateInProgress && (
          <ReachableRobotBanner key={robot.name} {...robot} />
        )}
        {robot.status === CONNECTABLE && (
          <ConnectBanner {...robot} key={Number(robot.connected)} />
        )}

        <RobotSettings
          robot={robot}
          updateUrl={updateUrl}
          calibrateDeckUrl={calibrateDeckUrl}
          resetUrl={resetUrl}
        />
      </Page>
      <Switch>
        <Route
          path={`${path}/${UPDATE_FRAGMENT}`}
          render={routeProps => {
            return (
              <UpdateBuildroot
                robot={robot}
                close={() => routeProps.history.push(url)}
              />
            )
          }}
        />

        <Route
          path={`${path}/${CALIBRATE_DECK_FRAGMENT}`}
          render={props => <CalibrateDeck robot={robot} parentUrl={url} />}
        />

        <Route
          path={`${path}/${RESET_FRAGMENT}`}
          render={props => <ResetRobotModal robot={robot} />}
        />

        <Route
          exact
          path={path}
          render={() => {
            if (showUpdateModal) return <Redirect to={updateUrl} />

            // only show homing spinner and error on main page
            // otherwise, it will show up during homes in pipette swap
            return (
              <React.Fragment>
                {homeInProgress && (
                  <SpinnerModalPage
                    titleBar={titleBarProps}
                    message="Robot is homing."
                  />
                )}

                {!!homeError && (
                  <ErrorModal
                    heading="Robot unable to home"
                    error={homeError}
                    description="Robot was unable to home, please try again."
                    close={closeHomeAlert}
                  />
                )}
              </React.Fragment>
            )
          }}
        />
      </Switch>

      {showConnectAlert && (
        <ConnectAlertModal onCloseClick={closeConnectAlert} />
      )}
    </>
  )
}

function makeMapStateToProps(): (state: State, ownProps: OP) => SP {
  const getHomeRequest = makeGetRobotHome()

  return (state, ownProps) => {
    const { robot } = ownProps
    const connectRequest = robotSelectors.getConnectRequest(state)
    const homeRequest = getHomeRequest(state, robot)
    const buildrootUpdateSeen = getBuildrootUpdateSeen(state)
    const buildrootUpdateType = getBuildrootUpdateAvailable(state, robot)
    const updateInProgress = getBuildrootUpdateInProgress(state, robot)
    const currentBrRobot = getBuildrootRobot(state)

    const showUpdateModal =
      updateInProgress ||
      (!buildrootUpdateSeen &&
        buildrootUpdateType === 'upgrade' &&
        currentBrRobot === null)

    return {
      updateInProgress,
      showUpdateModal: !!showUpdateModal,
      homeInProgress: homeRequest && homeRequest.inProgress,
      homeError: homeRequest && homeRequest.error,
      showConnectAlert: !connectRequest.inProgress && !!connectRequest.error,
    }
  }
}

function mergeProps(stateProps: SP, dispatchProps: DP, ownProps: OP): Props {
  const { robot } = ownProps
  const { dispatch } = dispatchProps
  const props = {
    ...stateProps,
    ...ownProps,
    closeConnectAlert: () => dispatch(robotActions.clearConnectResponse()),
  }

  if (robot) {
    return {
      ...props,
      closeHomeAlert: () => dispatch(clearHomeResponse(robot)),
    }
  }

  return props
}
