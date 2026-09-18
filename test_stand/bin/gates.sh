#!/usr/bin/env bash
# Build the compiler, then run every check that needs no model.
#
#   gates.sh                    use the default preset
#   gates.sh v12-published-grammar
#
# This is a convenience wrapper: `benchmark.py check` does the checking, and
# resolves its inputs the same way every other entry point does.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAND="$ROOT/test_stand"
PRESET="${1:-v12-baseline}"

# shellcheck disable=SC1091
[ -f "$STAND/.env" ] && . "$STAND/.env"
COMPILER="${DEAL_COMPILER:?set DEAL_COMPILER in $STAND/.env}"

echo "=== building the compiler"
"$STAND/bin/build_compiler.sh" "$COMPILER"
echo
python3 "$STAND/benchmark.py" check --preset "$PRESET"
