# GF03: collect static facts (no execution of downloaded code) into one JSON.
# Usage: python -I GF03_collect_facts.py <GF03 scratch root> <fatbin_archs.py> <out.json>
import sys, json, hashlib, zipfile, subprocess, os
root, fat, out = sys.argv[1:4]
dl = os.path.join(root, "dl")
W1 = "nvidia_nvimgcodec_cu12-0.10.0.9-py3-none-win_amd64.whl"
W2 = "nvidia_nvjpeg_cu12-12.4.0.76-py3-none-win_amd64.whl"
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
facts = {"access_date": "2026-11-10", "wheels": {}, "pypi": {}, "redistrib_libnvjpeg": {}, "spdx": {}, "fatbin": {}}
for w in (W1, W2):
    p = os.path.join(dl, w); z = zipfile.ZipFile(p)
    facts["wheels"][w] = {"sha256": sha(p), "members": [[i.filename, i.file_size] for i in z.infolist()],
        "licence_like_members": [i.filename for i in z.infolist() if any(k in i.filename.upper() for k in ("LICEN", "EULA", "NOTICE", "COPYING"))]}
for f, key in (("pypi_nvimgcodec_0.10.0.9.json", "nvidia-nvimgcodec-cu12==0.10.0.9"), ("pypi_nvjpeg_12.4.0.76.json", "nvidia-nvjpeg-cu12==12.4.0.76"),
               ("pypi_nvjpeg_latest.json", "nvidia-nvjpeg-cu12 (latest)"), ("pypi_nvimgcodec_latest.json", "nvidia-nvimgcodec-cu12 (latest)")):
    d = json.load(open(os.path.join(dl, f), encoding="utf-8")); i = d["info"]
    facts["pypi"][key] = {"url_file": f, "version": i.get("version"), "license": i.get("license"), "license_expression": i.get("license_expression"),
        "classifiers_license": [c for c in i.get("classifiers", []) if c.startswith("License")], "requires_dist": i.get("requires_dist"),
        "win_amd64": [[u["filename"], u["url"], u["digests"]["sha256"]] for u in d["urls"] if "win_amd64" in u["filename"]]}
for v in ("12.4.0", "12.8.0", "12.8.1", "12.9.0", "12.9.1"):
    d = json.load(open(os.path.join(dl, f"redistrib_{v}.json"), encoding="utf-8"))
    facts["redistrib_libnvjpeg"][v] = {"url": f"https://developer.download.nvidia.com/compute/cuda/redist/redistrib_{v}.json", "libnvjpeg.version": d["libnvjpeg"]["version"]}
d = json.load(open(os.path.join(dl, "spdx_licenses.json"), encoding="utf-8"))
facts["spdx"] = {"url": "https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json", "licenseListVersion": d.get("licenseListVersion"),
    "entries": {l["licenseId"]: {"isOsiApproved": l.get("isOsiApproved"), "isFsfLibre": l.get("isFsfLibre")} for l in d["licenses"] if l["licenseId"] in ("AGPL-3.0-only", "AGPL-3.0-or-later", "Apache-2.0")}}
for w, m in ((W2, "nvidia/nvjpeg/bin/nvjpeg64_12.dll"), (W1, "nvidia/nvimgcodec/extensions/nvjpeg_ext_0.dll"), (W1, "nvidia/nvimgcodec/nvimgcodec_0.dll"), (W1, "nvidia/nvimgcodec/nvimgcodec_impl.cp312-win_amd64.pyd")):
    r = subprocess.run([sys.executable, "-I", fat, os.path.join(dl, w), m], capture_output=True, text=True, check=True)
    facts["fatbin"][f"{w}#{m}"] = json.loads(r.stdout)
json.dump(facts, open(out, "w", encoding="utf-8"), indent=1)
print("ok")
