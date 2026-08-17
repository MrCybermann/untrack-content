# Media (visual guides)

Optional short clips showing a suggestion's steps being carried out.

## Format

Animated WebP, and nothing else. MP4 would mean shipping a video player for
clips that are silent, ten seconds long and want to loop; GIF is worse than
WebP at every part of this.

## Recording

Use the phone's own screen recorder — on Android it's a Quick Settings tile.
That gives a clean portrait clip of just the screen, with nothing else in frame
and nothing to crop afterwards.

Keep it to the one setting being changed. Under twenty seconds is the target;
the app has no way to scrub through a longer clip.

## Converting

Any tool that produces an animated WebP will do. Aim for:

| | |
|---|---|
| Width | 480 px, height following the original proportions |
| Frame rate | 12 fps |
| Quality | around 80 |
| Loop | forever |
| Size | under 2 MB |

Then take the fingerprint, which the suggestion has to declare:

```bash
shasum -a 256 media/com.instagram.android/ig-private-account.webp
```

**Check the result actually animates before committing it.** Some encoders
collapse low-motion footage — which a settings walkthrough is — into a single
still frame that still carries a `.webp` extension. CI catches this, but it is
quicker to notice by opening the file.

## Naming

Directory is the app's package id, or the device slug for device files.
Filename is the suggestion's `id`.

```
media/com.instagram.android/ig-private-account.webp
media/pixel/delete-advertising-id.webp
```

A suggestion's `media.src` is that path relative to this folder, so the first
one is referenced as `com.instagram.android/ig-private-account.webp`.

## What CI enforces

1. The file named by `src` is committed here.
2. It is at most **2 MB**.
3. Its **`sha256` matches** the one recorded in the suggestion. The app checks
   the same hash after downloading, before the bytes reach an image decoder —
   guides are fetched separately from the signed catalog, so this is what keeps
   them inside the chain of trust.
4. It has **two or more animation frames**.

## No personal information

Record on a throwaway account, with notifications off, on a profile carrying
nothing personal. Then look at the result before committing: names, avatars,
message previews and the status bar are the usual leaks. None of it is detected
or redacted automatically, and a guide is published permanently.

## App icons

Installed apps show the icon Android already provides, so a bundled logo is
usually unnecessary. An optional catalog logo (an app file's `icon` field) is
used only when showing an app in search before it is installed: `.webp` or
`.png`, at most 100 KB. App logos are trademarks of their owners and are not
covered by the content licence — see
[LICENSE-CONTENT.md](../LICENSE-CONTENT.md).

See [CONTRIBUTING.md](../CONTRIBUTING.md) for full guidelines.
