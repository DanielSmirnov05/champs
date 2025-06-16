from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='viewer')
    avatar_url = db.Column(db.String)
    first_name = db.Column(db.String)
    last_name = db.Column(db.String)
    phone = db.Column(db.String)
    bio = db.Column(db.Text)

    tournaments_created = db.relationship(
        'Tournament',
        backref=db.backref('creator', lazy=True),
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    discussions = db.relationship(
        'Discussion',
        backref=db.backref('author', lazy=True),
        lazy='dynamic', 
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    messages = db.relationship(
        'DiscussionMessage',
        backref=db.backref('author', lazy=True),
        lazy='dynamic', 
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"

    @property
    def tournaments_count(self):
        return self.tournaments_created.count()

    @property
    def discussions_count(self):
        return self.discussions.count()

    @property
    def messages_count(self):
        return self.messages.count()



class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(100), nullable=True)
    format = db.Column(db.String(50), nullable=True)
    max_teams = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    creator_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE', name='fk_tournament_creator'),
        nullable=True
    )

    teams = db.relationship('Team', backref='tournament', lazy=True, cascade='all, delete-orphan', passive_deletes=True)
    matches = db.relationship('Match', backref='tournament', lazy=True, cascade='all, delete-orphan', passive_deletes=True)

    def __repr__(self):
        return f'<Tournament {self.name}>'


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id', ondelete='CASCADE', name='fk_team_tournament'), nullable=False)

    players = db.relationship('Player', backref='team', cascade='all, delete-orphan', passive_deletes=True)
    home_matches = db.relationship('Match', foreign_keys='Match.team1_id', backref='team1_alias', cascade='all, delete-orphan', passive_deletes=True)
    away_matches = db.relationship('Match', foreign_keys='Match.team2_id', backref='team2_alias', cascade='all, delete-orphan', passive_deletes=True)

    def __repr__(self):
        return f'<Team {self.name}>'


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id', ondelete='CASCADE'), nullable=False)
    team1_id = db.Column(db.Integer, db.ForeignKey('team.id', ondelete='CASCADE'), nullable=False)
    team2_id = db.Column(db.Integer, db.ForeignKey('team.id', ondelete='CASCADE'), nullable=False)

    date = db.Column(db.Date, nullable=True)
    time = db.Column(db.Time, nullable=True)
    location = db.Column(db.String(100), nullable=True)
    score1 = db.Column(db.Integer)
    score2 = db.Column(db.Integer)
    status = db.Column(db.String(20), default='scheduled')

    goals = db.relationship('Goal', backref='match', cascade='all, delete-orphan')
    lineup = db.relationship('Lineup', backref='match', cascade='all, delete-orphan')
    team1 = db.relationship('Team', foreign_keys=[team1_id])
    team2 = db.relationship('Team', foreign_keys=[team2_id])

    def __repr__(self):
        return f"<Match {self.team1_id} vs {self.team2_id} ({self.date})>"



class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    number = db.Column(db.Integer)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id', ondelete='CASCADE', name='fk_player_team'), nullable=False)

    def __repr__(self):
        return f'<Player {self.name} #{self.number}>'


class Lineup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id', ondelete='CASCADE', name='fk_lineup_match'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE', name='fk_lineup_player'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id', ondelete='CASCADE', name='fk_lineup_team'), nullable=False)

    player = db.relationship('Player')
    team = db.relationship('Team')


class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id', ondelete='CASCADE', name='fk_goal_match'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id', ondelete='CASCADE', name='fk_goal_team'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='SET NULL', name='fk_goal_player'))
    scorer = db.Column(db.String(100), nullable=False)
    minute = db.Column(db.Integer, nullable=False)

    player = db.relationship('Player')
    team = db.relationship('Team')


class Discussion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE', name='fk_discussion_author'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    messages = db.relationship('DiscussionMessage', backref='discussion', cascade='all, delete-orphan', passive_deletes=True)


class DiscussionMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discussion_id = db.Column(db.Integer, db.ForeignKey('discussion.id', ondelete='CASCADE', name='fk_msg_discussion'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE', name='fk_msg_author'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    short_description = db.Column(db.String(300), nullable=False)
    content = db.Column(db.Text, nullable=False)
    news_type = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



