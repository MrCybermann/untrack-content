# Untrack — the tip catalog

The privacy suggestions the [Untrack](https://untrack.mjcyberwise.com) Android app
shows: what to change, why it matters, what it costs you, and the steps.

This repository is the product. The app is a reader for it.

> **About to change a tip?** [BEFORE-YOU-PUSH.md](BEFORE-YOU-PUSH.md) is the
> four-step routine — the same four whether you are editing an existing tip or
> adding a new app.

## What is here

```
content/
  apps/<publisher>/<package-id>.json    apps/meta/com.instagram.android.json
  device/<manufacturer>/<skin>.json     device/google/pixel.json
  schema/suggestion.schema.json         the rules every file must follow
  pubkey.txt                            the key phones use to check the seal
  index.json                            the signed list (generated — never edit)
media/                                  visual guides, animated WebP
tools/                                  validation and signing
```

## How a tip reaches a phone

1. Someone opens a pull request, or submits one from inside the app.
2. CI checks it against the schema and against every uuid already published.
3. A maintainer reviews it and merges.
4. CI signs `index.json` with an Ed25519 key and commits it.
5. Phones fetch the signed catalog from a CDN, verify the signature against a
   public key compiled into the app, and show the new tip — **without an app
   update**.

That last point is why this repository exists separately. Tips go stale when apps
redesign their settings, and waiting on a store release to fix a wrong
instruction would mean shipping wrong instructions.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

```bash
pip install -r tools/requirements.txt
python3 tools/new_suggestion.py app --publisher meta --package com.example.app --name "Example"
# fill in the TODOs
python3 tools/validate_content.py
```

Then open a pull request. You do not need to touch the app, or know any Kotlin.

**What makes a good tip:** steps verified against the current version of the app
or OS, an honest impact rating, and the trade-off stated plainly. A suggestion
that says what you give up is worth more than one that only says what you gain —
someone who follows advice and then finds a feature broken will not follow the
next piece.

**Two identifiers, doing different jobs.** Every suggestion has a `uuid` that
must never change — the app remembers what a person ticked off by it — and an
`id` that is a readable label and can be renamed freely. CI fails a pull request
that changes or removes a published `uuid`, because that failure has no error
message and no visible symptom: people just quietly lose their progress.

## Why the catalog is signed

The app downloads these files and tells people to change settings based on them.
If someone could substitute their own file, they could feed harmful advice to
every user through a channel those users trust.

So `index.json` lists every file with a SHA-256 fingerprint and carries an
Ed25519 signature over that list. The app checks the signature against a key it
was compiled with, then checks each file against its fingerprint. Tamper with
either and verification fails, and the app keeps the last catalog it trusted.

**The private key is never in this repository.** It lives in one GitHub secret
and one password manager. `content/pubkey.txt` is the public half — it can only
verify, never sign, which is why publishing it costs nothing.

This is also why the app's own source repository can be private while this one is
public: trust comes from the key, not from where the file was served.

## Licence

Suggestion content (`content/`, `media/`) is licensed
[CC BY-SA 4.0](LICENSE-CONTENT.md). The tooling here is part of the Untrack
project and is GPLv3, like the app.

App names and logos are trademarks of their respective owners.
