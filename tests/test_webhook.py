import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def registered_device(webhook_device):
    return webhook_device


def test_webhook_idempotency(client):
    # 1. Register employee first
    client.post("/employees/", json={
        "pin": "12345",
        "full_name": "Karyawan Uji Webhook",
        "is_active": True
    })

    payload = {
        "type": "attlog",
        "cloud_id": "CLOUD_OK",
        "data": [
            {
                "pin": "12345",
                "scan": "2026-08-14 08:00:00",
                "verify": 1,
                "status_scan": 0,
                "sn": "FINGERSPOT_SN_1"
            }
        ]
    }
    
    # First request
    response = client.post("/webhook/fingerspot", json=payload)
    assert response.status_code == 200
    
    # Check attendance count
    res_att = client.get("/attendance/?employee_pin=12345")
    assert len(res_att.json()["data"]) == 1
    
    # Second request (Idempotency check)
    response2 = client.post("/webhook/fingerspot", json=payload)
    assert response2.status_code == 200
    
    # Check attendance count again (should still be 1)
    res_att2 = client.get("/attendance/?employee_pin=12345")
    assert len(res_att2.json()["data"]) == 1

    # 2. Test unregistered PIN is rejected/ignored
    unregistered_payload = {
        "type": "attlog",
        "cloud_id": "CLOUD_OK",
        "data": [
            {
                "pin": "999999",
                "scan": "2026-08-14 08:00:00",
                "verify": 1,
                "status_scan": 0,
                "sn": "FINGERSPOT_SN_1"
            }
        ]
    }
    client.post("/webhook/fingerspot", json=unregistered_payload)
    res_unreg = client.get("/attendance/?employee_pin=999999")
    assert len(res_unreg.json()["data"]) == 0


def _attlog(cloud_id=None):
    payload = {"type": "attlog", "data": {"pin": "12345", "scan": "2026-08-14 08:00:00", "verify": 1, "status_scan": 0}}
    if cloud_id:
        payload["cloud_id"] = cloud_id
    return payload


def test_webhook_rejects_unknown_or_missing_device(client):
    client.post("/employees/", json={"pin": "12345", "full_name": "Karyawan Uji", "is_active": True})
    assert client.post("/webhook/fingerspot", json=_attlog()).status_code == 403
    assert client.post("/webhook/fingerspot", json=_attlog("PALSU")).status_code == 403
    assert client.post("/webhook/fingerspot", json=["bukan", "dict"]).status_code == 403
    assert client.get("/attendance/?employee_pin=12345").json()["data"] == []
    assert client.post("/webhook/fingerspot", json=_attlog("CLOUD_OK")).status_code == 200
    assert len(client.get("/attendance/?employee_pin=12345").json()["data"]) == 1


def test_webhook_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_TOKEN", "rahasia-uji")
    assert client.post("/webhook/fingerspot", json=_attlog("CLOUD_OK")).status_code == 403
    assert client.post("/webhook/fingerspot?token=salah", json=_attlog("CLOUD_OK")).status_code == 403
    assert client.post("/webhook/fingerspot?token=rahasia-uji", json=_attlog("CLOUD_OK")).status_code == 200
