// @flow
// setup pipettes component
import * as React from 'react'
import { connect } from 'react-redux'
import { Redirect } from 'react-router'

import { selectors as robotSelectors } from '../../robot'
import { getPipettesState, fetchPipettes } from '../../robot-api'
import { getConnectedRobot } from '../../discovery'

import Page, { RefreshWrapper } from '../../components/Page'
import TipProbe from '../../components/TipProbe'
import { PipetteTabs, Pipettes } from '../../components/calibrate-pipettes'
import SessionHeader from '../../components/SessionHeader'

import type { ContextRouter } from 'react-router'
import type { State, Dispatch } from '../../types'
import type { Pipette, TiprackByMountMap } from '../../robot'
import type { PipettesState } from '../../robot-api'
import type { Robot } from '../../discovery'

type OP = ContextRouter

type SP = {|
  pipettes: Array<Pipette>,
  tipracksByMount: TiprackByMountMap,
  currentPipette: ?Pipette,
  actualPipettes: ?PipettesState,
  _robot: ?Robot,
|}

type DP = {| dispatch: Dispatch |}

type Props = {|
  ...OP,
  ...SP,
  fetchPipettes: () => mixed,
  changePipetteUrl: string,
|}

export default connect<Props, OP, SP, {||}, State, Dispatch>(
  mapStateToProps,
  null,
  mergeProps
)(CalibratePipettesPage)

function CalibratePipettesPage(props: Props) {
  const {
    pipettes,
    tipracksByMount,
    actualPipettes,
    currentPipette,
    fetchPipettes,
    match: { url, params },
    changePipetteUrl,
  } = props

  // redirect back to mountless route if mount doesn't exist
  if (params.mount && !currentPipette) {
    return <Redirect to={url.replace(`/${params.mount}`, '')} />
  }

  return (
    <RefreshWrapper refresh={fetchPipettes}>
      <Page titleBarProps={{ title: <SessionHeader /> }}>
        <PipetteTabs {...{ pipettes, currentPipette }} />
        <Pipettes
          {...{
            pipettes,
            tipracksByMount,
            currentPipette,
            actualPipettes,
            changePipetteUrl,
          }}
        />
        {!!currentPipette && <TipProbe {...currentPipette} />}
      </Page>
    </RefreshWrapper>
  )
}

function mapStateToProps(state: State, ownProps: OP): SP {
  const { mount } = ownProps.match.params
  const _robot = getConnectedRobot(state)
  const pipettes = robotSelectors.getPipettes(state)
  const tipracksByMount = robotSelectors.getTipracksByMount(state)
  const currentPipette = pipettes.find(p => p.mount === mount)
  const actualPipettes = _robot && getPipettesState(state, _robot.name)

  return {
    _robot,
    pipettes,
    tipracksByMount,
    actualPipettes,
    currentPipette,
  }
}

function mergeProps(stateProps: SP, dispatchProps: DP, ownProps: OP): Props {
  const { dispatch } = dispatchProps
  const { _robot } = stateProps
  const changePipetteUrl = _robot
    ? `/robots/${_robot.name}/instruments`
    : '/robots'

  return {
    ...ownProps,
    ...stateProps,
    changePipetteUrl,
    fetchPipettes: () => _robot && dispatch(fetchPipettes(_robot)),
  }
}
