#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LLAMA="$ROOT/.deps/llama.cpp"
HF_MODEL="$ROOT/.deps/qwen2.5-coder-0.5b-instruct"
VENV="$ROOT/.venv-convert"
F16="$ROOT/models/qwen2.5-coder-0.5b-instruct-control-f16.gguf"
Q4="$ROOT/models/qwen2.5-coder-0.5b-instruct-control-q4_k_m.gguf"
REVISION="ea3f2471cf1b1f0db85067f1ef93848e38e88c25"
EXPECTED_SHA256="5231325088f468169793028bd680f714548fe36977f89f0fc64fbdffeb519220"

test -x "$LLAMA/build/bin/llama-quantize" || {
  echo "Run scripts/build_llama.sh first" >&2
  exit 1
}

python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install \
  'torch==2.8.0' \
  'transformers==4.57.6' \
  'sentencepiece==0.2.1' \
  'safetensors==0.7.0' \
  'huggingface_hub[cli]'

mkdir -p "$ROOT/.deps" "$ROOT/models"
"$VENV/bin/hf" download Qwen/Qwen2.5-Coder-0.5B-Instruct \
  --revision "$REVISION" \
  --local-dir "$HF_MODEL"

if [[ ! -f "$F16" ]]; then
  "$VENV/bin/python" "$LLAMA/convert_hf_to_gguf.py" \
    "$HF_MODEL" --outfile "$F16" --outtype f16
fi
if [[ ! -f "$Q4" ]]; then
  "$LLAMA/build/bin/llama-quantize" "$F16" "$Q4" Q4_K_M
fi

ACTUAL_SHA256="$(shasum -a 256 "$Q4" | awk '{print $1}')"
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  echo "Model SHA-256 mismatch" >&2
  echo "expected: $EXPECTED_SHA256" >&2
  echo "actual:   $ACTUAL_SHA256" >&2
  exit 1
fi
echo "Verified $Q4"
