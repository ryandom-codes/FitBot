import pytest

from src import progress


def test_canonical_unit_conversions():
    assert progress.weight_to_kg(100, 'lb') == pytest.approx(45.359237)
    assert progress.weight_to_kg(50, 'kg') == 50
    assert progress.height_to_cm(70, 'in') == pytest.approx(177.8)
    assert progress.height_to_cm(170, 'cm') == 170
    assert progress.weight_to_kg(None, 'kg') is None


@pytest.mark.parametrize('value,unit', [(-1, 'kg'), (float('inf'), 'kg'), (True, 'kg'), (10, 'stone')])
def test_invalid_weight_units(value, unit):
    with pytest.raises(ValueError):
        progress.weight_to_kg(value, unit)


def test_missing_observations_do_not_become_zero():
    summary = progress.summarize_history({'checkins': [{'date': '2026-01-01', 'weight_kg': 80, 'cardio_minutes': None}], 'lifts': []})
    assert summary['checkin_days'] == 1
    assert summary['cardio_observed_days'] == 0
    assert summary['total_logged_cardio_minutes'] is None
    assert summary['weight_change_kg'] is None
    assert summary['weight_measurements'] == 1


def test_totals_use_observed_days_and_sorted_weight_measurements():
    summary = progress.summarize_history({'checkins': [
        {'date': '2026-01-03', 'weight_kg': 81, 'cardio_minutes': 20},
        {'date': '2026-01-01', 'weight_kg': 80, 'cardio_minutes': 0},
        {'date': '2026-01-02', 'weight_kg': None, 'cardio_minutes': None},
    ], 'lifts': []})
    assert summary['cardio_observed_days'] == 2
    assert summary['total_logged_cardio_minutes'] == 20
    assert summary['weight_change_kg'] == 1
    assert summary['weight_start_date'] == '2026-01-01'
    assert summary['weight_end_date'] == '2026-01-03'


def test_lifting_volume_compares_only_same_exercise():
    summary = progress.summarize_history({'checkins': [], 'lifts': [
        {'date': '2026-01-01', 'exercise': ' Squat ', 'sets': 2, 'reps': 5, 'load_kg': 20},
        {'date': '2026-01-02', 'exercise': 'squat', 'sets': 1, 'reps': 5, 'load_kg': 30},
        {'date': '2026-01-01', 'exercise': 'Goblet squat', 'sets': 1, 'reps': 5, 'load_kg': 10},
    ]})
    assert summary['lifts_by_exercise']['squat']['logged_volume_kg_reps'] == 350
    assert summary['lifts_by_exercise']['goblet squat']['logged_volume_kg_reps'] == 50
    assert summary['lifts_by_exercise']['squat']['observed_days'] == 2
    assert 'not evidence of physiological improvement' in summary['limitations']


def test_recorded_zero_remains_observed_zero():
    summary = progress.summarize_history({'checkins': [{'date': '2026-01-01', 'cardio_minutes': 0}], 'lifts': []})
    assert summary['cardio_observed_days'] == 1
    assert summary['total_logged_cardio_minutes'] == 0


@pytest.mark.parametrize('value,unit', [(-1, 'cm'), (float('nan'), 'in'), (True, 'cm'), (2, 'm')])
def test_invalid_height_units(value, unit):
    with pytest.raises(ValueError):
        progress.height_to_cm(value, unit)
