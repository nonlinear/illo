#!/usr/bin/env python3
"""
Illo server — :3003

  ~/Documents/illo  is the product. This file is part of it.

  python3 server/illo_server.py        (or ./serve.sh)

WHAT IT SERVES
--------------
Everything in the app folder, plus an append-only API for strokes.

  GET  /                     the app  (index.html, then vault.html, then index.html)
  POST /api/page             create or reopen the one page  -> {id}
  GET  /api/page/<id>        read a page (strokes, reassembled)
  POST /api/append           append strokes to a page
  POST /api/page/<id>/replace  rewrite a page (undo / clear)

ONE PAGE, BY DEFAULT
--------------------
No page picker, no gallery, no decision. The client asks for "the page", the
server makes one if none exists and returns the same one forever. A drawing that
is open for anyone to draw on is the whole product at this stage.

THE ONE RULE
------------
    A request must NEVER be on the path of a pen sample.

The client renders from memory. Points stream in batches, separately from
rendering, and a failed request is dropped, not retried in a tight loop. That is
why storage is append-only JSONL: appending is one write, and it is the shape a
later git-backed format can read without being rewritten.

STORAGE
-------
  data/<page-id>.jsonl       append-only, one JSON object per line
  data/<page-id>.meta.json   derived; safe to delete

Bind is 127.0.0.1. Public exposure is the tunnel's job, never this file's.
"""

import json
import os
import re
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                 # the app folder, not server/
DATA = os.path.join(HERE, "data")            # state lives beside the code
PORT = 3003
MAX_BODY = 8 * 1024 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DEFAULT_ID = "default"                       # MVP: exactly one page, forever

os.makedirs(DATA, exist_ok=True)


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def page_path(page_id):
    return os.path.join(DATA, page_id + ".jsonl")


def meta_path(page_id):
    return os.path.join(DATA, page_id + ".meta.json")


def valid_id(page_id):
    return bool(page_id) and bool(ID_RE.match(page_id))


def read_meta(page_id):
    try:
        with open(meta_path(page_id), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"id": page_id, "created": None, "updated": None,
                "strokes": 0, "points": 0, "bytes": 0}


def write_meta(page_id, meta):
    tmp = meta_path(page_id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    os.replace(tmp, meta_path(page_id))


def create_page(page_id):
    if not os.path.exists(page_path(page_id)):
        open(page_path(page_id), "a", encoding="utf-8").close()
        write_meta(page_id, {"id": page_id, "created": now_iso(),
                             "updated": now_iso(), "strokes": 0,
                             "points": 0, "bytes": 0})
    return read_meta(page_id)


def append_lines(page_id, objs):
    """Append-only. One open, one write, one close — never one per stroke."""
    meta = read_meta(page_id)
    blob = "".join(json.dumps(o, separators=(",", ":")) + "\n" for o in objs)
    with open(page_path(page_id), "a", encoding="utf-8") as fh:
        fh.write(blob)
    if not meta.get("created"):
        meta["created"] = now_iso()
    meta["updated"] = now_iso()
    for o in objs:
        if o.get("t") == "stroke":
            meta["strokes"] = meta.get("strokes", 0) + 1
            meta["points"] = meta.get("points", 0) + len(o.get("pts") or [])
    meta["bytes"] = os.path.getsize(page_path(page_id))
    write_meta(page_id, meta)
    return meta


def read_strokes(page_id):
    out = []
    with open(page_path(page_id), "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue                      # a torn line never kills the page
            if o.get("t") == "stroke":
                out.append({"id": o.get("id"), "pts": o.get("pts") or []})
    return out


class Handler(SimpleHTTPRequestHandler):
    # Serve the APP folder. server/ is reachable only under /server/, and
    # data/ is never served: the API is the only way to read a page.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    # macOS has no entry for .webmanifest, so it would ship as
    # application/octet-stream and Chrome would refuse to install the app.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".webmanifest": "application/manifest+json",
        ".json": "application/json",
        ".png": "image/png",
        ".js": "text/javascript",
    }

    def log_message(self, fmt, *args):
        pass                              # a chatty log inside the path is its own jank

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        if n > MAX_BODY:
            return "TOO_LARGE"
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _blocked(self, path):
        """data/ holds the drawing; it is not a static file."""
        return path.startswith("/data/") or path == "/data"

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            payload = self._body()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._json(400, {"error": "bad json"})
        if payload == "TOO_LARGE":
            return self._json(413, {"error": "body too large"})

        # create / reopen a page. With no id, the server decides: `default`.
        if path == "/api/page":
            page_id = payload.get("id") or DEFAULT_ID
            if not valid_id(page_id):
                return self._json(400, {"error": "bad id"})
            return self._json(200, create_page(page_id))

        if path == "/api/append":
            page_id = payload.get("page") or DEFAULT_ID
            if not valid_id(page_id):
                return self._json(400, {"error": "bad page"})
            strokes = payload.get("strokes") or []
            if not isinstance(strokes, list) or not strokes:
                return self._json(400, {"error": "no strokes"})
            if not os.path.exists(page_path(page_id)):
                return self._json(404, {"error": "no such page"})
            objs = [{"t": "stroke", "id": str(s.get("id") or "")[:64],
                     "pts": s.get("pts") or [], "at": now_iso()} for s in strokes]
            return self._json(200, append_lines(page_id, objs))

        m = re.match(r"^/api/page/([^/]+)/replace$", path)
        if m:
            page_id = m.group(1)
            if not valid_id(page_id):
                return self._json(400, {"error": "bad id"})
            strokes = payload.get("strokes") or []
            tmp = page_path(page_id) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                for s in strokes:
                    fh.write(json.dumps({"t": "stroke",
                                         "id": str(s.get("id") or "")[:64],
                                         "pts": s.get("pts") or [],
                                         "at": now_iso()},
                                        separators=(",", ":")) + "\n")
            os.replace(tmp, page_path(page_id))
            write_meta(page_id, {"id": page_id,
                                 "created": read_meta(page_id).get("created") or now_iso(),
                                 "updated": now_iso(),
                                 "strokes": len(strokes),
                                 "points": sum(len(s.get("pts") or []) for s in strokes),
                                 "bytes": os.path.getsize(page_path(page_id))})
            return self._json(200, read_meta(page_id))

        return self._json(404, {"error": "no such endpoint"})

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if self._blocked(path):
            return self._json(403, {"error": "data is not a static file"})

        if path == "/api/pages":
            pages = [read_meta(fn[:-6]) for fn in sorted(os.listdir(DATA))
                     if fn.endswith(".jsonl")]
            pages.sort(key=lambda m: m.get("updated") or "", reverse=True)
            return self._json(200, {"pages": pages})

        if path.startswith("/api/page/"):
            page_id = path[len("/api/page/"):].strip("/")
            if "/" in page_id:
                page_id = page_id.split("/", 1)[0]
            if not valid_id(page_id) or not os.path.exists(page_path(page_id)):
                return self._json(404, {"error": "no such page"})
            meta = read_meta(page_id)
            strokes = read_strokes(page_id)
            meta["strokeCount"] = len(strokes)
            return self._json(200, {"meta": meta, "strokes": strokes})

        # "/" is the app. index.html is the single-file offline app; vault.html
        # is the one that talks to this server. Prefer the server-aware one.
        if path == "/":
            for cand in ("vault.html", "index.html"):
                if os.path.exists(os.path.join(ROOT, cand)):
                    return self._serve_file(cand)
            return self._json(404, {"error": "no app in " + ROOT})

        return super().do_GET()

    def _serve_file(self, name):
        full = os.path.join(ROOT, name)
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(full))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"illo on http://127.0.0.1:{PORT}  (app -> {ROOT})  (data -> {DATA})")
    srv.serve_forever()
