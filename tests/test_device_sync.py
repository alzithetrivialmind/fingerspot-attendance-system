"""Sinkron karyawan ke mesin: format perintah sesuai dokumentasi fingerspot.io, antrean, dan konfirmasi webhook."""
import asyncio

import httpx
import pytest

from app.models.device import Device
from app.models.employee import Employee
from app.models.employee_device_access import EmployeeDeviceAccess as EDA
from app.models.trans_log import FingerspotTransLog
from app.services import fingerspot_api, sync_engine


@pytest.fixture(autouse=True)
def clean_engine_state():
    sync_engine._last_sent.clear()
    sync_engine._backup_requested.clear()
    yield


@pytest.fixture
def device(db_session):
    d = Device(name="Mesin 01", cloud_id="CLOUD_OK", is_active=True)
    db_session.add(d)
    db_session.commit()
    return d


def _employee(db, pin="100", name="Budi", active=True, template=None):
    emp = Employee(pin=pin, full_name=name, is_active=active, fingerprint_template=template,
                   device_privilege="1" if template else None)
    db.add(emp)
    db.commit()
    return emp


def _row(db, pin, device, status):
    row = EDA(employee_pin=pin, device_id=device.id, sync_status=status)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def api_calls(monkeypatch):
    """Tangkap permintaan ke fingerspot.io tanpa jaringan."""
    calls = []
    reply = {"response": httpx.Response(200, json={"success": True, "trans_id": "1"})}

    def handler(request):
        import json
        calls.append((request.url.path, json.loads(request.content)))
        return reply["response"]

    real_client = httpx.AsyncClient
    monkeypatch.setattr(fingerspot_api.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(fingerspot_api.settings, "FINGERSPOT_API_KEY", "kunci-uji")
    calls_obj = calls
    return calls_obj, reply


@pytest.fixture
def sent(monkeypatch):
    """Tangkap perintah yang dikirim antrean."""
    log = []
    privileges = []
    monkeypatch.setattr(sync_engine, "_test_privileges", privileges, raising=False)

    async def fake_set(db, cloud_id, pin, name, rfid="", template="", privilege="1"):
        log.append(("set", pin, name, template))
        privileges.append(privilege)

    async def fake_del(db, cloud_id, pin):
        log.append(("del", pin))

    async def fake_get(db, cloud_id, pin):
        log.append(("get", pin))

    monkeypatch.setattr(sync_engine, "trigger_set_userinfo", fake_set)
    monkeypatch.setattr(sync_engine, "trigger_delete_userinfo", fake_del)
    monkeypatch.setattr(sync_engine, "trigger_get_userinfo", fake_get)
    return log


# --- Format perintah ---

def test_set_userinfo_body_follows_docs(db_session, device, api_calls):
    calls, _ = api_calls
    asyncio.run(fingerspot_api.trigger_set_userinfo(db_session, "CLOUD_OK", "100", "Budi", template="TPL"))
    path, body = calls[0]
    assert path.endswith("/set_userinfo")
    # Semua isian wajib ada: tanpa ini fingerspot.io menjawab ERR_02
    assert body["data"] == {"pin": "100", "name": "Budi", "privilege": "1", "password": "", "rfid": "", "template": "TPL"}
    # trans_id harus angka: fingerspot.io memaksanya menjadi integer 32-bit
    assert body["trans_id"].isdigit() and int(body["trans_id"]) <= 2147483647
    # Template tidak ikut tersimpan di log transaksi
    trans = db_session.query(FingerspotTransLog).filter_by(trans_id=body["trans_id"]).one()
    assert "template" not in trans.request_payload


def test_delete_uses_delete_userinfo_endpoint(db_session, device, api_calls):
    calls, _ = api_calls
    asyncio.run(fingerspot_api.trigger_delete_userinfo(db_session, "CLOUD_OK", "100"))
    path, body = calls[0]
    assert path.endswith("/delete_userinfo")
    assert body["pin"] == "100"


def test_rejected_or_html_reply_is_error(db_session, device, api_calls):
    _, reply = api_calls
    reply["response"] = httpx.Response(200, json={"success": False})
    with pytest.raises(Exception):
        asyncio.run(fingerspot_api.trigger_get_userinfo(db_session, "CLOUD_OK", "100"))
    reply["response"] = httpx.Response(404, text="<!DOCTYPE html><html></html>")
    with pytest.raises(Exception, match="HTML"):
        asyncio.run(fingerspot_api.trigger_get_userinfo(db_session, "CLOUD_OK", "100"))
    statuses = {t.status for t in db_session.query(FingerspotTransLog).all()}
    assert statuses == {"FAILED"}


# --- Antrean ---

def test_remove_waits_for_template_then_deletes(db_session, device, sent):
    _employee(db_session, active=False)
    row = _row(db_session, "100", device, "PENDING_REMOVE")

    asyncio.run(sync_engine.process_task(db_session, row, device))
    assert sent == [("get", "100")]

    # Template tiba lewat webhook: perintah hapus baru dikirim
    emp = db_session.query(Employee).filter_by(pin="100").one()
    emp.fingerprint_template, emp.device_privilege = "TPL", "1"
    db_session.commit()
    asyncio.run(sync_engine.process_task(db_session, row, device))
    assert sent[-1] == ("del", "100")


def test_template_without_privilege_is_fetched_first_and_admin_is_kept(db_session, device, sent, monkeypatch):
    emp = _employee(db_session, template="TPL")
    emp.device_privilege = None
    db_session.commit()
    row = _row(db_session, "100", device, "PENDING_ADD")

    asyncio.run(sync_engine.process_task(db_session, row, device))
    assert sent == [("get", "100")]

    emp.device_privilege = "2"
    db_session.commit()
    asyncio.run(sync_engine.process_task(db_session, row, device))
    assert sent[-1] == ("set", "100", "Budi", "TPL")
    assert sync_engine._test_privileges == ["2"]


def test_remove_with_template_but_no_privilege_reply_still_deletes(db_session, device, sent, monkeypatch):
    emp = _employee(db_session, active=False, template="TPL")
    emp.device_privilege = None
    db_session.commit()
    row = _row(db_session, "100", device, "PENDING_REMOVE")
    asyncio.run(sync_engine.process_task(db_session, row, device))
    monkeypatch.setattr(sync_engine, "BACKUP_WAIT_SECONDS", -1)
    asyncio.run(sync_engine.process_task(db_session, row, device))
    assert sent[-1] == ("del", "100")


def test_remove_without_backup_fails_instead_of_deleting(db_session, device, sent, monkeypatch):
    _employee(db_session, active=False)
    row = _row(db_session, "100", device, "PENDING_REMOVE")
    asyncio.run(sync_engine.process_task(db_session, row, device))

    monkeypatch.setattr(sync_engine, "BACKUP_WAIT_SECONDS", -1)
    asyncio.run(sync_engine.process_task(db_session, row, device))
    assert ("del", "100") not in sent
    assert row.sync_status == "FAILED"
    assert row.failed_action == "PENDING_REMOVE"
    assert "sidik jari" in row.last_error
    assert "tidak ada di mesin" in row.last_error


def test_add_sends_stored_template(db_session, device, sent):
    _employee(db_session, template="TPL")
    row = _row(db_session, "100", device, "PENDING_ADD")
    asyncio.run(sync_engine.process_task(db_session, row, device))
    assert sent == [("set", "100", "Budi", "TPL")]


def test_unconfirmed_send_stops_after_limit(db_session, device, sent, monkeypatch):
    monkeypatch.setattr(sync_engine, "RESEND_INTERVAL_SECONDS", -1)
    _employee(db_session, template="TPL")
    row = _row(db_session, "100", device, "PENDING_ADD")
    for _ in range(sync_engine.MAX_SEND_ATTEMPTS + 1):
        asyncio.run(sync_engine.process_task(db_session, row, device))
    assert len(sent) == sync_engine.MAX_SEND_ATTEMPTS
    assert row.sync_status == "FAILED"
    assert row.failed_action == "PENDING_ADD"


def test_api_error_keeps_row_pending_for_retry(db_session, device, monkeypatch):
    async def boom(*a, **kw):
        raise Exception("mesin offline")

    monkeypatch.setattr(sync_engine, "trigger_set_userinfo", boom)
    _employee(db_session, template="TPL")
    row = _row(db_session, "100", device, "PENDING_ADD")
    asyncio.run(sync_engine.process_task(db_session, row, device))
    assert row.sync_status == "PENDING_ADD"
    assert row.attempts == 1
    assert row.last_error == "mesin offline"


def test_accepted_send_clears_old_error(db_session, device, sent):
    _employee(db_session, template="TPL")
    row = _row(db_session, "100", device, "PENDING_ADD")
    row.last_error = "ERR_02 lama"
    db_session.commit()
    asyncio.run(sync_engine.process_task(db_session, row, device))
    assert row.last_error is None


def test_unconfirmed_failure_reports_missing_confirmation(db_session, device, sent, monkeypatch):
    monkeypatch.setattr(sync_engine, "RESEND_INTERVAL_SECONDS", -1)
    _employee(db_session, template="TPL")
    row = _row(db_session, "100", device, "PENDING_ADD")
    row.last_error = "ERR_02 lama"
    db_session.commit()
    for _ in range(sync_engine.MAX_SEND_ATTEMPTS + 1):
        asyncio.run(sync_engine.process_task(db_session, row, device))
    assert row.sync_status == "FAILED"
    assert "konfirmasi" in row.last_error


# --- Webhook ---

def test_webhook_log_has_match_info_without_secret_values(client, db_session, device, caplog):
    _employee(db_session)
    _trans(db_session, "123460", "get_userinfo")
    with caplog.at_level("INFO", logger="app.routers.webhook"):
        client.post("/webhook/fingerspot", json={
            "type": "get_userinfo", "cloud_id": "CLOUD_OK", "trans_id": 123460,
            "data": {"pin": "100", "password": "RAHASIA", "template": "TEMPLATERAHASIA"}})
        client.post("/webhook/fingerspot", json={
            "type": "set_userinfo", "cloud_id": "CLOUD_OK", "trans_id": 999, "data": {"status": "1"}})
    text = caplog.text
    assert "type=get_userinfo trans_id=123460 cocok=True" in text
    assert "isian=password,pin,template" in text
    assert "type=set_userinfo trans_id=999 cocok=False status=1" in text
    assert "RAHASIA" not in text


def _trans(db, trans_id, action, pin="100"):
    db.add(FingerspotTransLog(trans_id=trans_id, cloud_id="CLOUD_OK", action_type=action, request_payload={"pin": pin}))
    db.commit()


def _hook(client, action, trans_id, status="1"):
    return client.post("/webhook/fingerspot", json={
        "type": action, "cloud_id": "CLOUD_OK", "trans_id": int(trans_id), "data": {"status": status}})


def test_machine_ok_status_confirms_add(client, db_session, device):
    """Jawaban asli Mesin Revo: {"status": "OK"}, bukan 1 seperti di dokumentasi."""
    _employee(db_session)
    _row(db_session, "100", device, "PENDING_ADD")
    _trans(db_session, "123461", "set_userinfo")
    _hook(client, "set_userinfo", "123461", status="OK")
    db_session.expire_all()
    assert db_session.query(EDA).one().sync_status == "SYNCED"
    assert db_session.query(FingerspotTransLog).filter_by(trans_id="123461").one().status == "SUCCESS"


def test_machine_ok_status_confirms_delete(client, db_session, device):
    _employee(db_session, active=False)
    _row(db_session, "100", device, "PENDING_REMOVE")
    _trans(db_session, "123462", "delete_userinfo")
    _hook(client, "delete_userinfo", "123462", status="OK")
    db_session.expire_all()
    assert db_session.query(EDA).count() == 0


def test_late_ok_confirms_row_already_failed(client, db_session, device):
    _employee(db_session)
    row = _row(db_session, "100", device, "FAILED")
    row.failed_action = "PENDING_ADD"
    db_session.commit()
    _trans(db_session, "123463", "set_userinfo")
    _hook(client, "set_userinfo", "123463", status="OK")
    db_session.expire_all()
    assert db_session.query(EDA).one().sync_status == "SYNCED"


def test_unknown_status_stays_pending(client, db_session, device):
    _employee(db_session)
    _row(db_session, "100", device, "PENDING_ADD")
    _trans(db_session, "123464", "set_userinfo")
    _hook(client, "set_userinfo", "123464", status="SOMETHING")
    db_session.expire_all()
    assert db_session.query(EDA).one().sync_status == "PENDING_ADD"
    assert db_session.query(FingerspotTransLog).filter_by(trans_id="123464").one().status == "PENDING"


def test_numeric_trans_id_callback_confirms_add(client, db_session, device):
    _employee(db_session)
    _row(db_session, "100", device, "PENDING_ADD")
    _trans(db_session, "123456", "set_userinfo")
    assert _hook(client, "set_userinfo", "123456").status_code == 200
    db_session.expire_all()
    assert db_session.query(EDA).one().sync_status == "SYNCED"


def test_delete_callback_removes_row(client, db_session, device):
    _employee(db_session, active=False)
    _row(db_session, "100", device, "PENDING_REMOVE")
    _trans(db_session, "123457", "delete_userinfo")
    _hook(client, "delete_userinfo", "123457")
    db_session.expire_all()
    assert db_session.query(EDA).count() == 0


def test_failed_callback_marks_failed(client, db_session, device):
    _employee(db_session, active=False)
    _row(db_session, "100", device, "PENDING_REMOVE")
    _trans(db_session, "123458", "delete_userinfo")
    _hook(client, "delete_userinfo", "123458", status="2")
    db_session.expire_all()
    row = db_session.query(EDA).one()
    assert row.sync_status == "FAILED"
    assert row.failed_action == "PENDING_REMOVE"


def test_stale_delete_callback_does_not_undo_reactivation(client, db_session, device):
    _employee(db_session)
    _row(db_session, "100", device, "PENDING_ADD")
    _trans(db_session, "123459", "delete_userinfo")
    _hook(client, "delete_userinfo", "123459")
    db_session.expire_all()
    assert db_session.query(EDA).one().sync_status == "PENDING_ADD"


def test_get_userinfo_stores_template_and_keeps_name(client, db_session, device):
    _employee(db_session, name="Budi Santoso")
    client.post("/webhook/fingerspot", json={
        "type": "get_userinfo", "cloud_id": "CLOUD_OK", "trans_id": 0,
        "data": {"pin": "100", "name": "Nama Mesin", "privilege": "2", "rfid": "CARD1", "template": "TPL"}})
    db_session.expire_all()
    emp = db_session.query(Employee).filter_by(pin="100").one()
    assert emp.full_name == "Budi Santoso"
    assert emp.fingerprint_template == "TPL"
    assert emp.rfid == "CARD1"
    assert emp.device_privilege == "2"
    assert db_session.query(EDA).one().sync_status == "SYNCED"


# --- Perubahan karyawan ---

def test_deactivate_queues_removal_without_existing_row(client, db_session, device):
    emp = _employee(db_session)
    res = client.put(f"/employees/{emp.id}", json={"is_active": False})
    assert res.status_code == 200
    row = db_session.query(EDA).one()
    assert (row.employee_pin, row.sync_status) == ("100", "PENDING_REMOVE")


def test_bulk_deactivate_and_reactivate(client, db_session, device):
    emp = _employee(db_session)
    client.post("/employees/bulk-status", json={"employee_ids": [emp.id], "is_active": False})
    db_session.expire_all()
    assert db_session.query(EDA).one().sync_status == "PENDING_REMOVE"

    client.post("/employees/bulk-status", json={"employee_ids": [emp.id], "is_active": True})
    db_session.expire_all()
    assert db_session.query(EDA).one().sync_status == "PENDING_ADD"


def test_bulk_status_unchanged_employee_is_not_queued(client, db_session, device):
    emp = _employee(db_session)
    client.post("/employees/bulk-status", json={"employee_ids": [emp.id], "is_active": True})
    assert db_session.query(EDA).count() == 0


def test_reactivate_via_form_returns_to_machine(client, db_session, device):
    emp = _employee(db_session, active=False)
    client.put(f"/employees/{emp.id}", json={"is_active": True, "device_access_ids": []})
    assert db_session.query(EDA).one().sync_status == "PENDING_ADD"


def test_rename_resends_only_to_known_machine(client, db_session, device):
    known = _employee(db_session, pin="100")
    _row(db_session, "100", device, "SYNCED")
    unknown = _employee(db_session, pin="200", name="Ani")

    client.put(f"/employees/{known.id}", json={"full_name": "Budi Baru"})
    client.put(f"/employees/{unknown.id}", json={"full_name": "Ani Baru"})
    db_session.expire_all()
    assert db_session.query(EDA).one().sync_status == "PENDING_ADD"


def test_pin_change_resends_and_keeps_old_pin_on_machine(client, db_session, device, sent):
    emp = _employee(db_session, template="TPL")
    _row(db_session, "100", device, "SYNCED")
    res = client.put(f"/employees/{emp.id}", json={"pin": "101"})
    assert res.status_code == 200
    db_session.expire_all()
    row = db_session.query(EDA).one()
    assert row.sync_status == "PENDING_ADD"
    # Tidak ada perintah hapus untuk PIN lama
    assert not any(c[0] == "del" for c in sent)


def test_saving_form_retries_failed_row(client, db_session, device):
    emp = _employee(db_session)
    row = _row(db_session, "100", device, "FAILED")
    row.failed_action, row.last_error = "PENDING_ADD", "x"
    db_session.commit()
    client.put(f"/employees/{emp.id}", json={"device_access_ids": [device.id]})
    db_session.expire_all()
    row = db_session.query(EDA).one()
    assert (row.sync_status, row.last_error) == ("PENDING_ADD", None)


def test_delete_employee_removes_pin_from_machine(client, db_session, device, monkeypatch):
    removed = []

    async def fake(pins, cloud_ids):
        removed.append((pins, cloud_ids))

    monkeypatch.setattr(sync_engine, "delete_pins_from_devices", fake)
    emp = _employee(db_session)
    assert client.delete(f"/employees/{emp.id}").status_code == 200
    assert removed == [(["100"], ["CLOUD_OK"])]


# --- Menu mesin ---

def test_employee_list_reports_template_without_exposing_it(client, db_session, device):
    _employee(db_session, pin="100", template="TEMPLATERAHASIA")
    _employee(db_session, pin="200", name="Ani")
    res = client.get("/employees/?limit=10")
    assert res.status_code == 200
    rows = {e["pin"]: e for e in res.json()["data"]}
    assert rows["100"]["has_device_template"] is True
    assert rows["200"]["has_device_template"] is False
    assert "TEMPLATERAHASIA" not in res.text


def test_push_only_queues_active_employees(client, db_session, device):
    active = _employee(db_session, pin="100")
    inactive = _employee(db_session, pin="200", active=False)
    res = client.post(f"/devices/{device.id}/push-employees", json={"employee_ids": [active.id, inactive.id]})
    assert res.status_code == 200
    assert res.json()["queued"] == 1
    assert [r.employee_pin for r in db_session.query(EDA).all()] == ["100"]


def test_summary_and_retry_failed(client, db_session, device):
    _employee(db_session, active=False)
    row = _row(db_session, "100", device, "FAILED")
    row.failed_action, row.last_error = "PENDING_REMOVE", "alasan"
    db_session.commit()

    summary = client.get("/devices/sync-summary").json()[str(device.id)]
    assert summary["failed"] == 1
    assert summary["failures"][0]["error"] == "alasan"

    assert client.post(f"/devices/{device.id}/retry-failed").json() == {"retried": 1}
    db_session.expire_all()
    assert db_session.query(EDA).one().sync_status == "PENDING_REMOVE"
