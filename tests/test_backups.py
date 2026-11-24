from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.core.timezone import LOCAL_TZ
from app.services import backup_service as bs


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "BACKUP_HOUR", 23)

    def fake_run(cmd, env=None):
        if cmd[0] == "pg_dump":
            open(cmd[cmd.index("--file") + 1], "wb").write(b"dump")
    monkeypatch.setattr(bs, "_run", fake_run)
    return tmp_path


def at(day, hour=23):
    return LOCAL_TZ.localize(datetime(2026, 10, day, hour, 5))


def test_scheduled_daily_weekly_monthly(backup_dir):
    assert bs.run_scheduled(at(19, hour=12)) == []          # belum jam 23
    made = bs.run_scheduled(at(19))                           # Senin
    assert [n.split("_")[1] for n in made] == ["harian", "mingguan", "bulanan"]
    assert bs.run_scheduled(at(19, hour=23)) == []            # hari yang sama tidak dobel
    made = bs.run_scheduled(at(20))                           # minggu & bulan sama
    assert [n.split("_")[1] for n in made] == ["harian"]
    made = bs.run_scheduled(at(26))                           # Senin minggu berikutnya
    assert [n.split("_")[1] for n in made] == ["harian", "mingguan"]


def test_retention_keeps_newest(backup_dir):
    start = at(1)
    for i in range(10):
        bs.create_backup("harian", start + timedelta(days=i))
    names = [f["name"] for f in bs.list_files("harian")]
    assert len(names) == 7 and names[0].endswith("20261010_230500.dump")
    assert all("2026100[1-3]" not in n for n in names)


def test_resolve_rejects_traversal(backup_dir):
    bs.create_backup("manual", at(5))
    name = bs.list_files("manual")[0]["name"]
    assert bs.resolve("manual", name).name == name
    for kind, bad in [("manual", "../../etc/passwd"), ("harian", name), ("x", name), ("manual", "attendance_manual_1.dump")]:
        with pytest.raises(bs.BackupError):
            bs.resolve(kind, bad)


def test_restore_requires_typed_confirmation_and_saves_current_state(client, backup_dir, monkeypatch):
    bs.create_backup("harian", at(5))
    name = bs.list_files("harian")[0]["name"]
    restored = []
    monkeypatch.setattr(bs, "restore_backup", lambda path: restored.append(path.name))

    res = client.post("/backups/restore", json={"kind": "harian", "name": name, "confirm": "salah"})
    assert res.status_code == 400 and restored == []

    res = client.post("/backups/restore", json={"kind": "harian", "name": name, "confirm": name})
    assert res.status_code == 200, res.text
    assert restored == [name]
    assert res.json()["safety_backup"] in [f["name"] for f in bs.list_files("sebelum-restore")]

    listing = client.get("/backups/").json()
    assert {g["kind"] for g in listing["groups"]} == set(bs.KINDS)
