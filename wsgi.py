"""Punkt wejscia dla serwera produkcyjnego (gunicorn).

Uruchamiane przez: gunicorn -c gunicorn.conf.py wsgi:app

W app.py tworzenie katalogu uploadow i tabel bazy (db.create_all) znajduje sie
w bloku `if __name__ == '__main__'`, ktory NIE wykonuje sie pod gunicornem.
Dlatego powtarzamy te inicjalizacje tutaj, aby aplikacja dzialala po wdrozeniu.
"""
import os

from app import app, db, migrate_legacy_document_titles

with app.app_context():
    upload_folder = os.path.join(app.root_path, app.config.get("UPLOAD_FOLDER", "static/uploads"))
    os.makedirs(upload_folder, exist_ok=True)
    db.create_all()
    migrate_legacy_document_titles()


if __name__ == "__main__":
    app.run()
