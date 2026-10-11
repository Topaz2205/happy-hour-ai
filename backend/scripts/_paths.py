"""
Source-file resolution for the importers.

The importers were originally written against the sandbox upload directory.
For the project to run on any machine, each importer asks for its file by a
stable prefix and this resolver looks in, in order:

  1. $HAPPY_HOUR_DATA_DIR   (explicit override)
  2. backend/scripts/data/  (where the repo expects the source workbooks)
  3. the original sandbox upload directory (so the sandbox keeps working)

Match is by filename prefix, because the source workbooks have long Hebrew
names that get mangled differently depending on how they were transferred.
"""
import os
import glob
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
LOCAL_DATA_DIR = SCRIPTS_DIR / "data"
SANDBOX_UPLOAD_DIR = "/root/.claude/uploads/eeb87316-9fcb-5edc-bb37-6fbeb64a1718"


def search_dirs() -> list[str]:
    dirs = []
    env_dir = os.environ.get("HAPPY_HOUR_DATA_DIR")
    if env_dir:
        dirs.append(env_dir)
    dirs.append(str(LOCAL_DATA_DIR))
    dirs.append(SANDBOX_UPLOAD_DIR)
    return dirs


def resolve(prefix: str, human_name: str) -> str:
    """
    Return the path to the workbook whose filename starts with `prefix`.

    Raises FileNotFoundError with an actionable message rather than returning
    None, so an importer never silently proceeds against no data.
    """
    for directory in search_dirs():
        if not os.path.isdir(directory):
            continue
        matches = sorted(glob.glob(os.path.join(directory, f"{prefix}*.xlsx")))
        if matches:
            return matches[0]

    searched = "\n  ".join(search_dirs())
    raise FileNotFoundError(
        f"Could not find the source workbook for {human_name!r} "
        f"(expected a file starting with {prefix!r}).\n"
        f"Searched:\n  {searched}\n\n"
        f"Fix: put the workbook in backend/scripts/data/, or set "
        f"HAPPY_HOUR_DATA_DIR to the folder that holds it."
    )
