"""The fixtures the tests of `jbus view` share: a scene, and the server open over it."""

import pytest

from view.scene import Process, Scene, Served


@pytest.fixture
def scene(tmp_path, monkeypatch):
    return Scene(tmp_path, monkeypatch)


@pytest.fixture
def served(scene):
    made = Served(scene)
    yield made
    made.close()


@pytest.fixture
def process(scene):
    made = Process(scene)
    yield made
    made.stop()
