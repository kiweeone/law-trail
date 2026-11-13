"""Per-assembly MP rosters and dated parliamentary-group memberships.

ASSEMBLIES: folder number (as used in bill signatures, e.g. "49") -> {id, start, end, name}
resolve(name, ns) -> MP id within that assembly
group_at(mp_id, date) -> parliamentary group short name at that date
"""
import datetime as dt, json, pathlib, re
import pbg

HERE = pathlib.Path(__file__).parent
FOLDER_TO_ID = {"47": 57, "48": 58, "49": 59, "50": 60, "51": 61, "52": 62}


def _assemblies():
    arch = {a["A_ns_id"]: a for a in pbg.get("archive/bg")}
    out = {}
    for f, i in FOLDER_TO_ID.items():
        a = arch.get(i, {})
        out[f] = {"id": i, "start": a.get("A_ns_start", "2026-04-30"), "end": a.get("A_ns_end", "9999-12-31"),
                  "name": (a.get("A_nsL_value") or f"{f}-то Народно събрание").title()}
    return out


ASSEMBLIES = _assemblies()


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().upper()


def _snapshot_dates(start, end, step_days=40):
    s = dt.date.fromisoformat(start)
    e = min(dt.date.fromisoformat(end) if end[:4] != "9999" else dt.date.today(), dt.date.today())
    d, out = s + dt.timedelta(days=7), []
    while d < e:
        out.append(d.isoformat()); d += dt.timedelta(days=step_days)
    out.append((e - dt.timedelta(days=1)).isoformat())
    return out


def _build():
    names, members = {}, []
    for f, a in ASSEMBLIES.items():
        mps = pbg.get(f"fn-mps/bg/{a['id']}") or []
        idx = {}
        for m in mps:
            full = _norm(m["A_ns_MP_short_name"])
            parts = full.split()
            idx[full] = m["A_ns_MP_id"]
            if len(parts) >= 3:
                idx.setdefault(f"{parts[0]} {parts[-1]}", m["A_ns_MP_id"])
        names[f] = idx
        for d in _snapshot_dates(a["start"], a["end"]):
            snap = pbg.get(f"coll-list-ns/bg?nsId={a['id']}&date={d}") or {}
            for m in snap.get("colListMP", []):
                members.append((m["A_ns_MP_id"], m["A_ns_CL_value_short"], m["A_ns_MSP_date_F"], m["A_ns_MSP_date_T"], f,
                                " ".join(m[f"A_ns_MPL_Name{i}"] for i in (1, 2, 3)).title()))
    members = sorted(set(members))
    return names, members


_NAMES, _MEMBERS = None, None


def _load():
    global _NAMES, _MEMBERS
    if _NAMES is None:
        p = HERE / "rosters.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            _NAMES, _MEMBERS = d["names"], [tuple(x) for x in d["members"]]
        else:
            _NAMES, _MEMBERS = _build()
            p.write_text(json.dumps({"names": _NAMES, "members": _MEMBERS}, ensure_ascii=False), encoding="utf-8")


def current():
    """Folder number of the sitting assembly."""
    return max(ASSEMBLIES, key=int)


def refresh(ns=None):
    """Re-read the sitting assembly's roster: new MPs become resolvable, today's group memberships are recorded.

    Memberships that were open at the last look and are gone now are closed with today's date, so a past
    proposal still resolves to the group its author sat in then. Returns the current MP ids.
    """
    global _NAMES, _MEMBERS
    _load()
    ns = ns or current()
    a, today = ASSEMBLIES[ns], dt.date.today().isoformat()
    mps = pbg.get_fresh(f"fn-mps/bg/{a['id']}")
    snap = pbg.get_fresh(f"coll-list-ns/bg?nsId={a['id']}&date={today}")
    if not mps or not (snap or {}).get("colListMP"):
        raise RuntimeError("parliament.bg returned no MP roster")
    idx = _NAMES.setdefault(ns, {})
    for m in mps:
        full = _norm(m["A_ns_MP_short_name"])
        parts = full.split()
        idx[full] = m["A_ns_MP_id"]
        if len(parts) >= 3:
            idx.setdefault(f"{parts[0]} {parts[-1]}", m["A_ns_MP_id"])
    now = {(m["A_ns_MP_id"], m["A_ns_CL_value_short"], m["A_ns_MSP_date_F"], m["A_ns_MSP_date_T"], ns,
            " ".join(m[f"A_ns_MPL_Name{i}"] for i in (1, 2, 3)).title()) for m in snap["colListMP"]}
    open_now = {(r[0], r[1], r[2]) for r in now}
    kept = []
    for r in _MEMBERS:
        if r[4] == ns and r[3].startswith("9999") and (r[0], r[1], r[2]) not in open_now:
            r = (r[0], r[1], r[2], today, r[4], r[5])           # was open, is gone: close it today
        kept.append(tuple(r))
    _MEMBERS = sorted(set(kept) | now)
    (HERE / "rosters.json").write_text(json.dumps({"names": _NAMES, "members": _MEMBERS}, ensure_ascii=False), encoding="utf-8")
    return sorted({m["A_ns_MP_id"] for m in mps})


def resolve(name, ns):
    _load()
    key = _norm(name)
    idx = _NAMES.get(ns, {})
    if key in idx:
        return idx[key]
    parts = key.split()
    if len(parts) >= 2:
        return idx.get(f"{parts[0]} {parts[-1]}")
    return None


def group_at(mp_id, date, ns=None):
    _load()
    best = None
    for (i, g, f, t, nsf, _n) in _MEMBERS:
        if i != mp_id or (ns and nsf != ns):
            continue
        if f <= date <= t:
            return g
        best = best or g
    return best


def mp_name(mp_id):
    _load()
    for (i, g, f, t, nsf, n) in _MEMBERS:
        if i == mp_id:
            return n
    return None


def short_group(g):
    return re.sub(r'^(?:ПГ на |ПГ |Парламентарна група )', "", g or "").strip('"').replace("“", "").replace("„", "")


if __name__ == "__main__":
    _load()
    from collections import Counter
    for f in ASSEMBLIES:
        gs = Counter(short_group(g) for (i, g, fr, t, nsf, n) in _MEMBERS if nsf == f)
        print(f, ASSEMBLIES[f]["start"], ASSEMBLIES[f]["end"], len(_NAMES.get(f, {})), "names |", dict(gs.most_common(9)))
