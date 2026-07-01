"""Punkt wejścia dla serwera produkcyjnego (Gunicorn)."""
import os

from app import app, db, migrate_legacy_document_titles

with app.app_context():
    upload_folder = os.path.join(app.root_path, app.config.get("UPLOAD_FOLDER", "static/uploads"))
    os.makedirs(upload_folder, exist_ok=True)
    db.create_all()
    migrate_legacy_document_titles()


if __name__ == "__main__":
    app.run()
