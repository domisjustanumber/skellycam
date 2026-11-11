# GF03: verify that every quote in GF03_quotes.json occurs verbatim (whitespace-normalised)
# in the downloaded source, and write short excerpts for the record.
# Usage: python -I GF03_verify_quotes.py --quotes GF03_quotes.json --root <scratchpad step3/GF03>
#        --out <results/licensing/gapfill/GF03_quote_verification.json> --excerpts <dir>
import argparse, hashlib, json, os, re


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quotes", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--excerpts", required=True)
    a = ap.parse_args()
    q = json.load(open(a.quotes, encoding="utf-8"))
    os.makedirs(a.excerpts, exist_ok=True)
    res, by_src = [], {}
    for item in q["quotes"]:
        p = os.path.join(a.root, item["file"])
        raw = open(p, "rb").read()
        text = raw.decode("utf-8", errors="replace")
        found = norm(item["quote"]) in norm(text)
        res.append({"id": item["id"], "url": item["url"], "file": item["file"],
                    "sha256": hashlib.sha256(raw).hexdigest(), "quote": item["quote"],
                    "found_verbatim": found})
        by_src.setdefault(item["file"], []).append((item["id"], item["quote"], found))
    for item in q.get("ordered", []):
        p = os.path.join(a.root, item["file"])
        raw = open(p, "rb").read()
        lines = [l.strip() for l in raw.decode("utf-8", errors="replace").splitlines()]
        try:
            h = lines.index(item["heading"])
            r = lines.index(item["row"], h + 1)
            n = lines.index(item["next_heading"], h + 1)
            ok = h < r < n
        except ValueError:
            ok, h, r, n = False, -1, -1, -1
        res.append({"id": item["id"], "url": item["url"], "file": item["file"],
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "quote": f'row "{item["row"]}" listed under heading "{item["heading"]}" (text lines {h+1}, {r+1}; next heading line {n+1})',
                    "found_verbatim": ok})
        by_src.setdefault(item["file"], []).append((item["id"], f'{item["heading"]} ... {item["row"]}', ok))
    json.dump({"access_date": "2026-11-10", "n": len(res),
               "n_found": sum(r["found_verbatim"] for r in res), "quotes": res},
              open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for f, items in by_src.items():
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(f)) + ".excerpt.txt"
        with open(os.path.join(a.excerpts, name), "w", encoding="utf-8") as o:
            o.write(f"source file: {f}\naccess date: 2026-11-10\n\n")
            for i, qt, ok in items:
                o.write(f"[{i}] found_verbatim={ok}\n{qt}\n\n")
    print(sum(r["found_verbatim"] for r in res), "/", len(res))
    for r in res:
        if not r["found_verbatim"]:
            print("MISSING", r["id"])


main()
