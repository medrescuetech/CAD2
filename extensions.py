from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.orm import scoped_session, sessionmaker
from threading import Lock
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_assets import Environment as FlaskAssets

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO(
    cors_allowed_origins="*", 
    async_mode='eventlet',
    logger=True,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    reconnection=True,
    reconnection_attempts=5,
    reconnection_delay=1000,
    reconnection_delay_max=5000
)
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()
mail = Mail()
assets = FlaskAssets()

# Create thread-safe session factory
session_factory = sessionmaker()
Session = scoped_session(session_factory)
db_lock = Lock()

@login_manager.user_loader
def load_user(user_id):
    from models import User
    with db_lock:
        return User.query.get(int(user_id))
