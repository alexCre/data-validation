import shutil
from pathlib import Path

from scripts.promote_operator import promote

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_draft(tmp_path: Path, passing: bool) -> Path:
    draft_dir = tmp_path / "example_operator"
    draft_dir.mkdir()
    (draft_dir / "__init__.py").write_text("")
    (draft_dir / "operator.py").write_text(
        "def example_operator(x):\n    return x is not None\n"
    )
    body = "assert True\n" if passing else "assert False, 'intentionally failing'\n"
    (draft_dir / "test_operator.py").write_text(f"def test_example():\n    {body}")
    return draft_dir


def test_promotion_refuses_when_tests_fail(tmp_path, capsys):
    draft_dir = _make_draft(tmp_path, passing=False)
    exit_code = promote(draft_dir, assume_yes=True)
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "FAILED" in captured.out or "FAILED" in captured.err


def test_promotion_succeeds_and_appends_to_promoted_file(tmp_path):
    promoted_file = REPO_ROOT / "validation" / "operators" / "promoted.py"
    original_contents = promoted_file.read_text()
    draft_dir = _make_draft(tmp_path, passing=True)
    try:
        exit_code = promote(draft_dir, assume_yes=True)
        assert exit_code == 0
        new_contents = promoted_file.read_text()
        assert "example_operator" in new_contents
        assert new_contents.startswith(original_contents)
    finally:
        promoted_file.write_text(original_contents)
