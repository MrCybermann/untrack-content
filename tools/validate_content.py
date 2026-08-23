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

# Type annotations are not evaluated at runtime, so `tuple[int, int] | None`
# below works on Python 3.7 upwards rather than 3.10 upwards.
#
# WHY THIS MATTERS HERE MORE THAN IT LOOKS
# CI pins Python 3.12 and a maintainer's machine may ship anything. Modern
# annotation syntax therefore passes CI and fails locally — which is the wrong
# way round, because the person it fails for is the one who cannot see why, and
# the check that was supposed to run before pushing is the thing that broke.
from __future__ import annotations

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

# The longest edge a guide may declare, in pixels.
#
# Must match MAX_DECODED_EDGE_PX in the app's GuidePlayer, which samples anything
# larger down rather than allocating it. Guides are recorded on a phone and shown
# in a card narrower than a phone screen, so this is already generous; a sensibly
# recorded guide is a third of it.
MEDIA_MAX_EDGE_PX = 1440

ICON_SIZE_LIMIT = 100 * 1024  # 100 KB
ICON_EXTENSIONS = {".webp", ".png"}

# -----------------------------------------------------------------------------
#  What the app will actually accept
#
#  MUST MATCH ContentLimits IN THE APP'S DownloadedContent.kt. The app repository
#  runs check_content_limits.py, which fetches these numbers and fails if the two
#  sets disagree.
#
#  WHY THE PUBLISHER ENFORCES THE CONSUMER'S LIMITS
#  It did not, and that is a strange gap to leave: this repository could publish,
#  sign and serve a catalog that every phone then refuses. The signature would be
#  valid, CI green, the CDN correct — and the app would fall back to its bundled
#  copy and quietly stop receiving tips.
#
#  Failing here instead turns a silent field failure into a red pull request,
#  which is the difference between finding out now and finding out from a user.
#
#  These are ceilings, not targets. See --headroom for how close the catalog is.
# -----------------------------------------------------------------------------
MAX_FILE_BYTES = 512 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_FILES = 500
MAX_TOTAL_BYTES = 8 * 1024 * 1024

# Warn once a limit is this close, so growth is noticed with room to act rather
# than at the moment publishing breaks.
HEADROOM_WARN_AT = 0.80

# A catalog path becomes part of a URL. The app's isSafeContentPath rejects
# traversal and control characters but not URL syntax, so `pixel?x.json` passes
# there and then silently becomes a query string when appended to the CDN base —
# the wrong file is requested and the hash fails. Constrain it at the source.
URL_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Matches isSafeContentPath in the app's DownloadedContent.kt, which refuses any
# path longer than this. Applies to media paths too: MediaStore's isSafeMediaPath
# uses the same bound, and a guide whose path the app rejects is a guide that
# never loads.
MAX_PATH_LENGTH = 200

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
    """Rule 1: the file must satisfy the JSON Schema.

    WHY THIS IS MORE THAN A LOOP OVER iter_errors
    The schema's top level is `oneOf: [appFile, deviceFile]`. When a file fails
    — for any reason, however small — it fails *both* branches, so jsonschema
    reports one error at the root: "is not valid under any of the given
    schemas", with the entire document as context.

    For a file with one tip that is merely unhelpful. At nineteen it is four
    thousand characters of JSON that names neither the suggestion nor the field,
    and finding the fault means reading the schema and the file side by side.
    An apostrophe in an id cost exactly that.

    So when the root error is a `oneOf`, this picks the branch the file was
    obviously *meant* to satisfy — `package` means an app file, `target` means a
    device one — and reports that branch's errors instead. Those carry a real
    path: `suggestions/3/id`, not `(top level)`.
    """
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))

    root_oneof = [
        error for error in errors
        if error.validator == "oneOf" and not list(error.path)
    ]

    if root_oneof and isinstance(data, dict):
        branch = _intended_branch(validator.schema, data)
        if branch is not None:
            from jsonschema import Draft202012Validator

            resolver_schema = dict(branch)
            # Carry $defs across so internal $refs still resolve when the branch
            # is validated on its own.
            for key in ("$defs", "definitions"):
                if key in validator.schema:
                    resolver_schema[key] = validator.schema[key]

            branch_errors = sorted(
                Draft202012Validator(resolver_schema).iter_errors(data),
                key=lambda e: list(e.path),
            )
            if branch_errors:
                for error in branch_errors:
                    problems.append((path, f"{_where(error)}: {error.message}"))
                return

        # No branch could be identified, or the branch validated cleanly and the
        # oneOf failed for a reason this cannot narrow. Say so rather than
        # dumping the document.
        problems.append((
            path,
            "does not match either the app-file or device-file shape. An app "
            "file needs 'package' and 'appName'; a device file needs 'target'.",
        ))
        return

    for error in errors:
        problems.append((path, f"{_where(error)}: {error.message}"))


def _where(error) -> str:
    """A readable location, naming the suggestion rather than its index.

    `suggestions/3/id` is findable but requires counting. `suggestion
    'facebook-limit-location-service' → id` is the thing you search for.
    """
    parts = list(error.absolute_path)

    if len(parts) >= 2 and parts[0] == "suggestions" and isinstance(parts[1], int):
        remainder = "/".join(str(p) for p in parts[2:])
        return f"suggestions[{parts[1]}]" + (f" → {remainder}" if remainder else "")

    return "/".join(str(p) for p in parts) or "(top level)"


def _intended_branch(schema, data):
    """Which half of the top-level oneOf this file was clearly aiming at.

    Decided on the discriminating field rather than on which branch produces
    fewer errors: a file with three faults in the app shape should be reported
    as a broken app file, not compared against the device shape it never
    resembled.
    """
    defs = schema.get("$defs") or schema.get("definitions") or {}

    wanted = "appFile" if "package" in data or "appName" in data else (
        "deviceFile" if "target" in data else None
    )
    if wanted is None:
        return None

    branch = defs.get(wanted)
    if branch is not None:
        return branch

    # The oneOf may inline the branches rather than $ref them.
    for candidate in schema.get("oneOf", []):
        ref = candidate.get("$ref", "")
        if ref.endswith(f"/{wanted}"):
            return defs.get(wanted)
    return None


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


def webp_canvas(path: Path) -> tuple[int, int] | None:
    """The declared canvas size of a WebP, or None if it cannot be read.

    Parses the container rather than decoding, because the whole point is to
    know how large a decode would be *before* doing one.

    Two chunk types carry it. VP8X is the extended header an animated file
    always has, and stores width-1 and height-1 as 24-bit little-endian. ANMF
    frame headers use the same encoding for each frame, but the canvas is what
    a decoder allocates, so VP8X is the one that matters.
    """
    raw = path.read_bytes()
    if raw[0:4] != b"RIFF" or raw[8:12] != b"WEBP":
        return None

    i = 12
    while i + 8 <= len(raw):
        fourcc = raw[i:i + 4]
        size = int.from_bytes(raw[i + 4:i + 8], "little")
        body = raw[i + 8:i + 8 + size]

        if fourcc == b"VP8X" and len(body) >= 10:
            width = int.from_bytes(body[4:7], "little") + 1
            height = int.from_bytes(body[7:10], "little") + 1
            return width, height

        i += 8 + size + (size & 1)

    return None


def check_os_range(problems, path, data):
    """Rule 5c: a device entry's osMin must not be above its osMax.

    WHY THIS IS NOT CAUGHT BY THE SCHEMA
    Both are optional integers and each is individually valid. Only the
    *relationship* is wrong, which JSON Schema can express but awkwardly, and
    which reads far more clearly here.

    WHY IT MATTERS
    SuggestionMatcher refuses a device entry when the phone's API level is below
    osMin or above osMax. With osMin above osMax there is no API level that
    satisfies both, so every suggestion in that entry is silently unreachable on
    every phone ever made. Nothing else notices: the file is valid, it signs, it
    publishes, and it shows to nobody.

    A typo produces this, not malice — which is why it is worth a rule rather
    than a note.
    """
    for suggestion in data.get("suggestions", []):
        if not isinstance(suggestion, dict):
            continue

        os_min = suggestion.get("osMin")
        os_max = suggestion.get("osMax")

        if isinstance(os_min, int) and isinstance(os_max, int) and os_min > os_max:
            problems.append((
                path,
                f"suggestion '{suggestion.get('id', '?')}' has osMin {os_min} above "
                f"osMax {os_max}. No phone can satisfy both, so this suggestion "
                "would publish and reach nobody.",
            ))


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

        # Same bound as content paths, and the same reason: MediaStore's
        # isSafeMediaPath refuses anything longer, so an over-long guide path is
        # published and never fetched.
        if len(src) > MAX_PATH_LENGTH:
            problems.append((
                path,
                f"media path '{src[:60]}…' is {len(src)} characters, over the "
                f"app's {MAX_PATH_LENGTH}-character limit — the app refuses it, "
                "so the guide would never load.",
            ))

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

        # A file under the size cap can still declare an enormous canvas — WebP
        # compresses a flat settings screen extremely well, so 8000 × 8000 fits
        # in a few hundred kilobytes and becomes 256 MB once decoded. Bytes on
        # disk and bytes in memory are different questions and only one was
        # being asked.
        canvas = webp_canvas(media_path)
        if canvas is None:
            problems.append((
                path,
                f"media '{src}' is not a readable WebP container — no VP8X "
                "header found. Re-convert it.",
            ))
        else:
            width, height = canvas
            if max(width, height) > MEDIA_MAX_EDGE_PX:
                problems.append((
                    path,
                    f"media '{src}' is {width}x{height}, and its longest edge is "
                    f"over {MEDIA_MAX_EDGE_PX}px. A guide is a recording of a "
                    "phone screen shown in a card narrower than one, so this is "
                    "far more pixels than anything will display — and the app "
                    "would have to allocate them all to decode it.",
                ))

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

def usage(content_files):
    """Where the catalog currently sits against each of the app's ceilings.

    Returns name -> (actual, limit, unit). The manifest is measured from the
    file on disk when there is one; before the first publish there is nothing
    to measure and it is reported as zero.
    """
    sizes = [path.stat().st_size for path in content_files]
    manifest = CONTENT_DIR / "index.json"

    return {
        "files": (len(content_files), MAX_FILES, "files"),
        "largest file": (max(sizes, default=0), MAX_FILE_BYTES, "bytes"),
        "total size": (sum(sizes), MAX_TOTAL_BYTES, "bytes"),
        "manifest": (
            manifest.stat().st_size if manifest.exists() else 0,
            MAX_MANIFEST_BYTES,
            "bytes",
        ),
    }


def check_app_limits(problems, content_files):
    """Rule 6: nothing the app would refuse to load.

    Publishing something the app rejects is the worst shape of failure this
    repository can produce — everything here looks correct, the signature
    verifies, and phones silently stop receiving tips because the catalog
    exceeds a ceiling compiled into the APK.
    """
    for name, (actual, limit, unit) in usage(content_files).items():
        if actual > limit:
            problems.append((
                CONTENT_DIR,
                f"{name}: {actual} {unit}, over the app's limit of {limit} — "
                "the app would refuse this catalog and fall back to its "
                "bundled copy",
            ))

    # Path grammar. The app checks for traversal; it does not check that a name
    # survives being put in a URL.
    for path in content_files:
        relative = path.relative_to(CONTENT_DIR).as_posix()

        if len(relative) > MAX_PATH_LENGTH:
            problems.append((
                path,
                f"the path is {len(relative)} characters, over the app's "
                f"{MAX_PATH_LENGTH}-character limit. The app refuses it outright, "
                "so this file would be published and never read.",
            ))

        for segment in path.relative_to(CONTENT_DIR).parts:
            if not URL_SAFE_SEGMENT.match(segment):
                problems.append((
                    path,
                    f"'{segment}' is not safe in a URL. Use letters, digits, "
                    "dot, underscore or hyphen — a '?' or '#' here silently "
                    "becomes a query string or fragment when the app builds "
                    "the download address, and the wrong file is fetched",
                ))


def report_headroom(content_files):
    """Print how close each limit is, and say so loudly past the warn level.

    Printed rather than failed. The point is to notice growth with room to act,
    not to block a pull request for being successful — CI turns the WARNING
    lines below into an issue, which is what reaches an inbox.
    """
    print("\nHeadroom against the app's limits:")
    warned = False

    for name, (actual, limit, unit) in usage(content_files).items():
        fraction = actual / limit if limit else 0
        marker = "  "
        if fraction >= HEADROOM_WARN_AT:
            marker = "!!"
            warned = True
        print(f"  {marker} {name:<14} {actual:>9} / {limit} {unit}  ({fraction:.0%})")

    if warned:
        print(
            f"\nWARNING: a limit is over {HEADROOM_WARN_AT:.0%} used.\n"
            "One file per app is a deliberate choice, so the answer is not a "
            "bigger number — past a few hundred files the update path issues "
            "one request per file and becomes slow on a phone. The move is to "
            "group several apps per file, which changes the manifest format "
            "and the app's loader together."
        )


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
            check_os_range(problems, path, data)
            check_media(problems, path, data)

    check_app_limits(problems, content_files)

    if problems:
        print(f"✗ {len(problems)} problem(s) found:\n")
        for path, message in problems:
            print(f"  - {path.relative_to(REPO_ROOT)}: {message}")
        return 1

    print(f"✓ {len(content_files)} content file(s) valid.")

    if "--headroom" in sys.argv:
        report_headroom(content_files)

    return 0


if __name__ == "__main__":
    sys.exit(main())
