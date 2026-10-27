# AGENTS.md — Illo

Instructions for any agent working in this repository.

## What this is

**Illo** — a private, offline drawing app in **one HTML file**. No build, no
dependencies, no network.

| | |
|---|---|
| Local | `~/Documents/illo` |
| Repo | `github.com/nonlinear/illo` · repo `illo` · user `nonlinear` |
| Agent owner | `illo` (`~/.openclaw/agents/illo/`) |

There is **no build step and no Pages deployment**. The repo is the source of truth;
`index.html` at the root *is* the app. To use it, take the file — that is the whole
product. GitHub Pages is not used for this project.

## The one rule that shapes everything

**Zero network requests.** Not "few" — zero. No CDN, no web fonts, no analytics,
no telemetry, no external images. Open DevTools → Network → reload: the page itself
is the only entry. This is what makes the app work on a machine with no internet,
which is the entire point.

A PR that adds a network call is rejected, however small.

## Ground rules

| Rule | Why |
|---|---|
| **One file.** `index.html` holds HTML, CSS and vanilla JS. | The deliverable is a file you can put on a USB stick. A build step would break that. |
| **No dependencies.** No npm, no bundler, no framework. | Every dependency is a supply chain and a thing that can break offline. |
| **No build step.** Edit, refresh. | If you need a compiler to test a change, the change is wrong. |
| **Pressure matters.** Test with a stylus when you can. | Tapered lines are the product, not a detail. |

## Storage keys

| File | Key | Status |
|---|---|---|
| `index.html` | `offline-sketch-v1` | unchanged — carries no brand, nothing to migrate |
| `vault.html` | `illo-vault` | migrated from `dillon-vault` on load (read old, write new, drop old) |

**Never rename a storage key without migrating.** A bare rename orphans saved
drawings: the user opens the app and finds it empty. The migration is five lines in
`vault.html` — read the legacy key when the current one is absent, write it under the
current key, remove the legacy key. Copy that shape if another key ever moves.

Do not fold a storage-key migration into a cosmetic rename. It is its own change,
tested on its own, because it touches user data.

This is the same defect class as renaming an OpenClaw agent without rewriting its
session pointers: the system keeps working and silently loses the user's data.

## Name

The product and the agent are both **Illo**. There is no "Dillon" anywhere except
the frozen storage key above. If you find another occurrence, it is a rename that
was missed — fix it.

## Testing before a PR

By hand, with a mouse and if possible a stylus:

- draw, erase, change colour and size
- undo / redo / clear
- export PNG, export and re-import `.json`
- reload — autosave must restore the drawing
- **DevTools → Network → reload: still 0 requests**

## What fits

Smoother strokes, more brushes, fill and shapes. Pan and zoom, layers. Better touch
and palm rejection. Accessibility.

## What does not fit

Anything needing a server, an account or a network call. Heavy libraries or a build
pipeline. Anything that breaks the single-file promise.

## License

MIT. By contributing you agree your work is licensed under it.
