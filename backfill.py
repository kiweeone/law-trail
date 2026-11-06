"""Build law records for the 47th–52nd assemblies and write them to laws.json (current set kept in laws_52.json).

Past laws come from bill records (promulgated, with ДВ issue/year); their gazette text is found via the
State Gazette issue-contents index (dv_ns_index.json) and matched by title and issue.
"""
import difflib, json, pathlib, re
import dv, pbg, extract, laws as lawsmod, rosters

HERE = pathlib.Path(__file__).parent
PAST = {"47", "48", "49", "50", "51"}


def key(t):
    t = t.lower().replace("законопроект", "закон")
    return re.sub(r"[^а-яa-z0-9 ]", "", re.sub(r"\s+", " ", t)).strip()


def gazette_match(bill, index):
    """Find the promulgated law in the ДВ index: best title match whose material is in the bill's issue."""
    want = key(bill["L_ActL_title"])
    cands = sorted(((difflib.SequenceMatcher(None, want, key(r["title"])).ratio(), r) for r in index
                    if r["title"].startswith(("Закон", "Кодекс"))), key=lambda x: -x[0])[:6]
    for score, r in cands:
        if score < 0.8:
            break
        d = dv.parse(r["idMat"], dv.fetch(r["idMat"]))
        if d and str(d["issue"]) == str(bill.get("L_Act_dv_iss")) and d["date"].endswith(str(bill.get("L_Act_dv_year"))):
            return d, score
    return None, cands[0][0] if cands else 0


def enrich(law, b, ns):
    """Same fields as extract.main(), with names resolved inside the right assembly."""
    sr_meta = (b.get("stan_list2_1") or [{}])[-1]
    extract.CTX.update(ns=ns, date=(sr_meta.get("A_Cm_Stan_date") or b["L_Act_date"])[:10])
    law["ns"] = ns
    law["bill_id"] = b["L_Act_id"]
    law["bill_sign"] = b["L_Act_sign"]
    law["bill_date"] = b["L_Act_date"][:10]
    law["sponsors_mp"] = [{"id": m["A_ns_MP_id"], "name": " ".join(m[f"A_ns_MPL_Name{i}"] for i in (1, 2, 3)).title()}
                          for m in b.get("imp_list") or []]
    law["sponsor_cabinet"] = bool(b.get("imp_list_min"))
    law["committees"] = [(d["A_ns_CL_value"], d["L_Act_DTL_value"]) for d in b.get("dist_list") or []]
    law["stakeholder_opinions"] = [s["A_Cm_Stan_sub"] for s in b.get("standp_list") or []]
    law["bill_url"] = f"https://www.parliament.bg/bg/bills/ID/{b['L_Act_id']}"
    law["second_reading"] = extract.extract(b)
    text = extract.report_for(b)[0]
    if text and law["second_reading"]:
        for a in law["pzr_other_laws"]:
            a.update(extract.origin(text, a["law"], law["second_reading"]["proposals"]))
    extract.CTX.update(ns=None, date=None)
    return law


def main():
    cur_p = HERE / "laws_52.json"
    if not cur_p.exists():
        cur_p.write_text((HERE / "laws.json").read_text(encoding="utf-8"), encoding="utf-8")
    current = json.loads(cur_p.read_text(encoding="utf-8"))
    out = []
    for law in current:  # re-resolve the current assembly the same way, for consistent group naming
        if law.get("bill_id"):
            enrich(law, pbg.bill(law["bill_id"]), "52")
        else:
            law["ns"] = "52"
        out.append(law)
    index = json.loads((HERE / "dv_ns_index.json").read_text(encoding="utf-8"))
    bills = [b for b in json.loads((HERE / "backfill_bills.json").read_text(encoding="utf-8")) if b["dv"] and b["ns"] in PAST]
    unmatched = []
    for bb in bills:
        b = pbg.bill(bb["id"])
        d, score = gazette_match(b, index)
        if d:
            law = lawsmod.extract(d)
        else:
            unmatched.append((bb["ns"], bb["dv"], bb["dvy"], bb["title"][:80], round(score, 2)))
            law = {"idMat": None, "dv_issue": int(b["L_Act_dv_iss"]), "dv_date": None, "title": re.sub(r"^Законопроект", "Закон", b["L_ActL_title"]),
                   "amends": None, "assembly": int(bb["ns"]), "adopted": (b.get("L_Act_date2") or "")[:10] or None,
                   "body_chars": 0, "pzr_chars": 0, "pzr_other_laws": [], "url": f"https://www.parliament.bg/bg/bills/ID/{b['L_Act_id']}"}
        law["dv_year"] = b.get("L_Act_dv_year")
        law["match_method"] = "bill_first"
        out.append(enrich(law, b, bb["ns"]))
    # stable synthetic ids for laws without a gazette match
    for k, l in enumerate(out):
        if not l.get("idMat"):
            l["idMat"] = -l["bill_id"]
    (HERE / "laws.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print("laws", len(out), Counter(l["ns"] for l in out))
    print("gazette-matched past laws", len(bills) - len(unmatched), "of", len(bills))
    for u in unmatched[:15]:
        print("  unmatched", u)
    return out


if __name__ == "__main__":
    main()
