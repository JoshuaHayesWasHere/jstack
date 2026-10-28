"""`jbus project add` adds one project's table to the config, and the next pass works on that
project.

Every test runs the real command on the made-up config of `test_jbus_kitchen`, and reads the file,
its mode and the copy that jbus keeps of it. The pass is the real one, against the faked T3 Code
server.
"""

import json
import tomllib

import pytest

import jbus

NEW = "p-added"


@pytest.fixture
def added(kitchen):
    """Make a second repo that the config does not have, with an origin."""
    checkout = kitchen.root / "added"
    kitchen.repo(checkout, kitchen.root / "added-origin.git")
    return checkout


def config(kitchen):
    return kitchen.config_dir / "config.toml"


def backups(kitchen):
    return sorted(kitchen.config_dir.glob("config.toml.*.bak"))


def mode(path):
    return path.stat().st_mode & 0o777


def add(kitchen, name, checkout, project=NEW):
    return kitchen.main(
        "project", "add", name, "--checkout", str(checkout), "--project-id", project
    )


def test_it_adds_one_table_after_the_bytes_the_file_had_and_keeps_the_file_as_it_was(
    kitchen, added
):
    was = config(kitchen).read_bytes()
    code, out = add(kitchen, "added", added)
    (backup,) = backups(kitchen)
    assert (code, out) == (
        0,
        f"added: one [[project]] table, the file as it was is {backup}: "
        "the next pass works it, restart no unit\n",
    )
    now = config(kitchen).read_bytes()
    assert now.startswith(was)
    assert now[len(was) :].decode() == (
        f'\n[[project]]\nname = "added"\ncheckout = {json.dumps(str(added))}\nprojectId = "{NEW}"\n'
    )
    assert backup.read_bytes() == was
    assert (mode(config(kitchen)), mode(backup)) == (0o600, 0o600)
    assert [p.name for p in kitchen.config_dir.iterdir() if p.name.startswith(".")] == []


def test_the_table_has_three_keys_and_the_loader_reads_it(kitchen, added):
    add(kitchen, "added", added)
    table = tomllib.loads(config(kitchen).read_text())["project"][-1]
    assert sorted(table) == ["checkout", "name", "projectId"]
    project = jbus.load().project("added")
    assert (project.checkout, project.state, project.project_id) == (added, "added", NEW)


def test_no_line_it_prints_has_a_value_of_a_key_of_the_config(kitchen, added):
    values = [
        str(value)
        for entry in tomllib.loads(config(kitchen).read_text())["project"]
        for value in entry.values()
    ]
    said = [add(kitchen, "added", added)[1], add(kitchen, "added", added)[1]]
    said.append(add(kitchen, "demo", kitchen.root / "nowhere")[1])
    for line in said:
        assert [value for value in (*values, str(added), NEW) if value in line] == []


@pytest.mark.parametrize(
    ("name", "where", "why"),
    [
        ("added", "added", "refused: the config already has this project"),
        ("added", "third", "refused: the config already has a project of that name"),
        ("again", "added", "refused: the config already has a project with that checkout"),
        ("demo", "third", "refused: the config already has a project of that name"),
        ("third", "demo", "refused: the config already has a project with that checkout"),
        (
            "a name",
            "third",
            "refused: a project's name is letters, digits, dots, dashes and underscores",
        ),
        ("third", "nowhere", "refused: --checkout is not a directory"),
    ],
)
def test_a_second_run_and_a_name_or_a_checkout_the_config_has_are_refused_and_write_nothing(
    kitchen, added, name, where, why
):
    (kitchen.root / "third").mkdir()
    add(kitchen, "added", added)
    was, kept = config(kitchen).read_bytes(), backups(kitchen)
    assert add(kitchen, name, kitchen.root / where) == (1, why + "\n")
    assert (config(kitchen).read_bytes(), backups(kitchen)) == (was, kept)


def test_a_config_others_can_read_is_refused_and_not_written(kitchen, added):
    config(kitchen).chmod(0o644)
    was = config(kitchen).read_bytes()
    code, out = add(kitchen, "added", added)
    assert (code, out.split(" is mode ")[0]) == (1, f"refused: {config(kitchen)}")
    assert (config(kitchen).read_bytes(), backups(kitchen)) == (was, [])


def test_the_pass_after_it_works_the_new_project_with_nothing_restarted(kitchen, added):
    (kitchen.root / "home" / "added" / "tasks").mkdir(parents=True)
    kitchen.poll()
    assert "added" not in json.loads((kitchen.state_dir / "status.json").read_text())["projects"]
    add(kitchen, "added", added)
    kitchen.poll()
    status = json.loads((kitchen.state_dir / "status.json").read_text())
    assert sorted(status["projects"]) == ["added", "demo"]
    assert status["projects"]["added"]["last_error"] == ""
    assert (kitchen.state_dir / "added").is_dir()


@pytest.mark.parametrize("text", ['[[project]]\nname = "demo"\n', "server = \n"])
def test_a_config_a_pass_would_refuse_is_refused_and_not_written(kitchen, added, text):
    kitchen.write(config(kitchen), text)
    code, out = add(kitchen, "added", added)
    assert code == 1 and out.startswith(f"refused: {config(kitchen)} ")
    assert (config(kitchen).read_text(), backups(kitchen)) == (text, [])


def settings(tmp_path, lines):
    path = tmp_path / "config.toml"
    path.write_text(
        'server = "http://127.0.0.1:1"\n\n[[project]]\n'
        f'name = "demo"\ncheckout = "{tmp_path}"\nprojectId = "p1"\n{lines}'
    )
    path.chmod(0o600)
    return jbus.load(tmp_path)


def test_a_project_has_no_migrations_unless_it_names_a_directory(tmp_path):
    (project,) = settings(tmp_path, "").projects
    assert (project.migrations, project.migration_names) == ("", "numbered")


@pytest.mark.parametrize(
    ("lines", "want"),
    [
        ('migrations = "db/migrations"\n', ("db/migrations", "numbered")),
        ('migrations = "db/migrations/"\n', ("db/migrations", "numbered")),
        ('migrations = "db/m"\nmigration_names = "timestamped"\n', ("db/m", "timestamped")),
    ],
)
def test_a_project_names_the_directory_of_its_migrations_and_how_they_are_named(
    tmp_path, lines, want
):
    (project,) = settings(tmp_path, lines).projects
    assert (project.migrations, project.migration_names) == want


@pytest.mark.parametrize(
    "lines",
    [
        'migrations = "/db"\n',
        'migrations = "../db"\n',
        'migrations = "db/../../x"\n',
        "migrations = 5\n",
    ]
    + ['migrations = "db"\nmigration_names = "dated"\n'],
)
def test_a_directory_outside_the_checkout_or_an_unknown_naming_is_refused(tmp_path, lines):
    with pytest.raises(jbus.Refused, match="refused: project demo has migration"):
        settings(tmp_path, lines)


@pytest.mark.parametrize(
    ("lines", "want"),
    [
        ("", ()),
        (
            'generated = ["uv.lock -> uv lock", "a.json -> make a"]\n',
            ("uv.lock -> uv lock", "a.json -> make a"),
        ),
    ],
)
def test_a_project_names_the_files_a_command_writes_or_none(tmp_path, lines, want):
    (project,) = settings(tmp_path, lines).projects
    assert project.generated == want


@pytest.mark.parametrize(
    "lines",
    ['generated = "uv.lock -> uv lock"\n', 'generated = ["uv.lock"]\n', "generated = [1]\n"],
)
def test_a_generated_that_is_not_a_list_of_file_arrow_command_is_refused(tmp_path, lines):
    with pytest.raises(jbus.Refused, match="refused: project demo has a generated that is not"):
        settings(tmp_path, lines)


def test_the_view_table_gives_the_views_address_names_and_origins_or_none(tmp_path):
    assert settings(tmp_path, "").view == jbus.View()
    view = settings(
        tmp_path,
        '[view]\nhost = "192.0.2.7"\nnames = ["box"]\norigins = ["https://example.test"]\n',
    ).view
    assert view == jbus.View("192.0.2.7", ("box",), ("https://example.test",))


@pytest.mark.parametrize(
    "lines",
    [
        "[view]\nhost = 1\n",
        '[view]\nnames = "box"\n',
        "[view]\norigins = [1]\n",
        '[view]\nport = "4389"\n',
    ],
)
def test_a_view_table_with_another_key_or_shape_is_refused(tmp_path, lines):
    with pytest.raises(jbus.Refused, match=r"refused: .* has a \[view\] that is not"):
        settings(tmp_path, lines)
