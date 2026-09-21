import type { RecoveryProposal, RecoveryReceipt } from './types'

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
  busy,
  onApply,
  onRefresh,
}: {
  proposals: RecoveryProposal[]
  receipts: RecoveryReceipt[]
  busy: boolean
  onApply: (proposalId: string) => Promise<void>
  onRefresh: () => Promise<void>
}) {
  return (
    <div className="recovery-panel">
      <div className="recovery-head">
        <div>
          <span>RECOVERY PLANS</span>
          <b>Operator-approved mitigation proposals</b>
        </div>
        <div className="recovery-head-actions">
          <small>AUTO-APPLY OFF</small>
          <button disabled={busy} onClick={onRefresh}>Recalculate</button>
        </div>
      </div>

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
                  <b>Human operator</b>
                </div>
                <button
                  disabled={busy || !proposal.requires_approval}
                  onClick={() => onApply(proposal.id)}
                >
                  Approve & apply
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="recovery-receipts">
        <span className="section-kicker">RECENT OPERATOR RECEIPTS · {receipts.length}</span>
        {receipts.length === 0 ? (
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
              <small>{receipt.approved_by.replace('_', ' ')}</small>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
