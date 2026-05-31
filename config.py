import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'twoj-super-tajny-klucz-2024'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///fiszki.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # max 16MB
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx'}