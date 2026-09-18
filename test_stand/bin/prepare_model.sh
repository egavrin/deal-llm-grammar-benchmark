#!/usr/bin/env bash
# Convert and quantize one model from test_stand/models.json locally.
#
#   prepare_model.sh NAME
#   prepare_model.sh --list
#
# This is the published benchmark's conversion-control path: download the
# untouched Hugging Face weights at a pinned revision, convert them with the
# pinned llama.cpp converter, quantize. It needs torch and a few gigabytes.
# The everyday path is `models.py fetch NAME`, which downloads a ready GGUF;
# this script is for entries that carry a `repo` and no `url`, and for anyone
# who wants to rebuild exactly the published benchmark's model.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAND="$ROOT/test_stand"
LLAMA="$ROOT/.deps/llama.cpp"
VENV="$ROOT/.venv-convert"

if [ "${1:-}" = "--list" ] || [ -z "${1:-}" ]; then
  python3 "$STAND/models.py" list
  [ -n "${1:-}" ] || { echo "usage: prepare_model.sh NAME" >&2; exit 2; }
  exit 0
fi

NAME="$1"
read -r REPO REVISION QUANT FILE < <(cd "$STAND" && python3 -c "
import sys, config as cfg
name = '$NAME'
registry = cfg.known_models()
if name not in registry:
    sys.exit(f'unknown model {name!r}; try: python3 test_stand/models.py list')
spec = registry[name]
if not spec.get('repo'):
    sys.exit(f'{name} has no source repo in models.json; it is a download-only entry')
print(spec['repo'], spec['revision'], spec.get('quantization', 'F16'), spec['file'])")

HF_MODEL="$ROOT/.deps/hf-$NAME"
F16="$ROOT/models/${FILE%.gguf}-f16.gguf"
[ "${QUANT^^}" = "F16" ] && F16="$ROOT/models/$FILE"
OUT="$ROOT/models/$FILE"

test -x "$LLAMA/build/bin/llama-quantize" || {
  echo "Run test_stand/bin/setup_linux.sh llama first" >&2; exit 1; }

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet \
    'torch==2.8.0' 'transformers==4.57.6' 'sentencepiece==0.2.1' \
    'safetensors==0.7.0' 'huggingface_hub[cli]'
fi

mkdir -p "$ROOT/models"
[ -d "$HF_MODEL" ] || "$VENV/bin/hf" download "$REPO" --revision "$REVISION" \
  --local-dir "$HF_MODEL"
[ -f "$F16" ] || "$VENV/bin/python" "$LLAMA/convert_hf_to_gguf.py" \
  "$HF_MODEL" --outfile "$F16" --outtype f16
if [ "${QUANT^^}" != "F16" ]; then
  [ -f "$OUT" ] || "$LLAMA/build/bin/llama-quantize" "$F16" "$OUT" "$QUANT"
fi

# Hash, compare with the registry and the published benchmark, and write the
# provenance record beside the file.
python3 "$STAND/models.py" verify "$NAME"
echo "$OUT"
