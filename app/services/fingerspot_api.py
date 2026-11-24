import secrets
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.trans_log import FingerspotTransLog

BASE_API_URL = settings.FINGERSPOT_API_URL.rstrip("/")
REQUEST_TIMEOUT = 30
MAX_TRANS_ID = 2147483647


def get_auth_headers() -> dict:
    if not settings.FINGERSPOT_API_KEY:
        raise ValueError("FINGERSPOT_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {settings.FINGERSPOT_API_KEY}",
        "Content-Type": "application/json"
    }


def new_trans_id(db: Session) -> str:
    """trans_id angka 32-bit. fingerspot.io memaksa trans_id menjadi integer sebelum dikirim balik lewat
    webhook: UUID '386a...' kembali sebagai 386 dan 'f97...' sebagai 0, sehingga callback tidak bisa dicocokkan."""
    while True:
        trans_id = str(secrets.randbelow(MAX_TRANS_ID - 1_000_000) + 1_000_000)
        if not db.query(FingerspotTransLog.trans_id).filter(FingerspotTransLog.trans_id == trans_id).first():
            return trans_id


def _short_error(response: httpx.Response) -> str:
    text = response.text or ""
    if "<!doctype" in text.lower() or "<html" in text.lower():
        return f"fingerspot.io membalas halaman HTML (HTTP {response.status_code})"
    return f"HTTP {response.status_code}: {text[:200]}"


async def _send_command(db: Session, action: str, cloud_id: str, body_extra: dict, log_payload: dict = None) -> dict:
    """Catat transaksi, kirim perintah, lalu kembalikan konfirmasi API. Hasil dari mesin datang lewat webhook.
    log_payload hanya berisi data ringan: template sidik jari tidak disimpan di log transaksi."""
    if not cloud_id:
        raise ValueError("cloud_id is required")

    trans_id = new_trans_id(db)
    trans = FingerspotTransLog(trans_id=trans_id, cloud_id=cloud_id, action_type=action, request_payload=log_payload)
    db.add(trans)
    db.commit()

    body = {"trans_id": trans_id, "cloud_id": cloud_id, **body_extra}
    error = None
    result = {}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(f"{BASE_API_URL}/{action}", json=body, headers=get_auth_headers())
        if response.status_code >= 400:
            error = _short_error(response)
        else:
            try:
                result = response.json()
            except ValueError:
                error = _short_error(response)
            else:
                if not isinstance(result, dict) or result.get("success") is False or result.get("status") is False:
                    error = f"Perintah ditolak fingerspot.io: {str(result)[:200]}"
    except httpx.HTTPError as e:
        error = f"Tidak bisa menghubungi fingerspot.io: {e}"

    if error:
        trans.status = 'FAILED'
        trans.request_payload = {**(log_payload or {}), "error": error}
        db.commit()
        raise Exception(error)

    return {**result, "trans_id": trans_id}


async def trigger_get_all_pin(db: Session, cloud_id: str) -> dict:
    return await _send_command(db, "get_all_pin", cloud_id, {})


async def trigger_get_userinfo(db: Session, cloud_id: str, pin: str) -> dict:
    return await _send_command(db, "get_userinfo", cloud_id, {"pin": pin}, {"pin": pin})


async def get_device_info(db: Session, cloud_id: str) -> dict:
    if not cloud_id:
        raise ValueError("cloud_id is required")

    url = f"{BASE_API_URL}/get_device"
    trans_id = new_trans_id(db)

    body = {
        "cloud_id": cloud_id,
        "trans_id": trans_id
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(url, json=body, headers=get_auth_headers())
        if response.status_code >= 400:
            raise Exception(f"API Error {response.status_code}: {response.text}")

        return response.json()


async def set_device_time(db: Session, cloud_id: str, timezone: Optional[str] = None) -> dict:
    timezone = timezone or settings.TIMEZONE
    return await _send_command(db, "set_time", cloud_id, {"timezone": timezone}, {"timezone": timezone})


async def restart_device(db: Session, cloud_id: str) -> dict:
    return await _send_command(db, "restart_device", cloud_id, {})


async def pull_attendance_log(db: Session, cloud_id: str, start_date: str, end_date: str) -> dict:
    if not cloud_id:
        raise ValueError("cloud_id is required")

    url = f"{BASE_API_URL}/get_attlog"
    trans_id = new_trans_id(db)

    body = {
        "cloud_id": cloud_id,
        "trans_id": trans_id,
        "start_date": start_date,
        "end_date": end_date
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(url, json=body, headers=get_auth_headers())
        if response.status_code >= 400:
            raise Exception(f"API Error {response.status_code}: {response.text}")

        return response.json()


async def trigger_set_userinfo(db: Session, cloud_id: str, pin: str, name: str, rfid: str = "", template: str = "",
                               privilege: str = "1") -> dict:
    """Semua isian dikirim: tanpa privilege/password/rfid fingerspot.io menjawab ERR_02 walau dokumentasinya
    hanya mewajibkan pin. Password dan kartu di dalam template diutamakan mesin daripada isian ini."""
    data = {"pin": pin, "name": name or f"User {pin}", "privilege": privilege or "1",
            "password": "", "rfid": rfid or "", "template": template or ""}
    return await _send_command(db, "set_userinfo", cloud_id, {"data": data}, {"pin": pin, "name": data["name"]})


async def trigger_delete_userinfo(db: Session, cloud_id: str, pin: str) -> dict:
    return await _send_command(db, "delete_userinfo", cloud_id, {"pin": pin}, {"pin": pin})
