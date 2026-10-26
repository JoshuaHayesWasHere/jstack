"""`jbus link` prints the address of this repo's project in jbus view, the page that shows the facts
a home's status reply tells: what is out, what waits on the user, and what went wrong. A home ends
its status reply with that line. The address is where the user reaches the view: the proxy in front
of it, else its name or its address on the tailnet, else 127.0.0.1, at the view's port."""

import subprocess

import pytest

from jbus import cards

VIEW = ("JBUS_VIEW_ORIGINS", "JBUS_VIEW_NAMES", "JBUS_VIEW_HOST")


@pytest.fixture
def here(kitchen, monkeypatch):
    for name in VIEW:
        monkeypatch.delenv(name, raising=False)
    return kitchen


def test_it_prints_the_projects_page_on_this_machine(here):
    assert here.main("link") == (0, "http://127.0.0.1:4388/#/demo\n")


def test_it_prints_the_page_behind_the_proxy_the_user_opens(here, monkeypatch):
    monkeypatch.setenv("JBUS_VIEW_ORIGINS", " , https://example.test/,https://example.com")
    monkeypatch.setenv("JBUS_VIEW_NAMES", "box.tail")
    assert here.main("link") == (0, "https://example.test/#/demo\n")


@pytest.mark.parametrize(
    ("names", "host", "address"),
    [
        ("box.tail, other", "192.0.2.9", "http://box.tail:4388/#/demo\n"),
        ("", "192.0.2.9", "http://192.0.2.9:4388/#/demo\n"),
    ],
)
def test_it_prints_the_name_or_address_the_view_listens_on(here, monkeypatch, names, host, address):
    monkeypatch.setenv("JBUS_VIEW_NAMES", names)
    monkeypatch.setenv("JBUS_VIEW_HOST", host)
    assert here.main("link") == (0, address)


def test_an_item_and_the_project_page_are_at_the_same_place(here, monkeypatch):
    monkeypatch.setenv("JBUS_VIEW_ORIGINS", "https://example.test")
    code, said = here.main("link")
    assert code == 0
    assert cards.view_link("demo", "i-7") == said.strip() + "/item/i-7"


def test_it_names_the_project_the_user_asks_for(here):
    here.second("other two")
    assert here.main("--project", "other two", "link") == (
        0,
        "http://127.0.0.1:4388/#/other%20two\n",
    )


def test_a_repo_jbus_does_not_keep_has_no_page(here, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=elsewhere, check=True)
    monkeypatch.chdir(elsewhere)
    here.second()
    code, said = here.main("link")
    assert code != 0
    assert said.startswith("refused: no project for this repo (elsewhere)")
