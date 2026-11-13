"""Assemble site data for the 47th–52nd assemblies and render the page.

The page carries summaries; amendment texts and before/after diffs go to one detail file per assembly
(site/detail-<ns>.json), fetched when a law is opened.
"""
import collections, json, pathlib, re
import pbg, rosters, influence, topics

_BIZ = re.compile(r"(?<![А-ЯA-Z])(?:Е?ООД|Е?АД|ЕТ|КД|КДА|СД|ЕООД|EOOD|OOD|AD|EAD|ET)(?![А-ЯA-Z])|КООПЕРАЦИЯ|LTD|GMBH")
_STATE1 = re.compile(r"ДЪРЖАВНО ПРЕДПРИЯТИЕ|МИНИСТЕРСТВО|^ОБЩИНА|(?:ИЗПЪЛНИТЕЛНА|ДЪРЖАВНА|НАЦИОНАЛНА) АГЕНЦИЯ|АГЕНЦИЯ (?:ЗА|ПО)|ДЪРЖАВЕН|ДИРЕКЦИЯ|ПРОКУРАТУРА|ОБЛАСТНА АДМИНИСТРАЦИЯ|ИНСПЕКЦИЯ|НАРОДНА БАНКА|КОМИСИЯ (?:ЗА|ПО)|^СМЕТНА ПАЛАТА|ОМБУДСМАН|ДЪРЖАВАТА|ИЗБИРАТЕЛНА КОМИСИЯ|НАЦИОНАЛНО БЮРО")
_NGO = re.compile(r"СДРУЖЕНИЕ|ФОНДАЦИЯ|ЧИТАЛИЩЕ|АСОЦИАЦИЯ|СЪЮЗ|КЛУБ|ХРАМ|ЦЪРКОВ|КАМАРА|ФЕДЕРАЦИЯ|ДРУЖЕСТВО|НАСТОЯТЕЛСТВО|ОРГАНИЗАЦИЯ|АКАДЕМИЯ|ФОНД|КОЛЕГИЯ|СИНДИКАТ|КОНФЕДЕРАЦИЯ")
_STATE2 = re.compile(r"(?<![А-Я])(?:УНИВЕРСИТЕТ|УЧИЛИЩЕ|ГИМНАЗИЯ|БОЛНИЦА|ДЪРЖАВН\w*|СЪД|РАЙОНЕН СЪД|ДЕТСКА ГРАДИНА|ИНСТИТУТ|МУЗЕЙ|ТЕАТЪР|БИБЛИОТЕКА)(?![А-Я])")


def etype(name, person):
    """Kind of register entity: biz, ngo, state, other; self/parl/party are dropped from the network."""
    u = re.sub(r"\s+", " ", name.upper()).strip()
    if u == person.upper() or u.startswith(person.upper()):
        return "self"
    if u.startswith("НАРОДНО СЪБРАНИЕ"):
        return "parl"
    if re.search(r"ПАРТИЯ(?![А-Я])|^ПП |КОАЛИЦИЯ|ПОЛИТИЧЕСКО ДВИЖЕНИЕ|^(?:ПРОДЪЛЖАВАМЕ ПРОМЯНАТА|ДЕМОКРАТИЧНА БЪЛГАРИЯ|ГЕРБ|ВЪЗРАЖДАНЕ|ДВИЖЕНИЕ ЗА ПРАВА И СВОБОДИ|ИМА ТАКЪВ НАРОД|ВЕЛИЧИЕ|МЕЧ|ДА,? БЪЛГАРИЯ|ДЕМОКРАТИ ЗА СИЛНА БЪЛГАРИЯ|ЗЕЛЕНОТО ДВИЖЕНИЕ|СЪЮЗ НА ДЕМОКРАТИЧНИТЕ СИЛИ|БЪЛГАРСКИ ВЪЗХОД|АЛИАНС ЗА ПРАВА И СВОБОДИ|МОРАЛ,? ЕДИНСТВО,? ЧЕСТ|ПРОГРЕСИВНА БЪЛГАРИЯ|БЪЛГАРСКА СОЦИАЛИСТИЧЕСКА|ВОЛЯ|НФСБ|АТАКА|ВМРО)(?:$| -| \")", u):
        return "party"
    if _BIZ.search(u):
        return "biz"
    if _STATE1.search(u):
        return "state"
    if _NGO.search(u):
        return "ngo"
    if _STATE2.search(u):
        return "state"
    return "biz"  # archive-format company names often lack the legal form


def split_latin(n):
    """ЩРАК appends the Latin name: 'МАРТИН МД ДОЦОВ ЕООД MARTIN MD DOTSOV' -> (bg, latin)."""
    n = re.sub(r"\s+", " ", n).strip()
    m = re.match(r"^(.*[А-Яа-я][^\"]*?)\s+([A-Z0-9][A-Z0-9 .,&'\-/]{2,})$", n)
    n = re.sub(r"\s+(?:Сдружение|Фондация|Държавно предприятие|Сдружение с нестопанска цел)\s*$", "", n)
    if not m or n.count('"') % 2 or not re.search(r"[A-Z]{3,}", re.sub(r"\b(?:LTD|EOOD|OOD|EAD|AD|ET|LLC)\b", "", m.group(2))):
        return n, ""
    bg = re.sub(r"\s+(?:Сдружение|Фондация|Държавно предприятие)\s*$", "", m.group(1).strip())
    return bg, m.group(2).strip()

HERE = pathlib.Path(__file__).parent
SITE = HERE / "site"
OK = ("supported", "supported_in_principle", "partly_supported")
NS_ORDER = ["52", "51", "50", "49", "48", "47"]


def short_group(g):
    return rosters.short_group(g).strip()


def iso_dv(d):
    try:
        dd, mm, yy = d.split("."); return f"{yy}-{int(mm):02d}-{int(dd):02d}"
    except Exception:
        return ""


def journey(l):
    if not l.get("bill_id"):
        return None
    b = pbg.bill(l["bill_id"])
    act = b.get("activity") or []
    second = [a["L_Act_St_date"] for a in act if a.get("L_Act_St_date") and a.get("L_Act_St2_name") == "зала второ гласуване" and a.get("L_Act_St_name") == "приет"]
    st1 = [s["A_Cm_Stan_date"] for s in b.get("stan_list") or [] if s.get("A_Cm_Stan_date")]
    st2 = [s["A_Cm_Stan_date"] for s in b.get("stan_list2_1") or [] if s.get("A_Cm_Stan_date")]
    dl = b.get("L_act_proposal_date") or ""
    return {"sub": (b.get("L_Act_date") or "")[:10], "r1c": min(st1) if st1 else "", "r1": influence.first_reading_date(b),
            "dl": dl if dl[:4].isdigit() and dl[:4] != "0000" else "", "r2c": max(st2) if st2 else "",
            "r2": max(second) if second else (l.get("adopted") or ""), "dv": iso_dv(l.get("dv_date") or "")}


def main():
    laws = json.loads((HERE / "laws.json").read_text(encoding="utf-8"))
    fps = json.loads((HERE / "footprints.json").read_text(encoding="utf-8")) if (HERE / "footprints.json").exists() else []
    echoes = json.loads((HERE / "crossparty.json").read_text(encoding="utf-8")) if (HERE / "crossparty.json").exists() else []
    ops = json.loads((HERE / "opinions.json").read_text(encoding="utf-8"))
    diffs = json.loads((HERE / "diffs.json").read_text(encoding="utf-8")) if (HERE / "diffs.json").exists() else {}
    rosters._load()
    law_ns = {l["idMat"]: l["ns"] for l in laws}

    # ---- every bill sponsored in these assemblies (current search + past enumeration)
    cur_bills = [b["L_Act_id"] for b in pbg.bills("2026-04-01", "2026-11-04")]
    past_bills = [b["id"] for b in json.loads((HERE / "backfill_bills.json").read_text(encoding="utf-8")) if b["ns"] in set(NS_ORDER)]
    all_bills = [d for d in (pbg.bill(i) for i in dict.fromkeys(cur_bills + past_bills)) if d]

    # ---- MPs across assemblies, with the group they sat in for each assembly
    member_as = collections.defaultdict(dict)  # id -> ns -> (date_T, group)
    for (i, g, f, t, ns, n) in rosters._MEMBERS:
        prev = member_as[i].get(ns)
        if not prev or t > prev[0]:
            member_as[i][ns] = (t, short_group(g))
    ids = set(member_as)
    for l in laws:
        for p in (l.get("second_reading") or {}).get("proposals", []):
            ids.update(p["mp_ids"])
        ids.update(s["id"] for s in l.get("sponsors_mp", []))
    # parliament.bg ids are per mandate; merge mandates into people by full name + date of birth
    prof = {i: (pbg.get(f"mp-profile/bg/{i}") or {}) for i in ids}
    def person_key(i):
        p = prof[i]
        nm = " ".join(p.get(f"A_ns_MPL_Name{k}", "") for k in (1, 2, 3)).strip().upper() or (rosters.mp_name(i) or "").upper()
        return (nm, p.get("A_ns_MP_BDate") or "")
    mandate_ns = {i: next(iter(member_as[i]), None) if member_as.get(i) else None for i in ids}
    people = collections.defaultdict(list)
    for i in ids:
        people[person_key(i)].append(i)
    PID = {}
    for key, mids in people.items():
        latest_id = max(mids, key=lambda i: (NS_ORDER[::-1].index(mandate_ns[i]) if mandate_ns[i] in NS_ORDER else -1, i))
        for i in mids:
            PID[i] = latest_id
    pid = lambda i: PID.get(i, i)
    mps = {}
    for key, mids in people.items():
        i = pid(mids[0])
        p = prof[i]
        as_ = {}
        for m in mids:
            as_.update({ns: v[1] for ns, v in member_as.get(m, {}).items()})
        latest = next((ns for ns in NS_ORDER if ns in as_), None)
        coms = [{"c": m["A_ns_CL_value"], "r": m["A_ns_MP_PosL_value"].strip()} for m in p.get("mshipList") or []
                if m["A_ns_MSP_date_T"].startswith("9999") and re.match(r"(Временна )?[Кк]омисия", m["A_ns_CL_value"])]
        name = " ".join(p.get(f"A_ns_MPL_Name{k}", "") for k in (1, 2, 3)).title().strip() or rosters.mp_name(i) or f"#{i}"
        mps[i] = {"id": i, "n": name, "as": as_, "g": as_.get(latest, ""), "ns": latest, "mand": sorted(mids),
                  "va": (p.get("A_ns_Va_name") or "").split("-", 1)[-1].title(),
                  "prof": ", ".join(x["A_ns_MP_Pr_TL_value"] for x in p.get("prsList") or []),
                  "coms": coms, "bills": [], "props": [], "fp": [], "echo": []}
    for d in all_bills:
        status = "promulgated" if d.get("L_Act_dv_iss") else ("withdrawn" if d.get("withdrawn") else "pending")
        for m in d.get("imp_list") or []:
            if pid(m["A_ns_MP_id"]) in mps:
                mps[pid(m["A_ns_MP_id"])]["bills"].append({"t": d["L_ActL_title"], "d": d["L_Act_date"][:10], "st": status,
                                                      "ns": str(d.get("A_ns_folder") or ""), "u": f"https://www.parliament.bg/bg/bills/ID/{d['L_Act_id']}"})
    for law in laws:
        for k, p in enumerate((law.get("second_reading") or {}).get("proposals", [])):
            for i in {pid(x) for x in p["mp_ids"]}:
                if i in mps:
                    mps[i]["props"].append({"law": law["idMat"], "k": k, "o": p["outcome"]})

    # ---- company ties (ЩРАК): match level + entities per person; the parliament itself, parties and
    #      personal BULSTAT registrations are dropped so the network shows real ties
    lp = HERE / "shtrack_links.json"
    links = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {}
    CO, co_idx = [], {}
    for i, v in links.items():
        m = mps.get(pid(int(i)))
        if not m:
            continue
        co = []
        for f in v.get("f", []):
            t = etype(f["n"], m["n"])
            if t in ("self", "parl", "party"):
                continue
            k = co_idx.get(f["e"])
            if k is None:
                k = co_idx[f["e"]] = len(CO)
                bg, lat = split_latin(f["n"])
                CO.append({"e": f["e"], "n": bg, **({"l": lat} if lat else {}), "t": t, "m": []})
            if m["id"] not in CO[k]["m"]:
                CO[k]["m"].append(m["id"])
                co.append([k, "; ".join(f["r"])])
        m["sh"] = {"s": v["s"], "f": len(co), **({"g": v["g"]} if v.get("g") else {}), **({"k": v["k"]} if v.get("k") else {})}
        m["co"] = co

    # ---- footprints
    seen, FP = set(), []
    for f in fps:
        key = (influence.org_name(f["org"])[0], tuple(f["proposers"]), f["idMat"], f["passage"][:80])
        if key in seen:
            continue
        seen.add(key)
        strong = f["run_words"] >= 40 or (f["run_words"] >= 20 and f["coverage"] >= 0.4)
        on, ot = influence.org_name(f["org"])
        FP.append({"org": on, "ot": ot, "law": f["idMat"], "ns": law_ns.get(f["idMat"]), "who": f["proposers"], "ids": list(dict.fromkeys(pid(i) for i in f["mp_ids"])),
                   "o": f["outcome"], "w": f["run_words"], "cov": f["coverage"], "order": f["order"], "od": f["opinion_date"],
                   "fr": f["first_reading"], "ou": f["opinion_url"], "pas": f["passage"][:420], "tier": "strong" if strong else "partial"})
    FP.sort(key=lambda f: (f["tier"] != "strong", f["order"] != "opinion_first", -f["w"]))
    for k, f in enumerate(FP):
        for i in f["ids"]:
            if i in mps:
                mps[i]["fp"].append(k)

    # ---- cross-party echoes (names resolved inside the law's assembly)
    EC = []
    by_title = {l["title"]: l for l in laws}
    for e in echoes:
        law = by_title.get(e["law"])
        ns = law["ns"] if law else None
        ids_ = {side: [pid(i) for i in (rosters.resolve(n, ns) for n in e[side]["who"]) if i] for side in ("a", "b")}
        EC.append({"law": law["idMat"] if law else None, "ns": ns, "a": {**e["a"], "ids": ids_["a"]}, "b": {**e["b"], "ids": ids_["b"]},
                   "jac": e["jac"], "t": e["text"][:360]})
        for i in ids_["a"] + ids_["b"]:
            if i in mps:
                mps[i]["echo"].append(len(EC) - 1)

    # ---- organisations
    orgs = {}
    law_by_bill = {l.get("bill_id"): l for l in laws if l.get("bill_id")}
    for o in ops:
        name, typ = influence.org_name(o["org"])
        if name == "(unnamed attachment)":
            continue
        law = law_by_bill.get(o["bill_id"])
        if not law:
            continue
        org = orgs.setdefault(name, {"n": name, "t": typ, "filings": [], "fp": []})
        org["filings"].append({"law": law["idMat"], "d": o["date"], "st": o["stage"], "u": "https://www.parliament.bg" + o["path"]})
    for k, f in enumerate(FP):
        if f["org"] in orgs:
            orgs[f["org"]]["fp"].append(k)
    ORG = sorted(orgs.values(), key=lambda o: (-len({f["law"] for f in o["filings"]}), o["n"]))
    # register entities that also filed opinions on bills (exact or prefix name match)
    onorm = lambda x: re.sub(r"\s+", " ", re.sub(r"[^А-ЯA-Z0-9 ]", " ", x.upper())).strip()
    # org names in opinions are often cut short ("Българска асоциация"), so prefixes only count from 4 words
    form = lambda x: re.sub(r"\b(?:Е?ООД|Е?АД|СДРУЖЕНИЕ|ФОНДАЦИЯ)\s*$", "", x).strip()
    onames = sorted(((form(onorm(o["n"])), k) for k, o in enumerate(ORG) if len(onorm(o["n"])) >= 12), key=lambda t: -len(t[0]))
    for c in CO:
        cn = form(onorm(c["n"]))
        for on, k in (onames if c["t"] in ("biz", "ngo") else []):
            if cn == on or (len(on.split()) >= 4 and cn.startswith(on + " ")):
                c["o"] = k
                break
    ops_by_bill = collections.defaultdict(list)
    for o in ops:
        n, t = influence.org_name(o["org"])
        if n != "(unnamed attachment)":
            ops_by_bill[o["bill_id"]].append({"org": n, "t": t, "d": o["date"], "u": "https://www.parliament.bg" + o["path"]})

    # ---- laws: summary in the page, detail per assembly file
    LAWS, DETAIL = [], collections.defaultdict(dict)
    for l in sorted(laws, key=lambda l: (l.get("adopted") or "", l["idMat"]), reverse=True):
        sr = l.get("second_reading") or {}
        props = sr.get("proposals", [])
        bl = diffs.get(str(l["idMat"])) or []
        aligned = bool(bl) and sum(b["n_props"] for b in bl) == len(props)
        LAWS.append({
            "id": l["idMat"], "ns": l["ns"], "t": l["title"], "iss": l["dv_issue"], "dvy": l.get("dv_year"), "dvd": l.get("dv_date"),
            "ad": l.get("adopted"), "url": l["url"] if l["idMat"] and l["idMat"] > 0 else None,
            "bill": l.get("bill_url"), "sign": l.get("bill_sign"), "sp": [s["name"] for s in l.get("sponsors_mp", [])],
            "spi": list(dict.fromkeys(pid(s["id"]) for s in l.get("sponsors_mp", []))), "cab": l.get("sponsor_cabinet", False),
            "com": [c for c, r in l.get("committees", []) if r == "водеща"][:1],
            "other": [{"law": a["law"], "ch": a["chars"], "or": a.get("origin", "no_report"),
                       "by": [", ".join(p["proposers"][:3]) for p in a.get("proposed_by", [])]} for a in l["pzr_other_laws"]],
            "props": [{"ids": list(dict.fromkeys(pid(i) for i in p["mp_ids"])), "grp": [short_group(g) for g in p["groups"]], "o": p["outcome"], "pzr": p["in_pzr"],
                       **({} if p["mp_ids"] else {"who": p["proposers"][:4]})} for p in props],
            "ops": ops_by_bill.get(l.get("bill_id"), []),
            "tl": journey(l), "nbl": len(bl),
            "bk": dict(collections.Counter(b["kind"] for b in bl)),
        })
        DETAIL[l["ns"]][str(l["idMat"])] = {
            "pt": [p["text"][:420] for p in props], "pw": [p["proposers"] for p in props], "doc": [p["doc"] for p in props],
            "att": l.get("attendees", "")[:900], "al": aligned,
            "bl": [{"lb": b["label"], "k": b["kind"], "d": b.get("diff") if b["kind"] != "unchanged" else None,
                    "ins": b.get("ins", 0), "del": b.get("dele", 0), "fp": b.get("fp", []),
                    "acc": [k for k in b.get("props", []) if aligned and k < len(props) and props[k]["outcome"] in OK],
                    "np": b["n_props"], "dv": b.get("in_dv"), "ex": b["before"][:240] if b["kind"] == "unchanged" else ""} for b in bl],
        }

    # ---- topics: law subject from its title, entity sector from its name; then sector leads:
    #      an MP sponsored or amended a law in a sector where they hold a register role (confirmed matches only)
    for L_ in LAWS:
        L_["t"] = topics.short_title(L_["t"])
        L_["tp"] = topics.law_topics(L_["t"])
    for c in CO:
        c["tp"] = topics.entity_topics(c["n"] + " " + c.get("l", "")) if c["t"] in ("biz", "ngo") else []
    rp = HERE / "shtrack_roles.json"
    roles = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    CF = []
    for L_ in LAWS:
        if not L_["tp"]:
            continue
        who = collections.defaultdict(lambda: {"sp": False, "n": 0, "acc": 0})
        for i in L_["spi"]:
            who[i]["sp"] = True
        for p in L_["props"]:
            for i in p["ids"]:
                who[i]["n"] += 1
                who[i]["acc"] += p["o"] in OK
        tl = L_["tl"] or {}
        start, end = tl.get("sub") or L_["ad"] or "", tl.get("r2") or L_["ad"] or tl.get("dv") or ""
        for i, w in who.items():
            m = mps.get(i)
            if not m or (m.get("sh") or {}).get("s") not in ("matched", "ambiguous"):
                continue
            cos = []
            for k, _ in m.get("co", []):
                tp = [t for t in CO[k]["tp"] if t in L_["tp"]]
                if not tp:
                    continue
                r = (roles.get(CO[k]["e"]) or {}).get(m["sh"]["g"]) or {}
                if not r.get("seen") or not start:
                    st = "undated"
                elif r["from"] and end and r["from"] > end:
                    continue                                   # the role began after the law: not a lead
                elif r["to"] and r["to"] < start:
                    if int(start[:4]) - int(r["to"][:4]) > 3:
                        continue                               # ended long before
                    st = "ended"
                else:
                    st = "active"
                cos.append({"k": k, "st": st, "tp": tp, **({"f": r["from"]} if r.get("from") else {}), **({"to": r["to"]} if r.get("to") else {})})
            if cos:
                best = "active" if any(c["st"] == "active" for c in cos) else "undated" if any(c["st"] == "undated" for c in cos) else "ended"
                sc = 1 + (2 if w["acc"] else 0) + (1 if w["sp"] else 0) + {"active": 2, "undated": 0.5, "ended": 0}[best] + (1 if any(CO[c["k"]]["t"] == "biz" for c in cos) else 0)
                CF.append({"mp": i, "law": L_["id"], "ns": L_["ns"], "tp": sorted({t for c in cos for t in c["tp"]}), "sp": w["sp"], "n": w["n"], "acc": w["acc"],
                           "co": cos, "st": best, "sc": sc})
    CF.sort(key=lambda c: -c["sc"])
    # ---- footprint score: who copied whom matters more when the source is business, came first, and the text passed
    cf_pairs = {(c["mp"], c["law"]) for c in CF}
    for f in FP:
        f["sc"] = ((3 if f["tier"] == "strong" else 1) + {"business": 3, "professional": 2, "civil": 1}.get(f["ot"], 0)
                   + (2 if f["order"] == "opinion_first" else 0) + {"supported": 2, "supported_in_principle": 1.5, "partly_supported": 1.5}.get(f["o"], 0)
                   + (1 if f["cov"] >= 0.6 else 0) + (2 if any((i, f["law"]) in cf_pairs for i in f["ids"]) else 0))
    order = sorted(range(len(FP)), key=lambda k: (FP[k]["tier"] != "strong", -FP[k]["sc"], -FP[k]["w"]))
    remap = {old: new for new, old in enumerate(order)}      # people and organisations point at footprints by index
    FP[:] = [FP[o] for o in order]
    for m in mps.values():
        m["fp"] = sorted(remap[k] for k in m["fp"])
    for o in ORG:
        o["fp"] = sorted(remap[k] for k in o["fp"])

    # ---- groups per assembly
    GR = []
    for ns in NS_ORDER:
        by_g = collections.defaultdict(list)
        for m in mps.values():
            if ns in m["as"]:
                by_g[m["as"][ns]].append(m["id"])
        ns_laws = {l["idMat"] for l in laws if l["ns"] == ns}
        for g, gids in by_g.items():
            gp = list({(p["law"], p["k"]): p for i in gids for p in mps[i]["props"] if p["law"] in ns_laws}.values())
            GR.append({"ns": ns, "g": g, "ids": sorted(gids, key=lambda i: (-sum(1 for p in mps[i]["props"] if p["law"] in ns_laws), mps[i]["n"])),
                       "np": len(gp), "na": sum(p["o"] in OK for p in gp)})
    GR.sort(key=lambda g: (NS_ORDER.index(g["ns"]), -len(g["ids"])))

    ASM = [{"ns": ns, "name": rosters.ASSEMBLIES[ns]["name"], "start": rosters.ASSEMBLIES[ns]["start"],
            "end": rosters.ASSEMBLIES[ns]["end"], "laws": sum(1 for l in laws if l["ns"] == ns)} for ns in NS_ORDER]
    P = [p for l in LAWS for p in l["props"]]
    readable = 0
    for o in ops:
        t = HERE / "raw" / "opinions" / (o["path"].rsplit("/", 1)[-1] + ".txt")
        readable += t.exists() and len(t.read_text(encoding="utf-8").strip()) > 300
    stats = {"laws": len(LAWS), "props": len(P), "acc": sum(p["o"] in OK for p in P), "resolved": sum(1 for p in P if p["ids"]),
             "opinions": len(ops), "readable": readable, "orgs": len(ORG), "fp_strong": sum(1 for f in FP if f["tier"] == "strong"),
             "fp": len(FP), "other": sum(len(l["other"]) for l in LAWS), "mps": len(mps), "bills": len(all_bills),
             "sh": sum(1 for m in mps.values() if (m.get("sh") or {}).get("s") in ("matched", "ambiguous", "name_only")), "blocks": sum(l["nbl"] for l in LAWS)}
    # ---- method numbers, recomputed on every build so the "how it works" page stays honest
    allb = [b for bl in diffs.values() for b in bl]
    chk = [b for b in allb if b.get("in_dv") is not None]
    stats["m"] = {
        "unclear_pct": round(100 * sum(p["o"] == "unclear" for p in P) / max(1, len(P)), 1),
        "resolved_pct": round(100 * stats["resolved"] / max(1, len(P)), 1),
        "dv_checked": len(chk), "dv_found": sum(1 for b in chk if b["in_dv"]),
        "dv_pct": round(100 * sum(1 for b in chk if b["in_dv"]) / max(1, len(chk)), 1),
        "no_before": sum(1 for b in allb if b["kind"] in ("reworded",) and not b["before"]),
        "readable_pct": round(100 * readable / max(1, len(ops)), 1),
        "no_gazette": sum(1 for l in laws if not (l["idMat"] and l["idMat"] > 0)),
        "no_report": sum(1 for l in laws if not l.get("second_reading")),
        "no_report_ratif": sum(1 for l in laws if not l.get("second_reading") and (l.get("title") or "").startswith("Закон за ратифициране")),
        "fp_first": sum(1 for f in FP if f["tier"] == "strong" and f["order"] == "opinion_first"),
        "people": len(mps), "mandates": sum(len(m["mand"]) for m in mps.values()),
        "sh_pct": round(100 * stats["sh"] / max(1, len(mps)), 1),
        "inadm": sum(p["o"] == "inadmissible_out_of_scope" for p in P),
        "shl": dict(collections.Counter((m.get("sh") or {}).get("s", "none") for m in mps.values())),
        "co": len(CO), "co_shared": sum(1 for c in CO if len(c["m"]) > 1), "co_org": sum(1 for c in CO if "o" in c),
        "cf": len(CF), "cf_mps": len({c["mp"] for c in CF}), "cf_st": dict(collections.Counter(c["st"] for c in CF)),
        "asm": len(ASM), "from": ASM[-1]["start"], "updated": __import__("datetime").date.today().isoformat(), "contact": __import__("os").environ.get("LT_CONTACT") or ((HERE / "contact.txt").read_text(encoding="utf-8").strip() if (HERE / "contact.txt").exists() else ""),
    }
    data = {"stats": stats, "asm": ASM, "laws": LAWS, "mps": mps, "groups": GR, "orgs": ORG, "fp": FP, "echo": EC, "co": CO, "cf": CF,
            "topics": {k: {"bg": bg, "en": en} for k, (bg, en) in topics.LABELS.items()}}
    SITE.mkdir(exist_ok=True)
    for ns, d in DETAIL.items():
        (SITE / f"detail-{ns}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (HERE / "site_data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tpl = (SITE / "template.html").read_text(encoding="utf-8")
    page = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (SITE / "law-trail.html").write_text(page, encoding="utf-8")
    deploy(page, stats)
    return stats


def deploy(page, stats):
    """Standalone static site for Vercel/any host: deploy/index.html + detail files."""
    import shutil
    out = HERE / "deploy"
    out.mkdir(exist_ok=True)
    head, body = page.split("</style>", 1)
    desc = (f"Кой оформя българските закони: {stats['laws']} закона, {stats['props']} предложения на депутати, "
            f"{stats['opinions']} становища и връзките на депутатите с фирми, 47-мо – 52-ро Народно събрание.")
    icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%2315171c'/%3E"
            "%3Ccircle cx='9' cy='22' r='4' fill='%23ec6340'/%3E%3Ccircle cx='23' cy='10' r='4' fill='%233e68e0'/%3E%3Cpath d='M9 22L23 10' stroke='%23fff' stroke-width='2.5'/%3E%3C/svg%3E")
    meta = ('<!doctype html>\n<html lang="bg">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            f'<meta name="description" content="{desc}">\n'
            '<meta property="og:title" content="Law Trail">\n'
            f'<meta property="og:description" content="{desc}">\n'
            '<meta property="og:type" content="website">\n'
            f'<link rel="icon" href="{icon}">\n')
    head = head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
    (out / "index.html").write_text(meta + head + "</style>\n</head>\n<body>" + body + "\n</body>\n</html>\n", encoding="utf-8")
    for f in SITE.glob("detail-*.json"):
        shutil.copy(f, out / f.name)
    (out / "vercel.json").write_text(json.dumps({
        "cleanUrls": True,
        "headers": [{"source": "/detail-(.*).json", "headers": [{"key": "Cache-Control", "value": "public, max-age=3600"}]},
                    {"source": "/(.*)", "headers": [{"key": "X-Content-Type-Options", "value": "nosniff"},
                                                    {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"}]}]}, indent=1), encoding="utf-8")
    (out / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")


if __name__ == "__main__":
    print(main())
