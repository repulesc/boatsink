#!/usr/bin/env bash
# Compile-check LSL scripts with LSL-PyOptimizer (a full LSL parser + type checker),
# then print a rough Mono memory estimate per script.
#   usage: tools/lslcheck.sh [files...]      (default: src/*.lsl)
set -u
DIR="${LSLOPT_DIR:-$HOME/.cache/lsl-pyoptimizer}"
if [ ! -f "$DIR/main.py" ]; then
    git clone -q --depth 1 https://github.com/Sei-Lisa/LSL-PyOptimizer "$DIR" || { echo "cannot fetch LSL-PyOptimizer"; exit 2; }
fi
files=("$@")
[ ${#files[@]} -eq 0 ] && files=(src/*.lsl)
rc=0
for f in "${files[@]}"; do
    if python3 "$DIR/main.py" -O clear -o /dev/null "$f"; then
        # rough Mono size model fitted on in-world readings: ~18 KB base + ~58 B per statement + 2 B per string char,
        # plus ~30 B for each element of a constant list (every element is an object): 4.8.0 crashed with "Stack-Heap
        # Collision" in the UI script while this model, then without that term, still showed 15 KB free
        python3 -I - "$f" <<'PY'
import re, sys
f = sys.argv[1]
# one pass: keep string literals as they are, drop // comments (a "//" inside a string, such as a URL, is not a comment)
t = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*', lambda m: m.group(0) if m.group(0)[0] == '"' else '', open(f).read())
chars = sum(len(x) for x in re.findall(r'"((?:\\.|[^"\\])*)"', t))
stmts = re.sub(r'"(?:\\.|[^"\\])*"', '""', t).count(';')
clean = re.sub(r'"(?:\\.|[^"\\])*"', '""', t)
elems = sum(m.group(1).count(',') + 1 for m in re.finditer(r'\blist\s+\w+\s*=\s*\[(.*?)\];', clean, re.S) if m.group(1).strip())
free = 64 - (18372 + 58.3 * stmts + 2 * chars + 30 * elems) / 1024
print(f"OK    {f}: {stmts} statements, est. free memory {free:.1f} KB" + ("   <-- LOW" if free < 10 else ""))
PY
    else
        echo "FAIL  $f"
        rc=1
    fi
done
exit $rc
