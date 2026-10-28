#!/bin/zsh
# illo — the app + its API on 127.0.0.1:3003
# Convention: mood=3001, reels=3002, illo=3003. The port is the address the
# Cloudflare tunnel points at, so it does not change.
#
# Localhost-only, deliberately. Public exposure is the tunnel's job.
APP="$(cd "$(dirname "$0")" && pwd)"
cd "$APP" || exit 1
exec python3 server/illo_server.py
