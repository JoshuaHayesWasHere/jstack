"""`jbriefs --shown <thread>` names the file of each picture the user sent in a T3 thread, so a
home can put each path on a brief's `Shown:` line and the crew opens it (po-brief-shown). It
reads T3 Code's store read-only and prints, for each user message with an image, its time, its
id, its first words and each picture's absolute path, or `gone` where the file is not on disk."""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from jbriefs import cli

THREAD = "mcp:launch:the-polish-home"
PICTURE = f"{THREAD.replace(':', '-')}-e2abb2b8"


def _store(path, messages):
    with sqlite3.connect(path) as db:
        db.execute(
            "create table orchestration_v2_projection_messages (message_id text primary key,"
            " thread_id text not null, run_id text, node_id text, role text not null,"
            " streaming integer not null, created_at text not null, updated_at text not null,"
            " payload_json text not null)"
        )
        for message, thread, role, at, payload in messages:
            db.execute(
                "insert into orchestration_v2_projection_messages values"
                " (?, ?, null, null, ?, 0, ?, ?, ?)",
                (message, thread, role, at, at, json.dumps(payload)),
            )
    return path


def _said(text, *pictures, by="user"):
    return {
        "createdBy": by,
        "text": text,
        "attachments": [
            {"type": "image", "id": one, "name": "image.png", "mimeType": "image/png"}
            for one in pictures
        ],
    }


@pytest.fixture
def t3(tmp_path):
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / f"{PICTURE}.png").write_bytes(b"\x89PNG")
    store = _store(
        tmp_path / "statev2.sqlite",
        [
            (
                "m-picture",
                THREAD,
                "user",
                "2026-11-09T16:15:05.233Z",
                _said(
                    'why is this "stalled 2h"\nstill in my sidebar? '
                    "![image.png](t3-context://v1/image/image_5f6f)",
                    PICTURE,
                    "lost-one",
                ),
            ),
            ("m-words", THREAD, "user", "2026-11-09T16:20:00.000Z", _said("go")),
            ("m-agent", THREAD, "user", "2026-11-09T16:21:00.000Z", _said("x", PICTURE, by="agent")),
            ("m-reply", THREAD, "assistant", "2026-11-09T16:22:00.000Z", _said("y", PICTURE)),
            ("m-other", "mcp:another", "user", "2026-11-09T16:23:00.000Z", _said("z", PICTURE)),
        ],
    )
    return store, attachments


def _run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out.splitlines(), out.err


def test_shown_prints_the_path_of_each_picture_the_user_sent_in_the_thread(t3, capsys):
    store, attachments = t3
    code, lines, _ = _run(
        capsys, "--shown", THREAD, "--store", str(store), "--attachments", str(attachments)
    )
    assert code == 0
    assert lines == [
        "2026-11-09T16:15:05.233Z m-picture"
        ' "why is this \\"stalled 2h\\" still in my sidebar?"'
        f" {(attachments / f'{PICTURE}.png').resolve()} gone"
    ]


def test_shown_with_since_leaves_out_what_came_before(t3, capsys):
    store, attachments = t3
    later = datetime(2026, 11, 9, 16, 16, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    for since in ("2026-11-09T16:16:00Z", later.isoformat()):
        code, lines, _ = _run(
            capsys,
            "--shown",
            THREAD,
            "--since",
            since,
            "--store",
            str(store),
            "--attachments",
            str(attachments),
        )
        assert (code, lines) == (0, []), since
    code, lines, _ = _run(
        capsys,
        "--shown",
        THREAD,
        "--since",
        "2026-11-09T16:15:05.233Z",
        "--store",
        str(store),
        "--attachments",
        str(attachments),
    )
    assert [line.split()[1] for line in lines] == ["m-picture"]


def test_shown_reads_the_store_read_only(t3, capsys):
    store, attachments = t3
    before = store.read_bytes(), sorted(attachments.iterdir())
    _run(capsys, "--shown", THREAD, "--store", str(store), "--attachments", str(attachments))
    assert (store.read_bytes(), sorted(attachments.iterdir())) == before


def test_shown_refuses_a_store_it_cannot_read(tmp_path, capsys):
    code, lines, err = _run(capsys, "--shown", THREAD, "--store", str(tmp_path / "none.sqlite"))
    assert (code, lines) == (1, [])
    assert "none.sqlite" in err
    assert not (tmp_path / "none.sqlite").exists()
