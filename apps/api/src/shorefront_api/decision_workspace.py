"""Read-only projections. No store, credentials or external adapters are attached."""
from .models import HarborOverview, IncidentType, OperatorRole
from .simulator import HarborSimulator


def recovery_comparison(snapshot: HarborOverview) -> dict:
    working = HarborSimulator(initial=snapshot)
    options = []
    for proposal in working.generate_recovery_proposals()[:3]:
        projected = HarborSimulator(initial=snapshot)
        projected._apply_recovery_actions(proposal.actions)
        options.append({'proposal': proposal, 'harbor': projected.overview()})
    return {
        'read_only': True,
        'current': snapshot,
        'options': options,
        'model_notice': (
            'Synthetic delay exposure uses USD 720 per delay minute. '
            'Projections are not observed outcomes, verified savings or cash.'
        ),
    }


def guided_story() -> dict:
    working = HarborSimulator()
    baseline = working.overview()
    working.inject_incident(IncidentType.TUG_UNAVAILABLE, 'pc-aurora', 40)
    disrupted = working.overview()
    graph = working.dependency_graph('pc-aurora')
    comparison = recovery_comparison(disrupted)
    proposal = working.generate_recovery_proposals()[0]
    receipt = working.apply_recovery_proposal(
        proposal.id,
        approved_by='guided-demo-simulation',
        approved_role=OperatorRole.OPERATOR,
        approved_display_name='Simulated operator (not an authenticated session)',
    )
    return {
        'synthetic': True,
        'writes_operational_state': False,
        'receipt_is_simulated': True,
        'baseline': baseline,
        'disrupted': disrupted,
        'comparison': comparison,
        'dependency_graph': graph,
        'receipt': receipt,
        'recovered': working.overview(),
    }
