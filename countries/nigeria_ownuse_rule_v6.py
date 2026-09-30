"""Round 6, point 2: how Nigeria's 1,839 own-use producers are identified.

The build (build_harmonized_v2.py) takes them from the derived work-status
variable s4aq21 == 2 ("FAMILY FARM ONLY"). This script shows which answers to
the output-destination questions put a person there:
  s4aq13a  destination of farm output in the last seven days
           (1 only for sale, 2 both, 3 only for household use)
  s4aq13b  share sold, if both (1 <1/4, 2 1/4, 3 1/2, 4 3/4, 5 >3/4)
  s4aq13c  at exactly 1/2: 1 mainly sold, 2 mainly kept, 3 insists 50/50
  s4aq19a/b the same questions for usual farm work, asked of people with
           no farm work in the last seven days.
Writes a new file only: results/ngownuse_v6_py.json.
"""
import json
import pandas as pd

lab = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv",
                  low_memory=False)


def code(s):
    return pd.to_numeric(s.astype("string").str.extract(r"^\s*(\d+)")[0], errors="coerce")


st = code(lab["s4aq21"])
a, b, c = code(lab["s4aq13a"]), code(lab["s4aq13b"]), code(lab["s4aq13c"])
ua, ub = code(lab["s4aq19a"]), code(lab["s4aq19b"])

# mainly for household use: sells at most a quarter, or half with "mainly kept"
week_only = a.eq(3)
week_mainly = a.eq(2) & (b.isin([1, 2]) | (b.eq(3) & c.eq(2)))
usual_only = a.isna() & ua.eq(3)
usual_mainly = a.isna() & ua.eq(2) & ub.isin([1, 2])
rule = week_only | week_mainly | usual_only | usual_mainly

fam = st.eq(2)
out = {
    "family_farm_only": int(fam.sum()),
    "week_only_household": int((fam & week_only).sum()),
    "week_mainly_household": int((fam & week_mainly).sum()),
    "usual_only_household": int((fam & usual_only).sum()),
    "usual_mainly_household": int((fam & usual_mainly).sum()),
    "only_household_total": int((fam & (week_only | usual_only)).sum()),
    "mainly_household_total": int((fam & (week_mainly | usual_mainly)).sum()),
    "family_farm_failing_rule": int((fam & ~rule).sum()),
    # people meeting the destination rule who have other work (status 3)
    "rule_met_with_other_work": int((rule & st.eq(3)).sum()),
}
assert out["family_farm_only"] == 1839
assert out["family_farm_failing_rule"] == 0
json.dump(out, open("results/ngownuse_v6_py.json", "x"), indent=1)
print(json.dumps(out, indent=1))
