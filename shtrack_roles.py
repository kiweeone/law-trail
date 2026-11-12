"""When did an MP hold a role in a company? Read from the company's dated register entries (ЩРАК timeline).

Only fetched for companies that matter for a lead (an MP changed a law in the company's sector), to keep
the load on ЩРАК small. Output: shtrack_roles.json {eik: {guid: {"from": date|None, "to": date|None, "seen": bool}}}
  from  earliest dated entry that lists the person      to  date of the entry that removed them (None = still listed)
"""
import html, json, pathlib, re, time, urllib.parse, urllib.request
import shtrack, topics

HERE = pathlib.Path(__file__).parent
RAW = shtrack.RAW
AJAX = "https://shtrack.net/wp-admin/admin-ajax.php?bird_lang=bg"


def timeline(eik, max_pages=6):
    """All timeline pages for a company (cached). A fresh page gives the nonce the timeline call needs."""
    pages, nonce = [], None
    for page in range(1, max_pages + 1):
        p = RAW / f"t_{eik}_{page}.html"
        if p.exists():
            h = p.read_text(encoding="utf-8")
        else:
            if nonce is None:
                req = urllib.request.Request(f"https://shtrack.net/view/company/{eik}/?bird_lang=bg", headers=shtrack.UA)
                with urllib.request.urlopen(req, timeout=40) as r:
                    s = r.read().decode("utf-8", errors="replace")
                m = re.search(r'BIRD_TIMELINE = \{"ajax":"[^"]*","nonce":"([a-f0-9]+)"', s)
                if not m:
                    break
                nonce = m.group(1)
                time.sleep(1.5)
            data = urllib.parse.urlencode({"action": "bird_company_timeline", "nonce": nonce, "eik": eik, "category": "all", "timeline_page": page}).encode()
            req = urllib.request.Request(AJAX, data=data, headers=shtrack.UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read().decode("utf-8", errors="replace"))
            h = (d.get("data") or {}).get("html", "") if d.get("success") else ""
            p.write_text(h, encoding="utf-8")
            time.sleep(1.5)
        keys = re.findall(r'data-event-key="([^"]+)"', h)
        if not keys or (pages and keys[0] in pages[-1][0]):
            break
        pages.append((set(keys), h))
        if f"timeline_page={page + 1}" not in h:
            break
    return [h for _, h in pages]


def people(side):
    """(guid, NAME) for every person listed on one side of a register entry."""
    out = set()
    for li in re.findall(r"<li[^>]*>(.*?)</li>", side, re.S):
        g = re.search(r"/view/person/p_([0-9a-f]{64})", li)
        if g:
            nm = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", li)).split("·")[0]).strip().upper()
            out.add((g.group(1), nm))
    return out


def for_person(per, guid, name):
    """Merge the periods of every register identity that is this person (same guid, or same full name incl. hyphenated surname)."""
    nm = name.upper()
    hits = [r for (g, n), r in per.items() if g == guid or n == nm or n.startswith(nm + "-") or n.startswith(nm + " -")]
    if not hits:
        return {"from": None, "to": None, "seen": False}
    frm = min((r["from"] for r in hits if r["from"]), default=None)
    to = None if any(r["to"] is None for r in hits) else max(r["to"] for r in hits)
    return {"from": frm, "to": to, "seen": True}


def periods(pages, own_eik):
    """{guid: {from, to}} from the dated before/after lists of people fields."""
    ev = []
    for h in pages:
        for a in re.split(r"<article class=\"event\"", h)[1:]:
            d = re.search(r"<strong>(\d{4}-\d\d-\d\d)", a)
            if not d:
                continue
            # entries recorded on another company's file are about that company, not this one
            if re.search(r"Вписване по партидата на", a):
                continue
            for sec in re.split(r"<section class=\"field\"", a)[1:]:
                sides = re.split(r"<h4>", sec)
                before = people(sides[1]) if len(sides) > 1 else set()
                after = people(sides[2]) if len(sides) > 2 else set()
                prev = re.search(r'<p class="meta">(\d{4}-\d\d-\d\d)', sides[1]) if len(sides) > 1 else None
                ev.append((d.group(1), prev.group(1) if prev else None, before, after))
    out = {}
    for date, prev, before, after in sorted(ev, key=lambda e: e[0]):
        for g in before | after:
            r = out.setdefault(g, {"from": None, "to": None})
            start = prev if (g in before and prev) else date
            if r["from"] is None or start < r["from"]:
                r["from"] = start
            if g in before and g not in after:
                r["to"] = date            # removed by this entry
            elif g in after:
                r["to"] = None            # (re)listed
    return out


def wanted():
    d = json.loads((HERE / "site_data.json").read_text(encoding="utf-8"))
    C, M = d["co"], d["mps"]
    ct = [topics.entity_topics(c["n"] + " " + c.get("l", "")) if c["t"] in ("biz", "ngo") else [] for c in C]
    eiks = {}
    for l in d["laws"]:
        lt = set(topics.law_topics(l["t"]))
        if not lt:
            continue
        for i in set(l["spi"]) | {i for p in l["props"] for i in p["ids"]}:
            m = M[str(i)]
            if (m.get("sh") or {}).get("s") not in ("matched", "ambiguous"):
                continue
            for k, _ in m.get("co", []):
                if lt & set(ct[k]):
                    eiks.setdefault(C[k]["e"], set()).add((m["sh"]["g"], m["n"]))
    return eiks


def run():
    outp = HERE / "shtrack_roles.json"
    out = json.loads(outp.read_text(encoding="utf-8")) if outp.exists() else {}
    want = wanted()
    for n, (eik, guids) in enumerate(sorted(want.items())):
        if eik in out and all(g in out[eik] for g, _ in guids):
            continue
        try:
            per = periods(timeline(eik), eik)
        except Exception as e:
            print("err", eik, e, flush=True)
            continue
        out[eik] = {**out.get(eik, {}), **{g: for_person(per, g, nm) for g, nm in guids}}
        if n % 20 == 0:
            outp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            print(n, len(want), flush=True)
    outp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    allr = [r for v in out.values() for r in v.values()]
    print("companies", len(out), "roles", len(allr), "dated", sum(r["seen"] for r in allr), "ended", sum(1 for r in allr if r["to"]))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        per = periods(timeline(sys.argv[1]), sys.argv[1])
        for (g, n), r in per.items():
            print(n, g[:8], r)
        if len(sys.argv) > 2:
            print("=>", for_person(per, "", sys.argv[2]))
    else:
        run()
