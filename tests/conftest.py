import pytest

from app import app as flask_app, db, User, Document

VALID_PASSWORD = "TestPass1!"


def _create_user(email: str, password: str, *, is_admin: bool = False) -> User:
    user = User(email=email, is_admin=is_admin)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def app():
    flask_app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret-key",
        }
    )

    with flask_app.app_context():
        db.engine.dispose()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def test_user(app):
    return _create_user("test@example.com", VALID_PASSWORD, is_admin=False)


@pytest.fixture
def admin_user(app):
    return _create_user("admin@example.com", VALID_PASSWORD, is_admin=True)


@pytest.fixture
def foreign_document(app):
    owner = _create_user("other@example.com", VALID_PASSWORD, is_admin=False)
    document = Document(
        title="foreign_doc.txt",
        processed_text="Tresc obcego dokumentu.",
        user_id=owner.id,
    )
    db.session.add(document)
    db.session.commit()
    return document


@pytest.fixture
def logged_in_client(client, test_user):
    client.post(
        "/login",
        data={"email": test_user.email, "password": VALID_PASSWORD},
    )
    return client
