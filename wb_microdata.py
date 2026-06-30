"""World Bank Microdata Library helper for LSMS-ISA.

TWO layers, because the WB library splits them:
  1. DISCOVERY  -> fully OPEN catalog API (no key, no login). Enumerate every
                   LSMS-ISA dataset, its data files, and its variables.
  2. DOWNLOAD   -> requires a FREE account login (even 'public' files gate the
                   actual zip behind accepting the data-use terms). No anonymous
                   bulk download exists. Use your logged-in session cookie.

Usage:
  python wb_microdata.py discover           # writes lsms_isa_manifest.csv (no auth)
  python wb_microdata.py files NGA_2023_GHSP-W5_v01_M     # list files for one study
  python wb_microdata.py download <id> --cookie "<your session cookie>"
"""
import sys, json, csv, urllib.request, urllib.parse, time

BASE = "https://microdata.worldbank.org/index.php/api"   # open catalog API root
UA = {"User-Agent": "Mozilla/5.0"}
# the 8 LSMS-ISA (Integrated Surveys on Agriculture) countries
ISA = ["Burkina Faso", "Ethiopia", "Malawi", "Mali", "Niger", "Nigeria", "Tanzania", "Uganda"]

def _get(url, tries=5):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:               # 502/timeout = transient WB load
            last = e; time.sleep(2 * (i + 1))
    raise last

def discover():
    rows = []
    for c in ISA:
        q = urllib.parse.urlencode({"sk": "LSMS-ISA", "country": c, "ps": 100, "format": "json"})
        try:
            res = _get(f"{BASE}/catalog/search?{q}").get("result", {}).get("rows", [])
        except Exception as e:
            print(f"  ! {c}: {e}"); continue
        for x in res:
            if x.get("repositoryid") == "lsms":   # the LSMS collection (ISA panels live here)
                rows.append({"id": x["id"], "idno": x["idno"], "country": x["nation"],
                             "year_start": x["year_start"], "year_end": x["year_end"],
                             "title": x["title"], "varcount": x.get("varcount"),
                             "url": x["url"].replace("\\/", "/")})
        time.sleep(0.3)
    if not rows:
        print("No datasets returned (WB API may be down - rerun in a minute)."); return
    rows.sort(key=lambda r: (r["country"], r["year_start"]))
    with open("lsms_isa_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"wrote lsms_isa_manifest.csv: {len(rows)} datasets across {len(set(r['country'] for r in rows))} countries")
    for r in rows:
        print(f"  {r['id']:>5}  {r['idno']:<34} {r['country']:<13} {r['year_start']}")

def files(idno):
    d = _get(f"{BASE}/catalog/{idno}/data_files?format=json").get("datafiles", {})
    print(f"{idno}: {len(d)} data files")
    for k, v in d.items():
        print(f"  {k:>4} {v['file_name']:<34} cases={v.get('case_count')} vars={v.get('var_count')}")

def variables(idno, fileid=None):
    # the endpoint behind the user's listVariables link
    u = f"{BASE}/catalog/{idno}/variables?format=json"
    d = _get(u)
    vs = d.get("variables", d)
    print(json.dumps(vs, indent=2)[:2000])

def download(study_id, cookie, dest="."):
    """Download all microdata resources for a study using your logged-in cookie.
    Get the cookie from your browser (DevTools > Application > Cookies) AFTER you
    log in at microdata.worldbank.org and have accepted the dataset's terms once."""
    import os
    page = f"https://microdata.worldbank.org/index.php/catalog/{study_id}/download"
    req = urllib.request.Request(page, headers={**UA, "Cookie": cookie})
    html = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "ignore")
    import re
    links = sorted(set(re.findall(r'href="([^"]*?/download/[^"]+?)"', html)))
    if not links:
        print("No download links found - are you logged in AND accepted the terms for this study?"); return
    for link in links:
        if link.startswith("/"): link = "https://microdata.worldbank.org" + link
        fn = os.path.join(dest, link.rstrip("/").split("/")[-1] or f"{study_id}.zip")
        print("downloading", link)
        r = urllib.request.Request(link, headers={**UA, "Cookie": cookie})
        with urllib.request.urlopen(r, timeout=600) as resp, open(fn, "wb") as out:
            out.write(resp.read())
        print("  ->", fn)

if __name__ == "__main__":
    a = sys.argv
    if len(a) < 2 or a[1] == "discover": discover()
    elif a[1] == "files": files(a[2])
    elif a[1] == "variables": variables(a[2])
    elif a[1] == "download":
        ck = a[a.index("--cookie") + 1] if "--cookie" in a else ""
        download(a[2], ck)
