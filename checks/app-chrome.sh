#!/usr/bin/env bash
# illo.app.chrome @ 1.0.0
# predicate: the bar has no menus, and `?` goes to the studio
#
# Owner, 2026-10-28:
#   "tira vários menus tá uma bagunça. illo menu. todo menu que tem PNG export etc.
#    primeiro não pedi. segundo tá incompleto. terceiro que combinamos tablet first ux
#    grammar não um porrilhao de ícones e botões. deleta. zoom menu, deleta. o meuzinho
#    abaixo com tool e TAMANHO. deleta. ? menu tem que linkar pra nonlinearstudio.org"
#
# The property is not "the file is small". It is: NOTHING in the app is a menu of file
# actions, and the only link out is the studio. Every case below is live publishing --
# the app on disk is the app on the wire (illo.repo.clean-tree).
set -uo pipefail
REPO="${1:?repo}"
F="$REPO/index.html"

fail() { echo "FAILURE_TYPE: ASSERTION"; echo "$1"; exit 1; }

# ---- 1. the deleted surfaces are gone --------------------------------------
for gone in btnPng btnExport btnImport btnSaveIllo btnOpenIllo btnClearIllo \
            zoomIn zoomOut zoomLbl statusbar zoombar sizePop sizeRange appVer; do
  n=$(grep -c "id=\"$gone\"" "$F" || true)
  [ "$n" = "0" ] || fail "id=\"$gone\" is still in the document — that surface was deleted by the owner"
done

# ---- 2. the menu labels are gone, even as dead code inside handlers ---------
# `brush size` and the zoom % were UI strings; a leftover dead handler that says
# "Brush size" means the surface is half-removed, and the next edit revives it.
hits=$(grep -nE "Brush size|zoomLbl|sizeRange|sizeVal" "$F" || true)
[ -z "$hits" ] || fail "dead size/zoom UI code still present:
$hits"

# ---- 3. `?` links to the studio, not to a second help menu ----------------
grep -q 'href="https://nonlinearstudio.org"' "$F" \
  || fail "no link to https://nonlinearstudio.org — the owner asked the ? to go there"
if grep -q "nonlinear\.nyc" "$F"; then
  fail "nonlinear.nyc is still linked — the studio is nonlinearstudio.org"
fi

# ---- 4. no file-format words on the surface -------------------------------
# PNG / Export / Import / .illo belong to a save model that does not exist yet.
# Anchored on purpose: "illo save" also matches inside ".illo save+open", so an
# unanchored pattern flags the very comment that records the removal.
surface=$(grep -nE "(exportPNG|exportJSON|saveIlloFile|openIlloFile)\.onclick|>(PNG|Export|Import)<|^[^/]*>illo (save|open)<" "$F" || true)
[ -z "$surface" ] || fail "file action still visible in the UI:
$surface"

echo "no menus · no zoom/size panels · ? → nonlinearstudio.org"
