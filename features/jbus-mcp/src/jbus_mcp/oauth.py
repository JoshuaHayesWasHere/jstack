"""The server's own OAuth 2.1 authorization server, for one client and one user.

claude.ai's custom connector signs in with "Use your own OAuth client": the client ID and secret
that `jbus-mcp client` makes on this machine, entered once in the connector's settings. Nobody
registers a client over the network, so the metadata names no `registration_endpoint`.

The sign-in page (`/authorize`) asks for a sign-in code that `jbus-mcp code` makes on this
machine: eight letters, good for `CODE_TTL` seconds, once. So only someone at a shell of this
machine as the server's user can let a connector in. Five wrong tries burn the code.

The flow is the authorization code grant with PKCE (S256 only), back to claude.ai's one
callback. A grant lives `GRANT_TTL` seconds and is used once. An access token lives `ACCESS_TTL`
seconds, and a refresh token `REFRESH_TTL`; each refresh gives a new pair and spends the old
refresh token, and a spent refresh token used again revokes its whole family. Every secret is
kept only as its sha256, in `oauth.json` in the server's state, mode 0600.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus, urlencode

from jbus_mcp import Refused

__all__ = [
    "CALLBACK",
    "FILE",
    "Asked",
    "Failed",
    "Store",
    "authorization_server",
    "protected_resource",
]

FILE = "oauth.json"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
SCOPE = "jbus"
SCOPES = (SCOPE, "offline_access")
CODE_TTL = 600
CODE_TRIES = 5
GRANT_TTL = 60
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 86400
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}")


class Failed(Exception):
    """An OAuth error: its `error` code, its description, and the HTTP status it answers."""

    def __init__(self, error: str, description: str, status: int = 400) -> None:
        super().__init__(description)
        self.error, self.description, self.status = error, description, status

    def body(self) -> dict[str, str]:
        return {"error": self.error, "error_description": self.description}


@dataclass(frozen=True)
class Asked:
    """One checked authorization request."""

    client_id: str
    redirect_uri: str
    state: str
    challenge: str
    scope: str
    resource: str


def protected_resource(origin: str) -> dict[str, Any]:
    """The protected resource metadata (RFC 9728) of the MCP endpoint."""
    return {
        "resource": f"{origin}/mcp",
        "authorization_servers": [origin],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "jbus",
    }


def authorization_server(origin: str) -> dict[str, Any]:
    """The authorization server metadata (RFC 8414)."""
    return {
        "issuer": origin,
        "authorization_endpoint": f"{origin}/authorize",
        "token_endpoint": f"{origin}/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "scopes_supported": list(SCOPES),
        "authorization_response_iss_parameter_supported": True,
    }


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _same(secret: str, kept: str) -> bool:
    return isinstance(kept, str) and hmac.compare_digest(_hash(secret), kept)


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class Store:
    """The client, the sign-in codes, the grants and the tokens, in one file."""

    def __init__(self, path: Path, origin: str, clock: Callable[[], datetime] | None = None):
        self.path, self.origin = path, origin
        self.resource = f"{origin}/mcp"
        self.clock = clock or (lambda: datetime.now(UTC))
        self.lock = path.with_suffix(".lock")

    @contextmanager
    def _held(self) -> Iterator[None]:
        """Hold the file's lock, which the server and the `client`, `code` and `revoke`
        commands share across processes, for one read and its write."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _now(self) -> float:
        return self.clock().timestamp()

    def _read(self) -> dict[str, Any]:
        try:
            kept = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            kept = {}
        except ValueError as error:
            raise Refused(f"refused: {self.path} is not JSON: {error}") from None
        for part in ("codes", "grants", "access", "refresh"):
            kept.setdefault(part, {})
        now = self._now()
        for part in ("codes", "grants", "access", "refresh"):
            kept[part] = {k: v for k, v in kept[part].items() if v.get("expires", 0) > now}
        return kept

    def _write(self, kept: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fresh = self.path.with_suffix(".tmp")
        fd = os.open(fresh, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(kept, out, indent=2, sort_keys=True)
        fresh.replace(self.path)

    def make_client(self) -> tuple[str, str]:
        """Make the one client anew and return its ID and secret, shown this once. Every grant
        and token of the old client is revoked."""
        client_id = "jbus-mcp-" + secrets.token_hex(6)
        secret = secrets.token_urlsafe(32)
        with self._held():
            made = self.clock().isoformat(timespec="seconds")
            self._write(
                {
                    "client": {"id": client_id, "secret_sha256": _hash(secret), "made_at": made},
                    "codes": {},
                    "grants": {},
                    "access": {},
                    "refresh": {},
                }
            )
        return client_id, secret

    def make_code(self) -> str:
        """Make a sign-in code, in place of any other, and return it, shown this once."""
        code = "".join(secrets.choice(LETTERS) for _ in range(8))
        with self._held():
            kept = self._read()
            if "client" not in kept:
                raise Refused("refused: there is no client yet: run jbus-mcp client first")
            kept["codes"] = {_hash(code): {"expires": self._now() + CODE_TTL, "tries": 0}}
            self._write(kept)
        return f"{code[:4]}-{code[4:]}"

    def revoke(self) -> int:
        """Drop every grant and token, and return how many tokens there were."""
        with self._held():
            kept = self._read()
            count = len(kept["access"]) + len(kept["refresh"])
            kept["grants"], kept["access"], kept["refresh"] = {}, {}, {}
            self._write(kept)
        return count

    def asked(self, query: Mapping[str, str]) -> Asked:
        """Check an authorization request. A client or a callback that is not this server's is a
        `Failed` the page shows, since a redirect would go somewhere unknown."""
        with self._held():
            client = self._read().get("client", {})
        if query.get("client_id") != client.get("id"):
            raise Failed("invalid_client", "this is not the client jbus-mcp client made")
        if query.get("redirect_uri") != CALLBACK:
            raise Failed("invalid_request", f"the one callback is {CALLBACK}")
        if query.get("response_type") != "code":
            raise Failed("unsupported_response_type", "the one response type is code")
        challenge = query.get("code_challenge", "")
        if query.get("code_challenge_method") != "S256" or not 43 <= len(challenge) <= 128:
            raise Failed("invalid_request", "PKCE with S256 is required")
        resource = query.get("resource") or self.resource
        if resource != self.resource:
            raise Failed("invalid_target", f"the one resource is {self.resource}")
        wanted = set((query.get("scope") or SCOPE).split())
        if not wanted <= set(SCOPES):
            raise Failed("invalid_scope", f"the scopes are {' '.join(SCOPES)}")
        return Asked(
            client["id"], CALLBACK, query.get("state", ""), challenge, SCOPE, self.resource
        )

    def grant(self, asked: Asked, typed: str) -> str:
        """Spend the sign-in code `typed` and return the callback address with a grant. A wrong
        code is counted, and the fifth wrong one burns the code."""
        given = "".join(typed.upper().split()).replace("-", "")
        with self._held():
            kept = self._read()
            codes = kept["codes"]
            if not codes:
                self._write(kept)
                raise Failed("access_denied", "no sign-in code is live: run jbus-mcp code")
            key, code = next(iter(codes.items()))
            if not given or not _same(given, key):
                code["tries"] += 1
                if code["tries"] >= CODE_TRIES:
                    codes.clear()
                self._write(kept)
                raise Failed("access_denied", "that is not the sign-in code")
            codes.clear()
            grant = secrets.token_urlsafe(32)
            kept["grants"][_hash(grant)] = {
                "expires": self._now() + GRANT_TTL,
                "client": asked.client_id,
                "redirect_uri": asked.redirect_uri,
                "challenge": asked.challenge,
                "scope": asked.scope,
                "resource": asked.resource,
            }
            self._write(kept)
        answer = {"code": grant, "iss": self.origin}
        if asked.state:
            answer["state"] = asked.state
        return f"{asked.redirect_uri}?{urlencode(answer)}"

    def _client(self, kept: Mapping[str, Any], form: Mapping[str, str], basic: str) -> str:
        client = kept.get("client", {})
        client_id, secret = form.get("client_id", ""), form.get("client_secret", "")
        scheme, _, encoded = basic.partition(" ")
        if scheme.lower() == "basic" and encoded:
            try:
                pair = base64.b64decode(encoded.strip(), validate=True).decode()
            except ValueError:
                pair = ""
            name, _, word = pair.partition(":")
            client_id, secret = unquote_plus(name), unquote_plus(word)
        if client_id != client.get("id") or not _same(secret, client.get("secret_sha256", "")):
            raise Failed("invalid_client", "the client or its secret is wrong", 401)
        return client_id

    def _pair(self, kept: dict[str, Any], family: str) -> dict[str, Any]:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = self._now()
        kept["access"][_hash(access)] = {"expires": now + ACCESS_TTL, "family": family}
        kept["refresh"][_hash(refresh)] = {
            "expires": now + REFRESH_TTL,
            "family": family,
            "used": False,
        }
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": ACCESS_TTL,
            "refresh_token": refresh,
            "scope": SCOPE,
        }

    def token(self, form: Mapping[str, str], basic: str = "") -> dict[str, Any]:
        """The token endpoint: a grant, or a refresh token, for a new pair of tokens."""
        with self._held():
            kept = self._read()
            client_id = self._client(kept, form, basic)
            kind = form.get("grant_type")
            if kind == "authorization_code":
                answer = self._from_grant(kept, client_id, form)
            elif kind == "refresh_token":
                answer = self._from_refresh(kept, form)
            else:
                raise Failed(
                    "unsupported_grant_type", "the grants are authorization_code and refresh_token"
                )
            self._write(kept)
        return answer

    def _from_grant(
        self, kept: dict[str, Any], client_id: str, form: Mapping[str, str]
    ) -> dict[str, Any]:
        one = kept["grants"].pop(_hash(form.get("code", "")), None)
        if one is None or one["client"] != client_id:
            self._write(kept)
            raise Failed("invalid_grant", "the grant is unknown, spent or expired")
        if form.get("redirect_uri", one["redirect_uri"]) != one["redirect_uri"]:
            self._write(kept)
            raise Failed("invalid_grant", "the callback is not the one the grant was given to")
        if form.get("resource", one["resource"]) != one["resource"]:
            self._write(kept)
            raise Failed("invalid_target", "the resource is not the one the grant was given for")
        verifier = form.get("code_verifier", "")
        if not VERIFIER.fullmatch(verifier) or not hmac.compare_digest(
            _challenge(verifier), one["challenge"]
        ):
            self._write(kept)
            raise Failed("invalid_grant", "the code verifier does not match the challenge")
        return self._pair(kept, secrets.token_hex(8))

    def _from_refresh(self, kept: dict[str, Any], form: Mapping[str, str]) -> dict[str, Any]:
        key = _hash(form.get("refresh_token", ""))
        one = kept["refresh"].get(key)
        if one is None:
            raise Failed("invalid_grant", "the refresh token is unknown or expired")
        if one["used"]:
            family = one["family"]
            for part in ("access", "refresh"):
                kept[part] = {k: v for k, v in kept[part].items() if v["family"] != family}
            self._write(kept)
            raise Failed("invalid_grant", "the refresh token was spent: its family is revoked")
        one["used"] = True
        return self._pair(kept, one["family"])

    def allows(self, authorization: str) -> bool:
        """Whether a request's `Authorization` header is `Bearer <token>` with a live access
        token."""
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return False
        with self._held():
            return _hash(token.strip()) in self._read()["access"]
