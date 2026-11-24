import pytest

from app.config import settings
from app.core.timezone import LOCAL_TZ
from app.core.security import create_access_token
from app.models.user import User
from app.services import live_scan_service


KEY = {"X-Monitor-Key": "kunci-monitor-uji"}
TODAY = live_scan_service._now().date()


@pytest.fixture(autouse=True)
def fresh_feed(webhook_device, monkeypatch):
    monkeypatch.setattr(settings, "MONITOR_KEY", "kunci-monitor-uji")
    live_scan_service.reset()
    yield
    live_scan_service.reset()


def _feed(client, query=""):
    return client.get(f"/monitor/feed{query}", headers=KEY).json()


def _scan(client, pin, scan, verify=1):
    return client.post("/webhook/fingerspot", json={
        "type": "attlog", "cloud_id": "CLOUD_OK",
        "data": {"pin": pin, "scan": scan, "verify": verify, "status_scan": 0},
    })


def test_feed_shows_registered_and_unregistered_scans(client):
    client.post("/employees/", json={"pin": "501", "full_name": "Budi Monitor", "nik": "EMP-501", "is_active": True})

    assert _scan(client, "501", f"{TODAY} 06:58:01").status_code == 200
    assert _scan(client, "77777", f"{TODAY} 06:58:05").status_code == 200

    feed = _feed(client, "?cloud_id=CLOUD_OK")
    newest, older = feed["events"]
    assert newest["pin"] == "77777" and newest["registered"] is False
    assert older["name"] == "Budi Monitor" and older["nik"] == "EMP-501"
    assert older["verify_label"] == "Sidik jari"
    assert older["scan_time"].startswith(f"{TODAY}T06:58:01+07:00")
    # PIN tak terdaftar tampil di monitor tapi tetap tidak disimpan ke attendance_logs
    assert client.get("/attendance/?employee_pin=77777").json()["data"] == []


def test_feed_after_cursor_and_resend_dedup(client):
    client.post("/employees/", json={"pin": "502", "full_name": "Sari", "is_active": True})
    _scan(client, "502", f"{TODAY} 07:00:00")
    first = _feed(client)
    assert len(first["events"]) == 1

    _scan(client, "502", f"{TODAY} 07:00:00")      # kiriman ulang webhook
    assert _feed(client, f"?after={first['last_seq']}")["events"] == []

    _scan(client, "502", f"{TODAY} 07:02:00")      # tap lagi < 5 menit
    later = _feed(client, f"?after={first['last_seq']}")["events"]
    assert len(later) == 1 and later[0]["repeat"] is True


def test_feed_filters_by_device(client):
    _scan(client, "1", f"{TODAY} 07:00:00")
    assert len(_feed(client, "?cloud_id=CLOUD_OK")["events"]) == 1
    assert _feed(client, "?cloud_id=LAIN")["events"] == []


def test_feed_seeds_from_realtime_logs_after_restart(client):
    client.post("/employees/", json={"pin": "503", "full_name": "Andi", "is_active": True})
    from datetime import datetime
    now = datetime.now(LOCAL_TZ).replace(microsecond=0, tzinfo=None)
    _scan(client, "503", now.strftime("%Y-%m-%d %H:%M:%S"))
    live_scan_service.reset()                         # seperti proses baru
    events = _feed(client)["events"]
    assert [e["name"] for e in events] == ["Andi"]


def test_feed_requires_login_or_key(client, db_session):
    assert client.get("/monitor/feed").status_code == 401
    assert client.get("/monitor/feed", headers={"Authorization": "Bearer palsu"}).status_code == 401

    db_session.add(User(username="layar1", password_hash="x", full_name="Layar 1", role="view-only", is_active=True))
    db_session.commit()
    token = create_access_token({"sub": "layar1"})
    assert client.get("/monitor/feed", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    assert client.get("/monitor/feed?key=salah").status_code == 401
    assert client.get("/monitor/feed?key=kunci-monitor-uji").status_code == 200
    assert client.get("/monitor/devices", headers={"X-Monitor-Key": "kunci-monitor-uji"}).json()[0]["cloud_id"] == "CLOUD_OK"
    assert client.get("/monitor").status_code == 200


def test_feed_only_today(client):
    from datetime import timedelta
    yesterday = TODAY - timedelta(days=1)
    _scan(client, "1", f"{yesterday} 23:50:00")      # termasuk kiriman antrian yang terlambat
    _scan(client, "2", f"{TODAY} 00:05:00")
    feed = _feed(client)
    assert [e["pin"] for e in feed["events"]] == ["2"]
    assert feed["today"]["scans"] == 1 and feed["date"] == TODAY.isoformat()


def test_monitor_role_only_reaches_monitor(client, db_session):
    from app.dependencies import get_current_user
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    db_session.add(User(username="layar1", password_hash="x", full_name="Layar Lobi", role="monitor", is_active=True))
    db_session.commit()
    auth = {"Authorization": f"Bearer {create_access_token({'sub': 'layar1'})}"}
    assert client.get("/monitor/feed", headers=auth).status_code == 200
    assert client.get("/auth/me", headers=auth).json()["role"] == "monitor"
    assert client.get("/employees/", headers=auth).status_code == 403
    assert client.get("/attendance/", headers=auth).status_code == 403
