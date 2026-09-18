#!/usr/bin/env bash
# Demonstrate two claims that are easy to assert and easy to doubt:
#   1. inference runs locally, on this machine, from a local weights file;
#   2. the GBNF grammar really constrains decoding inside llama.cpp.
#
# Everything here is observable: sockets, memory maps, and generations that
# could not have come out any other way.
#
#   prove.sh                       default preset
#   prove.sh v12-1.5b              another preset
#   PORT=8200 prove.sh             another port
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
PRESET="${1:-v12-baseline}"
PORT="${PORT:-8145}"

# Paths come from the same resolution every entry point uses; nothing here
# assumes a .deps layout.
RESOLVED="$(python3 test_stand/benchmark.py doctor --preset "$PRESET" --json)" || exit 2
field() { printf '%s' "$RESOLVED" | python3 -c "import json,sys; v=json.load(sys.stdin)['$1']; print('' if v is None else v)"; }
SERVER_BIN="$(field llama_server)"
MODEL="$(field model)"
GRAMMAR="$(field grammar)"

test -x "$SERVER_BIN" || { echo "missing $SERVER_BIN; run test_stand/bin/setup_linux.sh llama" >&2; exit 2; }
test -f "$MODEL" || { echo "missing model $MODEL; run test_stand/bin/setup_linux.sh model" >&2; exit 2; }

"$SERVER_BIN" -m "$MODEL" -c 4096 -np 1 --host 127.0.0.1 --port "$PORT" \
  --no-cache-prompt -t "$(( $(nproc) - 2 ))" > "$ROOT/test_stand/prove-server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
until curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
  kill -0 "$SERVER" 2>/dev/null || { echo "llama-server exited; see test_stand/prove-server.log" >&2; exit 2; }
  sleep 1
done

echo "=============================================================="
echo "1. IS IT LOCAL?"
echo
echo "-- the server listens on loopback only:"
ss -tlnp 2>/dev/null | grep ":$PORT" | sed 's/^/   /'
echo
echo "-- it holds no outbound connection:"
ss -tnp 2>/dev/null | grep "pid=$SERVER" | sed 's/^/   /' || echo "   none"
echo
echo "-- the weights are mapped from a file on this disk:"
grep -i gguf "/proc/$SERVER/maps" | awk '{print "   " $NF}' | sort -u
echo
echo "-- and it is burning this machine's CPU:"
ps -o pid,user,%cpu,rss,comm -p "$SERVER" | sed 's/^/   /'

echo
echo "=============================================================="
echo "2. IS THE GRAMMAR APPLIED?"
echo
echo "Same prompt, same seed, same temperature. Only the grammar changes."
python3 - "$PORT" "$PRESET" "$GRAMMAR" <<'PY'
import json, pathlib, sys, urllib.request
sys.path.insert(0, "test_stand")
import argparse, config as cfg
port, preset, grammar_path = sys.argv[1:4]
QUESTION = "What is the capital of France? Answer in one word."

def ask(grammar, prompt=QUESTION, n=24, system=None):
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}]
    body = {"model": "m", "messages": messages, "temperature": 0, "seed": 42,
            "max_tokens": n, "stream": False, "cache_prompt": False}
    if grammar:
        body["grammar"] = grammar
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)["choices"][0]["message"]["content"]

for label, grammar in (
        ("no grammar", None),
        ('root ::= "BANANA"', 'root ::= "BANANA"'),
        ('root ::= [0-9]{6}', 'root ::= [0-9]{6}'),
        ('root ::= "yes" | "no"', 'root ::= "yes" | "no"')):
    print(f"   {label:24s} -> {ask(grammar)!r}")

print()
print("   The model knows the answer is Paris. Under a grammar it cannot say it:")
print("   the sampler is filtered to tokens the grammar still allows.")
print()
print("   Now the real DEAL grammar and the stand's own prompt for one task,")
print("   identical in both runs:")
config = cfg.resolve(argparse.Namespace(preset=preset, prompts=None, grammar=None,
                                        compiler=None, primer=None, model=None))
task = config.tasks()[0]
prompt = config.render_prompt(task)
deal = pathlib.Path(grammar_path).read_text()
print(f"   task: {task.id}")
for label, grammar in (("without grammar", None), ("with grammar", deal)):
    print(f"   --- {label}:")
    text = ask(grammar, prompt, 120, system=config.system_prompt())
    print("\n".join("       " + line for line in text.splitlines()[:8]))
PY

echo
echo "=============================================================="
echo "3. HOW OFTEN DID THE GRAMMAR OVERRULE THE MODEL?"
echo
echo "From the most recent recorded run: at each decoding step the runner"
echo "compares the token chosen against the model's own most probable token."
python3 - <<'PY'
import glob, json, os
runs = sorted(glob.glob("test_stand/results/*/raw.jsonl"), key=os.path.getmtime)
if not runs:
    print("   no run recorded yet; use: python3 test_stand/benchmark.py run --preset v12-baseline --out test_stand/results/today")
else:
    print(f"   {runs[-1]}")
    rows = [json.loads(l) for l in open(runs[-1]) if l.strip()]
    for profile in ("raw", "constrained"):
        items = [r for r in rows
                 if r.get("profile") == profile and not r.get("request_error")]
        steps = sum(r.get("pressure_steps") or 0 for r in items)
        rejected = sum(r.get("rejected_argmax_steps") or 0 for r in items)
        share = 100 * rejected / steps if steps else 0
        print(f"   {profile:12s} {steps:6d} steps, argmax overruled {rejected:5d} "
              f"times ({share:.2f}%)")
PY

echo
echo "=============================================================="
echo "4. NO NETWORK AT ALL"
echo
echo "Re-run this script inside a private network namespace — loopback only,"
echo "no DNS, no route out — and section 2 still produces DEAL:"
echo
echo "   unshare -rn bash -c 'ip link set lo up; test_stand/bin/prove.sh'"
