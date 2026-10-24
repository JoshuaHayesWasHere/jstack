"""Read why a webhook refused a POST, from the `error` text of its answer's JSON body.

A webhook that refuses may say why: Cursor's automation answers 400 with
`{"success": false, "error": "Automation ... is disabled"}`. `said` gives that text for the end of
the line `wake._post` returns, so the journal and `last_error` say why and not only the code. The
text may quote the URL or the key, so `said` cuts both out of it.
"""

from __future__ import annotations

import http.client
import json
import urllib.error

CAP = 16_000
SHOWN = 200


def said(error: urllib.error.HTTPError, url: str, key: str) -> str:
    """Return `: <the error text>` on one line, with the URL and the key cut out of it, or nothing
    when the body gives no such text or cannot be read whole."""
    try:
        answer = json.loads(error.read(CAP) or b"null")
    except (OSError, ValueError, http.client.HTTPException):
        return ""
    text = answer.get("error") if isinstance(answer, dict) else None
    if not isinstance(text, str) or not text.strip():
        return ""
    text = " ".join(text.split())
    for secret in (url, key):
        text = text.replace(secret, "[webhook]") if secret else text
    return f": {text if len(text) <= SHOWN else text[: SHOWN - len('[cut]')] + '[cut]'}"
