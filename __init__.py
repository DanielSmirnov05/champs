from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_babel import Babel, _

import os

app = Flask(__name__)
app.secret_key = 'super-secret-key-123'

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, '..', 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Language settings
app.config['BABEL_DEFAULT_LOCALE'] = 'ru'
app.config['BABEL_SUPPORTED_LOCALES'] = ['ru', 'en', 'lv']

# Initialize Babel
babel = Babel(app)

@babel.localeselector
def get_locale():
    return session.get('lang') or request.accept_languages.best_match(app.config['BABEL_SUPPORTED_LOCALES'])

@app.context_processor
def inject_translations():
    return dict(_=_)

# Initialize database
db = SQLAlchemy(app)

from app import routes, models  # after creating app and db

# Login manager setup
from flask_login import LoginManager
from app.models import User

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Flask-Migrate initialization
from flask_migrate import Migrate
migrate = Migrate(app, db)

from flask_babel import get_locale

# Register get_locale function for Jinja templates
app.jinja_env.globals['get_locale'] = get_locale