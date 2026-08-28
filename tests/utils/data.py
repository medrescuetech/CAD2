from typing import Iterable
from app import db
from models import Role, User, Permission, UnitType, Unit


def ensure_admin_role_and_user() -> User:
    admin_role = Role.query.filter_by(name='administrator').first()
    if not admin_role:
        admin_role = Role(name='administrator', permissions=0)
        db.session.add(admin_role)
        db.session.commit()
    # Aggregate all permission bits
    full_perms = 0
    for attr in dir(Permission):
        if attr.isupper():
            val = getattr(Permission, attr)
            if isinstance(val, int):
                full_perms |= val
    admin_role.permissions = full_perms
    db.session.commit()

    user = User.query.filter_by(username='admin').first()
    if not user:
        user = User(username='admin', email='admin@example.com', role=admin_role, first_name='Admin', last_name='User')
        user.set_password('admin')
        db.session.add(user)
        db.session.commit()
    else:
        user.role = admin_role
        db.session.commit()
    return user


def ensure_unit_types(names: Iterable[str] = ("Paramedic", "Critical Care")) -> None:
    for name in names:
        ut = UnitType.query.filter_by(name=name).first()
        if not ut:
            ut = UnitType(name=name, description=f"{name} unit")
            db.session.add(ut)
    db.session.commit()


def ensure_units(units: Iterable[tuple[str, str]] = (("Alpha 1", "Paramedic"), ("Bravo 2", "Critical Care"))):
    for name, type_name in units:
        ut = UnitType.query.filter_by(name=type_name).first()
        if not ut:
            ut = UnitType(name=type_name, description=f"{type_name} unit")
            db.session.add(ut)
            db.session.commit()
        u = Unit.query.filter_by(name=name).first()
        if not u:
            u = Unit(name=name, type=ut, active=True)
            db.session.add(u)
    db.session.commit()
