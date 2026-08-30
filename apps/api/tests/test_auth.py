from test_api import authorization, register, request


def test_register_login_refresh_and_logout_flow():
    original = register()

    me = request("GET", "/api/v1/auth/me", headers=authorization(original))
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"
    assert me.json()["preferred_locale"] == "ru"
    assert len(me.json()["workspaces"]) == 1
    assert me.json()["workspaces"][0]["role"] == "owner"
    assert me.json()["workspaces"][0]["default_locale"] == "ru"

    login = request(
        "POST",
        "/api/v1/auth/login",
        json={"email": "OWNER@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200

    refreshed = request(
        "POST",
        "/api/v1/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != login.json()["refresh_token"]

    replay = request(
        "POST",
        "/api/v1/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )
    assert replay.status_code == 401

    logout = request(
        "POST",
        "/api/v1/auth/logout",
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert logout.status_code == 204

    after_logout = request(
        "POST",
        "/api/v1/auth/refresh",
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert after_logout.status_code == 401


def test_rejects_duplicate_email_and_wrong_password():
    register()
    duplicate = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "another-secure-password"},
    )
    assert duplicate.status_code == 409

    login = request(
        "POST",
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )
    assert login.status_code == 401


def test_registration_normalizes_locale_and_rejects_invalid_locale():
    registered = request(
        "POST",
        "/api/v1/auth/register",
        json={
            "email": "spanish@example.com",
            "password": "correct-horse-battery-staple",
            "preferred_locale": "es_mx",
        },
    )
    assert registered.status_code == 201
    me = request("GET", "/api/v1/auth/me", headers=authorization(registered.json()))
    assert me.json()["preferred_locale"] == "es-MX"
    assert me.json()["workspaces"][0]["default_locale"] == "es-MX"

    invalid = request(
        "POST",
        "/api/v1/auth/register",
        json={
            "email": "invalid-locale@example.com",
            "password": "correct-horse-battery-staple",
            "preferred_locale": "not a locale",
        },
    )
    assert invalid.status_code == 422
