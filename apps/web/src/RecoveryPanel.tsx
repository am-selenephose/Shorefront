import type { RecoveryProposal } from './types'

const usd = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)

export function RecoveryPanel({
  proposals,
  busy,
  onApply,
}: {
  proposals: RecoveryProposal[]
  busy: boolean
  onApply: (proposalId: string) => Promise<void>
}) {
  return (
    <div className="recovery-panel">
      <div className="recovery-authority">
        <div>
          <span>RECOVERY ENGINE</span>
          <b>Decision support, never auto-execution</b>
        </div>
        <span className="authority-pill">HUMAN APPROVAL</span>
      </div>

      {proposals.length === 0 ? (
        <div className="recovery-empty">
          <b>No corrective action required.</b>
          <span>Recovery proposals appear when the operational graph has a recoverable conflict or resource failure.</span>
        </div>
      ) : (
        <div className="recovery-list">
          {proposals.slice(0, 4).map((proposal, index) => (
            <article className={'recovery-card' + (index === 0 ? ' recommended' : '')} key={proposal.id}>
              <div className="recovery-card-head">
                <div>
                  <span>{index === 0 ? 'RECOMMENDED' : 'ALTERNATIVE ' + (index + 1)}</span>
                  <b>{proposal.title}</b>
                </div>
                <span className={'risk ' + proposal.projected_risk}>
                  {proposal.projected_risk.toUpperCase()}
                </span>
              </div>

              <div className="recovery-metrics">
                <div><span>DELAY</span><b>{proposal.projected_total_delay_minutes}m</b></div>
                <div><span>MODELED COST</span><b>{usd(proposal.projected_modeled_cost_usd)}</b></div>
                <div><span>CONFLICTS</span><b>{proposal.projected_berth_conflicts}</b></div>
                <div><span>BLOCKED</span><b>{proposal.projected_blocked_services}</b></div>
                <div><span>DISRUPTION</span><b>{proposal.disruption_score.toFixed(0)}</b></div>
              </div>

              <div className="recovery-rationale">
                {proposal.rationale.slice(0, 3).map(line => <p key={line}>{line}</p>)}
              </div>

              <div className="recovery-actions">
                <div>
                  {proposal.actions.map((action, actionIndex) => (
                    <span key={proposal.id + '-' + actionIndex}>
                      {action.action_type.replaceAll('_', ' ')}
                    </span>
                  ))}
                </div>
                <button disabled={busy} onClick={() => onApply(proposal.id)}>
                  Approve & apply
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
