from app.models.user import User
from app.core.security import get_password_hash

def test_create_user_endpoint(client, db_session):
    # Setup a super admin token
    super_admin = User(
        username="superadmin_test",
        password_hash=get_password_hash("admin123"),
        role="super admin",
        is_active=True
    )
    db_session.add(super_admin)
    db_session.commit()

    # Login to get token
    login_res = client.post("/auth/login", data={"username": "superadmin_test", "password": "admin123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create new user
    res = client.post("/users/", json={
        "username": "operator_test",
        "full_name": "Tim Operator",
        "password": "passUji123",
        "role": "operator",
        "is_active": True
    }, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "operator_test"
    assert data["role"] == "operator"
    assert data["full_name"] == "Tim Operator"

    # Verify duplicate username rejected
    dup_res = client.post("/users/", json={
        "username": "operator_test",
        "password": "passUji123",
        "role": "operator"
    }, headers=headers)
    assert dup_res.status_code == 400

    # Verify short password (< 8 chars) rejected with 422
    short_pw_res = client.post("/users/", json={
        "username": "user_short",
        "password": "12",
        "role": "operator"
    }, headers=headers)
    assert short_pw_res.status_code == 422

    # Role di luar daftar ditolak
    bad_role = client.post("/users/", json={
        "username": "user_role",
        "password": "passUji123",
        "role": "pemilik"
    }, headers=headers)
    assert bad_role.status_code == 422
