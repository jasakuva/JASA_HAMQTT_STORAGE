import io
from types import SimpleNamespace

from hamqtt_store import web


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def authenticated_client(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "SessionLocal", FakeSession)
    monkeypatch.setattr(web, "get_user", lambda session: SimpleNamespace(id=7, username="admin", password_hash="hash", session_version=1))
    monkeypatch.setattr(web, "get_backup_config", lambda session: {"repository_subdirectory": "hamqtt"})
    monkeypatch.setattr(web, "list_jobs", list)
    monkeypatch.setattr(web, "maintenance_status", lambda: None)
    monkeypatch.setenv("BACKUP_REPOSITORY_PATH", str(tmp_path))
    app = web.create_app()
    app.config.update(TESTING=True)
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["session_version"] = 1
    return client


def test_backup_files_page_lists_downloadable_dumps(monkeypatch, tmp_path):
    dump_directory = tmp_path / "dumps"
    dump_directory.mkdir()
    dump = dump_directory / "hamqtt-store-20261016-120000.dump"
    dump.write_bytes(b"portable backup")
    client = authenticated_client(monkeypatch, tmp_path)

    response = client.get("/settings/backup-files")

    assert response.status_code == 200
    assert dump.name.encode() in response.data
    assert b"Download" in response.data


def test_backup_files_page_requires_authentication(monkeypatch):
    monkeypatch.setattr(web, "SessionLocal", FakeSession)
    monkeypatch.setattr(web, "get_user", lambda session: SimpleNamespace(id=7, session_version=1))
    app = web.create_app()
    app.config.update(TESTING=True)

    response = app.test_client().get("/settings/backup-files")

    assert response.status_code == 302
    assert "/login?next=" in response.headers["Location"]


def test_backup_file_download_returns_attachment(monkeypatch, tmp_path):
    dump_directory = tmp_path / "dumps"
    dump_directory.mkdir()
    dump = dump_directory / "hamqtt-store-20261016-120000.dump"
    dump.write_bytes(b"portable backup")
    client = authenticated_client(monkeypatch, tmp_path)

    response = client.get(f"/settings/backup-files/download/{dump.name}")

    assert response.status_code == 200
    assert response.data == b"portable backup"
    assert f"filename={dump.name}" in response.headers["Content-Disposition"]


def test_backup_file_download_rejects_non_dump_and_traversal(monkeypatch, tmp_path):
    (tmp_path / "secret.dump").write_bytes(b"secret")
    client = authenticated_client(monkeypatch, tmp_path)

    assert client.get("/settings/backup-files/download/not-a-dump.txt").status_code == 404
    assert client.get("/settings/backup-files/download/%2E%2E%2Fsecret.dump").status_code == 404


def test_backup_upload_requires_csrf_and_stages_file(monkeypatch, tmp_path):
    staged = []
    client = authenticated_client(monkeypatch, tmp_path)
    monkeypatch.setattr(web, "stage_upload", lambda file, **kwargs: staged.append((file.filename, kwargs)) or {"id": "a" * 32})
    with client.session_transaction() as session:
        session["csrf_token"] = "token"

    missing_csrf = client.post(
        "/settings/backup-files/upload",
        data={"backup_file": (io.BytesIO(b"dump"), "backup.dump")},
        content_type="multipart/form-data",
    )
    response = client.post(
        "/settings/backup-files/upload",
        data={"csrf_token": "token", "backup_file": (io.BytesIO(b"dump"), "backup.dump")},
        content_type="multipart/form-data",
    )

    assert missing_csrf.status_code == 400
    assert response.status_code == 302
    assert staged == [("backup.dump", {"uploader_id": 7, "uploader_name": "admin"})]


def test_recovery_confirmation_requires_phrase_and_password(monkeypatch, tmp_path):
    requested = []
    client = authenticated_client(monkeypatch, tmp_path)
    monkeypatch.setattr(web, "password_matches", lambda user, password: password == "secret")
    monkeypatch.setattr(web, "request_recovery", lambda job_id, **kwargs: requested.append((job_id, kwargs)) or {"id": job_id})
    with client.session_transaction() as session:
        session["csrf_token"] = "token"
    job_id = "b" * 32

    bad_phrase = client.post(
        f"/settings/backup-files/recover/{job_id}",
        data={"csrf_token": "token", "current_password": "secret", "confirmation": "RESTORE"},
    )
    bad_password = client.post(
        f"/settings/backup-files/recover/{job_id}",
        data={"csrf_token": "token", "current_password": "wrong", "confirmation": "RESTORE DATABASE"},
    )
    response = client.post(
        f"/settings/backup-files/recover/{job_id}",
        data={"csrf_token": "token", "current_password": "secret", "confirmation": "RESTORE DATABASE"},
    )

    assert "Type+RESTORE+DATABASE+exactly" in bad_phrase.headers["Location"]
    assert "Current+password+is+incorrect" in bad_password.headers["Location"]
    assert response.status_code == 302
    assert requested == [(job_id, {"confirmed_by": "admin"})]


def test_health_reports_maintenance_without_opening_database(monkeypatch):
    monkeypatch.setattr(
        web,
        "maintenance_status",
        lambda: {"job_id": "a" * 32, "state": "recovering", "message": "Restoring"},
    )
    monkeypatch.setattr(web.engine, "connect", lambda: (_ for _ in ()).throw(AssertionError("database accessed")))
    app = web.create_app()
    app.config.update(TESTING=True)

    response = app.test_client().get("/health")

    assert response.status_code == 503
    assert response.get_json()["status"] == "maintenance"