"""Descriptive operational measurements; never counterfactual savings."""
from datetime import datetime
import json
from sqlalchemy import select
from .product_decisions import packets


def summarize_outcomes(connection, records, read_at):
    approved_rows = connection.execute(
        select(packets.c.id, packets.c.payload, packets.c.receipt)
        .where(packets.c.receipt.is_not(None)).order_by(packets.c.id)).mappings()
    observed = {r['payload']['decision_id']: r for r in records if r['kind']=='outcome'}
    approved = []
    measurements = []
    for row in approved_rows:
        packet=json.loads(row['payload'])
        receipt=json.loads(row['receipt'])
        option=next((o for o in packet['options'] if o['id']==receipt['option_id']),None)
        if option is None:  # Evidence corruption is never silently interpreted.
            raise ValueError('Approved decision is missing its selected option')
        approved.append(row['id'])
        record=observed.get(row['id'])
        if record is None:
            continue
        planned=option['call_payload']
        actual=record['payload']
        minutes=lambda end,start:round((datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()/60,2)
        arrival=minutes(actual['actual_arrival'], planned['eta'])
        departure=minutes(actual['actual_departure'], planned['etd'])
        occupancy=round(minutes(actual['actual_departure'],actual['actual_arrival'])
                        -minutes(planned['etd'],planned['eta']),2)
        measurements.append({
            'decision_id':row['id'],'call_id':packet['call_id'],
            'approved_at':receipt['approved_at'],
            'planned_arrival':planned['eta'],'planned_departure':planned['etd'],
            'actual_arrival':actual['actual_arrival'],'actual_departure':actual['actual_departure'],
            'arrival_deviation_minutes':arrival,
            'departure_deviation_minutes':departure,
            'occupancy_deviation_minutes':occupancy,
            'source':record['source'],'known_at':record['known_at'],
            'outcome_record_id':record['record_id'],'outcome_revision':record['revision'],
        })
    count=len(measurements)
    summary={
        'approved_decisions':len(approved),
        'outcomes_recorded':count,
        'outcomes_missing':len(approved)-count,
        'observation_coverage_pct':round(100*count/len(approved),2) if approved else None,
        'mean_absolute_arrival_deviation_minutes':round(sum(abs(m['arrival_deviation_minutes']) for m in measurements)/count,2) if count else None,
        'mean_absolute_departure_deviation_minutes':round(sum(abs(m['departure_deviation_minutes']) for m in measurements)/count,2) if count else None,
    }
    return {
        'read_at':read_at,
        'summary':summary,
        'measurements':measurements,
        'limitations':[
            'Descriptive deviations from the approved recorded plan, not causal delay savings.',
            'Outcomes are only as reliable as their explicitly recorded observation sources.',
            'Missing outcomes are not zeros and do not establish on-time performance.',
            'No provider feed, forecast calibration, or external marine safety approval is implied.',
        ],
    }
