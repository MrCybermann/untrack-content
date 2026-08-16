#!/usr/bin/env python3
"""
===============================================================================
 generate_keys.py — create the maintainer's signing keypair (run once)
===============================================================================

 WHAT THIS DOES
 Creates the pair of keys that protect the tip catalog:

   PRIVATE key — the stamp. Only you hold it. It creates signatures.
   PUBLIC key  — the pattern. Everyone holds it. It only checks signatures.

 That asymmetry is the whole trick: publishing the public key lets every phone
 verify the catalog came from you, while giving nobody the ability to forge it.

 WHAT TO DO WITH THE OUTPUT
   PRIVATE key → GitHub repository secret named UNTRACK_SIGNING_KEY,
                 plus a copy in your password manager. Never commit it.
   PUBLIC key  → content/pubkey.txt (committed), and later embedded in the app.

 WHY IT PRINTS INSTEAD OF SAVING
 Nothing is written to disk on purpose. A private key sitting in the project
 folder is a private key that can be committed by accident — and a leaked
 signing key means anyone can publish "privacy advice" in your name.

 RUN IT ONCE
 Generating a new pair invalidates the old one: apps carrying the old public key
 will correctly reject anything signed with the new private key until they
 update.

 To rotate after a suspected leak: generate a new pair, replace the
 UNTRACK_SIGNING_KEY secret, commit the new content/pubkey.txt, and release an
 app update containing the new public key.
===============================================================================
"""

import base64
import sys

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    print("Missing dependency. Run: pip install -r tools/requirements.txt")
    sys.exit(2)


def to_base64(key_bytes):
    """Keys are raw bytes; base64 turns them into text you can paste."""
    return base64.b64encode(key_bytes).decode()


def main():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    print("Ed25519 keypair generated.\n")
    print("PRIVATE KEY  — secret. Save as GitHub secret UNTRACK_SIGNING_KEY. Never commit:")
    print("  " + to_base64(private_bytes) + "\n")
    print("PUBLIC KEY   — safe to publish. Save to content/pubkey.txt and embed in the app:")
    print("  " + to_base64(public_bytes))


if __name__ == "__main__":
    main()
