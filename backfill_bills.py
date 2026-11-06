"""Enumerate bill records by ID for past assemblies (47th–51st) via /bill/{id}; cache everything."""
import json, pathlib, concurrent.futures as cf
import pbg
HERE = pathlib.Path(__file__).parent
LO, HI = 163700, 166934
def get(i):
    d = pbg.bill(i)
    return i, d if isinstance(d, dict) and d.get("L_ActL_title") else None
found = []
with cf.ThreadPoolExecutor(6) as ex:
    for k, (i, d) in enumerate(ex.map(get, range(LO, HI))):
        if d:
            found.append({"id": i, "ns": d.get("A_ns_folder"), "date": d["L_Act_date"][:10], "dv": d.get("L_Act_dv_iss"), "dvy": d.get("L_Act_dv_year"),
                          "opinions": len(d.get("standp_list") or []), "r2": bool(d.get("stan_list2_1")), "title": d["L_ActL_title"][:120]})
        if k % 500 == 0:
            print(k, len(found), flush=True)
(HERE / "backfill_bills.json").write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
from collections import Counter
print("bills", len(found), Counter(b["ns"] for b in found))
prom = [b for b in found if b["dv"]]
print("promulgated", len(prom), Counter(b["ns"] for b in prom))
print("opinions on promulgated", Counter({ns: sum(b["opinions"] for b in prom if b["ns"] == ns) for ns in {b["ns"] for b in prom}}))
