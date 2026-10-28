# AGENTS.md — Illo

Instructions for any agent working in this repository.

## What this is

**Illo** — a private drawing app in **one HTML file**, plus a small trusted
server so a drawing can stream as you draw. No build, no dependencies.

| | |
|---|---|
| Local | `~/Documents/illo` |
| Repo | `github.com/nonlinear/illo` · repo `illo` · user `nonlinear` |
| Agent owner | `illo` (`~/.openclaw/agents/illo/`) |
| Server | `server/illo_server.py` on `127.0.0.1:3003` (same port the tunnel points at) |
| Public | `illo.nonlinearstudio.org` → Cloudflare tunnel → `localhost:3003` |

There is **no build step**. `index.html` is the single-file offline app;
`vault.html` is the same idea wired to the server; `m0.html` and `probe.html` are
instruments. Whatever is in this folder **is** what the site serves — no symlink,
no copy, no second tree.

**This folder is the whole product.** If a change makes the folder and the site
differ, the change is wrong.

## The one rule that shapes everything

**A request must never be on the path of a pen sample.**

The client renders from memory. Points stream to the server in batches, apart from
rendering, and a failed request is dropped rather than retried in a tight loop.
That is the whole reason storage is append-only JSONL. Breaking this rule is how
the canvas starts to feel the save.

`index.html` (the offline app) must stay a single file with **zero network
requests** — it is the deliverable you can put on a USB stick. A pull request that
adds a network call to `index.html` is rejected, however small. `vault.html` is the
one allowed to talk to `/api`.

## Ground rules

| Rule | Why |
|---|---|
| **One file for the app.** `index.html` holds HTML, CSS and vanilla JS. | The deliverable is a file you can put on a USB stick. A build step would break that. |
| **No dependencies.** Stdlib Python and vanilla JS. No npm, no bundler, no framework. | Every dependency is a supply chain and a thing that can break. |
| **No build step.** Edit, refresh. | If you need a compiler to test a change, the change is wrong. |
| **Pressure matters.** Test with a stylus when you can. | Tapered lines are the product, not a detail. |
| **No symlinks into other folders.** | A symlink is a second tree with extra steps. The product is this folder. |
| **State is not source.** `server/data/` is ignored by git. | The drawing is data. It is backed up, not committed. |

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
- **`index.html` opened from disk: DevTools → Network → reload: 0 requests**
- **`vault.html` served from `:3003`: draw one line, then reload — the line comes
  back from the server, and the sync label reads `saved`**

## What fits

Smoother strokes, more brushes, fill and shapes. Pan and zoom, layers. Better touch
and palm rejection. Accessibility.

## What does not fit

Anything needing a server, an account or a network call. Heavy libraries or a build
pipeline. Anything that breaks the single-file promise.

## License

MIT. By contributing you agree your work is licensed under it.
