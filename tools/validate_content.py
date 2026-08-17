#!/usr/bin/env python3
"""
===============================================================================
 validate_content.py — is every privacy tip in this repository well-formed?
===============================================================================

 WHAT THIS DOES
 Reads every JSON file under content/apps/ and content/device/ and checks it
 follows the rules. Contributors run it before opening a pull request, and CI
 runs it on every change, so a malformed tip can never reach the app.

 WHAT IT CHECKS
   1. The file matches the JSON Schema (content/schema/suggestion.schema.json),
      which covers field names and types. Text fields are objects keyed by
      language and the schema accepts only "en" — the wrapper is kept so adding
      a language later is a schema change rather than a rewrite of every file.
      (This said "the both-languages requirement" until Arabic was removed.)
   2. The file is in the right folder:
          content/apps/<publisher>/<package-id>.json
          content/device/<manufacturer>/<skin>.json
   3. An app file's name matches the package id inside it.
   4. No two suggestions in one file share an id, and no two suggestions
      anywhere in the catalog share a uuid.
   5. Any committed media or icon is within the size caps.

 TWO IDENTIFIERS, AND WHY
   uuid  The permanent identity. The app uses it to remember which suggestions
         a user has ticked off, so it must be unique across the WHOLE catalog
         and must never change once published. Changing one silently resets
         that tick for every user.
   id    A human-readable label, unique only within its own file. It exists to
         make diffs and reviews readable, and is safe to rename at any time.

 HOW TO READ IT
   - The rules live in the constants at the top.
   - check_*() functions each check one thing and record problems.
   - main() walks the files and calls them.

 EXIT CODES  (this is how CI knows whether to fail the build)
   0 = everything valid
   1 = problems found
   2 = could not run (missing dependency or schema)
===============================================================================
"""

import hashlib
import json
import re
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    print("Missing dependency. Run: pip install -r tools/requirements.txt")
    sys.exit(2)


# -----------------------------------------------------------------------------
#  The rules
# -----------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content"
MEDIA_DIR = REPO_ROOT / "media"
SCHEMA_PATH = CONTENT_DIR / "schema" / "suggestion.schema.json"

# Biggest a visual guide may be. Guides are animated WebP and nothing else, so
# there is one number rather than a table. Keeping it small is what stops the
# app becoming slow to use on a poor connection.
#
# Must match MAX_BYTES in the app's MediaStore, which refuses to read further
# than this when downloading.
MEDIA_SIZE_LIMIT = 2 * 1024 * 1024

ICON_SIZE_LIMIT = 100 * 1024  # 100 KB
ICON_EXTENSIONS = {".webp", ".png"}

# Folder names must be lowercase slugs, e.g. "meta", "samsung", "google".
FOLDER_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# How deep a content file should sit: <group>/<publisher-or-maker>/<file>.json
EXPECTED_PATH_DEPTH = 3


# -----------------------------------------------------------------------------
#  Collecting problems
# -----------------------------------------------------------------------------

def find_content_files():
    """Every JSON file under content/apps and content/device, in a stable order."""
    for group in ("apps", "device"):
        group_dir = CONTENT_DIR / group
        if group_dir.is_dir():
            yield from sorted(group_dir.rglob("*.json"))


def check_folder_structure(problems, path):
    """Rule 2: the file must sit in <group>/<publisher-or-manufacturer>/<file>."""
    parts = path.relative_to(CONTENT_DIR).parts

    if len(parts) != EXPECTED_PATH_DEPTH:
        group = parts[0] if parts else "apps"
        folder_kind = "publisher" if group == "apps" else "manufacturer"
        problems.append(
            (path, f"must live in content/{group}/<{folder_kind}>/<file>.json")
        )
        return

    folder_name = parts[1]
    if not FOLDER_SLUG_PATTERN.match(folder_name):
        problems.append(
            (path, f"folder '{folder_name}' must be lowercase letters, numbers, or hyphens")
        )


def check_schema(problems, validator, path, data):
    """Rule 1: the file must satisfy the JSON Schema."""
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        location = "/".join(str(p) for p in error.path) or "(top level)"
        problems.append((path, f"{location}: {error.message}"))


def check_filename_matches_package(problems, path, data):
    """Rule 3: an app file must be named after the package id it declares."""
    is_app_file = path.relative_to(CONTENT_DIR).parts[0] == "apps"
    package_id = data.get("package")

    if not is_app_file or not package_id:
        return

    expected_filename = f"{package_id}.json"
    if path.name != expected_filename:
        problems.append(
            (path, f"filename should be '{expected_filename}' to match package '{package_id}'")
        )


def check_unique_suggestion_ids(problems, path, data):
    """Rule 4a: readable ids must be unique within their own file."""
    seen_ids = set()

    for suggestion in data.get("suggestions", []):
        if not isinstance(suggestion, dict):
            continue

        suggestion_id = suggestion.get("id")
        if suggestion_id in seen_ids:
            problems.append((path, f"duplicate suggestion id '{suggestion_id}'"))
        seen_ids.add(suggestion_id)


def check_unique_uuids(problems, path, data, uuids_seen_so_far):
    """Rule 4b: uuids must be unique across the entire catalog.

    Two suggestions sharing a uuid would share the user's "done" tick, so
    ticking one off would silently tick off the other.

    `uuids_seen_so_far` maps uuid -> the file it was first seen in, and is
    carried across every file rather than reset per file.
    """
    for suggestion in data.get("suggestions", []):
        if not isinstance(suggestion, dict):
            continue

        suggestion_uuid = suggestion.get("uuid")
        if not suggestion_uuid:
            continue  # the schema check already reported this

        first_seen_in = uuids_seen_so_far.get(suggestion_uuid)
        if first_seen_in is not None:
            problems.append((
                path,
                f"uuid '{suggestion_uuid}' is already used in "
                f"{first_seen_in.relative_to(REPO_ROOT)} — generate a new one",
            ))
        else:
            uuids_seen_so_far[suggestion_uuid] = path


def check_icon(problems, path, data):
    """Rule 5a: a declared app icon must exist, be the right type, and be small.

    WHY EXISTENCE IS CHECKED AND WAS NOT
    The size check used to read `if icon_path.exists() and ... > LIMIT`, so a
    declared icon whose file had never been committed passed silently — the
    guard meant to skip an absent file also skipped the question of whether it
    should be absent.

    That is not hypothetical. `com.instagram.android.json` declared
    `meta/com.instagram.android/icon.webp` for months. Nothing had ever
    committed it, this validator said the file was fine, and the reference was
    signed into every published manifest. It only surfaced when an external
    reviewer went looking.

    Guides are checked for existence a few lines below, and always were. The
    inconsistency is the whole story: two nearly identical rules, one of which
    happened to be written with a short-circuit and one of which was not.
    """
    icon = data.get("icon")
    if not isinstance(icon, str):
        return

    if Path(icon).suffix.lower() not in ICON_EXTENSIONS:
        problems.append((path, f"icon '{icon}' should end in .webp or .png"))

    icon_path = MEDIA_DIR / icon
    if not icon_path.exists():
        problems.append((
            path,
            f"icon '{icon}' is declared but not committed under media/ — "
            f"expected {icon_path.relative_to(MEDIA_DIR.parent)}. A declaration "
            "pointing at a missing file becomes a broken reference inside signed "
            "content, and nothing downstream will catch it.",
        ))
        return

    if icon_path.stat().st_size > ICON_SIZE_LIMIT:
        size = icon_path.stat().st_size
        problems.append((path, f"icon '{icon}' is {size} bytes, over the {ICON_SIZE_LIMIT}-byte cap"))


def animation_frames(path: Path) -> int:
    """How many frames a WebP actually contains.

    Parses the RIFF container directly: an animated WebP carries one ANMF chunk
    per frame. ffprobe is not used because it misreports animated WebP — it
    described a correct 96-frame file as a single frame of size 0x0.
    """
    raw = path.read_bytes()
    if raw[0:4] != b"RIFF" or raw[8:12] != b"WEBP":
        return 0

    frames, i = 0, 12
    while i + 8 <= len(raw):
        fourcc = raw[i:i + 4]
        size = int.from_bytes(raw[i + 4:i + 8], "little")
        if fourcc == b"ANMF":
            frames += 1
        i += 8 + size + (size & 1)

    return frames


def check_media(problems, path, data):
    """Rule 5b: a declared visual guide must exist, match its hash, and move.

    WHY THIS IS STRICTER THAN IT WAS
    An earlier version allowed a declared guide to be missing, on the theory
    that it might be hosted elsewhere. It is not: guides live under media/ in
    this repository, and a suggestion naming one that is not there produces a
    tip with a permanent blank where the walkthrough should be.

    The hash matters for a different reason. The app downloads guides over the
    network, and the signing chain only covers the JSON — so the fingerprint
    recorded here is what lets the app tell a genuine guide from anything else
    that arrives at that URL. A wrong hash means the app will refuse the file.

    The frame count is the third check and the least obvious. Several encoders —
    ffmpeg's libwebp_anim among them — silently collapse low-motion recordings
    into a still image that still carries a .webp extension and passes every
    other check. A settings walkthrough, which sits motionless between taps, is
    exactly the kind of footage that triggers it. A guide that is secretly a
    photograph looks fine in a file listing and shows the reader nothing, so it
    is caught here rather than discovered on someone's phone.
    """
    for suggestion in data.get("suggestions", []):
        if not isinstance(suggestion, dict):
            continue

        media = suggestion.get("media")
        if not isinstance(media, dict) or "src" not in media:
            continue

        src = media["src"]
        media_path = MEDIA_DIR / src

        if not media_path.is_file():
            problems.append(
                (path, f"media '{src}' is declared but not committed under media/. "
                       f"See media/README.md for how to produce one.")
            )
            continue

        size = media_path.stat().st_size
        if size > MEDIA_SIZE_LIMIT:
            problems.append(
                (path, f"media '{src}' is {size} bytes, over the {MEDIA_SIZE_LIMIT}-byte cap")
            )

        declared = media.get("sha256")
        actual = hashlib.sha256(media_path.read_bytes()).hexdigest()
        if declared != actual:
            problems.append(
                (path, f"media '{src}' does not match its sha256. "
                       f"Declared {declared}, file is {actual}.")
            )

        frames = animation_frames(media_path)
        if frames < 2:
            problems.append(
                (path, f"media '{src}' has {frames} animation frame(s) — it is a still "
                       f"image, not a guide. The encoder collapsed the animation; "
                       f"re-convert it, checking the result plays before committing.")
            )


# -----------------------------------------------------------------------------
#  Main
# -----------------------------------------------------------------------------

def main():
    if not SCHEMA_PATH.exists():
        print(f"Schema not found at {SCHEMA_PATH}")
        return 2

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    content_files = list(find_content_files())
    if not content_files:
        print("No content files found under content/apps or content/device.")
        return 1

    problems = []  # list of (path, message)
    uuids_seen = {}  # uuid -> first file it appeared in; shared across all files

    for path in content_files:
        check_folder_structure(problems, path)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            # Without valid JSON there is nothing further to check in this file.
            problems.append((path, f"invalid JSON ({exc})"))
            continue

        check_schema(problems, validator, path, data)

        if isinstance(data, dict):
            check_filename_matches_package(problems, path, data)
            check_unique_suggestion_ids(problems, path, data)
            check_unique_uuids(problems, path, data, uuids_seen)
            check_icon(problems, path, data)
            check_media(problems, path, data)

    if problems:
        print(f"✗ {len(problems)} problem(s) found:\n")
        for path, message in problems:
            print(f"  - {path.relative_to(REPO_ROOT)}: {message}")
        return 1

    print(f"✓ {len(content_files)} content file(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
