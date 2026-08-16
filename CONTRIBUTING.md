# Contributing to Untrack

Thank you for helping people protect their privacy. The most valuable contribution is **privacy suggestions** — for a phone/manufacturer or for a specific app. You don't need to know Android development to contribute: just how to change a privacy setting, and how to describe it clearly.

## The idea

Every suggestion is a small, structured entry in a JSON file under `content/`. The app downloads these (signed and verified) and shows them to users.

> **Don't want to touch git?** A **Contribute** tab is coming inside the app, where you can submit a tip through a simple form — no GitHub account needed. Submissions arrive here as issues for review. This page covers the pull-request path, for anyone comfortable editing files directly. Either way, every submission is reviewed by a maintainer before it reaches users.

> **Maintainers:** [PLAYBOOK.md](PLAYBOOK.md) has the full publishing sequence and a debugging guide.

## Where files live

Content is organized by **publisher** (apps) and **manufacturer** (device):

```
content/apps/<publisher>/<package-id>.json     e.g. content/apps/meta/com.instagram.android.json
content/device/<manufacturer>/<skin>.json       e.g. content/device/google/pixel.json
```

The folder name is a lowercase slug (letters, numbers, hyphens). A new publisher or manufacturer folder is created automatically the moment you add the first file in it.

## The easy way: scaffold it

```
python tools/new_suggestion.py app --publisher meta --package com.whatsapp --name WhatsApp
python tools/new_suggestion.py device --manufacturer samsung --skin oneui
```

This creates a correctly-placed file pre-filled with a placeholder suggestion. Then fill in the TODOs. (Run it with no arguments to be prompted step by step.)

## What a suggestion looks like

```json
{
  "uuid": "9c929e75-bc86-4edf-afcd-23fed94057a2",
  "id": "ig-private-account",
  "impact": "high",
  "category": "account-visibility",
  "audience": ["all"],
  "regions": ["*"],
  "title":     { "en": "Set your account to private", "ar": "…" },
  "why":       { "en": "What happens when it's on vs off, and why it matters.", "ar": "…" },
  "tradeoffs": { "en": "What you give up, if anything.", "ar": "…" },
  "steps":     { "en": ["Step 1", "Step 2"], "ar": ["…", "…"] },
  "settingsIntent": "android.settings.PRIVACY_SETTINGS",
  "media": { "type": "webp", "src": "com.instagram.android/ig-private-account.webp",
             "caption": { "en": "…", "ar": "…" } },
  "reference": "https://official-source-if-any"
}
```

### Field guide

Every suggestion carries **two identifiers**, and the difference matters:

- **uuid** — the permanent identity. The app uses it to remember which suggestions a person has ticked off, so **never change or reuse one**: changing it silently un-ticks that suggestion for every user. `new_suggestion.py` generates one for you, and the app proposes one on each submission. If you're writing a file by hand, generate one with `python3 -c "import uuid; print(uuid.uuid4())"`. CI blocks any pull request that changes or removes a published uuid, so if you see that check fail, you've probably edited one by accident — restore it and rename the `id` instead.
- **id** — a human-readable label, unique within its own file. It exists purely to make diffs and reviews readable, and is **safe to rename** whenever a clearer name comes along. Lowercase letters, numbers, and hyphens.

The rest:

- **impact** — `high`, `medium`, or `low`. It drives the user's privacy score, so be honest.
- **category** — short grouping label (e.g. `advertising`, `account-visibility`, `parental`).
- **audience** — `["all"]` for everyone, `["parental"]` to show only in child-user mode, or both.
- **regions** — `["*"]` for everywhere, or ISO codes like `["EU"]` / `["DE","FR"]` when a setting is region-specific.
- **title / why / tradeoffs / steps** — user-facing text, in English. Each is an object keyed by language (`{"en": "..."}`) even though there is only one language; see below.
- **settingsIntent** — *(device suggestions only, optional)* an Android settings action to deep-link the user to the right screen. Only add one if you know it opens the correct place.
- **media** — *(optional)* a visual guide (see below).
- **reference** — *(optional)* a link to an official help page backing the steps.

### App-level fields (top of an app file)

- **package** — the app's package id. The filename must be `<package>.json`.
- **appName**, **publisher** — display names.
- **icon** — *(optional)* a small logo (`.webp`/`.png`, ≤ 100 KB) used only when showing the app in search before it's installed. Installed apps use the icon Android already provides, so a logo is usually unnecessary. App logos are trademarks of their owners — only add one where such identifying use is appropriate; it is **not** covered by the content license.

### Writing good suggestions

- Verify the steps against the **current version** of the app or OS — UIs change.
- Explain the *why* in plain language: what data the setting affects when on vs off.
- Be honest about trade-offs so users can make an informed choice.
- Keep steps short and in order.

## Visual guides (media)

Optional but great. Rules:

- Format: **animated WebP**, and nothing else. Roughly 480px wide, 12 fps, under 2 MB.
- Record with the phone's own screen recorder, then convert with any tool that produces animated WebP. See [media/README.md](media/README.md) for the settings and the naming convention.
- Record on a **clean test profile with no personal information visible** (no real names, contacts, or photos). Nothing is redacted automatically, and a guide is published permanently.
- CI checks four things: the file is committed, it is ≤ 2 MB, its `sha256` matches the one in the suggestion, and it has more than one animation frame.

## Before you open a PR

1. Run the validator locally: `python tools/validate_content.py` (see [tools/README.md](tools/README.md) for setup).
2. Do **not** edit `content/index.json` — it's generated and signed automatically on merge.
3. Open the PR and fill in the template. CI validates schema, folder structure, and media/icon caps. A maintainer reviews and merges.

## Licensing of contributions

By contributing suggestion text and guide media you agree to license them under **CC-BY-SA 4.0**. Code contributions are under **GPLv3**. App names and logos remain the trademarks of their respective owners.
