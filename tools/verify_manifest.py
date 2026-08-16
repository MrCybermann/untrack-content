#!/usr/bin/env python3
"""
===============================================================================
 verify_manifest.py — check the seal, exactly as the app will
===============================================================================

 WHAT THIS DOES
 The mirror image of build_and_sign_manifest.py. It answers two questions:

   1. Was content/index.json really signed by the maintainer's key?
   2. Does every file still match the fingerprint recorded in it?

 Either answer being "no" means the catalog has been tampered with or has
 drifted out of sync, and the app would refuse it.

 WHY IT EXISTS SEPARATELY
 This is a rehearsal of the check the Android app performs before trusting
 downloaded content. Running it in CI means a broken signing chain is caught on
 our own machines rather than on someone's phone. If you change how signing
 works, change it here too — and if these two files ever disagree, the app will
 side with this one.

 USAGE
     python tools/verify_manifest.py

 The public key is read from content/pubkey.txt, or from the environment
 variable UNTRACK_PUBLIC_KEY if you want to test with a different one.

 EXIT CODES
   0 = signature valid and all fingerprints match
   1 = invalid, missing, or tampered
   2 = could not run (missing dependency)
===============================================================================
"""

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:
    print("Missing dependency. Run: pip install -r tools/requirements.txt")
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content"
MANIFEST_PATH = CONTENT_DIR / "index.json"
PUBLIC_KEY_PATH = CONTENT_DIR / "pubkey.txt"


def bytes_to_sign(manifest):
    """Rebuild the exact bytes that were signed.

    This must stay identical to the same function in build_and_sign_manifest.py.
    See the explanation there for why each rule matters.
    """
    unsigned = {key: value for key, value in manifest.items() if key != "signature"}
    return json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def load_public_key():
    """The public key can only verify a signature, never create one, so it is
    safe to publish — which is why it lives in the repository and ships in the
    app."""
    key_base64 = os.environ.get("UNTRACK_PUBLIC_KEY")

    if not key_base64 and PUBLIC_KEY_PATH.exists():
        key_base64 = PUBLIC_KEY_PATH.read_text(encoding="utf-8").strip()

    if not key_base64:
        return None

    return Ed25519PublicKey.from_public_bytes(base64.b64decode(key_base64))


def check_signature(public_key, manifest):
    """Question 1: was this manifest signed by the matching private key?"""
    signature_field = manifest.get("signature", "")

    if not signature_field.startswith("ed25519:"):
        print("Manifest signature is missing or malformed.")
        return False

    signature = base64.b64decode(signature_field.split(":", 1)[1])

    try:
        public_key.verify(signature, bytes_to_sign(manifest))
    except InvalidSignature:
        print("✗ Signature INVALID — this manifest was not signed by the expected key.")
        return False

    return True


def check_file_fingerprints(manifest):
    """Question 2: does every listed file still match its recorded fingerprint?"""
    problem_count = 0

    for entry in manifest.get("files", []):
        path = CONTENT_DIR / entry["path"]

        if not path.exists():
            print(f"✗ missing file: {entry['path']}")
            problem_count += 1
            continue

        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            print(f"✗ changed since signing: {entry['path']}")
            problem_count += 1

    return problem_count


def main():
    if not MANIFEST_PATH.exists():
        print(f"{MANIFEST_PATH.relative_to(REPO_ROOT)} not found. "
              f"Run tools/build_and_sign_manifest.py first.")
        return 1

    public_key = load_public_key()
    if public_key is None:
        print("No public key found (content/pubkey.txt or UNTRACK_PUBLIC_KEY).")
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    if not check_signature(public_key, manifest):
        return 1

    problem_count = check_file_fingerprints(manifest)
    if problem_count:
        print(f"✗ {problem_count} file problem(s).")
        return 1

    file_count = len(manifest.get("files", []))
    print(f"✓ Signature valid and {file_count} file fingerprint(s) match "
          f"(contentVersion {manifest.get('contentVersion')}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
