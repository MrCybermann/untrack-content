#!/usr/bin/env python3
"""
===============================================================================
 new_suggestion.py — start a new content file in the right place
===============================================================================

 WHAT THIS DOES
 Creates a correctly-named, correctly-located JSON file, pre-filled with one
 placeholder suggestion. Fill in the TODOs, run the validator, and open a pull
 request.

 WHY IT EXISTS
 Content lives in a specific folder structure, and app files must be named after
 their package id. Getting either wrong means the validator rejects the file —
 a frustrating first experience for someone who just wants to share a useful
 tip. This removes that whole class of mistake.

 USAGE
     python tools/new_suggestion.py app --publisher meta --package com.whatsapp --name WhatsApp
     python tools/new_suggestion.py device --manufacturer samsung --skin oneui

 Run it with no arguments to be prompted step by step.

 EXIT CODES
   0 = file created
   1 = a file already exists there (nothing was overwritten)
   2 = bad input
===============================================================================
"""

import argparse
import json
import re
import sys
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content"

# Folder names must be lowercase slugs, e.g. "meta", "samsung".
FOLDER_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def text(english):
    """Every user-facing field is an object keyed by language.

    The catalog is English only, so this always produces one key. The wrapper is
    kept rather than a bare string so that adding a language later is a schema
    change rather than a rewrite of every file — see content/schema.
    """
    return {"en": english}


def placeholder_suggestion():
    """One example suggestion with every required field present, so the file
    validates as soon as the TODOs are replaced with real text.

    The uuid is generated fresh here and should be left alone: it is the
    permanent identity the app uses to remember what a user has ticked off.
    The `id` beneath it is just a readable label, and you should rename it.
    """
    return {
        "uuid": str(uuid.uuid4()),
        "id": "todo-suggestion-id",
        "impact": "medium",
        "category": "TODO",
        "audience": ["all"],
        "regions": ["*"],
        "title": text("TODO: short title"),
        "why": text("TODO: what it does on vs off, and why it matters"),
        "tradeoffs": text("TODO: what you give up, if anything"),
        "steps": {"en": ["TODO: step 1", "TODO: step 2"]},
    }


def ask(question, default=None):
    """Prompt the user, offering a default in brackets."""
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer or (default or "")


def build_app_file(args):
    """content/apps/<publisher>/<package-id>.json"""
    publisher = args.publisher or ask("Publisher slug (e.g. meta)")
    package_id = args.package or ask("Package id (e.g. com.whatsapp)")
    app_name = args.name or ask("App name (e.g. WhatsApp)", package_id)

    if not FOLDER_SLUG_PATTERN.match(publisher):
        print("Publisher must be lowercase letters, numbers, or hyphens.")
        return None, None

    path = CONTENT_DIR / "apps" / publisher / f"{package_id}.json"
    document = {
        "schemaVersion": 1,
        "package": package_id,
        "appName": app_name,
        "publisher": publisher,
        "suggestions": [placeholder_suggestion()],
    }
    return path, document


def build_device_file(args):
    """content/device/<manufacturer>/<skin>.json"""
    manufacturer = args.manufacturer or ask("Manufacturer slug (e.g. samsung)")
    skin = args.skin or ask("Skin / file name (e.g. oneui)")

    if not FOLDER_SLUG_PATTERN.match(manufacturer):
        print("Manufacturer must be lowercase letters, numbers, or hyphens.")
        return None, None

    path = CONTENT_DIR / "device" / manufacturer / f"{skin}.json"
    document = {
        "schemaVersion": 1,
        # osMin / osMax describe the Android versions in which THIS SETTING
        # exists — not the versions the app runs on. Leave them null unless you
        # know the setting appeared in, or was removed by, a specific version.
        "target": {"manufacturer": manufacturer, "osMin": None, "osMax": None},
        "suggestions": [placeholder_suggestion()],
    }
    return path, document


def main():
    parser = argparse.ArgumentParser(description="Scaffold a new Untrack content file.")
    parser.add_argument("type", nargs="?", choices=["app", "device"])
    parser.add_argument("--publisher", help="app files: publisher folder, e.g. meta")
    parser.add_argument("--package", help="app files: package id, e.g. com.whatsapp")
    parser.add_argument("--name", help="app files: display name, e.g. WhatsApp")
    parser.add_argument("--manufacturer", help="device files: maker folder, e.g. samsung")
    parser.add_argument("--skin", help="device files: file name, e.g. oneui")
    args = parser.parse_args()

    file_type = args.type or ask("Type (app/device)", "app")

    if file_type == "app":
        path, document = build_app_file(args)
    elif file_type == "device":
        path, document = build_device_file(args)
    else:
        print("Unknown type; use 'app' or 'device'.")
        return 2

    if path is None:
        return 2

    # Never overwrite: someone else's work could be in there.
    if path.exists():
        print(f"Refusing to overwrite an existing file: {path.relative_to(REPO_ROOT)}")
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"✓ Created {path.relative_to(REPO_ROOT)}")
    print("  Fill in the TODOs, then run: python tools/validate_content.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
