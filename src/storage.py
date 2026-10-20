"""Parameterized SQLite persistence. Callers choose a private database path.

Record saves replace all fields of that record; missing optional values remain
NULL. Profiles represent local folders of records, not authenticated accounts.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date
import json
import math
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class Profile:
    label: str = ''
    goals: str = ''
    experience: str = ''
    equipment: str = ''
    available_days: int = 0
    height_cm: float | None = None


@dataclass(frozen=True)
class CheckIn:
    date: str
    weight_kg: float | None = None
    cardio_minutes: float | None = None
    sleep_hours: float | None = None
    notes: str | None = None


@dataclass(frozen=True)
class LiftEntry:
    date: str
    exercise: str
    sets: int
    reps: int
    load_kg: float


@contextmanager
def _connect(path):
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db(path):
    """Create an idempotent store; no sample or personal values are inserted."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY, label TEXT NOT NULL, goals TEXT NOT NULL,
                experience TEXT NOT NULL, equipment TEXT NOT NULL,
                available_days INTEGER NOT NULL CHECK(available_days BETWEEN 0 AND 7),
                height_cm REAL CHECK(height_cm >= 0)
            );
            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                date TEXT NOT NULL, weight_kg REAL CHECK(weight_kg >= 0),
                cardio_minutes REAL CHECK(cardio_minutes >= 0),
                sleep_hours REAL CHECK(sleep_hours >= 0), notes TEXT,
                UNIQUE(profile_id, date)
            );
            CREATE TABLE IF NOT EXISTS lifts (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                date TEXT NOT NULL, exercise TEXT NOT NULL,
                sets INTEGER NOT NULL CHECK(sets >= 0),
                reps INTEGER NOT NULL CHECK(reps >= 0),
                load_kg REAL NOT NULL CHECK(load_kg >= 0)
            );
        ''')


def _number(value, field, nullable=False, integer=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{field} must be a nonnegative number')
    if not math.isfinite(value) or value < 0 or (integer and int(value) != value):
        raise ValueError(f'{field} must be a finite nonnegative {"integer" if integer else "number"}')
    return int(value) if integer else float(value)


def _text(value, field, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ValueError(f'{field} must be text')
    return value


def _date(value):
    if not isinstance(value, str):
        raise ValueError('date must be YYYY-MM-DD')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('date must be a real YYYY-MM-DD date') from exc
    if parsed.isoformat() != value or parsed > date.today():
        raise ValueError('date must be YYYY-MM-DD and not in the future')
    return value


def _profile_exists(db, profile_id):
    if db.execute('SELECT id FROM profiles WHERE id = ?', (profile_id,)).fetchone() is None:
        raise ValueError('profile does not exist')


def save_profile(path, profile):
    values = asdict(Profile(**{key: profile[key] for key in Profile.__dataclass_fields__ if key in profile}))
    for key in ('label', 'goals', 'experience', 'equipment'):
        values[key] = _text(values[key], key)
    values['height_cm'] = _number(values['height_cm'], 'height_cm', nullable=True)
    values['available_days'] = _number(values['available_days'], 'available_days', integer=True)
    if values['available_days'] > 7:
        raise ValueError('available_days must be between 0 and 7')
    with _connect(path) as db:
        if profile.get('id') is not None:
            _profile_exists(db, profile['id'])
            db.execute('UPDATE profiles SET label=?,goals=?,experience=?,equipment=?,available_days=?,height_cm=? WHERE id=?', (*values.values(), profile['id']))
            return profile['id']
        return db.execute('INSERT INTO profiles(label,goals,experience,equipment,available_days,height_cm) VALUES(?,?,?,?,?,?)', tuple(values.values())).lastrowid


def list_profiles(path):
    with _connect(path) as db:
        return [dict(row) for row in db.execute('SELECT * FROM profiles ORDER BY id')]


def save_checkin(path, profile_id, record):
    if 'date' not in record:
        raise ValueError('date is required')
    values = asdict(CheckIn(**{key: record[key] for key in CheckIn.__dataclass_fields__ if key in record}))
    values['date'] = _date(values['date'])
    for key in ('weight_kg', 'cardio_minutes', 'sleep_hours'):
        values[key] = _number(values[key], key, nullable=True)
    values['notes'] = _text(values['notes'], 'notes', nullable=True)
    with _connect(path) as db:
        _profile_exists(db, profile_id)
        db.execute('''INSERT INTO checkins(profile_id,date,weight_kg,cardio_minutes,sleep_hours,notes)
            VALUES(?,?,?,?,?,?) ON CONFLICT(profile_id,date) DO UPDATE SET
            weight_kg=excluded.weight_kg,cardio_minutes=excluded.cardio_minutes,
            sleep_hours=excluded.sleep_hours,notes=excluded.notes''', (profile_id, *values.values()))
        return db.execute('SELECT id FROM checkins WHERE profile_id=? AND date=?', (profile_id, values['date'])).fetchone()['id']


def save_lift(path, profile_id, record):
    missing = {'date', 'exercise', 'sets', 'reps', 'load_kg'} - record.keys()
    if missing:
        raise ValueError('required lift fields missing: ' + ', '.join(sorted(missing)))
    values = asdict(LiftEntry(**{key: record[key] for key in LiftEntry.__dataclass_fields__ if key in record}))
    values['date'] = _date(values['date'])
    values['exercise'] = ' '.join(_text(values['exercise'], 'exercise').split())
    if not values['exercise']:
        raise ValueError('exercise must not be blank')
    for key in ('sets', 'reps', 'load_kg'):
        values[key] = _number(values[key], key, integer=key != 'load_kg')
    with _connect(path) as db:
        _profile_exists(db, profile_id)
        if record.get('id') is not None:
            cursor = db.execute('UPDATE lifts SET date=?,exercise=?,sets=?,reps=?,load_kg=? WHERE id=? AND profile_id=?', (*values.values(), record['id'], profile_id))
            if cursor.rowcount != 1:
                raise ValueError('lift does not belong to this profile')
            return record['id']
        return db.execute('INSERT INTO lifts(profile_id,date,exercise,sets,reps,load_kg) VALUES(?,?,?,?,?,?)', (profile_id, *values.values())).lastrowid


def get_history(path, profile_id):
    with _connect(path) as db:
        _profile_exists(db, profile_id)
        return {
            'profile': dict(db.execute('SELECT * FROM profiles WHERE id=?', (profile_id,)).fetchone()),
            'checkins': [dict(row) for row in db.execute('SELECT * FROM checkins WHERE profile_id=? ORDER BY date,id', (profile_id,))],
            'lifts': [dict(row) for row in db.execute('SELECT * FROM lifts WHERE profile_id=? ORDER BY date,id', (profile_id,))],
        }


def delete_profile(path, profile_id):
    with _connect(path) as db:
        _profile_exists(db, profile_id)
        db.execute('DELETE FROM profiles WHERE id=?', (profile_id,))


def delete_lift(path, profile_id, lift_id):
    with _connect(path) as db:
        if db.execute('DELETE FROM lifts WHERE id=? AND profile_id=?', (lift_id, profile_id)).rowcount != 1:
            raise ValueError('lift does not belong to this profile')


def export_history(path, profile_id):
    """Return JSON for the selected profile only; no implicit file write."""
    return json.dumps(get_history(path, profile_id), ensure_ascii=False, indent=2, allow_nan=False)
