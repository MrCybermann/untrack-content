#!/usr/bin/env python3
"""
===============================================================================
 build_and_sign_manifest.py — seal the tip catalog so the app can trust it
===============================================================================

 THE PROBLEM THIS SOLVES
 The app downloads privacy tips from the internet and tells people to change
 settings based on them. If someone could swap that file for their own, they
 could feed harmful "advice" to every user. So the app must be able to prove a
 catalog really came from the maintainer.

 THE APPROACH
 Public-key signing, which works like a wax seal on a letter: the maintainer
 holds the stamp (the private key) and everyone can recognise the pattern (the
 public key). Anyone can verify a seal; only the holder of the stamp can produce
 one.

 WHAT THIS SCRIPT PRODUCES
 content/index.json — a list of every content file with its fingerprint
 (SHA-256), a version number, and a signature covering the whole list:

     {
       "contentVersion": 42,
       "generatedAt": "2026-07-22T09:00:00Z",
       "files": [ { "path": "apps/meta/...json", "sha256": "3b1f..." } ],
       "signature": "ed25519:..."
     }

 So one signature protects the list, and each fingerprint protects a file. Change
 any tip and its fingerprint no longer matches; change the list and the
 signature no longer matches.

 WHO RUNS IT
 GitHub Actions, automatically, whenever content changes on the main branch.
 You'd only run it by hand while testing.

 SETUP
 The signing key is read from the environment, never from a file, so it cannot
 be committed by accident:

     export UNTRACK_SIGNING_KEY=<base64 private key from generate_keys.py>
     python tools/build_and_sign_manifest.py

 EXIT CODES
   0 = manifest written
   2 = could not run (missing dependency or signing key)
===============================================================================
"""

import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    print("Missing dependency. Run: pip install -r tools/requirements.txt")
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content"
MANIFEST_PATH = CONTENT_DIR / "index.json"


def find_content_files():
    """Every content file, in a stable order so the manifest is reproducible."""
    paths = []
    for group in ("apps", "device"):
        group_dir = CONTENT_DIR / group
        if group_dir.is_dir():
            paths += sorted(group_dir.rglob("*.json"))
    return paths


def fingerprint(path):
    """SHA-256 of a file's exact bytes.

    A fingerprint: change one character in the file and this changes completely,
    so the app can tell whether a downloaded file is the one we signed.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bytes_to_sign(manifest):
    """Produce the exact bytes that get signed — and later verified.

    This must match verify_manifest.py and the app's verifier *byte for byte*,
    or valid signatures would look invalid. Hence the strict rules:

      - drop the "signature" field (it can't cover itself)
      - sort the keys, so ordering can never differ between tools
      - no spaces between items, so formatting can never differ
      - UTF-8, so non-English text is encoded identically everywhere

    The order of the "files" list is preserved as-is.
    """
    unsigned = {key: value for key, value in manifest.items() if key != "signature"}
    return json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class MalformedManifest(RuntimeError):
    """The existing manifest could not be read. Refuse rather than guess."""


def read_previous_version():
    """Read the last contentVersion so we can increment it.

    The app uses this number to spot a newer catalog. It only ever goes up,
    which also means an attacker cannot replay an old catalog as if it were new.

    WHY A MALFORMED MANIFEST IS FATAL RATHER THAN ZERO
    This used to catch every parse failure and return 0, so the next signed
    manifest would be version 1. That is the quietest possible outage: signing
    succeeds, CI is green, the CDN serves a perfectly valid catalog — and every
    phone already on version 12 refuses it, correctly, because the app only
    accepts a version strictly higher than the one it has.

    Recovery would mean either publishing twelve times or editing the counter by
    hand, and the person doing it would first have to work out why a green
    pipeline was reaching nobody.

    Absent and unreadable are genuinely different questions. Absent means no
    catalog has ever been published, and 0 is the right answer. Unreadable means
    something is wrong that a human should look at.
    """
    if not MANIFEST_PATH.exists():
        return 0

    try:
        previous = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise MalformedManifest(
            f"{MANIFEST_PATH} is not valid JSON ({error}).\n"
            "Signing would restart the version counter at 1, which every phone "
            "on a higher version would refuse.\n"
            "Restore it from git history rather than deleting it."
        ) from error

    version = previous.get("contentVersion")
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise MalformedManifest(
            f"{MANIFEST_PATH} has contentVersion {version!r}, which is not a "
            "version number.\nSee above: restarting the counter is an outage, "
            "not a fresh start."
        )

    return version


def main():
    signing_key_base64 = os.environ.get("UNTRACK_SIGNING_KEY")
    if not signing_key_base64:
        print("UNTRACK_SIGNING_KEY is not set. Generate one with tools/generate_keys.py.")
        return 2

    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(signing_key_base64))

    # 1. List every content file with its fingerprint.
    files = [
        {"path": path.relative_to(CONTENT_DIR).as_posix(), "sha256": fingerprint(path)}
        for path in find_content_files()
    ]

    # 2. Assemble the manifest.
    try:
        next_version = read_previous_version() + 1
    except MalformedManifest as error:
        print(f"error: {error}")
        return 1

    manifest = {
        "contentVersion": next_version,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
    }

    # 3. Sign it, and store the signature alongside.
    signature = private_key.sign(bytes_to_sign(manifest))
    manifest["signature"] = "ed25519:" + base64.b64encode(signature).decode()

    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"✓ Wrote {MANIFEST_PATH.relative_to(REPO_ROOT)} "
          f"(contentVersion {manifest['contentVersion']}, {len(files)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
