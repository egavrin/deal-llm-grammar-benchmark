#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEAL="$ROOT/.deps/deal"
COMMIT="58a6dd3aeafc06168f2010c07d0aeae84d5364f3"

mkdir -p "$ROOT/.deps"
if [[ ! -d "$DEAL/.git" ]]; then
  git clone https://github.com/arkts-dev/deal.git "$DEAL"
fi
git -C "$DEAL" fetch origin "$COMMIT"
git -C "$DEAL" checkout --detach "$COMMIT"

mkdir -p "$DEAL/build"
javac --release 25 -d "$DEAL/build" \
  "$DEAL"/deal/ast/*.java \
  "$DEAL"/deal/types/*.java \
  "$DEAL"/deal/diagnostics/*.java \
  "$DEAL"/deal/lexer/*.java \
  "$DEAL"/deal/parser/*.java \
  "$DEAL"/deal/checker/*.java \
  "$DEAL"/deal/codegen/*.java \
  "$DEAL"/deal/codegen/lua/*.java \
  "$DEAL"/deal/codegen/jvm/*.java \
  "$DEAL"/deal/ir/*.java \
  "$DEAL"/deal/module/*.java \
  "$DEAL"/deal/Main.java

test -f "$DEAL/build/deal/Main.class"
echo "Built DEAL compiler at $COMMIT"
