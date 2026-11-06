"""Extract second-reading proposals (who proposed what, outcome) from committee reports."""
import json, re, html, pathlib
import pbg

HERE = pathlib.Path(__file__).parent

HEAD = re.compile(r"^\s*Предложени[ея] (?:на|от) (?P<who>[^:\n(]+?)(?:\s*\(№\s*(?P<rn>[\d-]+)\))?(?:\s*,?\s*направено по реда[^:\n]*)?\s*:\s*$", re.M)
OUTCOME = re.compile(
    r"(Комисията подкрепя по принцип предложението|Комисията подкрепя предложението|"
    r"Комисията не подкрепя предложението|Предложението е оттеглено|Комисията подкрепя частично предложението|"
    r"решение за недопустимост на предложението|прие решение да не допусне за разглеждане)")
PARA = re.compile(r"^\s*§\s*(\d+)\.", re.M)
PZR = re.compile(r"^\s*(?:Преходни и заключителни разпоредби|Заключителни разпоредби|Преходни разпоредби)\s*$", re.M | re.I)
NEW_PARA = re.compile(r"Комисията предлага да се създад\w+ нов\w* (§[^:\n]{1,40}):")
OTHER_LAW = re.compile(r"(?:В|Във)\s+((?:Закона|Кодекса|[А-Я]\w+ кодекс|Търговския закон)[^()\n§]{3,160}?)\s*\([Оо]бн\.")
OUTCOME_LABEL = {
    "Комисията подкрепя предложението": "supported",
    "Комисията подкрепя по принцип предложението": "supported_in_principle",
    "Комисията подкрепя частично предложението": "partly_supported",
    "Комисията не подкрепя предложението": "rejected",
    "Предложението е оттеглено": "withdrawn",
    "решение за недопустимост на предложението": "inadmissible_out_of_scope",
    "прие решение да не допусне за разглеждане": "inadmissible_out_of_scope",
}


def clean(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"[ \t\xa0]+", " ", s)


def _roster():
    idx = {}
    for m in pbg.get("coll-list-ns/bg")["colListMP"]:
        n1, n2, n3 = (m[f"A_ns_MPL_Name{i}"].title() for i in (1, 2, 3))
        rec = {"id": m["A_ns_MP_id"], "name": f"{n1} {n2} {n3}", "group": m["A_ns_CL_value_short"]}
        for k in (f"{n1} {n2} {n3}", f"{n1} {n3}"):
            idx[k.lower()] = rec
    return idx


ROSTER = _roster()


CTX = {"ns": None, "date": None}  # set by the backfill to resolve names within a past assembly


def resolve(name):
    if CTX["ns"]:
        import rosters
        i = rosters.resolve(name, CTX["ns"])
        if not i:
            return None
        return {"id": i, "name": rosters.mp_name(i) or name, "group": (rosters.group_at(i, CTX["date"] or "9999", CTX["ns"]) or "").strip()}
    return ROSTER.get(re.sub(r"\s+", " ", name).strip().lower())


def split_names(who):
    who = re.sub(r",?\s*(?:направено\s+)?по\s+(?:реда\s+на\s+)?чл\..*$", "", who.strip())
    who = re.sub(r"\bгр\.\s*н\.\s*пр\.?", "група н.п.", who)
    who = re.sub(r"^(?:н\.\s*п\.|нар\.\s*пр\.|народн\w+ представител\w*)\s*", "", who.strip())
    group = bool(re.search(r"група", who))
    who = re.sub(r"\s*и\s+група\s+(?:н\.\s*п\.|нар\.\s*пр\.|народни представители)\.?", "", who)
    names = [re.sub(r"^(?:н\.?\s*п\.?|нар\.?\s*пр\.?|н\.\s*пр\.?)\s+", "", n.strip(" .")) for n in re.split(r",\s*|\s+и\s+", who)]
    names = [n for n in names if n]
    return names, group


def report_for(bill):
    rows = bill.get("stan_list2_1") or []
    if not rows:
        return None, None
    s = rows[-1]
    r = pbg.get(f"com-stan/bg/{s['A_Cm_Stanid']}")
    return (clean(r.get("A_Cm_Stan_text")) if r else None), s


def extract(bill):
    text, meta = report_for(bill)
    if not text:
        return None
    mp_by_rn = {p["RN_DOC"]: p["imp_list"] for p in bill.get("proposal_12_list") or []}
    pzr_at = PZR.search(text)
    pzr_pos = pzr_at.start() if pzr_at else len(text)
    heads = list(HEAD.finditer(text))
    props = []
    for k, h in enumerate(heads):
        end = heads[k + 1].start() if k + 1 < len(heads) else len(text)
        chunk = text[h.end():end]
        o = OUTCOME.search(chunk)
        body = chunk[:o.start()] if o else chunk[:1500]
        paras = PARA.findall(text[:h.start()])
        names, group = split_names(h.group("who"))
        rn = h.group("rn")
        props.append({
            "proposers": names, "and_group": group, "doc": rn,
            "mp_ids": [m["A_ns_MP_id"] for m in mp_by_rn.get(rn, [])]
                      or [r["id"] for r in map(resolve, names) if r],
            "groups": sorted({r["group"] for r in map(resolve, names) if r}),
            "near_para": int(paras[-1]) if paras else None,
            "in_pzr": h.start() > pzr_pos,
            "outcome": OUTCOME_LABEL.get(o.group(1)) if o else "unclear",
            "other_laws": sorted({re.sub(r"\s+", " ", m).strip() for m in OTHER_LAW.findall(body)}),
            "text": body.strip()[:600],
        })
    new_paras = NEW_PARA.findall(text)
    return {
        "report_id": meta["A_Cm_Stanid"], "committee": meta["A_ns_CL_value"], "report_date": meta["A_Cm_Stan_date"],
        "report_chars": len(text), "proposals": props, "committee_new_paras": new_paras,
    }


def origin(text, law_name, props):
    """Was this other-law amendment in the bill as introduced, or added at second reading (and by whom)?"""
    core = re.sub(r"^(Закон|Кодекс)\s+", "", law_name)[:60]
    hits = [m.start() for m in re.finditer(r"(?:В|Във)\s+(?:\S+\s+)?" + re.escape(core) + r"[^(]{0,80}\([Оо]бн", text)]
    if not hits:
        return {"origin": "not_found_in_report"}
    i = hits[-1]  # last occurrence = the committee's final wording
    before = text[max(0, i - 400):i]
    after = text[i:i + 30000]
    mentions = [{"proposers": p["proposers"], "mp_ids": p["mp_ids"], "outcome": p["outcome"], "doc": p["doc"]}
                for p in props if any(core[:40] in ol for ol in p["other_laws"])]
    by = [m for m in mentions if m["outcome"].startswith(("supported", "partly"))]
    if re.search(r"Комисията предлага да се създад\w+ нов", before):
        return {"origin": "added_at_second_reading", "proposed_by": by}
    m = re.search(r"Комисията (подкрепя текста на вносителя|подкрепя по принцип текста на вносителя|предлага)", after)
    if m and "вносителя" in m.group(1):
        return {"origin": "in_bill_as_introduced", "proposed_by": by}
    return {"origin": "unclear", "proposed_by": by}


def main():
    laws = json.loads((HERE / "laws.json").read_text(encoding="utf-8"))
    for law in laws:
        if not law.get("bill_id"):
            continue
        b = pbg.bill(law["bill_id"])
        law["bill_sign"] = b["L_Act_sign"]
        law["bill_date"] = b["L_Act_date"][:10]
        law["sponsors_mp"] = [{"id": m["A_ns_MP_id"], "name": " ".join(m[f"A_ns_MPL_Name{i}"] for i in (1, 2, 3)).title()}
                              for m in b.get("imp_list") or []]
        law["sponsor_cabinet"] = bool(b.get("imp_list_min"))
        law["committees"] = [(d["A_ns_CL_value"], d["L_Act_DTL_value"]) for d in b.get("dist_list") or []]
        law["stakeholder_opinions"] = [s["A_Cm_Stan_sub"] for s in b.get("standp_list") or []]
        law["bill_url"] = f"https://www.parliament.bg/bg/bills/ID/{law['bill_id']}"
        law["second_reading"] = extract(b)
        text = report_for(b)[0]
        if text and law["second_reading"]:
            for a in law["pzr_other_laws"]:
                a.update(origin(text, a["law"], law["second_reading"]["proposals"]))
    (HERE / "laws.json").write_text(json.dumps(laws, ensure_ascii=False, indent=1), encoding="utf-8")
    return laws


if __name__ == "__main__":
    laws = main()
    for l in laws:
        sr = l.get("second_reading")
        if not sr:
            continue
        ps = sr["proposals"]
        from collections import Counter
        c = Counter(p["outcome"] for p in ps)
        print(f"{l['title'][:60]:60} props={len(ps):3d} {dict(c)} new§={len(sr['committee_new_paras'])}")
