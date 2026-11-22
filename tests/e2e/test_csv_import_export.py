"""Round-trip tests for user/unit CSV import & export (utils/csv_handler.py)."""
import csv
import io

import pytest

from extensions import db
from models import User, Unit, UnitType
from utils.csv_handler import CSVHandler


def _rows(csv_text):
    return list(csv.DictReader(io.StringIO(csv_text)))


def test_users_roundtrip(app):
    with app.app_context():
        csv_text = CSVHandler.export_users()
        assert 'username' in _rows(csv_text)[0] or csv_text.startswith('username')
        result = CSVHandler.import_users(io.StringIO(csv_text))
        assert 'error' not in result
        assert result['errors'] == []
        # every exported row should upsert (update), none added
        assert result['added'] == 0
        assert result['updated'] == len(_rows(csv_text))


def test_user_import_password_and_default(app):
    with app.app_context():
        before = set(u.username for u in User.query.all())
        data = (
            'username,email,first_name,last_name,role,active,password\n'
            'csvtest1,csv1@example.com,Csv,One,administrator,true,secretpw\n'
            'csvtest2,csv2@example.com,Csv,Two,,true,\n'
        )
        result = CSVHandler.import_users(io.StringIO(data))
        assert 'error' not in result
        assert result['added'] == 2, result
        u1 = User.query.filter_by(username='csvtest1').first()
        assert u1.check_password('secretpw')
        u2 = User.query.filter_by(username='csvtest2').first()
        assert u2.check_password('cadsystem')  # default password


def test_user_import_email_conflict(app):
    with app.app_context():
        existing = User.query.filter_by(username='admin').first()
        data = (
            'username,email\n'
            f'differentuser,{existing.email}\n'
        )
        result = CSVHandler.import_users(io.StringIO(data))
        assert result['added'] == 0
        assert any('Email' in e for e in result['errors'])


def test_units_roundtrip(app):
    with app.app_context():
        data = (
            'name,type,location,status,active\n'
            'CSV-AMB-1,Paramedic,Central Station,available,true\n'
        )
        result = CSVHandler.import_units(io.StringIO(data))
        assert 'error' not in result
        assert result['added'] == 1, result
        unit = Unit.query.filter_by(name='CSV-AMB-1').first()
        assert unit is not None
        assert unit.type.name == 'Paramedic'

        csv_text = CSVHandler.export_units()
        rows = _rows(csv_text)
        assert {'name', 'type', 'location', 'status', 'active'} <= set(rows[0].keys())
        assert any(r['name'] == 'CSV-AMB-1' for r in rows)

        result2 = CSVHandler.import_units(io.StringIO(csv_text))
        assert result2['errors'] == []
        assert result2['added'] == 0
        assert result2['updated'] == len(rows)


def test_unit_import_creates_type_and_updates(app):
    with app.app_context():
        data = (
            'name,type,location,status,active\n'
            'CSV-UNIT-X,Brand New Type,Station Z,available,true\n'
        )
        result = CSVHandler.import_units(io.StringIO(data))
        assert result['added'] == 1
        assert UnitType.query.filter_by(name='Brand New Type').first() is not None

        # re-import with changed location → update, not add
        data2 = (
            'name,type,location,status,active\n'
            'CSV-UNIT-X,Brand New Type,Station Y,available,true\n'
        )
        result2 = CSVHandler.import_units(io.StringIO(data2))
        assert result2['added'] == 0 and result2['updated'] == 1
        assert Unit.query.filter_by(name='CSV-UNIT-X').first().location == 'Station Y'
