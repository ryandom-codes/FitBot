"""Deterministic observations from explicitly logged records, not forecasts."""

from dataclasses import asdict, dataclass
import math


def _convert(value, unit, factors):
    if not isinstance(unit, str) or unit.lower() not in factors:
        raise ValueError('unsupported unit')
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('measurement must be finite and nonnegative')
    return value * factors[unit.lower()]


def weight_to_kg(value, unit='kg'):
    return _convert(value, unit, {'kg': 1.0, 'lb': 0.45359237, 'lbs': 0.45359237})


def height_to_cm(value, unit='cm'):
    return _convert(value, unit, {'cm': 1.0, 'in': 2.54, 'inches': 2.54})


@dataclass(frozen=True)
class ProgressSummary:
    checkin_days: int
    cardio_observed_days: int
    total_logged_cardio_minutes: float | None
    weight_measurements: int
    weight_change_kg: float | None
    weight_start_date: str | None
    weight_end_date: str | None
    lifts_by_exercise: dict
    limitations: str = ('Only explicitly logged observations are included; missing days are not zero. '
                        'Load × sets × reps is logged external-load volume, not evidence of physiological improvement. '
                        'Exercise variants are kept separate; no diagnosis or causal inference is made.')


def summarize_history(history):
    """Summarize a validated canonical-kg history, comparing like lift names."""
    checkins = sorted(history.get('checkins', []), key=lambda row: row['date'])
    cardio = [row['cardio_minutes'] for row in checkins if row.get('cardio_minutes') is not None]
    weights = [row for row in checkins if row.get('weight_kg') is not None]
    exercises = {}
    for row in history.get('lifts', []):
        key = ' '.join(row['exercise'].split()).casefold()
        group = exercises.setdefault(key, {'entry_count': 0, 'logged_volume_kg_reps': 0.0, 'dates': set()})
        group['entry_count'] += 1
        group['logged_volume_kg_reps'] += row['sets'] * row['reps'] * row['load_kg']
        group['dates'].add(row['date'])
    for group in exercises.values():
        group['observed_days'] = len(group.pop('dates'))
    return asdict(ProgressSummary(
        checkin_days=len({row['date'] for row in checkins}),
        cardio_observed_days=len(cardio),
        total_logged_cardio_minutes=sum(cardio) if cardio else None,
        weight_measurements=len(weights),
        weight_change_kg=weights[-1]['weight_kg'] - weights[0]['weight_kg'] if len(weights) >= 2 else None,
        weight_start_date=weights[0]['date'] if weights else None,
        weight_end_date=weights[-1]['date'] if weights else None,
        lifts_by_exercise=dict(sorted(exercises.items())),
    ))
