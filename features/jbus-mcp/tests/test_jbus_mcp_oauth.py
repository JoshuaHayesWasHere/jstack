"""The authorization server lets in one client, only with a sign-in code made on the machine,
only with PKCE, and rotates refresh tokens, revoking a family whose spent token comes back."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from jbus_mcp import Refused, oauth

ORIGIN = "https://jbus.example.test"
VERIFIER = "v" * 50


def challenge(verifier=VERIFIER):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 3, 22, 0, tzinfo=UTC)

    def __call__(self):
        return self.now

    def later(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return oauth.Store(tmp_path / oauth.FILE, ORIGIN, clock)


def query(client_id, **over):
    asked = {
        "client_id": client_id,
        "redirect_uri": oauth.CALLBACK,
        "response_type": "code",
        "state": "s-1",
        "code_challenge": challenge(),
        "code_challenge_method": "S256",
        "scope": "jbus offline_access",
        "resource": f"{ORIGIN}/mcp",
    }
    asked.update(over)
    return {key: value for key, value in asked.items() if value is not None}


def grant_code(back):
    from urllib.parse import parse_qs, urlsplit

    parts = urlsplit(back)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == oauth.CALLBACK
    found = {key: values[-1] for key, values in parse_qs(parts.query).items()}
    assert found["state"] == "s-1"
    assert found["iss"] == ORIGIN
    return found["code"]


def signed_in(store):
    client_id, secret = store.make_client()
    code = store.make_code()
    back = store.grant(store.asked(query(client_id)), code)
    form = {
        "grant_type": "authorization_code",
        "code": grant_code(back),
        "redirect_uri": oauth.CALLBACK,
        "code_verifier": VERIFIER,
        "client_id": client_id,
        "client_secret": secret,
    }
    return client_id, secret, store.token(form)


def test_the_whole_flow_gives_a_live_access_token(store, tmp_path):
    client_id, secret, tokens = signed_in(store)
    assert tokens["token_type"] == "Bearer"
    assert store.allows(f"Bearer {tokens['access_token']}")
    assert not store.allows("Bearer nope")
    kept = (tmp_path / oauth.FILE).read_text(encoding="utf-8")
    assert secret not in kept
    assert tokens["access_token"] not in kept
    assert tokens["refresh_token"] not in kept
    assert (tmp_path / oauth.FILE).stat().st_mode & 0o777 == 0o600


def test_the_client_secret_also_goes_by_basic(store):
    client_id, secret = store.make_client()
    back = store.grant(store.asked(query(client_id)), store.make_code())
    basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    form = {
        "grant_type": "authorization_code",
        "code": grant_code(back),
        "code_verifier": VERIFIER,
    }
    assert store.token(form, f"Basic {basic}")["access_token"]


@pytest.mark.parametrize(
    ("over", "error"),
    [
        ({"client_id": "someone"}, "invalid_client"),
        ({"redirect_uri": "https://evil.test/cb"}, "invalid_request"),
        ({"code_challenge_method": "plain"}, "invalid_request"),
        ({"code_challenge": None}, "invalid_request"),
        ({"resource": "https://other.test/mcp"}, "invalid_target"),
        ({"scope": "admin"}, "invalid_scope"),
        ({"response_type": "token"}, "unsupported_response_type"),
    ],
)
def test_it_refuses_a_request_that_is_not_the_one_client_s(store, over, error):
    client_id, _ = store.make_client()
    asked = query(client_id)
    for key, value in over.items():
        if value is None:
            asked.pop(key)
        else:
            asked[key] = value
    with pytest.raises(oauth.Failed) as failed:
        store.asked(asked)
    assert failed.value.error == error


def test_a_sign_in_code_is_used_once_and_burns_after_five_wrong_tries(store):
    client_id, _ = store.make_client()
    asked = store.asked(query(client_id))
    code = store.make_code()
    store.grant(asked, code.lower())
    with pytest.raises(oauth.Failed, match="no sign-in code is live"):
        store.grant(asked, code)
    code = store.make_code()
    for _ in range(oauth.CODE_TRIES):
        with pytest.raises(oauth.Failed, match="not the sign-in code"):
            store.grant(asked, "WRONG-CODE")
    with pytest.raises(oauth.Failed, match="no sign-in code is live"):
        store.grant(asked, code)


def test_a_sign_in_code_expires(store, clock):
    client_id, _ = store.make_client()
    asked = store.asked(query(client_id))
    code = store.make_code()
    clock.later(oauth.CODE_TTL + 1)
    with pytest.raises(oauth.Failed, match="no sign-in code is live"):
        store.grant(asked, code)


def test_there_is_no_code_without_a_client(store):
    with pytest.raises(Refused, match="no client yet"):
        store.make_code()


def test_a_grant_needs_its_verifier_and_is_spent_once(store):
    client_id, secret = store.make_client()
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": secret,
    }
    back = store.grant(store.asked(query(client_id)), store.make_code())
    with pytest.raises(oauth.Failed, match="verifier"):
        store.token({**form, "code": grant_code(back), "code_verifier": "w" * 50})
    with pytest.raises(oauth.Failed, match="unknown, spent"):
        store.token({**form, "code": grant_code(back), "code_verifier": VERIFIER})
    back = store.grant(store.asked(query(client_id)), store.make_code())
    store.token({**form, "code": grant_code(back), "code_verifier": VERIFIER})
    with pytest.raises(oauth.Failed, match="unknown, spent"):
        store.token({**form, "code": grant_code(back), "code_verifier": VERIFIER})


def test_a_wrong_secret_is_invalid_client_with_401(store):
    client_id, _ = store.make_client()
    with pytest.raises(oauth.Failed) as failed:
        store.token({"grant_type": "refresh_token", "client_id": client_id, "client_secret": "x"})
    assert (failed.value.error, failed.value.status) == ("invalid_client", 401)


def test_a_refresh_rotates_and_a_spent_one_revokes_its_family(store):
    client_id, secret, first = signed_in(store)
    form = {"grant_type": "refresh_token", "client_id": client_id, "client_secret": secret}
    second = store.token({**form, "refresh_token": first["refresh_token"]})
    assert second["refresh_token"] != first["refresh_token"]
    assert store.allows(f"Bearer {second['access_token']}")
    with pytest.raises(oauth.Failed) as failed:
        store.token({**form, "refresh_token": first["refresh_token"]})
    assert failed.value.error == "invalid_grant"
    assert not store.allows(f"Bearer {second['access_token']}")
    with pytest.raises(oauth.Failed):
        store.token({**form, "refresh_token": second["refresh_token"]})


def test_an_access_token_expires_and_revoke_signs_everyone_out(store, clock):
    client_id, secret, tokens = signed_in(store)
    clock.later(oauth.ACCESS_TTL + 1)
    assert not store.allows(f"Bearer {tokens['access_token']}")
    form = {"grant_type": "refresh_token", "client_id": client_id, "client_secret": secret}
    fresh = store.token({**form, "refresh_token": tokens["refresh_token"]})
    assert store.allows(f"Bearer {fresh['access_token']}")
    assert store.revoke() == 3
    assert not store.allows(f"Bearer {fresh['access_token']}")


def test_a_new_client_revokes_the_old_one(store):
    client_id, secret, tokens = signed_in(store)
    store.make_client()
    assert not store.allows(f"Bearer {tokens['access_token']}")


def test_the_metadata_names_the_endpoints_claude_reads():
    resource = oauth.protected_resource(ORIGIN)
    assert resource["resource"] == f"{ORIGIN}/mcp"
    assert resource["authorization_servers"] == [ORIGIN]
    server = oauth.authorization_server(ORIGIN)
    assert server["code_challenge_methods_supported"] == ["S256"]
    assert "offline_access" in server["scopes_supported"]
    assert "registration_endpoint" not in server
    assert json.dumps(server)
