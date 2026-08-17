# Publishing a suggestion

How a tip gets from an idea onto someone's phone, and what to do when it does
not.

> **Just want the routine?** [BEFORE-YOU-PUSH.md](BEFORE-YOU-PUSH.md) is the
> four commands and nothing else. This document is the long version, and Part 2
> is the troubleshooting guide you will want when something does not appear.

Everything here happens in this repository. The app lives in `Untrack`, and its
own playbook covers building and releasing the APK — you need it only when a tip
requires a *code* change, which is rarer than it sounds and is explained below.

---

## The one thing worth knowing first

**Content ships without an app release. Detection does not.**

A merged suggestion reaches phones within minutes, through the signed catalog on
a CDN. But the app can only *detect* an installed app if that package is listed
in `<queries>` in its `AndroidManifest.xml`, and that list is compiled into the
APK.

So for an app already covered, publishing is a content change and you are done.
For an app that is new to the catalog, the tip is still reachable — through
**+ Add an app** in the scan screen, which searches the whole catalog — but it
will not be found automatically until the next app release.

That is a deliberate trade, not a bug: the alternative is `QUERY_ALL_PACKAGES`,
a permission Google Play restricts to apps whose core purpose requires it.

**This is the seam between the two repositories.** You cannot fix it from here,
and you do not need to remember to report it: the app repository runs a daily
check that fails when a catalogued app is missing from its `<queries>` list.

---

# Part 1 — Publishing

Ordered. Each step assumes the previous one passed.

## 1. Scaffold the file, or open the existing one

For an app or device never covered before:

```bash
python3 tools/new_suggestion.py app --publisher meta --package com.whatsapp --name WhatsApp
python3 tools/new_suggestion.py device --manufacturer samsung --skin oneui
```

Run it with no arguments to be prompted. For an app already in `content/apps/`,
add another entry to its `suggestions` array.

## 2. Write the tip

Required, in English: `title`, `why`, `tradeoffs`, `steps`. Each is an object
keyed by language — `{"en": "..."}` — even though there is only one language.
The wrapper is kept so adding a language later is a schema change rather than a
rewrite of every file, and the schema refuses any other key today.

Two identity fields, and the distinction matters:

| Field | Rule |
|---|---|
| `uuid` | Assigned once, **never changed**. The app remembers completion by uuid. Changing one silently resets that person's progress. |
| `id` | Readable label, unique within its file. Safe to rename; nothing keys on it. |

`tools/check_uuid_stability.py` runs in CI and fails the build if a published
uuid disappears. It cannot tell a rename from a deletion, so treat it as final.

Write `steps` as what someone taps, in order, in the words the app itself uses.
`why` should say what changes, not why they should feel bad.

## 3. Add a visual guide, if you have one

Optional. The written steps are the suggestion; a guide is an extra.

1. Record with the **phone's own screen recorder**, on a throwaway account with
   notifications off. Keep it to the one setting, under twenty seconds.
2. Convert to **animated WebP** — roughly 480px wide, 12 fps, looping, under
   2 MB. Any tool that produces animated WebP will do; see
   [media/README.md](media/README.md).
3. Save it as `media/<package-or-slug>/<suggestion-id>.webp`.
4. **Look at the result.** Names, avatars, message previews and the status bar
   are the usual leaks. Nothing is redacted automatically and a guide is
   published permanently.
5. Take the fingerprint and add the block:

```bash
shasum -a 256 media/com.instagram.android/ig-private-account.webp
```

```json
      "media": {
        "type": "webp",
        "src": "com.instagram.android/ig-private-account.webp",
        "sha256": "<from shasum>"
      },
```

`src` is relative to `media/`, so it does **not** start with `media/`.

> **Check it actually animates.** Some encoders collapse low-motion footage —
> which a settings walkthrough is — into a single still frame that still carries
> a `.webp` extension. CI catches this, but noticing it now is quicker.

## 4. Run the local checks

**Two commands, before every push. Nothing else.**

```bash
python3 tools/validate_content.py --headroom
python3 tools/check_uuid_stability.py --base origin/main
```

These are the same checks CI runs, so a pass here means a green pipeline. They
take about a second and save a round trip.

What the first one covers, so you are not double-checking it by hand:

| | |
|---|---|
| Schema | field names, types, English present, `category` from the allowed set |
| Folder structure | `apps/<publisher>/<package>.json`, `device/<maker>/<skin>.json` |
| Filenames | an app file's name matches the `package` inside it |
| Identifiers | `id` unique per file, `uuid` unique across the whole catalog |
| Guides | file committed, under 2 MB, **sha256 matches**, and **more than one animation frame** |
| Icons | committed, right extension, under 100 KB |
| App limits | per-file, file count, total size, manifest size |
| Paths | URL-safe — a `?` in a filename would break the download address |
| `--headroom` | how close the catalog is to each limit |

The second one is separate because it asks a question the first cannot: not
"is this file correct" but "did this change take away a uuid somebody's phone
has already recorded progress against". It needs the previous state to compare
with, which is why it takes a base.

**Never edit `content/index.json`.** It is generated and signed by CI, which
rebuilds it from the content files on every publish — so a hand edit is
overwritten at best and published unverifiable at worst. CI rejects any change
that touches it.

**Do not sign locally either.** `contentVersion` increments on every signing run,
so a local signature puts this working copy ahead of what CI will produce and
guarantees a conflict on push.

## 5. Commit and push

```bash
git add -A
git commit -m "Add <what> for <app>"
git pull --rebase     # see A in Part 2 — expect this
git push
```

## 6. What happens automatically

```
push to main
  │
  ├─ validate-content.yml ── schema · media · sizes · uuid stability
  │
  └─ release-content.yml  ── (only on content/apps/** or content/device/**)
       ├─ validate again
       ├─ build_and_sign_manifest.py  → content/index.json, Ed25519 signed
       ├─ verify_manifest.py          → checks its own output
       ├─ commits it back to main as "untrack-bot" with [skip ci]
       └─ purges the CDN, files first, manifest last
```

That bot commit is why your next push needs a rebase. It is also why
`contentVersion` increments without you editing it.

**The purge is what makes this fast.** jsDelivr caches a branch reference for
around twelve hours, and the app cannot tell a stale answer from a current one —
a cached response is a valid response, so its fallback to raw.githubusercontent
never fires. Before the purge step existed, a merged tip could take half a day to
reach anyone, and there was no way to tell that from a broken pipeline.

The manifest is purged **last** on purpose. It names the files and their hashes,
so purging it first leaves a window where a phone reads new hashes against
cached old files, fails every check, and is shown an error for a release that
was fine.

## 7. Confirm it reached a phone

The app refuses any manifest that is not **strictly newer** than what it has, so
`contentVersion` must have increased.

```bash
echo -n "jsDelivr: "; curl -s "https://cdn.jsdelivr.net/gh/MrCybermann/untrack-content@main/content/index.json" | grep -o '"contentVersion":[0-9]*'
echo -n "raw:      "; curl -s "https://raw.githubusercontent.com/MrCybermann/untrack-content/main/content/index.json" | grep -o '"contentVersion":[0-9]*'
```

Both should agree within seconds of the workflow finishing. **If they disagree,
the purge step did not do its job** — check the Actions log before suspecting
anything else.

On the phone: pull down on the scan list. Rate limits are **5 seconds** between
pulls and **30 minutes** between automatic checks on open.

---

# Part 2 — When it does not work

Start from the symptom.

| What you see | Go to |
|---|---|
| `! [rejected] main -> main (fetch first)` | [A](#a-push-rejected) |
| Tip merged, CI green, not on the phone | [B](#b-tip-does-not-appear-on-the-phone) |
| "This guide couldn't be verified" | [C](#c-guide-fails-verification) |
| "The guide didn't load" | [D](#d-guide-does-not-load) |
| Guide plays as a frozen image | [E](#e-guide-is-a-still-image) |
| Someone's completed items came back | [F](#f-progress-reset) |
| CI validation failed | [G](#g-ci-validation-failed) |
| Signing workflow did not run | [H](#h-signing-workflow-did-not-run) |

---

### A. Push rejected

**Cause.** Almost always `release-content.yml` committing the signed
`content/index.json` back to main after your last push. The remote is one commit
ahead and it is your own automation.

```bash
git pull --rebase
git push
```

If it conflicts, it will be on `content/index.json` and nothing else. Take
either side — the next push regenerates it:

```bash
git checkout --theirs content/index.json
git add content/index.json
git rebase --continue
```

---

### B. Tip does not appear on the phone

Work down. Each step rules out one thing.

1. **Did `contentVersion` actually increase?** Run the pair of `curl`s from
   step 7. An unchanged version means the signing workflow did not run — go to
   [H](#h-signing-workflow-did-not-run).

2. **Do the two sources agree?** If jsDelivr is behind raw, the purge failed.
   Force it by hand:

   ```bash
   curl -s "https://purge.jsdelivr.net/gh/MrCybermann/untrack-content@main/content/index.json"
   ```

   Purge the changed tip files too, and the manifest last.

3. **Is the phone rate-limited?** 30 minutes between automatic checks. Pull down
   on the list to force one — that path allows a check every 5 seconds.

4. **Is the app new to the catalog?** Then the tip exists but cannot be found by
   scanning until the next app release. Search for it under **+ Add an app**. If
   it appears there, the content is fine and this is the release gate described
   at the top, not a fault.

5. **Is the suggestion filtered out?** Check `regions` and `audience`. A tip with
   `"regions": ["DE"]` will not show on a phone set to another country, and
   `"audience": ["parental"]` only shows on a phone configured as a child's.

**The authority on what was published is the repository, not either CDN:**

```bash
git show origin/main:content/index.json | grep -o '"contentVersion":[0-9]*'
```

---

### C. Guide fails verification

The app downloaded the file and its SHA-256 did not match the `sha256` in the
suggestion. It refuses rather than handing unverified bytes to the platform
image decoder.

**Almost always:** the `.webp` was replaced without updating the hash.

```bash
shasum -a 256 media/com.instagram.android/ig-private-account.webp
grep -n sha256 content/apps/meta/com.instagram.android.json
```

If they differ, update the JSON and push. `tools/validate_content.py` catches
this locally, and `validate-content.yml` catches it on any change to `content/**`
or `media/**` — including a commit that touches only the `.webp`.

If the hashes *do* match locally, you are being served a different file than the
one you committed — the media purge did not happen. See [B](#b-tip-does-not-appear-on-the-phone) step 2.

---

### D. Guide does not load

No file arrived. In order of likelihood: no connection, the guide has not
reached the CDN yet, or `src` points somewhere that does not exist.

```bash
curl -sI "https://cdn.jsdelivr.net/gh/MrCybermann/untrack-content@main/media/com.instagram.android/ig-private-account.webp" | head -1
```

A `200` means the file is being served and the problem is on the phone. A `404`
means `src` is wrong or the file was never committed. Remember `src` is relative
to `media/` and must not start with `media/`.

---

### E. Guide is a still image

The animation was collapsed at encoding time. `libwebp_anim` does this to
low-motion footage — exactly what a settings walkthrough is — while encoding
full-motion test footage perfectly, so nothing looks wrong until someone opens
the tip.

**Count the frames yourself.** Do not trust `ffprobe`, which misreports animated
WebP; it described a correct 96-frame file as a single frame of size 0×0.

```bash
python3 -c "
import struct,sys,pathlib
d=pathlib.Path(sys.argv[1]).read_bytes(); off=12; n=0
while off+8<=len(d):
    s=struct.unpack('<I',d[off+4:off+8])[0]
    n+= d[off:off+4]==b'ANMF'; off+=8+s+(s&1)
print(n,'animation frames')" media/com.instagram.android/ig-private-account.webp
```

Fewer than two means re-encode with a different tool. CI enforces this, so it
cannot reach a phone — but it can waste a round trip.

---

### F. Progress reset

A `uuid` changed or disappeared. The app keys completion by uuid, so a changed
one is a different suggestion as far as the phone is concerned.

```bash
python3 tools/check_uuid_stability.py --base origin/main
```

There is no repair once published — restore the original uuid and the
completions come back, because nothing was deleted, only orphaned.

---

### G. CI validation failed

The message names the file and the problem. The common ones:

| Message | Meaning |
|---|---|
| `is declared but not committed under media/` | `src` points at a file not in the repo. Check for a `media/` prefix in `src`. |
| `does not match its sha256` | See [C](#c-guide-fails-verification). |
| `has N animation frame(s)` | See [E](#e-guide-is-a-still-image). |
| uuid check failed | See [F](#f-progress-reset). |

Two checks that used to fail here now fail in the app repository instead —
`<queries>` coverage and the app-versus-Worker field limits. Both compare this
catalog against something only that repository has, so they run there, against
what this one publishes.

---

### H. Signing workflow did not run

`release-content.yml` triggers **only** on `content/apps/**` and
`content/device/**`. Changing a media file, a tool, or a document does not
re-sign anything, and does not need to.

If it should have run and did not:

1. Check the Actions tab for a skipped or failed run.
2. Confirm the repository secret `UNTRACK_SIGNING_KEY` still exists — the
   workflow fails at the signing step without it.
3. Confirm `permissions: contents: write` is still in the workflow, or the bot
   cannot push the manifest back.

The bot's own commit carries `[skip ci]` deliberately, so it does not trigger
another signing run and loop.

---

## Known gap

**Nothing checks what the CDN actually serves.** CI verifies a guide at merge
time and the app verifies it at download time, but the interval between is
unobserved. A wrong file there shows up as [C](#c-guide-fails-verification) on a
phone and as nothing at all in the repository. The purge step shrinks that
interval to seconds; it does not close it.
