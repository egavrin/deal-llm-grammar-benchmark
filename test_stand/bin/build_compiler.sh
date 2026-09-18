#!/usr/bin/env bash
# Build the DEAL compiler for one variant, using the stand-local JDK 25.
#
#   build_compiler.sh <compiler-checkout>
#
# Only the compiler proper is built (no tests, no JUnit classpath) — the stand
# needs `deal.Main` and the AST classes that test_stand/capability walks.
# Running the compiler repo's own ./run_tests.sh remains the correctness gate;
# this is the fast path used before every stand run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# The toolchain comes from the .env that setup_linux.sh writes, never from an
# assumed .deps layout.
# shellcheck disable=SC1091
[ -f "$ROOT/test_stand/.env" ] && . "$ROOT/test_stand/.env"
JDK="${DEAL_STAND_JDK:?run test_stand/bin/setup_linux.sh first}"
DEAL="${1:?usage: build_compiler.sh <compiler-checkout>}"

test -x "$JDK/bin/javac" || {
  echo "JDK 25 missing. Run: test_stand/bin/setup_linux.sh jdk" >&2
  exit 1
}
test -d "$DEAL/deal/ast" || {
  echo "not a DEAL compiler checkout: $DEAL" >&2
  exit 1
}

cd "$DEAL"
mkdir -p build

# Mirrors the source set of the repo's own run_tests.sh, minus test sources.
"$JDK/bin/javac" --release 25 -proc:none -d build \
  deal/source/*.java \
  deal/ast/*.java \
  deal/types/*.java \
  deal/descriptors/*.java \
  deal/diagnostics/*.java \
  deal/lexer/*.java \
  deal/parser/*.java \
  deal/checker/*.java \
  deal/codegen/*.java \
  deal/codegen/lua/*.java \
  deal/codegen/jvm/*.java \
  deal/codegen/js/*.java \
  deal/ir/*.java \
  deal/semantic/*.java \
  deal/module/*.java \
  deal/project/*.java \
  deal/identity/*.java \
  deal/Main.java

echo "built: $DEAL/build  ($(git -C "$DEAL" rev-parse --short HEAD))"
