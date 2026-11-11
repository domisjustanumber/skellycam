"""Query the IETF Datatracker IPR API for disclosures against given documents (RFCs and drafts).

The web search page is bot-protected (HTTP 403 to curl), the JSON API is not. For every document name
this lists the disclosures (id, title, holder, licensing declaration where present).
Usage: python ietf_ipr_query.py --out <json> rfc9043 draft-ietf-cellar-ffv1 ...
"""
import argparse
import datetime as dt
import json
import subprocess

API = "https://datatracker.ietf.org"


def get(path):
    r = subprocess.run(["curl", "-sL", "--max-time", "60", "-A", "Mozilla/5.0", API + path], capture_output=True)
    return json.loads(r.stdout)


ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("docs", nargs="+")
a = ap.parse_args()
res = {"queried_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "api": API, "docs": {}}
for d in a.docs:
    rel = get(f"/api/v1/ipr/iprdocrel/?document__name={d}&format=json&limit=200")
    items = []
    for o in rel["objects"]:
        disc_path = o["disclosure"]
        base = get(disc_path + "?format=json")
        item = {"disclosure": disc_path, "id": base.get("id"), "title": base.get("title"),
                "holder": base.get("holder_legal_name"), "state": base.get("state"), "time": base.get("time"),
                "revisions": o.get("revisions"),
                "url": f"{API}/ipr/{base.get('id')}/"}
        # licensing declaration lives on the subtype (holder / third-party / generic)
        for sub in ("holderiprdisclosure", "genericiprdisclosure", "thirdpartyiprdisclosure"):
            s = get(f"/api/v1/ipr/{sub}/{base.get('id')}/?format=json") if base.get("id") else {}
            if isinstance(s, dict) and s.get("id"):
                item["type"] = sub
                lic = s.get("licensing")
                if lic:
                    item["licensing"] = get(lic + "?format=json").get("desc") if lic.startswith("/api") else lic
                item["licensing_comments"] = (s.get("licensing_comments") or "")[:600]
                item["statement"] = (s.get("statement") or "")[:600]
                break
        items.append(item)
    res["docs"][d] = {"total_count": rel["meta"]["total_count"], "disclosures": items}
    print(d, rel["meta"]["total_count"])
open(a.out, "w", encoding="utf-8").write(json.dumps(res, indent=1))
