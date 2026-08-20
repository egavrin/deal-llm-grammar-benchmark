#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
LLAMA="$ROOT/.deps/llama.cpp"
BUILD="$LLAMA/build"

mkdir -p "$ROOT/tools"

/usr/bin/c++ -O3 -DNDEBUG -std=gnu++17 -arch arm64 \
  -DGGML_BACKEND_SHARED -DGGML_SHARED -DGGML_USE_BLAS -DGGML_USE_CPU -DGGML_USE_METAL -DLLAMA_SHARED -DLLAMA_SUBPROCESS \
  -I"$LLAMA" -I"$LLAMA/include" -I"$LLAMA/ggml/include" -I"$LLAMA/common" -I"$LLAMA/vendor" \
  "$ROOT/tools/gbnf_throughput.cpp" \
  -Wl,-rpath,"$BUILD/bin" \
  "$BUILD/bin/libllama-common.0.0.1.dylib" \
  "$BUILD/bin/libllama.0.0.1.dylib" \
  "$BUILD/bin/libggml.0.19.0.dylib" \
  "$BUILD/bin/libggml-cpu.0.19.0.dylib" \
  "$BUILD/bin/libggml-blas.0.19.0.dylib" \
  "$BUILD/bin/libggml-metal.0.19.0.dylib" \
  "$BUILD/bin/libggml-base.0.19.0.dylib" \
  "$BUILD/common/libllama-common-base.a" \
  -o "$ROOT/tools/gbnf-throughput"
