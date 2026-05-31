"""Nadaje uprawnienia administratora istniejacemu kontu uzytkownika.

Uzycie:
    python grant_admin.py adres@email.pl

Jesli nie podasz adresu, skrypt zapyta o niego interaktywnie.
"""
import sys

from app import app, db, User

with app.app_context():
    email = (sys.argv[1] if len(sys.argv) > 1 else input("Email konta: ")).strip()

    user = User.query.filter_by(email=email).first()
    if user is None:
        print(f"Nie znaleziono uzytkownika o adresie: {email}")
        sys.exit(1)

    user.is_admin = True
    db.session.commit()
    print(f"Nadano uprawnienia administratora kontu: {email}")
