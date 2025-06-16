from sqlalchemy.orm import joinedload
from flask import render_template, request, redirect, url_for, Flask, flash
from app import app, db
from app.models import Tournament, Team, Match, Goal, Player, Lineup, User, News
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime

@app.route('/')
def index():
    tournaments = Tournament.query.all()
    news = News.query.order_by(News.created_at.desc()).limit(3).all()
    standings_by_tournament = {}
    top_scorers = get_top_scorers(tournaments[0]) if tournaments else []

    for tournament in tournaments:
        standings = calculate_standings(tournament)
        standings.sort(key=lambda t: (-t['points'], -(t['goals_for'] - t['goals_against'])))
        standings_by_tournament[tournament.id] = standings

    return render_template('index.html',
                           tournaments=tournaments,
                           standings_by_tournament=standings_by_tournament,
                           top_scorers=top_scorers,
                           news=news)

# @app.route('/add_tournament', methods=['POST'])
# @login_required
# def add_tournament():
#     if current_user.role not in ['admin', 'organizer']:
#         return "Access denied", 403
# 
#     name = request.form.get('name')
#     if name:
#         tournament = Tournament(name=name)
#         db.session.add(tournament)
#         db.session.commit()
#     return redirect(url_for('index'))

@app.route('/add_team', methods=['POST'])
def add_team():
    name = request.form.get('team_name')
    tournament_id = request.form.get('tournament_id')

    if name and tournament_id:
        existing = Team.query.filter_by(name=name, tournament_id=tournament_id).first()
        if existing:
            return redirect(url_for('index'))

        team = Team(name=name, tournament_id=int(tournament_id))
        db.session.add(team)
        db.session.commit()

    return redirect(url_for('index'))


@app.route('/add_player', methods=['POST'])
def add_player():
    name = request.form.get('player_name')
    number = request.form.get('player_number')
    team_id = request.form.get('team_id')

    if name and number.isdigit() and team_id:
        player = Player(name=name.strip(), number=int(number), team_id=int(team_id))
        db.session.add(player)
        db.session.commit()

    return redirect(url_for('index'))


@app.route('/match/<int:match_id>/lineup', methods=['GET', 'POST'])
def match_lineup(match_id):
    match = Match.query.get_or_404(match_id)
    players_team1 = Player.query.filter_by(team_id=match.team1_id).all()
    players_team2 = Player.query.filter_by(team_id=match.team2_id).all()

    if request.method == 'POST':
        # Clear previous lineup for this match
        Lineup.query.filter_by(match_id=match.id).delete()

        selected_players = request.form.getlist('players')
        for player_id in selected_players:
            player = Player.query.get(int(player_id))
            if player:
                lineup = Lineup(
                    match_id=match.id,
                    player_id=player.id,
                    team_id=player.team_id
                )
                db.session.add(lineup)

        db.session.commit()
        return redirect(url_for('match_protocol', match_id=match.id))

    # Split selected player IDs by team
    selected_lineups = Lineup.query.filter_by(match_id=match.id).all()
    selected_ids_team1 = {l.player_id for l in selected_lineups if l.team_id == match.team1_id}
    selected_ids_team2 = {l.player_id for l in selected_lineups if l.team_id == match.team2_id}

    return render_template('lineup.html',
                           match=match,
                           players_team1=players_team1,
                           players_team2=players_team2,
                           selected_ids_team1=selected_ids_team1,
                           selected_ids_team2=selected_ids_team2)


@app.route('/match/<int:match_id>', methods=['GET', 'POST'])
def match_protocol(match_id):
    match = Match.query.get_or_404(match_id)

    if request.method == 'POST':
        # ✅ Save match score
        if 'save_score' in request.form:
            score1 = request.form.get('score1')
            score2 = request.form.get('score2')
            if score1.isdigit() and score2.isdigit():
                match.score1 = int(score1)
                match.score2 = int(score2)
                db.session.commit()
            return redirect(url_for('match_protocol', match_id=match.id))

        # ✅ Add goal
        elif 'add_goal' in request.form:
            player_id = int(request.form.get('scorer'))
            minute = request.form.get('minute')

            player = Player.query.get(player_id)
            if player and minute.isdigit():
                goal = Goal(
                    match_id=match.id,
                    team_id=player.team_id,
                    player_id=player.id,
                    scorer=player.name,
                    minute=int(minute)
                )
                db.session.add(goal)
                db.session.commit()
                recalculate_score(match)
            return redirect(url_for('match_protocol', match_id=match.id))

        # ✅ Update match info: date, time, location, status
        elif 'save_match_info' in request.form:
            date = request.form.get('date')
            time = request.form.get('time')
            location = request.form.get('location')
            status = request.form.get('status')

            try:
                match.date = datetime.strptime(date, '%Y-%m-%d').date()
                match.time = datetime.strptime(time, '%H:%M').time()
            except ValueError:
                flash("Invalid date or time format.")
                return redirect(url_for('match_protocol', match_id=match.id))

            match.location = location
            match.status = status
            db.session.commit()
            flash("Match information updated.")
            return redirect(url_for('match_protocol', match_id=match.id))

    # 📥 Lineups for both teams
    lineup_team1 = Lineup.query.options(joinedload(Lineup.player)).filter_by(
        match_id=match.id, team_id=match.team1_id).all()
    lineup_team2 = Lineup.query.options(joinedload(Lineup.player)).filter_by(
        match_id=match.id, team_id=match.team2_id).all()

    return render_template('match.html',
                           match=match,
                           lineup_team1=lineup_team1,
                           lineup_team2=lineup_team2)



def recalculate_score(match):
    goals = match.goals
    score1 = sum(1 for goal in goals if goal.team_id == match.team1_id)
    score2 = sum(1 for goal in goals if goal.team_id == match.team2_id)
    match.score1 = score1
    match.score2 = score2
    db.session.commit()


@app.route('/delete_goal/<int:goal_id>', methods=['POST'])
def delete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    match = goal.match
    db.session.delete(goal)
    db.session.commit()
    recalculate_score(match)
    return redirect(url_for('match_protocol', match_id=match.id))


@app.route('/edit_goal/<int:goal_id>', methods=['GET', 'POST'])
def edit_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    match = goal.match

    if request.method == 'POST':
        goal.scorer = request.form.get('scorer').strip()
        goal.minute = int(request.form.get('minute'))
        goal.team_id = int(request.form.get('team_id'))
        db.session.commit()
        recalculate_score(match)
        return redirect(url_for('match_protocol', match_id=match.id))

    return render_template('edit_goal.html', goal=goal, match=match)


def calculate_standings(tournament):
    teams = tournament.teams
    matches = tournament.matches

    standings = {team.id: {
        'team': team,
        'played': 0,
        'wins': 0,
        'draws': 0,
        'losses': 0,
        'goals_for': 0,
        'goals_against': 0,
        'points': 0
    } for team in teams}

    for match in matches:
        if match.score1 is not None and match.score2 is not None:
            t1 = standings[match.team1_id]
            t2 = standings[match.team2_id]

            t1['played'] += 1
            t2['played'] += 1

            t1['goals_for'] += match.score1
            t1['goals_against'] += match.score2

            t2['goals_for'] += match.score2
            t2['goals_against'] += match.score1

            if match.score1 > match.score2:
                t1['wins'] += 1
                t2['losses'] += 1
                t1['points'] += 3
            elif match.score1 < match.score2:
                t2['wins'] += 1
                t1['losses'] += 1
                t2['points'] += 3
            else:
                t1['draws'] += 1
                t2['draws'] += 1
                t1['points'] += 1
                t2['points'] += 1

    return list(standings.values())


from collections import defaultdict

def get_top_scorers(tournament):
    from app.models import Goal
    from collections import defaultdict

    scorers = defaultdict(lambda: {"name": "", "team": "", "goals": 0})

    for match in tournament.matches:
        for goal in match.goals:
            if goal.player_id:
                key = goal.player_id
                player = goal.player
                team = goal.team

                scorers[key]["name"] = player.name if player else goal.scorer
                scorers[key]["team"] = team.name if team else "Without a team"
                scorers[key]["goals"] += 1
            else:
                key = (goal.team_id, goal.scorer)
                scorers[key]["name"] = goal.scorer
                scorers[key]["team"] = goal.team.name if goal.team else "Without a team"
                scorers[key]["goals"] += 1

    
    top_scorers = sorted(scorers.values(), key=lambda x: x["goals"], reverse=True)[:5]
    return top_scorers


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        role = request.form.get('role', 'viewer')

        if len(password) < 8:
            return "Password must be at least 8 characters long", 400

        if User.query.filter_by(email=email).first():
            return "A user with this email already exists.", 400

        if User.query.filter_by(name=name).first():
            return "A user with this nickname already exists", 400

        new_user = User(email=email, name=name, role=role)
        new_user.set_password(password)

        try:
            db.session.add(new_user)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return "Error during registration", 500

        login_user(new_user)
        return redirect(url_for('index'))

    return render_template('register.html')





@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash("Incorrect email or password.")
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout', methods=['POST'])
def logout():
    logout_user()
    flash('You have successfully logged out of your account.', 'success')
    return redirect(url_for('index'))







from sqlalchemy import func

@app.route('/tournaments')
def view_tournaments():
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'date_desc')

    query = Tournament.query

    if search:
        query = query.filter(Tournament.name.ilike(f'%{search}%'))

    if sort == 'date_desc':
        query = query.order_by(Tournament.date_created.desc())
    elif sort == 'date_asc':
        query = query.order_by(Tournament.date_created.asc())
    elif sort == 'name':
        query = query.order_by(Tournament.name.asc())
    elif sort == 'teams':
        query = query.outerjoin(Tournament.teams).group_by(Tournament.id).order_by(func.count().desc())

    tournaments = query.all()
    return render_template('tournaments.html', tournaments=tournaments)


@app.route('/tournament/<int:tournament_id>')
def tournament_page(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    teams = tournament.teams
    matches = tournament.matches
    standings = calculate_standings(tournament)
    standings.sort(key=lambda t: (-t['points'], -(t['goals_for'] - t['goals_against'])))
    top_scorers = get_top_scorers(tournament)

    return render_template('tournament.html',
                           tournament=tournament,
                           teams=teams,
                           matches=matches,
                           standings=standings,
                           top_scorers=top_scorers)


@app.route('/add_tournament', methods=['GET', 'POST'])
@login_required
def add_tournament():
    if current_user.role not in ['admin', 'organizer', 'king']:

        return "Доступ запрещён", 403

    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            tournament = Tournament(name=name, creator_id=current_user.id)
            db.session.add(tournament)
            db.session.commit()
            return redirect(url_for('my_tournaments'))
    return render_template('add_tournament.html')




@app.route('/tournament/<int:tournament_id>')
def view_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    return f"Tournament: {tournament.name}"


@app.route('/tournament/<int:tournament_id>/add_team', methods=['POST'])
@login_required
def add_team_to_tournament(tournament_id):
    if current_user.role not in ['admin', 'organizer', 'king']:

        return "Access denied", 403

    name = request.form.get('team_name').strip()
    if not name:
        return redirect(url_for('view_tournament', tournament_id=tournament_id))

    existing_team = Team.query.filter_by(name=name, tournament_id=tournament_id).first()
    if existing_team:
        flash('A team with this name already exists.')
        return redirect(url_for('view_tournament', tournament_id=tournament_id))

    team = Team(name=name, tournament_id=tournament_id)
    db.session.add(team)
    db.session.commit()
    return redirect(url_for('view_tournament', tournament_id=tournament_id))



@app.route('/tournament/<int:tournament_id>/add_match', methods=['POST'])
@login_required
def add_match(tournament_id):
    if current_user.role not in ['admin', 'organizer', 'king']:

        flash("Access denied")
        return redirect(url_for('tournament_page', tournament_id=tournament_id))

    team1_id = request.form['team1_id']
    team2_id = request.form['team2_id']
    date_str = request.form['date']
    time_str = request.form['time']
    status = request.form.get('status', 'scheduled')

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        time_obj = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        flash("Invalid date or time format.")
        return redirect(url_for('tournament_page', tournament_id=tournament_id))

    match = Match(
        tournament_id=tournament_id,
        team1_id=team1_id,
        team2_id=team2_id,
        date=date_obj,
        time=time_obj,
        score1=None,
        score2=None,
        status=status
    )
    db.session.add(match)
    db.session.commit()
    flash("Match added.")
    return redirect(url_for('tournament_page', tournament_id=tournament_id))


@app.route('/team/<int:team_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_team(team_id):
    team = Team.query.get_or_404(team_id)
    if current_user.role not in ['admin', 'organizer', 'king']:

        abort(403)

    if request.method == 'POST':
        new_name = request.form.get('team_name')
        if new_name:
            team.name = new_name.strip()
            db.session.commit()
            flash("Team name updated.")

        player_name = request.form.get('player_name')
        player_number = request.form.get('player_number')
        if player_name and player_number.isdigit():
            new_player = Player(name=player_name.strip(), number=int(player_number), team_id=team.id)
            db.session.add(new_player)
            db.session.commit()
            flash("Player added to the application.")

        return redirect(url_for('edit_team', team_id=team.id))

    players = Player.query.filter_by(team_id=team.id).all()
    return render_template('edit_team.html', team=team, players=players)

@app.route('/player/<int:player_id>/delete', methods=['POST'])
@login_required
def delete_player(player_id):
    player = Player.query.get_or_404(player_id)
    team = player.team

    if current_user.role not in ['admin', 'organizer', 'king']:

        flash("No access.")
        return redirect(url_for('index'))

    db.session.delete(player)
    db.session.commit()
    flash(f"Player {player.name} deleted.")
    return redirect(url_for('edit_team', team_id=team.id))    



@app.route('/tournament/<int:tournament_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)

    if current_user.role not in ['admin', 'organizer', 'king']:

        abort(403)

    if request.method == 'POST':
        tournament.name = request.form.get('name', tournament.name).strip()
        start_date_str = request.form.get('start_date')
        if start_date_str:
            try:
                tournament.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid date format.")
                return redirect(url_for('edit_tournament', tournament_id=tournament_id))

        tournament.location = request.form.get('location', tournament.location)
        tournament.format = request.form.get('format', tournament.format)
        tournament.max_teams = request.form.get('max_teams', tournament.max_teams)
        tournament.description = request.form.get('description', tournament.description)

        db.session.commit()
        flash("The tournament has been updated.")
        return redirect(url_for('tournament_page', tournament_id=tournament_id))

    return render_template('edit_tournament.html', tournament=tournament)



@app.route('/generate_matches/<int:tournament_id>', methods=['POST'])
@login_required
def generate_matches(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)

    if not (
        current_user.role in ['admin', 'king'] or
        (current_user.role == 'organizer' and tournament.creator_id == current_user.id)
    ):
        return "Access denied", 403

    teams = Team.query.filter_by(tournament_id=tournament_id).all()

    if len(teams) < 2:
        flash("Not enough commands to generate a calendar.")
        return redirect(url_for('tournament_page', tournament_id=tournament_id))

    existing = Match.query.filter_by(tournament_id=tournament_id).count()
    if existing > 0:
        flash("The matches already exist.")
        return redirect(url_for('tournament_page', tournament_id=tournament_id))

    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            match = Match(
                tournament_id=tournament_id,
                team1_id=teams[i].id,
                team2_id=teams[j].id,
                status='scheduled'
            )
            db.session.add(match)

    db.session.commit()
    flash("The match calendar has been successfully created.")
    return redirect(url_for('tournament_page', tournament_id=tournament_id))



@app.route('/match/<int:match_id>/delete', methods=['POST'])
@login_required
def delete_match(match_id):
    match = Match.query.get_or_404(match_id)
    tournament = match.tournament

    if current_user.role not in ['admin', 'organizer', 'king']:

        abort(403)
    if current_user.role == 'organizer' and tournament.creator_id != current_user.id:
        abort(403)

    Goal.query.filter_by(match_id=match.id).delete()
    Lineup.query.filter_by(match_id=match.id).delete()
    db.session.delete(match)
    db.session.commit()

    flash('The match has been successfully deleted.', 'success')
    return redirect(url_for('tournament_page', tournament_id=tournament.id))



@app.route('/my_tournaments')
@login_required
def my_tournaments():
    if current_user.role not in ['admin', 'organizer', 'king']:

        flash("You do not have access to this page.", "warning")
        return redirect(url_for('index'))

    tournaments = Tournament.query.filter_by(creator_id=current_user.id).all()
    return render_template('my_tournaments.html', tournaments=tournaments)



from flask import render_template, request, redirect, url_for
from flask_login import login_required, current_user
from app import app, db
from app.models import News


@app.route('/news')
def news_list():
    news_list = News.query.order_by(News.created_at.desc()).all()
    return render_template('news_list.html', news_list=news_list)


@app.route('/news/<int:news_id>')
def view_single_news(news_id):
    news = News.query.get_or_404(news_id)
    return render_template('view_news.html', news=news)


@app.route('/news/add', methods=['GET', 'POST'])
@login_required
def add_news():
    if current_user.role not in ['admin', 'king']:
        return "Access denied", 403

    if request.method == 'POST':
        title = request.form['title']
        short_description = request.form['short_description']
        content = request.form['content']
        news_type = request.form['news_type']

        new_news = News(
            title=title,
            short_description=short_description,
            content=content,
            news_type=news_type
        )
        db.session.add(new_news)
        db.session.commit()
        return redirect(url_for('news_list'))

    return render_template('add_news.html')

@app.route('/news/<int:news_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_news(news_id):
    if current_user.role not in ['admin', 'king']:

        return "Access denied", 403

    news = News.query.get_or_404(news_id)

    if request.method == 'POST':
        news.title = request.form.get('title')
        news.short_description = request.form.get('short_description')
        news.content = request.form.get('content')
        news.news_type = request.form.get('news_type')
        db.session.commit()
        return redirect(url_for('view_single_news', news_id=news.id))

    return render_template('edit_news.html', news=news)


@app.route('/news/<int:news_id>/delete', methods=['POST'])
@login_required
def delete_news(news_id):
    if current_user.role not in ['admin', 'king']:

        return "Access denied", 403

    news = News.query.get_or_404(news_id)
    db.session.delete(news)
    db.session.commit()
    return redirect(url_for('news_list'))



from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import db, Discussion, DiscussionMessage, User
from datetime import datetime
from sqlalchemy import func

@app.route('/discussions')
def discussions_list():
    sort = request.args.get('sort', 'newest')

    base_query = db.session.query(
        Discussion,
        User,
        func.count(DiscussionMessage.id).label('msg_count'),
        func.max(DiscussionMessage.created_at).label('last_msg_time')
    )\
    .join(User, Discussion.author_id == User.id)\
    .outerjoin(DiscussionMessage, Discussion.id == DiscussionMessage.discussion_id)\
    .group_by(Discussion.id, User.id)

    if sort == 'alphabet':
        discussions = base_query.order_by(Discussion.title.asc()).all()
    elif sort == 'activity':
        discussions = base_query.order_by(func.count(DiscussionMessage.id).desc()).all()
    else:
        discussions = base_query.order_by(Discussion.created_at.desc()).all()

    return render_template('discussions_list.html', discussions=discussions, sort=sort, now=datetime.utcnow())




@app.route('/discussions/new', methods=['GET', 'POST'])
@login_required
def create_discussion():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description')

        if not title:
            flash('Discussion title is required.', 'danger')
            return redirect(url_for('create_discussion'))

        discussion = Discussion(
            title=title,
            description=description,
            author_id=current_user.id
        )
        db.session.add(discussion)
        db.session.commit()
        return redirect(url_for('discussion_chat', discussion_id=discussion.id))

    return render_template('discussions_create.html')


@app.route('/discussions/<int:discussion_id>', methods=['GET', 'POST'])
def discussion_chat(discussion_id):
    discussion = Discussion.query.get_or_404(discussion_id)

    messages = db.session.query(DiscussionMessage, User)\
        .join(User, DiscussionMessage.author_id == User.id)\
        .filter(DiscussionMessage.discussion_id == discussion.id)\
        .order_by(DiscussionMessage.created_at.asc())\
        .all()

    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Only authorized users can write messages.', 'warning')
            return redirect(url_for('login'))

        content = request.form['content']
        if content:
            message = DiscussionMessage(
                discussion_id=discussion.id,
                author_id=current_user.id,
                content=content
            )
            db.session.add(message)
            db.session.commit()
            return redirect(url_for('discussion_chat', discussion_id=discussion.id))

    return render_template('discussions_chat.html', discussion=discussion, messages=messages)



from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os

import os
from werkzeug.utils import secure_filename

import os
from werkzeug.utils import secure_filename
from flask import current_app, request, redirect, url_for, render_template, flash
from flask_login import login_required, current_user
from app import app, db 

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


import os
from flask import request, redirect, url_for, render_template, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import app, db

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        user = current_user

        user.name = request.form.get('name')
        user.first_name = request.form.get('first_name')
        user.last_name = request.form.get('last_name')
        user.phone = request.form.get('phone')
        user.bio = request.form.get('bio')

        avatar = request.files.get('avatar')
        if avatar and avatar.filename and allowed_file(avatar.filename):
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'avatars')
            os.makedirs(upload_folder, exist_ok=True)

            filename = f"user_{user.id}_" + secure_filename(avatar.filename)
            path = os.path.join(upload_folder, filename)
            avatar.save(path)

            user.avatar_url = f'uploads/avatars/{filename}'

        db.session.commit()
        flash('Profile updated', 'success')
        return redirect(url_for('profile'))

    return render_template('profile.html', user=current_user)




from app.models import User, Tournament, Discussion

from app.models import Discussion, User

from app.models import Discussion, News 

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role not in ['admin', 'king']:

        return redirect(url_for('index'))

    user_count = User.query.count()
    tournament_count = Tournament.query.count()
    discussion_count = Discussion.query.count()
    news_count = News.query.count()

    users = User.query.all()
    tournaments = Tournament.query.all()
    discussions = Discussion.query.options(
        db.joinedload(Discussion.author),
        db.joinedload(Discussion.messages)
    ).all()

    return render_template(
        'admin_panel.html',
        user_count=user_count,
        tournament_count=tournament_count,
        discussion_count=discussion_count,
        news_count=news_count,
        users=users,
        tournaments=tournaments,
        discussions=discussions
    )





from flask_login import current_user, login_required
from flask import request, render_template, redirect, url_for, flash
from app.models import User
from app import db

from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app import app, db
from app.models import User

@app.route('/user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    is_owner_or_admin = current_user.id == user.id or current_user.role in ['admin', 'king']

    if request.method == 'POST':
        if not is_owner_or_admin:
            flash("You do not have permission to edit this profile.", "danger")
            return redirect(url_for('user_profile', user_id=user.id))

        user.name = request.form['name']
        user.first_name = request.form['first_name']
        user.last_name = request.form['last_name']
        user.phone = request.form['phone']
        user.bio = request.form['bio']


        db.session.commit()
        flash('Profile updated', 'success')
        return redirect(url_for('user_profile', user_id=user.id))

    template = 'profile.html' if is_owner_or_admin else 'profile_view.html'
    return render_template(template, user=user)





from flask import redirect, flash

@app.post('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if current_user.role not in ['admin', 'king']:

        return redirect(url_for('index'))
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted', 'success')
    return redirect(url_for('admin_panel'))

@app.post('/admin/delete_tournament/<int:tournament_id>')
@login_required
def delete_tournament(tournament_id):
    if current_user.role not in ['admin', 'king']:

        return redirect(url_for('index'))
    tournament = Tournament.query.get_or_404(tournament_id)
    db.session.delete(tournament)
    db.session.commit()
    flash('The tournament has been deleted.', 'success')
    return redirect(url_for('admin_panel'))

@app.post('/admin/delete_discussion/<int:discussion_id>')
@login_required
def delete_discussion(discussion_id):
    if current_user.role not in ['admin', 'king']:

        return redirect(url_for('index'))
    discussion = Discussion.query.get_or_404(discussion_id)
    db.session.delete(discussion)
    db.session.commit()
    flash('Discussion deleted', 'success')
    return redirect(url_for('admin_panel'))



from flask_babel import Babel
from flask import Flask, request, session

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['BABEL_DEFAULT_LOCALE'] = 'ru'
app.config['BABEL_SUPPORTED_LOCALES'] = ['ru', 'en', 'lv']

babel = Babel(app)

@babel.localeselector
def get_locale():
    return session.get('lang') or request.accept_languages.best_match(app.config['BABEL_SUPPORTED_LOCALES'])


from flask import request, render_template
from app.models import Tournament

@app.route('/tournaments')
def tournament_list():
    search = request.args.get('search', '').strip() 
    sort = request.args.get('sort', 'date_desc')

    query = Tournament.query

    if search:
        query = query.filter(Tournament.name.ilike(f'%{search}%'))

    if sort == 'date_desc':
        query = query.order_by(Tournament.date_created.desc())
    elif sort == 'date_asc':
        query = query.order_by(Tournament.date_created.asc())
    elif sort == 'name':
        query = query.order_by(Tournament.name.asc())
    elif sort == 'teams':
        query = query.outerjoin(Tournament.teams).group_by(Tournament.id).order_by(db.func.count().desc())

    tournaments = query.all()
    return render_template('tournaments.html', tournaments=tournaments)


from flask_login import login_required, current_user
from flask import flash, redirect, url_for, abort



from flask import abort, flash, redirect, url_for
from flask_login import current_user, login_required
from app import app, db
from app.models import User

@app.route('/admin/promote/<int:user_id>')
@login_required
def promote_user(user_id):
    if current_user.role != 'king':
        abort(403)
    user = User.query.get_or_404(user_id)
    if user.role == 'organizer':
        user.role = 'admin'
        db.session.commit()
        flash(f'User {user.name} promoted to admin.', 'success')
    else:
        flash('The promotion is only available to organizers.', 'warning')
    return redirect(url_for('admin_panel'))

@app.route('/admin/demote/<int:user_id>')
@login_required
def demote_user(user_id):
    if current_user.role != 'king':
        abort(403)
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        user.role = 'organizer'
        db.session.commit()
        flash(f'User {user.name} demoted to organizer.', 'success')
    else:
        flash('Downgrade is only available for admins.', 'warning')
    return redirect(url_for('admin_panel'))







