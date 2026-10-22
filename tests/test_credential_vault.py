from __future__ import annotations

import builtins

import pytest

from sugar_core import credential_vault
from sugar_core.credential_store import CredentialError, CredentialStore


@pytest.fixture
def forbid_keychain(monkeypatch):
    """Detect even attempted keyring imports, including exceptions swallowed by fallback code."""
    attempts = []
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'keyring', 'keyrings'}:
            attempts.append(name)
            raise AssertionError('OS credential access is forbidden')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    yield
    assert attempts == []


def test_legacy_vault_operations_never_access_keychain(forbid_keychain):
    assert credential_vault.vault_status()['available'] is False
    assert credential_vault.load_credentials() == {}
    with pytest.raises(RuntimeError, match='removed'):
        credential_vault.save_credentials({'llm_api_key': 'test-only-secret'})
    with pytest.raises(RuntimeError, match='removed'):
        credential_vault.delete_credentials()


@pytest.mark.parametrize('backend', ['auto', 'memory', 'file'])
def test_all_credential_paths_avoid_keychain(tmp_path, monkeypatch, forbid_keychain, backend):
    monkeypatch.delenv('SUGAR_X_BEARER_TOKEN', raising=False)
    store = CredentialStore(tmp_path, backend=backend)
    for ref in ['provider:test', 'platform:x_bearer_token', 'platform:llm_api_key']:
        assert store.get(ref) == ''
        store.set(ref, 'test-only-secret')
        assert store.get(ref) == 'test-only-secret'
        assert store.has(ref)
        assert store.source_of(ref) == ('file' if backend == 'file' else 'memory')
        assert ref in store.refs()
        store.delete(ref)
        assert not store.has(ref)
    store.platform_secrets()


def test_default_is_session_only_and_ignores_existing_files(tmp_path, monkeypatch, forbid_keychain):
    monkeypatch.delenv('SUGAR_CREDENTIAL_BACKEND', raising=False)
    explicit_file = CredentialStore(tmp_path, backend='file')
    explicit_file.set('provider:old', 'test-only-old-secret')
    before = (tmp_path / 'credentials.json').read_bytes()
    store = CredentialStore(tmp_path)
    assert store.backend == 'memory'
    assert store.get('provider:old') == ''
    store.set('provider:new', 'test-only-new-secret')
    assert CredentialStore(tmp_path).get('provider:new') == ''
    assert (tmp_path / 'credentials.json').read_bytes() == before


def test_explicit_keyring_request_is_rejected(tmp_path, forbid_keychain):
    with pytest.raises(CredentialError, match='removed'):
        CredentialStore(tmp_path, backend='keyring')
