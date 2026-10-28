cp -r /src /tmp/p && pip install -q --no-deps /tmp/p 2>/dev/null
for t in "$@"; do echo "=== $t"; python -I /w/v_synth.py $t 2>&1 | tail -15; done
