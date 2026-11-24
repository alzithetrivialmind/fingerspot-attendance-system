from app.core.security import get_password_hash, verify_password
from app.main import app
from app.dependencies import get_current_user
from app.models.activity_log import ActivityLog
from app.models.user import User


def test_user_changes_own_password(client, db_session):
    user = User(username="rina", password_hash=get_password_hash("lama12345"), role="view-only", is_active=True)
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user

    assert client.post("/auth/change-password", json={"current_password": "salah", "new_password": "baru12345"}).status_code == 400
    assert client.post("/auth/change-password", json={"current_password": "lama12345", "new_password": "123"}).status_code == 422
    assert client.post("/auth/change-password", json={"current_password": "lama12345", "new_password": "lama12345"}).status_code == 400

    res = client.post("/auth/change-password", json={"current_password": "lama12345", "new_password": "baru12345"})
    assert res.status_code == 200
    db_session.refresh(user)
    assert verify_password("baru12345", user.password_hash)
    actions = [l.action for l in db_session.query(ActivityLog).filter_by(username="rina").all()]
    assert "CHANGE_PASSWORD" in actions and "CHANGE_PASSWORD_FAILED" in actions
