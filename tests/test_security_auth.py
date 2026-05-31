from io import BytesIO

from app import User, db


def test_register_rejects_password_shorter_than_8_chars(client, app):
    response = client.post(
        "/register",
        data={
            "email": "shortpw@example.com",
            "password": "Ab1!",
            "password2": "Ab1!",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "8 znak" in response.get_data(as_text=True)

    with app.app_context():
        assert User.query.filter_by(email="shortpw@example.com").first() is None


def test_login_success(client, test_user):
    response = client.post(
        "/login",
        data={"email": test_user.email, "password": "TestPass1!"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/dashboard" in response.location


def test_login_rejects_invalid_credentials(client, test_user):
    response = client.post(
        "/login",
        data={"email": test_user.email, "password": "WrongPass9!"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Nieprawidłowy email lub hasło" in response.get_data(as_text=True)


def test_idor_foreign_note_redirects_to_dashboard(logged_in_client, foreign_document):
    response = logged_in_client.get(
        f"/note/{foreign_document.id}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/dashboard" in response.location

    follow_up = logged_in_client.get(response.location, follow_redirects=True)
    assert "Nie masz dostępu do tej notatki" in follow_up.get_data(as_text=True)


def test_non_admin_cannot_toggle_admin(logged_in_client, admin_user, app):
    response = logged_in_client.post(
        f"/admin/toggle_admin/{admin_user.id}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/dashboard" in response.location

    with app.app_context():
        assert User.query.get(admin_user.id).is_admin is True


def test_upload_rejects_file_larger_than_16mb(logged_in_client, app):
    # W test client same Content-Length nie wyzwala 413 — obniżamy limit,
    # żeby zweryfikować handler @app.errorhandler(413) bez 17 MB payloadu.
    app.config["MAX_CONTENT_LENGTH"] = 32
    response = logged_in_client.post(
        "/upload",
        data={"file": (BytesIO(b"x" * 64), "test.txt")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "16 MB" in response.get_data(as_text=True)
