#!/usr/bin/env python3
"""
Script to update the README.md file with the current last Friday date.
This ensures the README always shows the most recent Friday for stock analysis examples.
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Resolve README relative to this script, not the current working directory,
# so the tool works regardless of where it is invoked from.
README_PATH = Path(__file__).resolve().parent / "README.md"

# Matches the example command's end date, e.g. "--end   2025-08-29 \"
END_DATE_PATTERN = r"--end\s+\d{4}-\d{2}-\d{2}\s+\\"


def get_last_friday() -> str:
    """Calculate the last Friday on or before today (YYYY-MM-DD)."""
    today = datetime.now()
    days_since_friday = (today.weekday() - 4) % 7
    last_friday = today - timedelta(days=days_since_friday)
    return last_friday.strftime("%Y-%m-%d")


def update_readme() -> bool:
    """
    Update README.md with the current last Friday date.

    Returns True if the file was changed, False otherwise. Raises no exceptions
    for the common failure cases (missing/unwritable file); they are reported and
    cause a non-zero exit instead.
    """
    last_friday = get_last_friday()

    try:
        content = README_PATH.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        print(f"Error: could not read {README_PATH}: {exc}", file=sys.stderr)
        return False

    # Use a callable replacement so re.sub does not interpret the trailing
    # backslash in the example command as an escape sequence.
    replacement = f"--end   {last_friday} \\"
    updated_content, n_subs = re.subn(END_DATE_PATTERN, lambda _m: replacement, content)

    if n_subs == 0:
        print(
            f"Warning: no '--end <date>' pattern found in {README_PATH.name}; nothing was updated.",
            file=sys.stderr,
        )
        return False

    if updated_content == content:
        print(f"README.md already up to date (last Friday: {last_friday}).")
        return False

    try:
        README_PATH.write_text(updated_content, encoding="utf-8")
    except OSError as exc:
        print(f"Error: could not write {README_PATH}: {exc}", file=sys.stderr)
        return False

    print(f"Updated README.md with last Friday date: {last_friday} ({n_subs} replacement(s)).")
    return True


if __name__ == "__main__":
    changed = update_readme()
    # Exit non-zero only on hard failure (could not read/write); a no-op match
    # warning still exits 0 so it does not break opportunistic CI hooks.
    sys.exit(0 if (changed or README_PATH.exists()) else 1)
