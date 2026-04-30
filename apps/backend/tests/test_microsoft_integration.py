from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import MicrosoftConnection, MicrosoftDataSource, MicrosoftOAuthState, Tenant, User
from app.modules.microsoft import service
from app.utils import encryption


def test_encrypt_decrypt_round_trip(monkeypatch) -> None:
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    encryption._fernet.cache_clear()

    encrypted = encryption.encrypt("secret-token")

    assert encrypted != "secret-token"
    assert encryption.decrypt(encrypted) == "secret-token"


def test_oauth_callback_creates_encrypted_connection(monkeypatch) -> None:
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    encryption._fernet.cache_clear()
    for db in db_session():
        tenant, user = seed_tenant_user(db)
        state = MicrosoftOAuthState(
            state="state-1",
            tenant_id=tenant.id,
            user_id=user.id,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
            used=False,
        )
        db.add(state)
        db.commit()

        monkeypatch.setattr(
            service,
            "_token_post",
            lambda tenant_id, data: {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
                "scope": "Files.Read User.Read offline_access",
                "id_token": make_id_token({"tid": "ms-tenant"}),
            },
        )
        monkeypatch.setattr(
            service,
            "_graph_json",
            lambda method, path, token: {
                "id": "ms-user",
                "displayName": "Ops Lead",
                "mail": "ops@example.com",
            },
        )

        connection = service.handle_callback(db, "auth-code", "state-1")

        assert connection.microsoft_user_id == "ms-user"
        assert connection.microsoft_tenant_id == "ms-tenant"
        assert connection.access_token != "access-token"
        assert encryption.decrypt(connection.access_token) == "access-token"
        assert encryption.decrypt(connection.refresh_token) == "refresh-token"
        assert db.get(MicrosoftOAuthState, state.id).used is True


def test_refresh_access_token_updates_tokens(monkeypatch) -> None:
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    encryption._fernet.cache_clear()
    for db in db_session():
        tenant, _ = seed_tenant_user(db)
        connection = make_connection(tenant.id)
        db.add(connection)
        db.commit()
        monkeypatch.setattr(
            service,
            "_token_post",
            lambda tenant_id, data: {
                "access_token": "fresh-access",
                "refresh_token": "fresh-refresh",
                "expires_in": 7200,
                "scope": "Files.Read User.Read",
            },
        )

        refreshed = service.refresh_access_token(db, connection)

        assert refreshed.is_active is True
        assert refreshed.auth_error is None
        assert encryption.decrypt(refreshed.access_token) == "fresh-access"
        assert refreshed.last_token_refresh_at is not None


def test_refresh_access_token_keeps_connection_active_on_transient_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    encryption._fernet.cache_clear()
    for db in db_session():
        tenant, _ = seed_tenant_user(db)
        connection = make_connection(tenant.id)
        db.add(connection)
        db.commit()
        monkeypatch.setattr(
            service,
            "_token_post",
            lambda tenant_id, data: (_ for _ in ()).throw(OSError("temporary DNS failure")),
        )

        refreshed = service.refresh_access_token(db, connection)

        assert refreshed.is_active is True
        assert "temporary DNS failure" in refreshed.auth_error


def test_download_file_retries_after_unauthorized(monkeypatch) -> None:
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    encryption._fernet.cache_clear()
    for db in db_session():
        tenant, _ = seed_tenant_user(db)
        connection = make_connection(tenant.id, expires_at=datetime.now(UTC) + timedelta(hours=1))
        db.add(connection)
        db.commit()
        responses = [
            httpx.Response(401),
            httpx.Response(200, content=b"shipment_id\nA-1\n"),
        ]
        monkeypatch.setattr(service, "_graph_response", lambda *args, **kwargs: responses.pop(0))
        monkeypatch.setattr(
            service,
            "_token_post",
            lambda tenant_id, data: {"access_token": "new-access", "expires_in": 3600, "scope": ""},
        )

        content = service.download_file(db, connection, "drive", "item")

        assert content == b"shipment_id\nA-1\n"
        assert encryption.decrypt(connection.access_token) == "new-access"


def test_list_drive_files_finds_stock_snapshot_via_root_search(monkeypatch) -> None:
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    encryption._fernet.cache_clear()
    for db in db_session():
        tenant, _ = seed_tenant_user(db)
        connection = make_connection(tenant.id, expires_at=datetime.now(UTC) + timedelta(hours=1))
        db.add(connection)
        db.commit()
        calls: list[str] = []

        def fake_graph_json(method: str, path: str, token: str) -> dict:
            calls.append(path)
            if "stock_snapshot" in path:
                return {
                    "value": [
                        {
                            "id": "item-1",
                            "name": "stock_snapshot.xlsx",
                            "size": 2048,
                            "lastModifiedDateTime": "2026-04-28T10:00:00Z",
                            "webUrl": "https://onedrive.example/stock_snapshot.xlsx",
                            "file": {"mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                            "parentReference": {"driveId": "drive-1"},
                        }
                    ]
                }
            return {"value": []}

        monkeypatch.setattr(service, "_graph_json", fake_graph_json)

        files = service.list_drive_files(db, connection)

        assert files[0]["name"] == "stock_snapshot.xlsx"
        assert any("/me/drive/root/search" in path for path in calls)


def test_microsoft_sync_task_continues_after_source_failure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    encryption._fernet.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with TestingSessionLocal() as db:
            tenant, _ = seed_tenant_user(db)
            connection = make_connection(tenant.id)
            db.add(connection)
            db.flush()
            db.add_all(
                [
                    MicrosoftDataSource(
                        tenant_id=tenant.id,
                        microsoft_connection_id=connection.id,
                        drive_id="drive",
                        item_id="ok",
                        file_type="shipment",
                        sync_status="idle",
                        is_active=True,
                    ),
                    MicrosoftDataSource(
                        tenant_id=tenant.id,
                        microsoft_connection_id=connection.id,
                        drive_id="drive",
                        item_id="bad",
                        file_type="shipment",
                        sync_status="idle",
                        is_active=True,
                    ),
                ]
            )
            db.commit()

        from app.workers.tasks import microsoft_sync

        monkeypatch.setattr(microsoft_sync, "SessionLocal", TestingSessionLocal)

        def fake_sync(db: Session, source: MicrosoftDataSource) -> dict:
            if source.item_id == "bad":
                raise RuntimeError("boom")
            source.sync_status = "success"
            db.commit()
            return {"status": "success"}

        monkeypatch.setattr(microsoft_sync, "sync_microsoft_data_source", fake_sync)

        results = microsoft_sync.sync_all_microsoft_sources()

        assert [item["status"] for item in results] == ["success", "error"]
    finally:
        Base.metadata.drop_all(bind=engine)


def make_id_token(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{body}.sig"


def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with TestingSessionLocal() as db:
            yield db
    finally:
        Base.metadata.drop_all(bind=engine)


def seed_tenant_user(db: Session) -> tuple[Tenant, User]:
    tenant = Tenant(name="Tenant A", slug=f"tenant-{uuid.uuid4().hex[:6]}")
    user = User(
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Ops User",
        password_hash="hashed",
        is_active=True,
    )
    db.add_all([tenant, user])
    db.commit()
    return tenant, user


def make_connection(
    tenant_id: int,
    expires_at: datetime | None = None,
) -> MicrosoftConnection:
    return MicrosoftConnection(
        tenant_id=tenant_id,
        microsoft_user_id=f"ms-{uuid.uuid4()}",
        microsoft_tenant_id="common",
        display_name="Ops User",
        email="ops@example.com",
        access_token=encryption.encrypt("access-token"),
        refresh_token=encryption.encrypt("refresh-token"),
        token_expires_at=expires_at or datetime.now(UTC) - timedelta(minutes=1),
        scope="Files.Read User.Read",
        connected_at=datetime.now(UTC),
        is_active=True,
    )
