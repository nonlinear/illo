#!/usr/bin/env bash
# illo.app.syntax @ 1.0.0
# predicate: every inline <script> in the app parses
# Catches the class of edit that leaves a dangling brace and turns the app into a
# blank page — which, because editing is publishing, is live immediately.
set -uo pipefail
REPO="${1:?repo}"
node --input-type=module -e "
import { readFileSync } from 'fs';
const file = process.argv[1];
const html = readFileSync(file,'utf8');
const blocks = html.match(/<script[^>]*>[\s\S]*?<\/script>/g) || [];
if (!blocks.length) { console.log('FAILURE_TYPE: ASSERTION'); console.log('no script block found'); process.exit(1); }
let bad = 0;
blocks.forEach((b,i) => {
  const code = b.replace(/^<script[^>]*>/,'').replace(/<\/script>\$/,'');
  try { new Function(code); }
  catch (e) { bad++; if (bad===1) console.log('FAILURE_TYPE: ASSERTION'); console.log('block '+i+' FAILED: '+e.message); }
});
console.log(blocks.length+' script block(s), '+(blocks.length-bad)+' parsed');
process.exit(bad ? 1 : 0);
" "$REPO/index.html"
