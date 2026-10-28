#!/bin/sh
# Verifies (1) tree of skellycam 777b058c == tree of 23ccbf20, (2) freemocap venv's installed skellycam == 777b058c (ignoring CRLF)
R=/c/Users/Dom/GitHub/freemocap/skellycam
SP=/c/Users/Dom/GitHub/freemocap/freemocap/.venv/Lib/site-packages/skellycam
echo "tree 777b058c: $(git -C $R rev-parse 777b058c^{tree})"
echo "tree 23ccbf20: $(git -C $R rev-parse 23ccbf20^{tree})"
git -C $R merge-base --is-ancestor 23ccbf20 777b058c && echo "23ccbf20 is ancestor of 777b058c"
n=0; d=0
for f in $(cd $SP && find . -name "*.py" | sed 's|^\./||'); do
  n=$((n+1))
  if ! git -C $R show 777b058c:skellycam/$f 2>/dev/null | diff -q --strip-trailing-cr - $SP/$f >/dev/null; then d=$((d+1)); echo "DIFF $f"; fi
done
echo "installed .py files checked=$n differing(ignoring CRLF)=$d"
cat $SP/../skellycam-2.0.0a6.dist-info/direct_url.json; echo
