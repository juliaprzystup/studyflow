"""Tworzy lub aktualizuje konto demonstracyjne administratora (recenzent).

Uzycie na serwerze produkcyjnym:
    python scripts/seed_demo_admin.py
"""
from app import app, db, User

DEMO_EMAIL = "admin@studyflow.pl"
DEMO_PASSWORD = "StudyFlow1!"

with app.app_context():
    user = User.query.filter_by(email=DEMO_EMAIL).first()
    if user is None:
        user = User(email=DEMO_EMAIL, is_admin=True)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        print(f"Utworzono konto demo: {DEMO_EMAIL}")
    else:
        user.is_admin = True
        user.set_password(DEMO_PASSWORD)
        print(f"Zaktualizowano konto demo: {DEMO_EMAIL}")

    db.session.commit()
