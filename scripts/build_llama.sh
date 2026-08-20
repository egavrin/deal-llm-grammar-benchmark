#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LLAMA="$ROOT/.deps/llama.cpp"
COMMIT="030ebb558a5820b444a8f836ed5cdd46c9b4bd7a"

mkdir -p "$ROOT/.deps"
if [[ ! -d "$LLAMA/.git" ]]; then
  git clone https://github.com/ggml-org/llama.cpp.git "$LLAMA"
fi
git -C "$LLAMA" fetch origin "$COMMIT"
git -C "$LLAMA" checkout --detach "$COMMIT"

cmake -S "$LLAMA" -B "$LLAMA/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_METAL=ON \
  -DLLAMA_CURL=OFF
cmake --build "$LLAMA/build" --config Release -j "$(sysctl -n hw.ncpu)" \
  --target llama-cli llama-server llama-quantize test-gbnf-validator

"$LLAMA/build/bin/llama-server" --version
"$LLAMA/build/bin/llama-cli" --list-devices
