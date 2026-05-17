import json
from pathlib import Path


def _auth_payload(access="access-token", refresh="refresh-token"):
    return {
        "version": 1,
        "providers": {
            "openai-codex": {
                "tokens": {
                    "access_token": access,
                    "refresh_token": refresh,
                },
                "last_refresh": "2026-01-01T00:00:00Z",
                "auth_mode": "chatgpt",
            }
        },
    }


def test_shared_codex_auth_seeds_from_profile_root(monkeypatch, tmp_path):
    root = tmp_path / "hermes-root"
    profile = root / "profiles" / "suya"
    profile.mkdir(parents=True)
    shared = root / "shared" / "codex" / "auth.json"
    (root / "auth.json").write_text(
        json.dumps(_auth_payload("root-access", "root-refresh")),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(profile))
    monkeypatch.setenv("HERMES_CODEX_SHARED_AUTH_PATH", str(shared))

    from hermes_cli import auth

    data = auth._read_codex_tokens()

    assert data["tokens"]["access_token"] == "root-access"
    assert shared.exists()
    saved = json.loads(shared.read_text(encoding="utf-8"))
    assert saved["providers"]["openai-codex"]["tokens"]["refresh_token"] == "root-refresh"


def test_codex_refresh_updates_shared_canonical_store(monkeypatch, tmp_path):
    home = tmp_path / "profile"
    home.mkdir()
    shared = tmp_path / "shared" / "codex" / "auth.json"
    shared.parent.mkdir(parents=True)
    shared.write_text(
        json.dumps(_auth_payload("old-access", "old-refresh")),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_CODEX_SHARED_AUTH_PATH", str(shared))

    from hermes_cli import auth

    def fake_refresh(access_token, refresh_token, *, timeout_seconds=20.0):
        assert access_token == "old-access"
        assert refresh_token == "old-refresh"
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "last_refresh": "2026-01-02T00:00:00Z",
        }

    monkeypatch.setattr(auth, "refresh_codex_oauth_pure", fake_refresh)

    creds = auth.resolve_codex_runtime_credentials(force_refresh=True)

    assert creds["api_key"] == "new-access"
    saved = json.loads(shared.read_text(encoding="utf-8"))
    tokens = saved["providers"]["openai-codex"]["tokens"]
    assert tokens == {"access_token": "new-access", "refresh_token": "new-refresh"}


def test_auxiliary_codex_reader_uses_runtime_resolver_before_pool(monkeypatch, tmp_path):
    home = tmp_path / "profile"
    home.mkdir()
    shared = tmp_path / "shared" / "codex" / "auth.json"
    shared.parent.mkdir(parents=True)
    shared.write_text(
        json.dumps(_auth_payload("shared-access", "shared-refresh")),
        encoding="utf-8",
    )
    # Profile-local pool contains a stale token; auxiliary must not prefer it.
    (home / "auth.json").write_text(
        json.dumps({
            "version": 1,
            "credential_pool": {
                "openai-codex": [{
                    "id": "stale",
                    "label": "stale",
                    "auth_type": "oauth",
                    "priority": 0,
                    "source": "device_code",
                    "access_token": "stale-pool-access",
                    "refresh_token": "stale-pool-refresh",
                }]
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_CODEX_SHARED_AUTH_PATH", str(shared))

    from agent import auxiliary_client

    assert auxiliary_client._read_codex_access_token() == "shared-access"
