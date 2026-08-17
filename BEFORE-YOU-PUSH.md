# Before you push

Four steps. The same four whether you edited an existing tip or added a new app.

Run everything from the repository root.

---

## 1. Fetch, so the uuid check has something real to compare against

```bash
git fetch origin
```

Step 3 compares your change against `origin/main`. A stale reference gives a
meaningless answer rather than an error, which is the worst kind.

## 2. Validate

```bash
python3 tools/validate_content.py --headroom
```

Expect `✓ N content file(s) valid.` and a headroom table. Every problem is
printed with the file and the reason.

<details>
<summary>What this already checks, so you don't check it by hand</summary>

| | |
|---|---|
| Schema | field names, types, text present, `category` from the allowed set |
| Folder structure | `apps/<publisher>/<package>.json`, `device/<maker>/<skin>.json` |
| Filenames | an app file's name matches the `package` inside it |
| Identifiers | `id` unique within its file, `uuid` unique across the catalog |
| Guides | committed, under 2 MB, **sha256 matches**, and **more than one animation frame** |
| Icons | committed, right extension, under 100 KB |
| App limits | per-file size, file count, total size, manifest size |
| Paths | URL-safe — a `?` in a filename silently breaks the download address |

`--headroom` prints how close the catalog is to each limit. CI opens an issue
past 80%, so you do not have to watch it.

</details>

## 3. Check no uuid was lost

```bash
python3 tools/check_uuid_stability.py --base origin/main
```

A separate command because it asks a different question: not "is this file
correct" but "does this change take away a `uuid` that phones have already
recorded progress against".

If it fails, restore the original uuid. Rename the `id` instead — nothing keys
on that. For a genuinely intentional removal, record the uuid in
`content/retired.json` with a reason.

## 4. Commit and push

```bash
git add -A
git commit -m "feat(content): add <what> for <app>"
git push
```

`feat(content)` for a new tip or app; `fix(content)` for correcting steps that
were wrong. See [CONTRIBUTING.md](CONTRIBUTING.md) for the commit format.

---

## Then watch it publish

Two workflows run. Both should be green, and the signing one ends with a purge
listing `200` for each file.

```bash
curl -s "https://cdn.jsdelivr.net/gh/MrCybermann/untrack-content@main/content/index.json" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['contentVersion'])"
```

Expect a number one higher than before. Then pull to refresh in the app.

If that number has not moved, or the two workflows disagree, see
[PUBLISHING.md](PUBLISHING.md) — it starts from the symptom.

---

## Extra steps, only when a guide is involved

Do these **before** step 2. No tool can do them for you.

1. **Save it** as `media/<package-or-slug>/<suggestion-id>.webp`.

2. **Watch it back.** Names, avatars, message previews and the status bar are the
   usual leaks. Nothing is redacted automatically and a guide is published
   permanently. Record on a throwaway account with notifications off.

3. **Take the fingerprint:**

   ```bash
   shasum -a 256 media/com.instagram.android/ig-private-account.webp | cut -d' ' -f1
   ```

   `sha256sum` works the same way if you have it. `openssl sha256` prints a
   different format — take only the hash, not the whole line.

4. **Paste it into that suggestion's `media.sha256`.** `src` is relative to
   `media/`, so it does **not** start with `media/`.

**Two hashes exist and only one is automatic.** The hashes in
`content/index.json` cover the tip *JSON files* and CI recomputes them on every
publish. The `media.sha256` inside a tip covers the *`.webp`* and is yours to
maintain — to the manifest it is just text, so a stale one produces a perfectly
valid catalog whose guide fails on every phone.

---

## Adding a new app: one thing to know, nothing to do

The scanner cannot auto-detect a package until it appears in `<queries>` in the
app's manifest, and that list is compiled into the APK. Your tip is live and
reachable immediately through **+ Add an app**; automatic detection waits for the
next app release.

Nothing to do about it here. The app repository checks this daily and fails when
a catalogued app is missing from that list, so it cannot be forgotten.

---

## Never

- **Do not edit `content/index.json`.** It is generated and signed by CI, which
  rebuilds it from the content files on every publish. An edit is overwritten at
  best and published unverifiable at worst. CI rejects any change touching it.

- **Do not run `build_and_sign_manifest.py` locally.** `contentVersion`
  increments on every signing run, so a local signature puts your working copy
  ahead of what CI produces and guarantees a conflict on push.
