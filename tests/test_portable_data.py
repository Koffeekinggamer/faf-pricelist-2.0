from __future__ import annotations

from pathlib import Path

from backend.config import resolve_data_dir, resolve_db_path, resolve_secrets_path
from backend.login_session import login_secret


def test_portable_data_dir_keeps_tests_on_the_checkout(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("FAF_DATA_DIR", raising=False)
    monkeypatch.delenv("FAF_DB_PATH", raising=False)
    monkeypatch.delenv("FAF_SECRETS_PATH", raising=False)

    assert resolve_data_dir().name == "FAF-pricelist-2.0"
    assert resolve_db_path().name == "master_pricebook.db"


def test_portable_data_dir_follows_env(monkeypatch, tmp_path: Path):
    secrets = tmp_path / "secrets.toml"
    secrets.write_text("[auth]\nusername = \"Foothills\"\npassword = \"Amish\"\n")
    monkeypatch.setenv("FAF_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FAF_DB_PATH", raising=False)
    monkeypatch.delenv("FAF_SECRETS_PATH", raising=False)

    assert resolve_data_dir() == tmp_path
    assert resolve_db_path() == tmp_path / "master_pricebook.db"
    assert resolve_secrets_path() == secrets


def test_login_secret_is_stored_beside_portable_data(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("FAF_LOGIN_SECRET", raising=False)
    secret = login_secret(root=tmp_path)
    assert (tmp_path / ".login_secret").is_file()
    assert login_secret(root=tmp_path) == secret
