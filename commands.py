from flask.cli import with_appcontext
import click
from extensions import db
from models import Role, User, Permission

@click.command('init-db')
@with_appcontext
def init_db_command():
    """Initialize the database."""
    db.create_all()
    from core.reference_data import insert_defaults as insert_core_reference_data
    insert_core_reference_data()
    click.echo('Initialized the database.')
