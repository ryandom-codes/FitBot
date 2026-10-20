"""Seed explicitly synthetic records into a new database outside the project."""

import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from src.storage import init_db, save_checkin, save_lift, save_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True, help='New demo database outside the public project')
    args = parser.parse_args()
    target = args.db.resolve()
    if target == PROJECT or PROJECT in target.parents:
        parser.error('Demo database must be outside the public project')
    if target.exists():
        parser.error('Refusing to overwrite an existing database; choose a new path')
    payload = json.loads((PROJECT / 'data' / 'demo_history.json').read_text(encoding='utf-8'))
    if payload.get('synthetic') is not True:
        parser.error('Demo input must be explicitly synthetic')
    init_db(target)
    profile_id = save_profile(target, payload['profile'])
    for record in payload['checkins']:
        save_checkin(target, profile_id, record)
    for record in payload['lifts']:
        save_lift(target, profile_id, record)
    print(f'Seeded synthetic demo profile {profile_id} into {target}')


if __name__ == '__main__':
    main()
