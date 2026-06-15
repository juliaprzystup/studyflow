from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from config import Config
from datetime import datetime, timedelta
from types import SimpleNamespace
from functools import wraps
from sqlalchemy import or_

from utils.flashcard_generator import generate_flashcards
from utils.smart_quiz_generator import generate_smart_quiz

from utils.text_processor import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_txt,
    clean_text,
    generate_summary,
    extract_key_points
)

import random
import os
import re
import uuid
from werkzeug.utils import secure_filename

# Inicjalizacja aplikacji
app = Flask(__name__)
app.config.from_object(Config)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
# Globalny limit uploadu (ochrona przed zbyt dużymi plikami / DoS)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# Inicjalizacja bazy danych
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# Inicjalizacja Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Import i inicjalizacja modeli
from models import init_db
User, Document, Summary, Flashcard, Quiz, QuizQuestion, StudyGoal, StudyActivity = init_db(db)

# User loader dla Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        if not current_user.is_admin:
            flash('Brak uprawnień do tej sekcji.', 'danger')
            return redirect(url_for('dashboard'))

        return view_func(*args, **kwargs)

    return wrapped_view


def redirect_to_admin_dashboard(default_tab='users'):
    requested_tab = request.form.get('tab') or request.args.get('tab') or default_tab
    if requested_tab not in {'users', 'documents'}:
        requested_tab = default_tab

    return redirect(url_for(
        'admin_dashboard',
        tab=requested_tab,
        user_q=request.form.get('user_q', request.args.get('user_q', '')),
        user_role=request.form.get('user_role', request.args.get('user_role', 'all')),
        user_sort=request.form.get('user_sort', request.args.get('user_sort', 'admins_first')),
        doc_q=request.form.get('doc_q', request.args.get('doc_q', '')),
        doc_sort=request.form.get('doc_sort', request.args.get('doc_sort', 'recent')),
    ))


def get_document_upload_path(document):
    return os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], document.title)


def cleanup_document_file(document):
    duplicate_document = Document.query.filter(
        Document.id != document.id,
        Document.title == document.title
    ).first()

    if duplicate_document:
        return

    file_path = get_document_upload_path(document)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as exc:
            app.logger.warning("Nie udalo sie usunac pliku %s: %s", file_path, exc)


def delete_document_bundle(document):
    cleanup_document_file(document)
    db.session.delete(document)


def delete_user_bundle(user):
    for document in list(user.documents):
        cleanup_document_file(document)

    if user.study_goal:
        db.session.delete(user.study_goal)

    for activity in list(user.study_activities):
        db.session.delete(activity)

    db.session.delete(user)


@app.errorhandler(413)
def request_entity_too_large(_error):
    flash('Plik jest za duży. Maksymalny rozmiar to 16 MB.', 'danger')
    return redirect(url_for('upload_file'))


@app.errorhandler(CSRFError)
def handle_csrf_error(_error):
    flash('Twoja sesja wygasła lub żądanie jest nieprawidłowe. Spróbuj ponownie.', 'danger')
    return redirect(request.referrer or url_for('login'))

# Strona główna
@app.route('/')
def index():
    return render_template('index.html')

# Strona logowania
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Zalogowano pomyślnie.', 'success')

            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Nieprawidłowy email lub hasło!', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

# Strona rejestracji
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        password2 = request.form.get('password2')

        password = password or ''
        if len(password) < 8:
            flash('Hasło musi mieć co najmniej 8 znaków.', 'danger')
            return redirect(url_for('register'))

        if not re.search(r'[A-Z]', password):
            flash('Hasło musi zawierać przynajmniej jedną wielką literę.', 'danger')
            return redirect(url_for('register'))

        if not re.search(r'\d', password):
            flash('Hasło musi zawierać przynajmniej jedną cyfrę.', 'danger')
            return redirect(url_for('register'))

        # Znak specjalny = cokolwiek spoza liter (A-Z) i cyfr (0-9)
        if not re.search(r'[^A-Za-z0-9]', password):
            flash('Hasło musi zawierać przynajmniej jeden znak specjalny.', 'danger')
            return redirect(url_for('register'))

        if password != password2:
            flash('Hasła nie są identyczne!', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email już jest zarejestrowany!', 'danger')
            return redirect(url_for('register'))

        new_user = User(email=email)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash('Rejestracja przebiegła pomyślnie! Możesz się zalogować.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Dashboard użytkownika
def log_study_activity(user_id, activity_type):
    today = datetime.utcnow().date()
    activity = StudyActivity.query.filter_by(user_id=user_id, activity_date=today).first()

    if activity:
        activity.sessions_count += 1
        activity.last_activity_at = datetime.utcnow()
        activity.activity_type = activity_type
    else:
        activity = StudyActivity(
            user_id=user_id,
            activity_date=today,
            sessions_count=1,
            last_activity_at=datetime.utcnow(),
            activity_type=activity_type
        )
        db.session.add(activity)


@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    # Statystyki bazujące na relacjach Document -> Quiz/Flashcard
    notes_count = len(current_user.documents)
    quizzes_count = Quiz.query.join(Document).filter(Document.user_id == current_user.id).count()
    flashcards_count = Flashcard.query.join(Document).filter(Document.user_id == current_user.id).count()

    goal = StudyGoal.query.filter_by(user_id=current_user.id).first()
    if not goal:
        goal = StudyGoal(user_id=current_user.id, weekly_sessions_goal=5)
        db.session.add(goal)
        db.session.commit()

    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())
    week_activities = StudyActivity.query.filter(
        StudyActivity.user_id == current_user.id,
        StudyActivity.activity_date >= week_start,
        StudyActivity.activity_date <= today
    ).all()
    week_sessions_done = sum(item.sessions_count for item in week_activities)
    weekly_goal = goal.weekly_sessions_goal
    sessions_left = max(weekly_goal - week_sessions_done, 0)

    if weekly_goal <= 0:
        recommendation = "Ustaw swój cel tygodniowy w zakładce Postępy, aby rozpocząć regularną naukę."
    elif sessions_left == 0:
        recommendation = "Cel tygodniowy zrealizowany! Utrzymaj tempo i zrób dziś krótką sesję powtórkową."
    elif sessions_left <= 2:
        recommendation = f"Świetnie Ci idzie! Zrób jeszcze tylko {sessions_left} sesje nauki, aby domknąć cel tygodniowy."
    elif week_sessions_done == 0:
        recommendation = "Zacznij od jednej krótkiej sesji dziś. Pierwszy krok uruchamia cały progres tygodnia."
    else:
        recommendation = f"Brakuje {sessions_left} sesji do celu tygodniowego. Jedna sesja dziennie i jesteś na dobrej drodze."

    return render_template('dashboard.html',
                           notes_count=notes_count,
                           quizzes_count=quizzes_count,
                           flashcards_count=flashcards_count,
                           recommendation=recommendation,
                           sessions_left=sessions_left)


@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    active_tab = request.args.get('tab', 'users')
    if active_tab not in {'users', 'documents'}:
        active_tab = 'users'

    user_query = (request.args.get('user_q') or '').strip()
    user_role = request.args.get('user_role', 'all')
    user_sort = request.args.get('user_sort', 'admins_first')
    doc_query = (request.args.get('doc_q') or '').strip()
    doc_sort = request.args.get('doc_sort', 'recent')

    user_documents_count = db.func.count(Document.id)
    users_query = (
        db.session.query(
            User,
            user_documents_count.label('documents_count')
        )
        .outerjoin(Document, Document.user_id == User.id)
    )

    if user_query:
        users_query = users_query.filter(User.email.ilike(f'%{user_query}%'))

    if user_role == 'admins':
        users_query = users_query.filter(User.is_admin.is_(True))
    elif user_role == 'members':
        users_query = users_query.filter(User.is_admin.is_(False))
    else:
        user_role = 'all'

    users_query = users_query.group_by(User.id)

    user_sort_options = {
        'admins_first': [User.is_admin.desc(), User.data_rejestracji.desc()],
        'recent': [User.data_rejestracji.desc()],
        'oldest': [User.data_rejestracji.asc()],
        'documents_desc': [user_documents_count.desc(), User.email.asc()],
        'documents_asc': [user_documents_count.asc(), User.email.asc()],
        'email_asc': [User.email.asc()],
    }
    user_sort_order = user_sort_options.get(user_sort, user_sort_options['admins_first'])
    if user_sort not in user_sort_options:
        user_sort = 'admins_first'

    for order_clause in user_sort_order:
        users_query = users_query.order_by(order_clause)

    user_rows = users_query.all()

    users = [
        SimpleNamespace(
            id=user.id,
            email=user.email,
            is_admin=user.is_admin,
            registered_at=user.data_rejestracji,
            documents_count=documents_count,
        )
        for user, documents_count in user_rows
    ]

    summaries_count = db.func.count(db.distinct(Summary.id))
    flashcards_count = db.func.count(db.distinct(Flashcard.id))
    quizzes_count = db.func.count(db.distinct(Quiz.id))
    documents_query = (
        db.session.query(
            Document,
            User.email.label('owner_email'),
            summaries_count.label('summaries_count'),
            flashcards_count.label('flashcards_count'),
            quizzes_count.label('quizzes_count'),
        )
        .join(User, User.id == Document.user_id)
        .outerjoin(Summary, Summary.document_id == Document.id)
        .outerjoin(Flashcard, Flashcard.document_id == Document.id)
        .outerjoin(Quiz, Quiz.document_id == Document.id)
    )

    if doc_query:
        like_term = f'%{doc_query}%'
        documents_query = documents_query.filter(
            or_(
                Document.title.ilike(like_term),
                User.email.ilike(like_term),
            )
        )

    documents_query = documents_query.group_by(Document.id, User.email)

    document_sort_options = {
        'recent': [Document.uploaded_at.desc()],
        'oldest': [Document.uploaded_at.asc()],
        'title_asc': [Document.title.asc()],
        'owner_asc': [User.email.asc(), Document.uploaded_at.desc()],
        'flashcards_desc': [flashcards_count.desc(), Document.uploaded_at.desc()],
        'quizzes_desc': [quizzes_count.desc(), Document.uploaded_at.desc()],
    }
    document_sort_order = document_sort_options.get(doc_sort, document_sort_options['recent'])
    if doc_sort not in document_sort_options:
        doc_sort = 'recent'

    for order_clause in document_sort_order:
        documents_query = documents_query.order_by(order_clause)

    document_rows = documents_query.all()

    documents = [
        SimpleNamespace(
            id=document.id,
            title=document.title,
            uploaded_at=document.uploaded_at,
            owner_email=owner_email,
            owner_id=document.user_id,
            summaries_count=summaries_count,
            flashcards_count=flashcards_count,
            quizzes_count=quizzes_count,
        )
        for document, owner_email, summaries_count, flashcards_count, quizzes_count in document_rows
    ]

    total_users = User.query.count()
    admin_users = User.query.filter_by(is_admin=True).count()
    total_documents = Document.query.count()
    total_summaries = Summary.query.count()
    total_flashcards = Flashcard.query.count()
    total_quizzes = Quiz.query.count()
    total_learning_assets = total_summaries + total_flashcards + total_quizzes
    users_with_documents = db.session.query(db.func.count(db.distinct(Document.user_id))).scalar() or 0
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    stats = SimpleNamespace(
        total_users=total_users,
        admin_users=admin_users,
        total_documents=total_documents,
        total_learning_assets=total_learning_assets,
        total_summaries=total_summaries,
        total_flashcards=total_flashcards,
        total_quizzes=total_quizzes,
        users_with_documents=users_with_documents,
        avg_documents_per_user=round(total_documents / total_users, 1) if total_users else 0,
        uploads_last_7_days=Document.query.filter(Document.uploaded_at >= seven_days_ago).count(),
        new_users_last_7_days=User.query.filter(User.data_rejestracji >= seven_days_ago).count(),
    )

    return render_template(
        'admin_dashboard.html',
        users=users,
        documents=documents,
        stats=stats,
        active_tab=active_tab,
        filters=SimpleNamespace(
            user_query=user_query,
            user_role=user_role,
            user_sort=user_sort,
            doc_query=doc_query,
            doc_sort=doc_sort,
        ),
    )


@app.route('/statistics')
@login_required
def statistics():
    scored_quizzes = Quiz.query.join(Document).filter(
        Document.user_id == current_user.id,
        Quiz.score.isnot(None)
    ).order_by(Quiz.created_at.desc()).all()

    attempts = []
    percentage_values = []

    for quiz in scored_quizzes:
        total_questions = len(quiz.quiz_questions) if quiz.quiz_questions else 0
        if total_questions == 0:
            continue

        score = quiz.score if quiz.score is not None else 0
        percent = round((score / total_questions) * 100)
        percentage_values.append(percent)
        attempts.append(SimpleNamespace(
            created_at=quiz.created_at,
            score=score,
            total_questions=total_questions,
            percent=percent,
            quiz=SimpleNamespace(title=f"Quiz: {quiz.document.title}")
        ))

    total_quizzes_solved = len(attempts)
    average_score = round(sum(percentage_values) / total_quizzes_solved) if total_quizzes_solved else 0
    best_score = max(percentage_values) if percentage_values else 0
    latest_score = attempts[0].percent if attempts else 0
    trend_attempts = list(reversed(attempts[:10]))

    return render_template(
        'statistics.html',
        attempts=attempts,
        total_quizzes_solved=total_quizzes_solved,
        average_score=average_score,
        best_score=best_score,
        latest_score=latest_score,
        trend_attempts=trend_attempts
    )


@app.route('/progress', methods=['GET', 'POST'])
@login_required
def progress():
    goal = StudyGoal.query.filter_by(user_id=current_user.id).first()
    if not goal:
        goal = StudyGoal(user_id=current_user.id, weekly_sessions_goal=5)
        db.session.add(goal)
        db.session.commit()

    if request.method == 'POST':
        weekly_goal = request.form.get('weekly_goal', type=int)
        if weekly_goal is None or weekly_goal < 1 or weekly_goal > 50:
            flash('Cel tygodniowy musi być liczbą od 1 do 50.', 'warning')
        else:
            goal.weekly_sessions_goal = weekly_goal
            db.session.commit()
            flash('Zaktualizowano cel tygodniowy.', 'success')
        return redirect(url_for('progress'))

    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())
    week_activities = StudyActivity.query.filter(
        StudyActivity.user_id == current_user.id,
        StudyActivity.activity_date >= week_start,
        StudyActivity.activity_date <= today
    ).all()
    week_sessions_done = sum(item.sessions_count for item in week_activities)
    weekly_goal = goal.weekly_sessions_goal
    weekly_progress_percent = min(int((week_sessions_done / weekly_goal) * 100), 100) if weekly_goal else 0

    all_activity_dates = {
        item.activity_date for item in StudyActivity.query.filter_by(user_id=current_user.id).all()
    }
    if not all_activity_dates:
        current_streak = 0
    else:
        latest_activity_date = max(all_activity_dates)
        if (today - latest_activity_date).days > 1:
            current_streak = 0
        else:
            streak_cursor = latest_activity_date
            current_streak = 0
            while streak_cursor in all_activity_dates:
                current_streak += 1
                streak_cursor -= timedelta(days=1)

    activity_map = {item.activity_date: item.sessions_count for item in week_activities}
    weekly_activity = []
    for day_offset in range(6, -1, -1):
        day = today - timedelta(days=day_offset)
        sessions = activity_map.get(day, 0)
        weekly_activity.append(SimpleNamespace(
            day_label=day.strftime('%a'),
            date_label=day.strftime('%d.%m'),
            sessions=sessions,
            is_active=sessions > 0
        ))

    return render_template(
        'progress.html',
        current_streak=current_streak,
        weekly_goal=weekly_goal,
        week_sessions_done=week_sessions_done,
        weekly_progress_percent=weekly_progress_percent,
        weekly_activity=weekly_activity
    )

# Wylogowanie
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Zostałeś wylogowany!', 'success')
    return redirect(url_for('index'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Strona przesyłania plików
@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Nie wybrano pliku!', 'danger')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('Nie wybrano pliku!', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            file_extension = filename.rsplit('.', 1)[1].lower()

            if file_extension == 'pdf':
                text = extract_text_from_pdf(filepath)
            elif file_extension in ['doc', 'docx']:
                text = extract_text_from_docx(filepath)
            elif file_extension == 'txt':
                text = extract_text_from_txt(filepath)
            else:
                flash('Nieobsługiwany typ pliku!', 'danger')
                return redirect(request.url)

            # Czyszczenie całego tekstu
            full_text = clean_text(text)

            # Zapis dokumentu z przetworzonym tekstem
            new_note = Document(
                title=filename,
                processed_text=full_text,
                user_id=current_user.id
            )
            db.session.add(new_note)
            db.session.flush()

            # Generowanie i zapis streszczenia TextRank
            summary = generate_summary(full_text, num_sentences=10)
            db.session.add(Summary(document_id=new_note.id, content=summary))
            log_study_activity(current_user.id, 'upload')
            db.session.commit()

            flash('Plik został przesłany i przetworzony!', 'success')
            return redirect(url_for('view_note', note_id=new_note.id))

        else:
            flash('Niedozwolony typ pliku! Dozwolone: txt, pdf, doc, docx', 'danger')
            return redirect(request.url)

    return render_template('upload.html')

# Strona wyświetlania notatki - "document hub" (centrum dowodzenia dla dokumentu)
@app.route('/note/<int:note_id>')
@login_required
def view_note(note_id):
    note = Document.query.get_or_404(note_id)

    if note.user_id != current_user.id:
        flash('Nie masz dostępu do tej notatki!', 'danger')
        return redirect(url_for('dashboard'))

    latest_summary = Summary.query.filter_by(document_id=note.id).order_by(Summary.id.desc()).first()
    note.summary = latest_summary.content if latest_summary else 'Brak podsumowania.'
    note.created_at = note.uploaded_at
    note.original_file = note.title

    # Fiszki należące tylko do tego dokumentu (talia)
    flashcards = Flashcard.query.filter_by(document_id=note.id) \
        .order_by(Flashcard.next_review.asc()).all()

    # Historia quizów wyłącznie dla tego dokumentu
    quizzes = Quiz.query.filter_by(document_id=note.id) \
        .order_by(Quiz.created_at.desc()).all()

    quiz_history = []
    for quiz in quizzes:
        total_questions = QuizQuestion.query.filter_by(quiz_id=quiz.id).count()
        score = quiz.score
        percent = (
            round((score / total_questions) * 100)
            if (total_questions and score is not None)
            else None
        )
        quiz_history.append(SimpleNamespace(
            id=quiz.id,
            created_at=quiz.created_at,
            score=score,
            total_questions=total_questions,
            percent=percent,
        ))

    return render_template(
        'view_note.html',
        note=note,
        flashcards=flashcards,
        quiz_history=quiz_history,
    )

# Lista wszystkich notatek
@app.route('/notes')
@login_required
def notes_list():
    notes = Document.query.filter_by(user_id=current_user.id).order_by(Document.uploaded_at.desc()).all()
    for note in notes:
        latest_summary = Summary.query.filter_by(document_id=note.id).order_by(Summary.id.desc()).first()
        note.summary = latest_summary.content if latest_summary else ''
        note.created_at = note.uploaded_at
    return render_template('notes_list.html', notes=notes)

# Generowanie quizu z notatki
@app.route('/generate_quiz/<int:note_id>')
@login_required
def generate_quiz(note_id):
    note = Document.query.get_or_404(note_id)

    if note.user_id != current_user.id:
        flash('Nie masz dostępu do tej notatki!', 'danger')
        return redirect(url_for('dashboard'))

    # Generuje pytania z pełnego tekstu dokumentu
    questions = generate_smart_quiz(note.processed_text, num_questions=5)

    if not questions:
        flash('Nie udało się wygenerować pytań z tej notatki.', 'warning')
        return redirect(url_for('view_note', note_id=note_id))

    new_quiz = Quiz(document_id=note.id)
    db.session.add(new_quiz)
    db.session.flush()

    for question_data in questions:
        all_answers = question_data.get('answers', [])
        correct_answer = question_data.get('correct_answer', '')
        distractors = [a for a in all_answers if a != correct_answer]

        db.session.add(QuizQuestion(
            quiz_id=new_quiz.id,
            question=question_data.get('question', ''),
            correct_answer=correct_answer,
            distractors=';'.join(distractors)
        ))

    db.session.commit()

    flash('Quiz został wygenerowany!', 'success')
    return redirect(url_for('take_quiz', quiz_id=new_quiz.id))

# --- ROZWIĄZYWANIE QUIZU (ZMODYFIKOWANE) ---
@app.route('/quiz/<int:quiz_id>', methods=['GET', 'POST'])
@login_required
def take_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)

    if quiz.document.user_id != current_user.id:
        flash('Nie masz dostępu do tego quizu!', 'danger')
        return redirect(url_for('dashboard'))

    quiz.title = f"Quiz: {quiz.document.title}"
    stored_questions = QuizQuestion.query.filter_by(quiz_id=quiz.id).all()
    questions = []

    for item in stored_questions:
        distractors = [ans.strip() for ans in (item.distractors or '').split(';') if ans.strip()]
        answers = distractors + [item.correct_answer]
        random.shuffle(answers)
        questions.append({
            'question': item.question,
            'answers': answers,
            'correct_answer': item.correct_answer
        })

    questions_with_index = []
    for i, question in enumerate(questions):
        question['index'] = i
        questions_with_index.append(question)

    if request.method == 'POST':
        score = 0
        results = []

        for i, question in enumerate(questions):
            user_answer = request.form.get(f'question_{i}')
            correct_answer = question['correct_answer']

            is_correct = (user_answer == correct_answer)
            if is_correct:
                score += 1

            results.append({
                'question': question['question'],
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'is_correct': is_correct,
                'correct_text': question['correct_answer']
            })

        # Zapisujemy wynik quizu
        quiz.score = score
        log_study_activity(current_user.id, 'quiz')
        db.session.commit()

        return render_template('quiz_results.html',
                               quiz=quiz,
                               results=results,
                               score=score,
                               total=len(questions))

    return render_template('take_quiz.html', quiz=quiz, questions=questions_with_index)

# Lista quizów - "Wybierz materiał do testu" (lista dokumentów posiadających quizy)
@app.route('/quizzes')
@login_required
def quizzes_list():
    rows = (
        db.session.query(
            Document,
            db.func.count(Quiz.id).label('quiz_count'),
            db.func.max(Quiz.created_at).label('last_quiz_at'),
            db.func.max(Quiz.score).label('best_score'),
        )
        .join(Quiz, Quiz.document_id == Document.id)
        .filter(Document.user_id == current_user.id)
        .group_by(Document.id)
        .order_by(db.func.max(Quiz.created_at).desc())
        .all()
    )

    quiz_decks = []
    for document, quiz_count, last_quiz_at, _best in rows:
        last_attempt = (
            Quiz.query.filter_by(document_id=document.id)
            .order_by(Quiz.created_at.desc())
            .first()
        )
        last_total = QuizQuestion.query.filter_by(quiz_id=last_attempt.id).count() if last_attempt else 0
        last_percent = (
            round((last_attempt.score / last_total) * 100)
            if (last_attempt and last_attempt.score is not None and last_total)
            else None
        )
        quiz_decks.append(SimpleNamespace(
            document=document,
            quiz_count=quiz_count,
            last_quiz_at=last_quiz_at,
            last_score=last_attempt.score if last_attempt else None,
            last_total=last_total,
            last_percent=last_percent,
        ))

    return render_template('quizzes_list.html', quiz_decks=quiz_decks)

# Generowanie fiszek z notatki
@app.route('/generate_flashcards/<int:note_id>')
@login_required
def generate_flashcards_route(note_id):
    note = Document.query.get_or_404(note_id)

    if note.user_id != current_user.id:
        flash('Nie masz dostępu do tej notatki!', 'danger')
        return redirect(url_for('dashboard'))

    # Generuje fiszki z pełnego tekstu dokumentu
    flashcards_data = generate_flashcards(note.processed_text, num_cards=10)

    if not flashcards_data:
        flash('Nie udało się wygenerować fiszek z tej notatki.', 'warning')
        return redirect(url_for('view_note', note_id=note_id))

    for card_data in flashcards_data:
        new_card = Flashcard(
            question=card_data['question'],
            answer=card_data['answer'],
            document_id=note.id,
            next_review=datetime.utcnow(),
            interval_days=1,
            ease_factor=2.5
        )
        db.session.add(new_card)

    db.session.commit()

    flash(f'Wygenerowano {len(flashcards_data)} fiszek!', 'success')
    return redirect(url_for('view_note', note_id=note.id))

# Lista fiszek - "Twoje talie" (dokumenty, które mają wygenerowane fiszki)
@app.route('/flashcards')
@login_required
def flashcards_list():
    rows = (
        db.session.query(
            Document,
            db.func.count(Flashcard.id).label('flashcard_count'),
            db.func.min(Flashcard.next_review).label('next_review_at'),
        )
        .join(Flashcard, Flashcard.document_id == Document.id)
        .filter(Document.user_id == current_user.id)
        .group_by(Document.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )

    today = datetime.utcnow()
    decks = []
    for document, flashcard_count, next_review_at in rows:
        due_count = (
            Flashcard.query.filter(
                Flashcard.document_id == document.id,
                Flashcard.next_review <= today,
            ).count()
        )
        decks.append(SimpleNamespace(
            document=document,
            flashcard_count=flashcard_count,
            due_count=due_count,
            next_review_at=next_review_at,
        ))

    return render_template('flashcards_list.html', decks=decks)

# --- FUNKCJE USUWANIA (CRUD) ---

@app.route('/delete_note/<int:note_id>', methods=['POST'])
@login_required
def delete_note(note_id):
    note = Document.query.get_or_404(note_id)

    if note.user_id != current_user.id:
        flash('Brak uprawnień do usunięcia tej notatki!', 'danger')
        return redirect(url_for('notes_list'))

    delete_document_bundle(note)
    db.session.commit()
    flash('Notatka została pomyślnie usunięta.', 'success')
    return redirect(url_for('notes_list'))


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('Nie możesz usunąć aktualnie zalogowanego administratora.', 'warning')
        return redirect_to_admin_dashboard('users')

    if user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
        flash('Nie można usunąć ostatniego administratora systemu.', 'warning')
        return redirect_to_admin_dashboard('users')

    user_email = user.email
    delete_user_bundle(user)
    db.session.commit()

    flash(f'Użytkownik {user_email} oraz jego dane zostały usunięte.', 'success')
    return redirect_to_admin_dashboard('users')


@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@admin_required
def admin_toggle_admin(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('Nie możesz zmienić uprawnień własnego konta.', 'warning')
        return redirect_to_admin_dashboard('users')

    if user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
        flash('Nie można odebrać uprawnień ostatniemu administratorowi.', 'warning')
        return redirect_to_admin_dashboard('users')

    user.is_admin = not user.is_admin
    db.session.commit()

    if user.is_admin:
        flash(f'Nadano uprawnienia administratora dla {user.email}.', 'success')
    else:
        flash(f'Odebrano uprawnienia administratora dla {user.email}.', 'success')

    return redirect_to_admin_dashboard('users')


@app.route('/admin/delete_document/<int:doc_id>', methods=['POST'])
@admin_required
def admin_delete_document(doc_id):
    document = Document.query.get_or_404(doc_id)

    document_title = document.title
    owner_email = document.user.email
    delete_document_bundle(document)
    db.session.commit()

    flash(f'Dokument {document_title} użytkownika {owner_email} został usunięty.', 'success')
    return redirect_to_admin_dashboard('documents')


@app.route('/delete_quiz/<int:quiz_id>', methods=['POST'])
@login_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)

    if quiz.document.user_id != current_user.id:
        flash('Brak uprawnień do usunięcia tego quizu!', 'danger')
        return redirect(url_for('quizzes_list'))

    document_id = quiz.document_id
    db.session.delete(quiz)
    db.session.commit()
    flash('Quiz został pomyślnie usunięty.', 'success')
    return redirect(url_for('view_note', note_id=document_id))


# ── Algorytm SM-2 (SuperMemo 2) ──────────────────────────────────────────
# Aktualizuje pola Flashcard: interval_days, ease_factor, next_review.
#
# Mapowanie ocen:
#   quality < 3  → odpowiedź błędna (reset interwału do 1 dnia, EF bez zmian),
#   quality >= 3 → odpowiedź poprawna (interwał rośnie wg EF).
#
# Bez dodatkowej kolumny `repetitions` – pierwsze powodzenie po resetcie
# wykrywamy po `interval_days <= 1` (wtedy następny krok = 6 dni, klasyczny SM-2).
def apply_sm2(card, quality):
    quality = max(0, min(5, int(quality)))
    ef = card.ease_factor or 2.5
    interval = card.interval_days or 1

    if quality < 3:
        new_interval = 1
        new_ef = ef
    else:
        if interval <= 1:
            new_interval = 6
        else:
            new_interval = max(1, round(interval * ef))

        new_ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        if new_ef < 1.3:
            new_ef = 1.3

    card.interval_days = new_interval
    card.ease_factor = round(new_ef, 4)
    card.next_review = datetime.utcnow() + timedelta(days=new_interval)
    return card


# Endpoint przyjmujący ocenę użytkownika dla pojedynczej fiszki (AJAX).
# Frontend wysyła JSON: { "quality": 0..5 }.
@app.route('/update_flashcard/<int:card_id>', methods=['POST'])
@login_required
def update_flashcard(card_id):
    card = Flashcard.query.get_or_404(card_id)

    if card.document.user_id != current_user.id:
        return jsonify({'error': 'forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    raw_quality = payload.get('quality')

    if raw_quality is None:
        return jsonify({'error': 'missing quality'}), 400

    try:
        quality = int(raw_quality)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid quality'}), 400

    apply_sm2(card, quality)
    db.session.commit()

    return jsonify({
        'id': card.id,
        'quality': quality,
        'interval_days': card.interval_days,
        'ease_factor': card.ease_factor,
        'next_review': card.next_review.isoformat(),
    })


@app.route('/edit_flashcard/<int:flashcard_id>', methods=['POST'])
@login_required
def edit_flashcard(flashcard_id):
    flashcard = Flashcard.query.get_or_404(flashcard_id)

    if flashcard.document.user_id != current_user.id:
        flash('Brak uprawnień do edycji tej fiszki!', 'danger')
        return redirect(url_for('flashcards_list'))

    question = (request.form.get('question') or '').strip()
    answer = (request.form.get('answer') or '').strip()

    if len(question) < 3:
        flash('Pytanie fiszki musi mieć co najmniej 3 znaki.', 'danger')
        return redirect(url_for('view_note', note_id=flashcard.document_id) + '#flashcards-pane')

    if not answer:
        flash('Odpowiedź fiszki nie może być pusta.', 'danger')
        return redirect(url_for('view_note', note_id=flashcard.document_id) + '#flashcards-pane')

    flashcard.question = question[:500]
    flashcard.answer = answer
    db.session.commit()
    flash('Fiszka została zaktualizowana.', 'success')
    return redirect(url_for('view_note', note_id=flashcard.document_id) + '#flashcards-pane')


@app.route('/delete_flashcard/<int:flashcard_id>', methods=['POST'])
@login_required
def delete_flashcard(flashcard_id):
    flashcard = Flashcard.query.get_or_404(flashcard_id)

    if flashcard.document.user_id != current_user.id:
        flash('Brak uprawnień do usunięcia tej fiszki!', 'danger')
        return redirect(url_for('flashcards_list'))

    document_id = flashcard.document_id
    db.session.delete(flashcard)
    db.session.commit()
    flash('Fiszka została usunięta ze zbioru.', 'success')
    return redirect(url_for('view_note', note_id=document_id))

# Nauka z fiszkami - bez parametru przekierowuje do wyboru talii
@app.route('/study_flashcards')
@login_required
def study_flashcards():
    flash('Wybierz talię, którą chcesz przećwiczyć.', 'info')
    return redirect(url_for('flashcards_list'))


# Sesja nauki SRS dla konkretnej talii (dokumentu)
@app.route('/study_flashcards/<int:document_id>')
@login_required
def study_flashcards_deck(document_id):
    document = Document.query.get_or_404(document_id)

    if document.user_id != current_user.id:
        flash('Nie masz dostępu do tej talii fiszek!', 'danger')
        return redirect(url_for('flashcards_list'))

    flashcards = (
        Flashcard.query.filter_by(document_id=document.id)
        .order_by(Flashcard.next_review.asc())
        .all()
    )

    if not flashcards:
        flash('Ta talia nie zawiera jeszcze żadnych fiszek.', 'warning')
        return redirect(url_for('view_note', note_id=document.id))

    random.shuffle(flashcards)
    log_study_activity(current_user.id, 'flashcards')
    db.session.commit()

    return render_template(
        'study_flashcards.html',
        flashcards=flashcards,
        document=document,
    )

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    with app.app_context():
        db.create_all()
        print("Baza danych została utworzona/zaktualizowana!")

    debug_mode = os.environ.get('FLASK_DEBUG') == '1'
    app.run(debug=debug_mode)