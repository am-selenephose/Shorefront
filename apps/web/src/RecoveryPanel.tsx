import { useState } from 'react'
import type {
  OperatorIdentity,
  RecoveryProposal,
  RecoveryReceipt,
} from './types'

const usd = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)

function actionLabel(action: RecoveryProposal['actions'][number]) {
  if (action.action_type === 'reassign_resource') {
    return (action.service_kind || 'resource') + ': ' +
      (action.from_resource_id || 'current') + ' → ' +
      (action.to_resource_id || 'new')
  }
  if (action.action_type === 'move_berth') {
    return 'berth: ' + (action.from_berth_id || 'current') + ' → ' +
      (action.to_berth_id || 'new')
  }
  return 'shift ' + (action.service_kind || 'window') + ' +' +
    String(action.shift_minutes) + 'm'
}

export function RecoveryPanel({
  proposals,
  receipts,
  identity,
  busy,
  authBusy,
  onApply,
  onRefresh,
  onConnect,
  onDisconnect,
}: {
  proposals: RecoveryProposal[]
  receipts: RecoveryReceipt[]
  identity: OperatorIdentity | null
  busy: boolean
  authBusy: boolean
  onApply: (proposalId: string) => Promise<void>
  onRefresh: () => Promise<void>
  onConnect: (token: string) => Promise<boolean>
  onDisconnect: () => void
}) {
  const [tokenInput, setTokenInput] = useState('')
  const canApprove = identity?.role === 'operator' || identity?.role === 'supervisor'

  async function connect() {
    const token = tokenInput.trim()
    if (!token) return
    const ok = await onConnect(token)
    if (ok) setTokenInput('')
  }

  return (
    <div className="recovery-panel">
      <div className="recovery-head">
        <div>
          <span>RECOVERY PLANS</span>
          <b>Identity-bound human approval</b>
        </div>
        <div className="recovery-head-actions">
          <small>AUTO-APPLY OFF</small>
          <button disabled={busy} onClick={onRefresh}>Recalculate</button>
        </div>
      </div>

      <div className="operator-session">
        <div className="operator-session-copy">
          <span>OPERATOR SESSION</span>
          {identity ? (
            <>
              <b>{identity.display_name}</b>
              <small>{identity.operator_id} · {identity.role}</small>
            </>
          ) : (
            <>
              <b>Not authenticated</b>
              <small>Proposal visibility is read-only until an operator session is verified.</small>
            </>
          )}
        </div>

        {identity ? (
          <div className="operator-connected">
            <span className={'role-badge ' + identity.role}>{identity.role}</span>
            <button disabled={authBusy || busy} onClick={onDisconnect}>End session</button>
          </div>
        ) : (
          <div className="operator-login">
            <input
              aria-label="Operator access token"
              type="password"
              autoComplete="off"
              placeholder="Operator access token"
              value={tokenInput}
              onChange={event => setTokenInput(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Enter') void connect()
              }}
            />
            <button
              disabled={authBusy || !tokenInput.trim()}
              onClick={() => void connect()}
            >
              {authBusy ? 'Verifying...' : 'Verify'}
            </button>
          </div>
        )}
      </div>

      {identity?.role === 'viewer' && (
        <div className="authority-note viewer">
          Viewer session active. Recovery proposals are inspectable, but approval is blocked by role policy.
        </div>
      )}

      {proposals.length === 0 ? (
        <div className="recovery-empty">
          <b>No mitigation proposal required.</b>
          <span>Inject a tug, berth, or scheduling incident to generate alternatives.</span>
        </div>
      ) : (
        <div className="recovery-grid">
          {proposals.slice(0, 4).map((proposal, index) => (
            <article className={'recovery-card' + (index === 0 ? ' preferred' : '')} key={proposal.id}>
              <div className="recovery-card-head">
                <div>
                  <span>{index === 0 ? 'LOWEST DISRUPTION' : 'ALTERNATIVE'}</span>
                  <b>{proposal.title}</b>
                </div>
                <span className={'risk ' + proposal.projected_risk}>
                  {proposal.projected_risk.toUpperCase()}
                </span>
              </div>

              <div className="recovery-metrics">
                <div><span>DELAY</span><b>{proposal.projected_total_delay_minutes}m</b></div>
                <div><span>COST</span><b>{usd(proposal.projected_modeled_cost_usd)}</b></div>
                <div><span>CONFLICTS</span><b>{proposal.projected_berth_conflicts}</b></div>
                <div><span>BLOCKED</span><b>{proposal.projected_blocked_services}</b></div>
                <div><span>SCORE</span><b>{proposal.disruption_score.toFixed(0)}</b></div>
                <div>
                  <span>CONFIDENCE</span>
                  <b className={'decision-confidence ' + proposal.decision_confidence}>
                    {proposal.decision_confidence.toUpperCase()}
                  </b>
                </div>
              </div>

              <div className={'recovery-data-quality ' + proposal.decision_confidence}>
                <b>DATA CONFIDENCE · {proposal.decision_confidence.toUpperCase()}</b>
                {proposal.data_quality_warnings.length === 0 ? (
                  <span>All active referenced sources are healthy live observations.</span>
                ) : (
                  proposal.data_quality_warnings.slice(0, 3).map(warning => (
                    <span key={warning}>{warning}</span>
                  ))
                )}
              </div>

              <div className="recovery-actions">
                {proposal.actions.map((action, actionIndex) => (
                  <div key={proposal.id + '-' + String(actionIndex)}>
                    <i />
                    <span>{actionLabel(action)}</span>
                  </div>
                ))}
              </div>

              <div className="recovery-rationale">
                {proposal.rationale.slice(0, 3).map(reason => <p key={reason}>{reason}</p>)}
              </div>

              <div className="recovery-approval">
                <div>
                  <span>AUTHORITY</span>
                  <b>
                    {identity
                      ? identity.display_name + ' · ' + identity.role
                      : 'Operator / supervisor required'}
                  </b>
                </div>
                <button
                  disabled={busy || !proposal.requires_approval || !canApprove}
                  onClick={() => onApply(proposal.id)}
                >
                  {!identity
                    ? 'Authenticate to apply'
                    : canApprove
                      ? 'Approve & apply'
                      : 'View only'}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="recovery-receipts">
        <span className="section-kicker">
          RECENT OPERATOR RECEIPTS · {identity ? receipts.length : 'AUTH REQUIRED'}
        </span>

        {!identity ? (
          <p>Authenticate to inspect identity-bound recovery receipts.</p>
        ) : receipts.length === 0 ? (
          <p>No recovery action has been approved in this demo state.</p>
        ) : (
          receipts.slice(0, 4).map(receipt => (
            <div className="recovery-receipt-row" key={receipt.proposal_id}>
              <div>
                <b>{receipt.target_port_call_id}</b>
                <span>{new Date(receipt.applied_at).toLocaleString()}</span>
              </div>
              <div>
                <span>{receipt.resulting_berth_conflicts} conflicts</span>
                <span>{receipt.resulting_blocked_services} blocked</span>
                <span>{receipt.resulting_total_delay_minutes}m delay</span>
              </div>
              <small>
                {(receipt.approved_display_name || receipt.approved_by) +
                  ' · ' + receipt.approved_role}
              </small>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
