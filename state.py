"""Compact state kept in the repository so an update can start from an empty cache.

bills.json        every bill of the covered assemblies: id, ns, title, date, status, sponsor MP ids
mp_profiles.json  the profile fields the site uses, per parliament.bg MP id
update_state.json last State Gazette contents page scanned, last run
"""
import json, pathlib, re
import pbg

HERE = pathlib.Path(__file__).parent
BILLS, PROFILES, STATE = HERE / "bills.json", HERE / "mp_profiles.json", HERE / "update_state.json"


def load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=None, separators=(",", ":")), encoding="utf-8")


def compact_bill(d):
    return {"id": d["L_Act_id"], "ns": str(d.get("A_ns_folder") or ""), "t": d["L_ActL_title"], "d": (d.get("L_Act_date") or "")[:10],
            "st": "promulgated" if d.get("L_Act_dv_iss") else ("withdrawn" if d.get("withdrawn") else "pending"),
            "imp": [m["A_ns_MP_id"] for m in d.get("imp_list") or []],
            **({"into": d["trans_list"][0]["L_Act_id"]} if d.get("trans_list") else {}),
            **({"cab": True} if d.get("imp_list_min") else {})}


def originals(b, getbill=None):
    """Bills that were merged into this common bill (общ законопроект) after first reading."""
    getbill = getbill or pbg.bill
    return [d for d in (getbill(x["L_Act_id"]) for x in b.get("union_list") or []) if d]


def compact_profile(p):
    keep = {k: p.get(k) for k in ("A_ns_MPL_Name1", "A_ns_MPL_Name2", "A_ns_MPL_Name3", "A_ns_MP_BDate", "A_ns_Va_name")}
    keep["prsList"] = [{"A_ns_MP_Pr_TL_value": x["A_ns_MP_Pr_TL_value"]} for x in p.get("prsList") or []]
    keep["mshipList"] = [{k: m[k] for k in ("A_ns_CL_value", "A_ns_MP_PosL_value", "A_ns_MSP_date_T")} for m in p.get("mshipList") or []
                         if m["A_ns_MSP_date_T"].startswith("9999") and re.match(r"(Временна )?[Кк]омисия", m["A_ns_CL_value"])]
    return keep


def journey(l, b, first_reading_date):
    """Dated steps of a law's path, from its bill record. A common bill starts with its originals: they were filed,
    reported on and passed at first reading; the common bill only exists from the second reading on."""
    orig = originals(b)
    act = b.get("activity") or []
    second = [a["L_Act_St_date"] for a in act if a.get("L_Act_St_date") and a.get("L_Act_St2_name") == "зала второ гласуване" and a.get("L_Act_St_name") == "приет"]
    st1 = [s["A_Cm_Stan_date"] for s in b.get("stan_list") or [] if s.get("A_Cm_Stan_date")]
    st2 = [s["A_Cm_Stan_date"] for s in b.get("stan_list2_1") or [] if s.get("A_Cm_Stan_date")]
    dl = b.get("L_act_proposal_date") or ""
    try:
        dd, mm, yy = (l.get("dv_date") or "").split("."); dv = f"{yy}-{int(mm):02d}-{int(dd):02d}"
    except Exception:
        dv = ""
    if orig:
        st1 = [s["A_Cm_Stan_date"] for o in orig for s in o.get("stan_list") or [] if s.get("A_Cm_Stan_date")] or st1
    sub = min([(o.get("L_Act_date") or "")[:10] for o in orig if o.get("L_Act_date")] or [(b.get("L_Act_date") or "")[:10]])
    return {"sub": sub, "r1c": min(st1) if st1 else "", "r1": first_reading_date(b),
            "dl": dl if dl[:4].isdigit() and dl[:4] != "0000" else "", "r2c": max(st2) if st2 else "",
            "r2": max(second) if second else (l.get("adopted") or ""), "dv": dv}
