import json
from datetime import date, timedelta
from pathlib import Path
import subprocess
import sys

import pytest

from src import storage


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'private' / 'history.sqlite3'
    storage.init_db(path)
    return path


def profile(db, **kwargs):
    return storage.save_profile(db, {'goals': 'General activity', **kwargs})


def test_profile_persists_and_updates(db):
    pid = profile(db, height_cm=170, available_days=3)
    storage.init_db(db)
    assert storage.list_profiles(db)[0]['height_cm'] == 170
    assert storage.save_profile(db, {'id': pid, 'goals': 'Walking'}) == pid
    assert storage.get_history(db, pid)['profile']['goals'] == 'Walking'


def test_checkin_upsert_preserves_missing_and_zero(db):
    pid = profile(db)
    first = storage.save_checkin(db, pid, {'date': '2026-01-01', 'cardio_minutes': 0})
    record = storage.get_history(db, pid)['checkins'][0]
    assert record['cardio_minutes'] == 0
    assert record['weight_kg'] is None
    assert storage.save_checkin(db, pid, {'date': '2026-01-01', 'weight_kg': 80}) == first
    records = storage.get_history(db, pid)['checkins']
    assert len(records) == 1
    assert records[0]['cardio_minutes'] is None


def test_profiles_and_lift_updates_are_isolated(db):
    one, two = profile(db), profile(db)
    rid = storage.save_lift(db, one, {'date': '2026-01-01', 'exercise': 'Squat', 'sets': 2, 'reps': 5, 'load_kg': 20})
    storage.save_lift(db, one, {'date': '2026-01-01', 'exercise': 'Squat', 'sets': 1, 'reps': 5, 'load_kg': 25})
    assert storage.get_history(db, two)['lifts'] == []
    with pytest.raises(ValueError):
        storage.save_lift(db, two, {'id': rid, 'date': '2026-01-01', 'exercise': 'Squat', 'sets': 1, 'reps': 5, 'load_kg': 0})
    storage.save_lift(db, one, {'id': rid, 'date': '2026-01-01', 'exercise': 'Squat', 'sets': 3, 'reps': 5, 'load_kg': 20})
    assert len(storage.get_history(db, one)['lifts']) == 2
    assert storage.get_history(db, one)['lifts'][0]['sets'] == 3
    with pytest.raises(ValueError):
        storage.delete_lift(db, two, rid)
    storage.delete_lift(db, one, rid)
    assert len(storage.get_history(db, one)['lifts']) == 1


def test_text_is_parameterized_and_export_is_readable(db):
    text = "x'); DROP TABLE profiles; --"
    pid = profile(db, goals=text)
    storage.save_checkin(db, pid, {'date': '2026-01-01', 'notes': text})
    exported = json.loads(storage.export_history(db, pid))
    assert exported['profile']['goals'] == text
    assert exported['checkins'][0]['notes'] == text
    assert len(storage.list_profiles(db)) == 1


def test_profile_delete_cascades_without_affecting_other(db):
    one, two = profile(db), profile(db)
    storage.save_checkin(db, one, {'date': '2026-01-01'})
    storage.save_lift(db, one, {'date': '2026-01-01', 'exercise': 'Row', 'sets': 1, 'reps': 1, 'load_kg': 0})
    storage.delete_profile(db, one)
    assert [p['id'] for p in storage.list_profiles(db)] == [two]
    with pytest.raises(ValueError):
        storage.get_history(db, one)


@pytest.mark.parametrize('record', [
    {'date': 'bad'}, {'date': '2026-02-30'},
    {'date': (date.today() + timedelta(days=1)).isoformat()},
    {'date': '2026-01-01', 'weight_kg': -1},
    {'date': '2026-01-01', 'cardio_minutes': float('nan')},
    {'date': '2026-01-01', 'sleep_hours': float('inf')},
    {'date': '2026-01-01', 'cardio_minutes': True},
])
def test_invalid_checkins_rejected(db, record):
    with pytest.raises(ValueError):
        storage.save_checkin(db, profile(db), record)


@pytest.mark.parametrize('change', [{'sets': -1}, {'reps': 1.5}, {'load_kg': -1}, {'exercise': '  '}, {'date': '2099-01-01'}])
def test_invalid_lifts_rejected(db, change):
    with pytest.raises(ValueError):
        storage.save_lift(db, profile(db), {'date': '2026-01-01', 'exercise': 'Row', 'sets': 1, 'reps': 1, 'load_kg': 0, **change})


def test_missing_profile_rejected(db):
    with pytest.raises(ValueError):
        storage.save_checkin(db, 999, {'date': '2026-01-01'})


@pytest.mark.parametrize('change', [{'height_cm': -1}, {'available_days': 8}, {'available_days': 1.5}])
def test_invalid_profile_rejected(db, change):
    with pytest.raises(ValueError):
        profile(db, **change)


def test_demo_seed_is_explicitly_synthetic_and_refuses_overwrite(tmp_path):
    project = Path(__file__).resolve().parents[1]
    target = tmp_path / 'demo.sqlite3'
    result = subprocess.run([sys.executable, str(project / 'scripts' / 'seed_demo.py'), '--db', str(target)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    pid = storage.list_profiles(target)[0]['id']
    history = storage.get_history(target, pid)
    assert history['profile']['label'] == 'Synthetic demo'
    assert len(history['checkins']) == 4
    assert len(history['lifts']) == 4
    again = subprocess.run([sys.executable, str(project / 'scripts' / 'seed_demo.py'), '--db', str(target)], capture_output=True, text=True)
    assert again.returncode != 0
    assert len(storage.list_profiles(target)) == 1


def test_demo_seed_refuses_public_database_location():
    project = Path(__file__).resolve().parents[1]
    target = project / 'data' / 'forbidden-demo.sqlite3'
    result = subprocess.run([sys.executable, str(project / 'scripts' / 'seed_demo.py'), '--db', str(target)], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'outside' in result.stderr
    assert not target.exists()


@pytest.mark.parametrize('kind,record', [('checkin', {}), ('lift', {'date': '2026-01-01'})])
def test_missing_required_fields_raise_validation_error(db, kind, record):
    saver = storage.save_checkin if kind == 'checkin' else storage.save_lift
    with pytest.raises(ValueError, match='required'):
        saver(db, profile(db), record)


def test_checkin_profile_isolation_and_delete_cascade(db):
    import sqlite3
    one, two = profile(db), profile(db)
    storage.save_checkin(db, one, {'date': '2026-01-01', 'weight_kg': 70})
    storage.save_checkin(db, two, {'date': '2026-01-01', 'weight_kg': 90})
    assert storage.get_history(db, one)['checkins'][0]['weight_kg'] == 70
    storage.delete_profile(db, one)
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT COUNT(*) FROM checkins WHERE profile_id=?', (one,)).fetchone()[0] == 0
    assert storage.get_history(db, two)['checkins'][0]['weight_kg'] == 90
