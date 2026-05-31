from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


def init_db(db):
    """Inicjalizacja modeli bazy danych"""

    class User(UserMixin, db.Model):
        __tablename__ = 'users'

        id = db.Column(db.Integer, primary_key=True)
        email = db.Column(db.String(120), unique=True, nullable=False)
        password_hash = db.Column(db.String(255), nullable=False)
        is_admin = db.Column(db.Boolean, default=False)
        data_rejestracji = db.Column(db.DateTime, default=datetime.utcnow)

        # Jeden użytkownik ma wiele dokumentów
        documents = db.relationship('Document', backref='user', lazy=True, cascade='all, delete-orphan')
        study_goal = db.relationship('StudyGoal', backref='user', uselist=False, cascade='all, delete-orphan')
        study_activities = db.relationship('StudyActivity', backref='user', lazy=True, cascade='all, delete-orphan')

        def set_password(self, password):
            self.password_hash = generate_password_hash(password)

        def check_password(self, password):
            return check_password_hash(self.password_hash, password)

        def __repr__(self):
            return f'<User {self.email}>'

    class Document(db.Model):
        __tablename__ = 'documents'

        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
        title = db.Column(db.String(200), nullable=False)
        processed_text = db.Column(db.Text, nullable=True)
        uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

        # Jeden dokument ma wiele streszczeń, fiszek i quizów
        summaries = db.relationship('Summary', backref='document', lazy=True, cascade='all, delete-orphan')
        flashcards = db.relationship('Flashcard', backref='document', lazy=True, cascade='all, delete-orphan')
        quizzes = db.relationship('Quiz', backref='document', lazy=True, cascade='all, delete-orphan')

        def __repr__(self):
            return f'<Document {self.title}>'

    class Summary(db.Model):
        __tablename__ = 'summaries'

        id = db.Column(db.Integer, primary_key=True)
        document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
        content = db.Column(db.Text, nullable=False)

        def __repr__(self):
            return f'<Summary {self.id}>'

    class Quiz(db.Model):
        __tablename__ = 'quizzes'

        id = db.Column(db.Integer, primary_key=True)
        document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
        score = db.Column(db.Integer, nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

        # Jeden quiz ma wiele pytań quizowych
        quiz_questions = db.relationship('QuizQuestion', backref='quiz', lazy=True, cascade='all, delete-orphan')

        def __repr__(self):
            return f'<Quiz {self.id}>'

    class Flashcard(db.Model):
        __tablename__ = 'flashcards'

        id = db.Column(db.Integer, primary_key=True)
        document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
        question = db.Column(db.String(500), nullable=False)
        answer = db.Column(db.Text, nullable=False)
        next_review = db.Column(db.DateTime, default=datetime.utcnow)
        interval_days = db.Column(db.Integer, default=1)
        ease_factor = db.Column(db.Float, default=2.5)

        def __repr__(self):
            return f'<Flashcard {self.question[:30]}>'

    class QuizQuestion(db.Model):
        __tablename__ = 'quiz_questions'

        id = db.Column(db.Integer, primary_key=True)
        quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
        question = db.Column(db.Text, nullable=False)
        correct_answer = db.Column(db.Text, nullable=False)
        distractors = db.Column(db.Text, nullable=True)

        def __repr__(self):
            return f'<QuizQuestion {self.id}>'

    class StudyGoal(db.Model):
        __tablename__ = 'study_goals'

        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
        weekly_sessions_goal = db.Column(db.Integer, nullable=False, default=5)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        def __repr__(self):
            return f'<StudyGoal user={self.user_id} weekly={self.weekly_sessions_goal}>'

    class StudyActivity(db.Model):
        __tablename__ = 'study_activities'

        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
        activity_date = db.Column(db.Date, nullable=False)
        sessions_count = db.Column(db.Integer, nullable=False, default=1)
        last_activity_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        activity_type = db.Column(db.String(50), nullable=True)

        __table_args__ = (
            db.UniqueConstraint('user_id', 'activity_date', name='uq_study_activity_user_day'),
        )

        def __repr__(self):
            return f'<StudyActivity user={self.user_id} date={self.activity_date}>'

    # Zwracamy modele do użycia w aplikacji
    return User, Document, Summary, Flashcard, Quiz, QuizQuestion, StudyGoal, StudyActivity