from test_api import authorization, request


def test_community_does_not_expose_license_activation():
    tokens = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": "community-owner@example.com", "password": "correct-horse-battery-staple"},
    ).json()
    headers = authorization(tokens)
    workspace_id = request("GET", "/api/v1/auth/me", headers=headers).json()["workspaces"][0]["workspace_id"]

    response = request("GET", f"/api/v1/workspaces/{workspace_id}/license", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "license_management_unavailable"
