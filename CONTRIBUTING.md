# Contributing a privacy tip

Thank you for helping people protect their privacy. The most valuable
contribution is a **privacy suggestion** — for a phone or manufacturer, or for a
specific app. You don't need to know Android development: just how to change a
privacy setting, and how to describe it clearly.

## The idea

Every suggestion is a small, structured entry in a JSON file under `content/`.
The app downloads these, verifies an Ed25519 signature over the whole set, and
shows them to people.

> **Don't want to touch git?** The **Contribute** tab inside the app submits a
> tip through a form — no GitHub account needed. Submissions arrive here as
> issues for review. This page covers the pull-request path, for anyone
> comfortable editing files directly. Either way, a maintainer reviews every
> submission before it reaches anyone.

> **Maintainers:** [PUBLISHING.md](PUBLISHING.md) has the full publishing
> sequence and a debugging guide.

## Where files live

Content is organised by **publisher** (apps) and **manufacturer** (device):

```
content/apps/<publisher>/<package-id>.json     e.g. content/apps/meta/com.instagram.android.json
content/device/<manufacturer>/<skin>.json      e.g. content/device/google/pixel.json
```

The folder name is a lowercase slug (letters, numbers, hyphens). A new publisher
or manufacturer folder is created the moment you add the first file in it.

## The easy way: scaffold it

```bash
python3 tools/new_suggestion.py app --publisher meta --package com.whatsapp --name WhatsApp
python3 tools/new_suggestion.py device --manufacturer samsung --skin oneui
```

This creates a correctly-placed file pre-filled with a placeholder suggestion.
Then fill in the TODOs. Run it with no arguments to be prompted step by step.

## What a suggestion looks like

```json
{
  "uuid": "9c929e75-bc86-4edf-afcd-23fed94057a2",
  "id": "ig-private-account",
  "impact": "high",
  "category": "account-visibility",
  "audience": ["all"],
  "regions": ["*"],
  "title":     { "en": "Set your account to private" },
  "why":       { "en": "What happens when it's on vs off, and why it matters." },
  "tradeoffs": { "en": "What you give up, if anything." },
  "steps":     { "en": ["Step 1", "Step 2"] },
  "settingsIntent": "android.settings.PRIVACY_SETTINGS",
  "media": { "type": "webp", "src": "com.instagram.android/ig-private-account.webp",
             "caption": { "en": "…" } },
  "reference": "https://official-source-if-any"
}
```

The catalog is **English only**. Text fields are still objects keyed by language
so that adding one later is a schema change rather than a rewrite of every file;
the schema refuses any key other than `en` today.

### Field guide

Every suggestion carries **two identifiers**, and the difference matters:

- **uuid** — the permanent identity. The app uses it to remember which
  suggestions a person has ticked off, so **never change or reuse one**:
  changing it silently un-ticks that suggestion for everyone. `new_suggestion.py`
  generates one for you, and the app proposes one on each submission. Writing a
  file by hand? `python3 -c "import uuid; print(uuid.uuid4())"`. CI blocks any
  pull request that changes or removes a published uuid — if you see that check
  fail, you have probably edited one by accident. Restore it and rename the `id`
  instead.
- **id** — a human-readable label, unique within its own file. It exists purely
  to make diffs and reviews readable, and is **safe to rename** whenever a
  clearer name comes along. Lowercase letters, numbers and hyphens.

The rest:

- **impact** — `high`, `medium` or `low`. It drives the privacy score, so be
  honest.
- **category** — short grouping label (e.g. `advertising`, `account-visibility`,
  `parental`).
- **audience** — `["all"]` for everyone, `["parental"]` to show only in child-user
  mode, or both.
- **regions** — `["*"]` for everywhere, or ISO codes like `["EU"]` or
  `["DE","FR"]` when a setting is region-specific.
- **title / why / tradeoffs / steps** — the text people read.
- **settingsIntent** — *(device suggestions only, optional)* an Android settings
  action to deep-link to the right screen. Only add one if you know it opens the
  correct place.
- **media** — *(optional)* a visual guide, see below.
- **reference** — *(optional)* a link to an official help page backing the steps.

### App-level fields (top of an app file)

- **package** — the app's package id. The filename must be `<package>.json`.
- **appName**, **publisher** — display names.
- **icon** — *(optional)* a small logo (`.webp`/`.png`, ≤ 100 KB) used only when
  showing the app in search before it is installed. Installed apps use the icon
  Android already provides, so a logo is usually unnecessary. App logos are
  trademarks of their owners — only add one where such identifying use is
  appropriate; it is **not** covered by the content licence.

### Writing good suggestions

- Verify the steps against the **current version** of the app or OS. UIs change.
- Explain the *why* in plain language: what data the setting affects when on
  versus off.
- Say what changes, not why someone should feel bad. The app names a problem and
  hands over a fix; it does not trade on unease.
- Be honest about trade-offs so people can make an informed choice.
- Keep steps short and in order, in the words the app itself uses.

## Visual guides (media)

Optional but great. Rules:

- Format: **animated WebP**, and nothing else. Roughly 480px wide, 12 fps, under
  2 MB.
- Record with the phone's own screen recorder, then convert with any tool that
  produces animated WebP. See [media/README.md](media/README.md) for the settings
  and the naming convention.
- Record on a **clean test profile with no personal information visible** — no
  real names, contacts or photos. Nothing is redacted automatically, and a guide
  is published permanently.
- CI checks four things: the file is committed, it is ≤ 2 MB, its `sha256`
  matches the one in the suggestion, and it has more than one animation frame.

## Before you open a pull request

1. Validate locally:

   ```bash
   pip install -r tools/requirements.txt
   python3 tools/validate_content.py
   ```

   **Python 3.9 or newer.** That is the floor because it is what macOS shipped
   for years, and the tools are written to stay inside it — CI runs a newer
   version, so anything relying on newer syntax would pass there and fail for
   you, which is the wrong way round for a check whose whole job is to run
   before you push. If one of these scripts fails with a `TypeError` about
   annotations or an unfamiliar syntax error, that is a bug here, not a reason
   to upgrade. Please report it.

2. Do **not** edit `content/index.json`. It is generated and signed
   automatically on merge, and editing it by hand only guarantees a conflict.
3. Open the pull request and fill in the template. CI validates the schema,
   folder structure, uuid stability and the media caps. A maintainer reviews and
   merges.

## Licensing of contributions

By contributing suggestion text and guide media you agree to license them under
**CC-BY-SA 4.0**. The app's code, in the other repository, is under **GPLv3**.
App names and logos remain the trademarks of their respective owners.
