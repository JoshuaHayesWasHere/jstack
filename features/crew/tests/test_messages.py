"""A thread messages its home only when the home must act. Where a shell block decides whether
a message goes, and to whom, the test copies the block out of its skill and runs it here."""

import pytest

from test_home_thread import THREAD, Scene, blocks

SLUG = "a-task"
CREWMATE = "mcp:the-crewmate-that-did-the-work"
URL = "https://example.test/pull/7"
BRIEF = f"""\
# {SLUG}: a title
Task: "make it so"
Decisions:
- Thread: and Branch: are fields only at the start of a line.
Review: review
Home: {THREAD}
"""
REPORT = "## Report\nStatus: done\nRecommendation: do it\n"


def the_block(skill, about):
    (found,) = [block for block in blocks(skill) if about in block]
    return found


def result(pull_request, heading="## Result"):
    return f"\n{heading}\nStatus: done\nBranch: {SLUG}   Pull request: {pull_request}\n"


class Threads(Scene):
    """A repo's home with one brief and one scout's request out."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.brief = self.home_dir / "tasks" / f"{SLUG}.md"
        self.request = self.home_dir / "scouts" / f"{SLUG}.md"
        for sent in (self.brief, self.request):
            sent.parent.mkdir()
        self.brief.write_text(BRIEF)
        self.request.write_text(f"# {SLUG}: a question\nHome: {THREAD}\n\n{REPORT}")

    def says(self, skill, about, slug_as="<slug>"):
        """What the skill's block prints for this slug, run as the skill says to run it."""
        block = the_block(skill, about)
        assert slug_as in block or slug_as == "$S"
        text = block.replace(slug_as, SLUG) if slug_as != "$S" else f"S={SLUG}\n{block}"
        return self.run(skill, text, self.worktree).stdout.strip()

    def crewmate_ends(self):
        return self.says("crew", "write the Result first")

    def crewmate_with_no_reviewer(self):
        return self.says("crew", "has no review")

    def reviewer_sends(self):
        block = the_block("pr-review", "the findings go there")
        assert "<slug>" in block
        filled = block.replace("<slug>", SLUG).replace("<clean, findings or not run>", "findings")
        return self.run("pr-review", filled, self.worktree).stdout.strip()

    def scout_is_told(self):
        return self.says("scout", '> "$H/scouts/$S.told"', "$S")

    def scout_after_the_page(self):
        return self.says("scout", "send nothing", "$S")


@pytest.fixture
def threads(tmp_path):
    return Threads(tmp_path)


def test_a_crewmate_with_a_pull_request_sends_its_home_nothing_at_its_result(threads):
    threads.brief.write_text(BRIEF + result(URL))
    assert threads.crewmate_ends().startswith(f"send nothing: {URL} is open")


def test_a_crewmate_that_ends_with_no_pull_request_tells_its_home(threads):
    threads.brief.write_text(BRIEF + result("none"))
    assert threads.crewmate_ends() == "tell the home: the task ends with no pull request"


def test_the_last_result_decides_after_a_follow_up(threads):
    later = "## Result, follow-up (2026-10-10, the user asked for a pull request)"
    threads.brief.write_text(BRIEF + result("none") + result(URL, later))
    assert threads.crewmate_ends().startswith("send nothing: ")
    threads.brief.write_text(BRIEF + result(URL) + result("none", later))
    assert threads.crewmate_ends().startswith("tell the home: ")


def test_a_brief_with_no_result_yet_decides_nothing(threads):
    assert threads.crewmate_ends().startswith("write the Result first")


def test_a_reviewer_sends_its_findings_to_the_crewmate_and_the_home_nothing(threads):
    threads.brief.write_text(BRIEF + f"Thread: {CREWMATE}\n" + result(URL))
    assert threads.reviewer_sends().startswith(f"crewmate {CREWMATE}: ")
    assert "the home is sent nothing" in threads.reviewer_sends()


def test_a_brief_with_no_thread_line_sends_the_findings_to_the_home(threads):
    threads.brief.write_text(BRIEF + result(URL))
    assert threads.reviewer_sends().startswith("home: ")


def test_a_scout_whose_report_is_as_the_home_was_told_sends_no_second_message(threads):
    threads.scout_is_told()
    assert threads.scout_after_the_page().startswith("send nothing: ")


def test_a_line_the_home_adds_above_the_report_is_not_a_changed_report(threads):
    threads.scout_is_told()
    text = threads.request.read_text()
    threads.request.write_text(
        text.replace("\n\n## Report", "\nThread: mcp:the-scout\n\n## Report")
    )
    assert threads.scout_after_the_page().startswith("send nothing: ")


def test_a_scout_whose_report_changed_on_the_page_tells_its_home_again(threads):
    threads.scout_is_told()
    text = threads.request.read_text()
    threads.request.write_text(text.replace("do it", "do not do it"))
    assert threads.scout_after_the_page().startswith("tell the home: ")


def test_a_follow_up_with_no_branch_line_is_not_decided_by_the_result_before_it(threads):
    later = "\n## Result, follow-up (2026-10-10, a steer)\nStatus: not done\n"
    threads.brief.write_text(BRIEF + result(URL) + later)
    assert threads.crewmate_ends().startswith("write the Result first")


def test_a_pull_request_with_no_reviewer_tells_its_home_once(threads):
    threads.brief.write_text(BRIEF + result(URL) + "Noticed: the brief says Reviewer: none\n")
    assert threads.crewmate_with_no_reviewer() == "tell the home: it is green and has no review"
    with threads.brief.open("a") as told:
        told.write("Reviewer: none, the brief says Review: none\n")
    assert threads.crewmate_with_no_reviewer().startswith("send nothing: ")
