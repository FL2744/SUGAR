from __future__ import annotations

import sys
import types

import pytest

from sugar_core import credential_vault


class FakeVault:
    __module__ = "keyring.backends.Windows"
    priority = 5

    def __init__(self):
        self.values = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        self.values[(service, username)] = value

    def delete_password(self, service, username):
        del self.values[(service, username)]


def fake_keyring(monkeypatch, backend=None):
    selected = backend or FakeVault()
    module = types.ModuleType("keyring")
    module.get_keyring = lambda: selected
    module.get_password = getattr(selected, "get_password", lambda *_args: None)
    module.set_password = getattr(selected, "set_password", lambda *_args: None)
    module.delete_password = getattr(selected, "delete_password", lambda *_args: None)
    monkeypatch.setitem(sys.modules, "keyring", module)
    return selected


def test_credentials_round_trip_using_only_os_backend(monkeypatch):
    backend = fake_keyring(monkeypatch)

    saved = credential_vault.save_credentials({"llm_api_key": "test-secret", "x_bearer_token": "x-secret"})
    assert saved == {"saved": ["llm_api_key", "x_bearer_token"], "count": 2}
    assert credential_vault.load_credentials() == {"llm_api_key": "test-secret", "x_bearer_token": "x-secret"}
    assert credential_vault.vault_status() == {
        "available": True,
        "backend": "FakeVault",
        "stored": {name: name in {"llm_api_key", "x_bearer_token"} for name in credential_vault.SECRET_NAMES},
    }
    assert credential_vault.delete_credentials(["x_bearer_token"]) == {"deleted": ["x_bearer_token"], "count": 1}
    assert credential_vault.load_credentials() == {"llm_api_key": "test-secret"}
    assert backend.values


def test_plaintext_and_unknown_keyrings_are_rejected(monkeypatch):
    backend = type("FileKeyring", (), {"priority": 1, "__module__": "keyrings.alt.file"})()
    fake_keyring(monkeypatch, backend)

    status = credential_vault.vault_status()
    assert status["available"] is False
    assert "memory for this session only" in status["message"]
    with pytest.raises(RuntimeError, match="operating-system credential vault"):
        credential_vault.save_credentials({"llm_api_key": "test-secret"})


def test_vault_rejects_unknown_fields_and_invalid_values(monkeypatch):
    fake_keyring(monkeypatch)
    with pytest.raises(ValueError, match="Unsupported credential field"):
        credential_vault.save_credentials({"private_note": "not a credential"})
    with pytest.raises(ValueError, match="no longer than"):
        credential_vault.save_credentials({"llm_api_key": "x" * 32_769})
    with pytest.raises(ValueError, match="Unsupported credential field"):
        credential_vault.delete_credentials(["private_note"])


def test_missing_keyring_reports_session_only_without_creating_a_file(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, "keyring", raising=False)
    monkeypatch.syspath_prepend(str(tmp_path))
    # Import is intentionally lazy; simulate a machine without the optional module.
    import builtins

    original_import = builtins.__import__

    def reject_keyring(name, *args, **kwargs):
        if name == "keyring":
            raise ImportError("disabled for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_keyring)
    status = credential_vault.vault_status()
    assert status["available"] is False
    assert "not installed" in status["message"]
    assert list(tmp_path.iterdir()) == []
