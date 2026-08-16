#!/usr/bin/env python3
"""
===============================================================================
 check_uuid_stability.py — stop a rename from wiping users' progress
===============================================================================

 THE PROBLEM THIS PREVENTS
 Every suggestion has a `uuid` that never changes, and an `id` that is just a
 readable label. The app remembers which suggestions a person has ticked off by
 their uuid.

 If a uuid is edited or deleted, the app no longer recognises that suggestion.
 It reappears as new and the person's tick is gone. This produces no error and
 no visible symptom, which is why it is checked automatically.

 WHAT THIS DOES
 Compares the uuids in this branch against the uuids on the base branch. If any
 uuid that was published before has vanished, the check fails.

 Moving a suggestion between files is fine: the uuid still exists somewhere.
 Renaming an `id` is fine: nothing depends on it. Only losing a uuid is a
 problem.

 WHEN A REMOVAL IS DELIBERATE
 Sometimes a tip genuinely has to go — a vendor removes the setting entirely.
 In that case, record it in `content/retired.json`:

     {
       "retired": [
         {
           "uuid": "9c929e75-bc86-4edf-afcd-23fed94057a2",
           "id": "ig-private-account",
           "reason": "Instagram removed this setting in version 300",
           "retiredOn": "2026-08-07"
         }
       ]
     }

 The check then allows it. Doing it this way means every removal is a visible,
 reviewed decision with a reason attached, rather than a line quietly vanishing
 from a diff.

 USAGE
     python tools/check_uuid_stability.py                  # compares to origin/main
     python tools/check_uuid_stability.py --base HEAD^     # compares to the previous commit

 EXIT CODES
   0 = no published uuid was lost (or the base doesn't exist yet)
   1 = a uuid disappeared without being retired
   2 = could not run
===============================================================================
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content"
RETIRED_PATH = CONTENT_DIR / "retired.json"

CONTENT_GROUPS = ("apps", "device")


# -----------------------------------------------------------------------------
#  Talking to git
# -----------------------------------------------------------------------------

def git(*args):
    """Run a git command and return its output, or None if it failed.

    Failures are expected and normal here — for example asking for a branch that
    doesn't exist yet on a brand-new repository.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def base_ref_exists(base_ref):
    return git("rev-parse", "--verify", "--quiet", base_ref) is not None


def content_files_at(base_ref):
    """Every content JSON file as it existed on the base branch."""
    listing = git("ls-tree", "-r", "--name-only", base_ref, "content/")
    if listing is None:
        return []

    return [
        line for line in listing.splitlines()
        if line.endswith(".json")
        and any(line.startswith(f"content/{group}/") for group in CONTENT_GROUPS)
    ]


def read_file_at(base_ref, path):
    """The contents of one file as it existed on the base branch."""
    return git("show", f"{base_ref}:{path}")


# -----------------------------------------------------------------------------
#  Collecting uuids
# -----------------------------------------------------------------------------

def uuids_from_json(text, source_label):
    """Pull every (uuid -> description) pair out of one content file's text."""
    found = {}

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # A malformed file on the base branch isn't this script's problem;
        # validate_content.py reports those.
        return found

    for suggestion in data.get("suggestions", []):
        if not isinstance(suggestion, dict):
            continue
        suggestion_uuid = suggestion.get("uuid")
        if suggestion_uuid:
            found[suggestion_uuid] = f"{suggestion.get('id', '?')} in {source_label}"

    return found


def uuids_on_base_branch(base_ref):
    """Every uuid that was already published on the base branch."""
    published = {}

    for path in content_files_at(base_ref):
        text = read_file_at(base_ref, path)
        if text is not None:
            published.update(uuids_from_json(text, path))

    return published


def uuids_in_working_tree():
    """Every uuid in the branch as it stands now."""
    current = set()

    for group in CONTENT_GROUPS:
        group_dir = CONTENT_DIR / group
        if not group_dir.is_dir():
            continue
        for path in sorted(group_dir.rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            current.update(uuids_from_json(text, str(path)).keys())

    return current


def deliberately_retired_uuids():
    """Uuids the maintainer has explicitly recorded as removed on purpose."""
    if not RETIRED_PATH.exists():
        return set()

    try:
        data = json.loads(RETIRED_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Warning: {RETIRED_PATH.name} is not valid JSON; ignoring it.")
        return set()

    return {
        entry["uuid"]
        for entry in data.get("retired", [])
        if isinstance(entry, dict) and entry.get("uuid")
    }


# -----------------------------------------------------------------------------
#  Main
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fail if a published suggestion uuid was changed or removed."
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Branch or commit to compare against (default: origin/main)",
    )
    args = parser.parse_args()

    if git("rev-parse", "--git-dir") is None:
        print("Not a git repository, or git is unavailable — skipping.")
        return 0

    if not base_ref_exists(args.base):
        # Normal on a brand-new repository, or the very first commit.
        print(f"Base '{args.base}' not found — nothing to compare against yet. Skipping.")
        return 0

    published = uuids_on_base_branch(args.base)
    if not published:
        print(f"No uuids found on '{args.base}' — nothing to protect yet.")
        return 0

    current = uuids_in_working_tree()
    retired = deliberately_retired_uuids()

    lost = {
        uuid_value: description
        for uuid_value, description in published.items()
        if uuid_value not in current and uuid_value not in retired
    }

    if lost:
        print(f"✗ {len(lost)} published uuid(s) went missing:\n")
        for uuid_value, description in sorted(lost.items(), key=lambda pair: pair[1]):
            print(f"  - {uuid_value}")
            print(f"    was: {description}")
        print(
            "\nEvery user who ticked one of these off would silently lose that progress,\n"
            "because the app recognises a suggestion by its uuid.\n"
            "\n"
            "If you renamed a suggestion: keep the original uuid and change the `id` instead.\n"
            "If you moved it to another file: that's fine, but the uuid must travel with it.\n"
            "If you removed it on purpose: add it to content/retired.json with a reason.\n"
        )
        return 1

    allowed_removals = [
        uuid_value for uuid_value in published
        if uuid_value not in current and uuid_value in retired
    ]

    print(f"✓ All {len(published)} published uuid(s) accounted for.")
    if allowed_removals:
        print(f"  ({len(allowed_removals)} deliberately retired — see content/retired.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
