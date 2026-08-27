"""Developer-side promotion workflow for a generated operator draft.

Usage:
    python -m scripts.promote_operator generated_drafts/<operator_name> [--yes]

Runs the draft's own tests in an isolated subprocess first; refuses to
promote if they fail. Requires an explicit --yes confirmation flag (or an
interactive y/N prompt) before touching the active codebase. Never invoked
automatically by the Streamlit app or the agents.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMOTED_OPERATORS_FILE = REPO_ROOT / "validation" / "operators" / "promoted.py"


def run_draft_tests(draft_dir: Path) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(draft_dir), "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    return result.returncode == 0


def promote(draft_dir: Path, assume_yes: bool) -> int:
    operator_file = draft_dir / "operator.py"
    if not operator_file.exists():
        print(f"error: {operator_file} not found", file=sys.stderr)
        return 1

    print(f"Running draft tests in {draft_dir} ...")
    if not run_draft_tests(draft_dir):
        print("Draft tests FAILED - refusing to promote.", file=sys.stderr)
        return 1
    print("Draft tests passed.")

    if not assume_yes:
        answer = input(f"Promote {draft_dir.name} into the active operator registry? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            return 1

    code = operator_file.read_text()
    with PROMOTED_OPERATORS_FILE.open("a") as f:
        f.write(f"\n\n# --- promoted from generated_drafts/{draft_dir.name} ---\n")
        f.write(code)

    print(f"Promoted {draft_dir.name} into {PROMOTED_OPERATORS_FILE}.")
    print("Restart the Streamlit app for the new operator to be registered.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft_dir", type=Path, help="Path to generated_drafts/<operator_name>")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt.")
    args = parser.parse_args()
    return promote(args.draft_dir, args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
