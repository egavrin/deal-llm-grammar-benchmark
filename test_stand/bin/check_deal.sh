#!/usr/bin/env bash
# Compile one .deal module with the real compiler and report diagnostics.
#
# Layout notes, both discovered the hard way and both required:
#  * the entry module must export `main(): null`, so the module under test is
#    compiled as a library imported by a generated entry (E2012);
#  * `moduleRoots` must be a named relative directory. The published
#    benchmark used ["."], which the current compiler rejects for any exported
#    class with E2010 "the configured root '.' is not representable".
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# The toolchain comes from the .env that setup_linux.sh writes, never from an
# assumed .deps layout.
# shellcheck disable=SC1091
[ -f "$ROOT/test_stand/.env" ] && . "$ROOT/test_stand/.env"
JDK="${DEAL_STAND_JDK:?run test_stand/bin/setup_linux.sh first}"
DEAL="${DEAL_COMPILER:?set DEAL_COMPILER, or run test_stand/bin/setup_linux.sh}"
status=0
for file in "$@"; do
  work="$(mktemp -d)"
  mkdir -p "$work/src"
  cp "$file" "$work/src/solution.deal"
  for support in "$(dirname "$file")"/_support/*.deal; do
    [ -e "$support" ] && cp "$support" "$work/src/"
  done
  cat > "$work/deal.json" <<'JSON'
{"languageVersion":"1.2","moduleRoots":["src"],"output":"lua","backend":"luajit"}
JSON
  cat > "$work/src/main.deal" <<'ENTRY'
import * as solution from "./solution";

export function main(): null {
  return null;
}
ENTRY
  out="$(cd "$DEAL" && "$JDK/bin/java" -cp build deal.Main compile \
        "$work/src/main.deal" --output "$work/lua" 2>&1)"
  if [ $? -eq 0 ]; then
    printf 'OK    %s\n' "$(basename "$file")"
  else
    status=1
    printf 'FAIL  %s\n' "$(basename "$file")"
    printf '%s\n' "$out" | sed 's/^/        /' | head -8
  fi
  rm -rf "$work"
done
exit $status
