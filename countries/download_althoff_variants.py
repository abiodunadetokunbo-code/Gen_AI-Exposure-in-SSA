"""Download the Althoff-Reichardt variant task-level files plus the canonical
file, pinned to one commit, and record provenance (URL, commit SHA, date,
SHA-256) for each.

Writes:
  countries/althoff_variants/<variant_name>.csv   (9 files: canonical + 8 variants)
  countries/althoff_provenance.json

Run with the full Python path (see research-data skill). Needs internet
access to raw.githubusercontent.com and api.github.com.
"""
import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone

REPO = "lukasalthoff/ai_labor_markets"
COMMIT = "4706d49b5da3fbc912679a51b670427b52fafd1f"  # main, pinned 2026-09-18
COMMIT_DATE = "2026-06-07T06:22:23Z"

VARIANTS = {
    "canonical_moderate_qwen": "ai_capabilities/task_ai_capabilities.csv",
    "no_explicit_scenario_gpt4o": "ai_capabilities/alternative_specifications/no_explicit_scenario/gpt4o/task_ai_capabilities.csv",
    "no_explicit_scenario_qwen": "ai_capabilities/alternative_specifications/no_explicit_scenario/qwen2.5-72b-awq/task_ai_capabilities.csv",
    "no_explicit_scenario_gptoss": "ai_capabilities/alternative_specifications/no_explicit_scenario/gpt-oss/task_ai_capabilities.csv",
    "slow_qwen": "ai_capabilities/alternative_specifications/slow/qwen2.5-72b-awq/task_ai_capabilities.csv",
    "slow_gptoss": "ai_capabilities/alternative_specifications/slow/gpt-oss/task_ai_capabilities.csv",
    "rapid_qwen": "ai_capabilities/alternative_specifications/rapid/qwen2.5-72b-awq/task_ai_capabilities.csv",
    "rapid_gptoss": "ai_capabilities/alternative_specifications/rapid/gpt-oss/task_ai_capabilities.csv",
    "moderate_gptoss": "ai_capabilities/alternative_specifications/moderate/gpt-oss/task_ai_capabilities.csv",
}

OUTDIR = "althoff_variants"
os.makedirs(OUTDIR, exist_ok=True)

download_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
provenance = {}

for name, path in VARIANTS.items():
    url = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{path}"
    body = urllib.request.urlopen(url, timeout=60).read()
    sha256 = hashlib.sha256(body).hexdigest()
    outpath = os.path.join(OUTDIR, f"{name}.csv")
    with open(outpath, "wb") as f:
        f.write(body)
    n_lines = body.count(b"\n")
    provenance[name] = dict(
        repo=REPO, path=path, commit=COMMIT, commit_date=COMMIT_DATE,
        url=url, download_date=download_date, sha256=sha256,
        n_bytes=len(body), n_lines=n_lines, local_path=f"countries/{outpath}")
    print(f"{name:32s} {len(body):>9,} bytes  sha256={sha256[:16]}...")

with open("althoff_provenance.json", "w") as f:
    json.dump(provenance, f, indent=2)
print("\nwrote althoff_provenance.json")
