#!/usr/bin/env bash
# Provision the Linux test-stand toolchain entirely under .deps/ — no sudo, no
# system packages.  Every step is idempotent and independently skippable.
#
#   setup_linux.sh              provision everything
#   setup_linux.sh jdk luajit   provision only the named steps
#   setup_linux.sh --force llama rebuild a step even if it is up to date
#
# Steps: jdk, luajit, llama, deal, model
#
# Environment knobs:
#   DEAL_COMPILER          your own DEAL checkout to measure; if unset, the
#                          pinned commit is cloned into .deps/deal
#   DEAL_REPO              where to clone it from (default: the team's SSH remote)
#   DEAL_STAND_MODEL_NAME  which models.json entry to fetch (default below)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPS="$ROOT/.deps"
STAND="$ROOT/test_stand"

JDK_RELEASE="jdk-25.0.4.1+1"
JDK_DIR="$DEPS/jdk-25"
LUAJIT_REF="v2.1"
LUAJIT_DIR="$DEPS/luajit"
LLAMA_COMMIT="030ebb558a5820b444a8f836ed5cdd46c9b4bd7a"
LLAMA_DIR="$DEPS/llama.cpp"
# The compiler repository is private: SSH with the team's keys by default.
DEAL_REPO="${DEAL_REPO:-git@github.com:arkts-dev/deal.git}"
DEAL_COMMIT="73b93e60ebe9c197e98e43f268ae0f7f1ba84ad0"
DEAL_DIR="$DEPS/deal"
MODEL_NAME="${DEAL_STAND_MODEL_NAME:-qwen2.5-coder-1.5b-official}"

STEPS=()
for arg in "$@"; do
  case "$arg" in
    --force) FORCE_REQUESTED=1 ;;
    *) STEPS+=("$arg") ;;
  esac
done
if [ ${#STEPS[@]} -eq 0 ]; then
  STEPS=(jdk luajit llama deal model)
fi

wants() {
  local want="$1" step
  for step in "${STEPS[@]}"; do
    [ "$step" = "$want" ] && return 0
  done
  return 1
}

say() { printf '\n=== %s\n' "$1"; }

# A step is cached by the ref it was built from, not by the mere existence of a
# binary. Otherwise changing a pinned commit above silently keeps the old build.
FORCE=0
stamp_path() { printf '%s/.stamp-%s' "$DEPS" "$1"; }
is_current() {
  [ "$FORCE" = "0" ] && [ -f "$(stamp_path "$1")" ] \
    && [ "$(cat "$(stamp_path "$1")")" = "$2" ]
}
mark_current() { printf '%s' "$2" > "$(stamp_path "$1")"; }

FORCE="${FORCE_REQUESTED:-0}"
mkdir -p "$DEPS"

# ---------------------------------------------------------------- JDK 25 -----
# The DEAL compiler builds with `javac --release 25`; the system JDK is 11.
if wants jdk; then
  say "JDK 25"
  if is_current jdk "$JDK_RELEASE" && [ -x "$JDK_DIR/bin/javac" ]; then
    echo "already present: $("$JDK_DIR/bin/javac" -version 2>&1)"
  else
    encoded="${JDK_RELEASE//+/%2B}"
    url="https://api.adoptium.net/v3/binary/version/${encoded}/linux/x64/jdk/hotspot/normal/eclipse"
    tmp="$DEPS/jdk-25.tar.gz"
    echo "downloading $JDK_RELEASE"
    curl -fsSL --retry 3 -o "$tmp" "$url"
    rm -rf "$JDK_DIR" && mkdir -p "$JDK_DIR"
    tar -xzf "$tmp" -C "$JDK_DIR" --strip-components=1
    rm -f "$tmp"
    "$JDK_DIR/bin/javac" -version
    mark_current jdk "$JDK_RELEASE"
  fi
fi

# ---------------------------------------------------------------- LuaJIT -----
# Default DEAL backend; the conformance corpus is best covered on LuaJIT.
if wants luajit; then
  say "LuaJIT"
  if is_current luajit "$LUAJIT_REF" && [ -x "$LUAJIT_DIR/install/bin/luajit" ]; then
    echo "already present: $("$LUAJIT_DIR/install/bin/luajit" -v)"
  else
    if [ ! -d "$LUAJIT_DIR/.git" ]; then
      git clone https://luajit.org/git/luajit.git "$LUAJIT_DIR"
    fi
    git -C "$LUAJIT_DIR" fetch --tags origin
    git -C "$LUAJIT_DIR" checkout --detach "$LUAJIT_REF"
    make -C "$LUAJIT_DIR" clean
    make -C "$LUAJIT_DIR" -j "$(nproc)" PREFIX="$LUAJIT_DIR/install"
    make -C "$LUAJIT_DIR" install PREFIX="$LUAJIT_DIR/install"
    # The build installs a versioned name; the compiler invokes plain `luajit`.
    if [ ! -x "$LUAJIT_DIR/install/bin/luajit" ]; then
      ln -sf "$(ls "$LUAJIT_DIR"/install/bin/luajit-* | head -1)" \
             "$LUAJIT_DIR/install/bin/luajit"
    fi
    "$LUAJIT_DIR/install/bin/luajit" -v
    mark_current luajit "$LUAJIT_REF"
  fi
fi

# ------------------------------------------------------------- llama.cpp -----
# Same pinned commit as the published benchmark, built for CPU: this host has
# no GPU, and the upstream build script targets Metal on Apple Silicon.
if wants llama; then
  say "llama.cpp (CPU)"
  if is_current llama "$LLAMA_COMMIT" && [ -x "$LLAMA_DIR/build/bin/llama-server" ]; then
    echo "already built"
  else
    if [ ! -d "$LLAMA_DIR/.git" ]; then
      git clone https://github.com/ggml-org/llama.cpp.git "$LLAMA_DIR"
    fi
    git -C "$LLAMA_DIR" fetch origin "$LLAMA_COMMIT"
    git -C "$LLAMA_DIR" checkout --detach "$LLAMA_COMMIT"
    cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" \
      -DCMAKE_BUILD_TYPE=Release \
      -DGGML_METAL=OFF \
      -DGGML_NATIVE=ON \
      -DLLAMA_CURL=OFF
    cmake --build "$LLAMA_DIR/build" --config Release -j "$(nproc)" \
      --target llama-cli llama-server llama-quantize test-gbnf-validator
    mark_current llama "$LLAMA_COMMIT"
  fi
  "$LLAMA_DIR/build/bin/llama-server" --version
fi

# ------------------------------------------------------- environment file ----
# Written before the compiler and model steps, because both go through the
# stand's own config resolution and need the toolchain paths from here.
# DEAL_COMPILER: an existing setting or the environment wins; otherwise the
# `deal` step fills it in with the pinned clone.
# On a fresh clone there is no .env yet; under `set -o pipefail` a sed over a
# missing file would abort the whole script before it printed anything.
EXISTING_COMPILER=""
EXISTING_MODEL=""
if [ -f "$STAND/.env" ]; then
  EXISTING_COMPILER="$(sed -n 's/^DEAL_COMPILER=//p' "$STAND/.env" | tail -1)"
  EXISTING_MODEL="$(sed -n 's/^DEAL_STAND_MODEL=//p' "$STAND/.env" | tail -1)"
fi
COMPILER="${DEAL_COMPILER:-$EXISTING_COMPILER}"

write_env() {
  {
    echo "# Written by test_stand/bin/setup_linux.sh."
    echo "# DEAL_COMPILER: the DEAL compiler checkout the stand measures."
    if [ -n "$COMPILER" ]; then
      echo "DEAL_COMPILER=$COMPILER"
    else
      echo "# DEAL_COMPILER=/path/to/deal"
    fi
    echo "DEAL_STAND_JDK=$JDK_DIR"
    echo "DEAL_STAND_LUAJIT=$LUAJIT_DIR/install/bin"
    echo "DEAL_STAND_LLAMA=$LLAMA_DIR/build/bin"
    echo "# DEAL_STAND_MODEL: the model used when neither --model nor the preset names one."
    if [ -n "${EXISTING_MODEL:-}" ]; then
      echo "DEAL_STAND_MODEL=$EXISTING_MODEL"
    else
      echo "# DEAL_STAND_MODEL=$MODEL_NAME"
    fi
  } > "$STAND/.env"
}
write_env

# ------------------------------------------------------------------ DEAL -----
# The compiler is the input being measured. A team member with their own
# checkout sets DEAL_COMPILER; everyone else gets the pinned commit under
# .deps/deal, so the first run measures a known compiler, not whatever
# happened to be on PATH.
if wants deal; then
  say "DEAL compiler"
  if [ -z "$COMPILER" ]; then
    if is_current deal "$DEAL_COMMIT" && [ -f "$DEAL_DIR/build/deal/Main.class" ]; then
      echo "already built: $DEAL_DIR @ ${DEAL_COMMIT:0:12}"
    else
      if [ ! -d "$DEAL_DIR/.git" ]; then
        git clone "$DEAL_REPO" "$DEAL_DIR" || {
          echo >&2
          echo "could not clone $DEAL_REPO" >&2
          echo "  The DEAL repository is private. Either:" >&2
          echo "    DEAL_COMPILER=/path/to/your/deal $0 deal     # measure a checkout you already have" >&2
          echo "    DEAL_REPO=<url you can reach> $0 deal        # clone from elsewhere" >&2
          exit 1
        }
      fi
      git -C "$DEAL_DIR" fetch origin "$DEAL_COMMIT"
      git -C "$DEAL_DIR" checkout --detach "$DEAL_COMMIT"
      "$STAND/bin/build_compiler.sh" "$DEAL_DIR"
      mark_current deal "$DEAL_COMMIT"
    fi
    COMPILER="$DEAL_DIR"
    write_env
  else
    echo "using your checkout: $COMPILER @ $(git -C "$COMPILER" rev-parse --short HEAD 2>/dev/null || echo '?')"
    "$STAND/bin/build_compiler.sh" "$COMPILER"
  fi
fi

# ----------------------------------------------------------------- model -----
# A ready GGUF from the registry, verified by hash. Converting from the
# original weights (the published benchmark's path, needs torch) stays
# available as bin/prepare_model.sh.
if wants model; then
  say "model: $MODEL_NAME"
  python3 "$STAND/models.py" fetch "$MODEL_NAME"
fi

say "done"
cat "$STAND/.env"
echo
echo "Next:"
echo "  python3 test_stand/benchmark.py doctor --preset v12-baseline"
echo "  python3 test_stand/benchmark.py check  --preset v12-baseline"
echo "  python3 test_stand/benchmark.py run    --preset v12-baseline --out test_stand/results/today"
echo
echo "Add the toolchain to PATH for interactive use:"
echo "  export PATH=\"$JDK_DIR/bin:$LUAJIT_DIR/install/bin:\$PATH\""
