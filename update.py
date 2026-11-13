"""Scheduled update: find newly promulgated laws, process only those, merge them into the data and rebuild the site.

Starts from an empty cache (a fresh GitHub runner): everything it needs about older laws is in the repository's
JSON files. Fails (so nothing is committed or published) if a source looks broken or the result fails the sanity checks.

  python3 update.py               run the update
  python3 update.py --selftest 2  proof run: forget the 2 newest laws, find and process them again from the live
                                  sources, and compare with what is stored. Writes nothing.
"""
import concurrent.futures as cf, datetime as dt, json, os, pathlib, re, sys, traceback

import pbg, dv, dv_issues, state, rosters, extract, laws as lawsmod, backfill, opinions, ocr, influence, diffparse, crossparty

HERE = pathlib.Path(__file__).parent
TODAY = dt.date.today().isoformat()
WAIT_DAYS = 45            # how long a promulgated bill may wait for its State Gazette page before it is added without one
EMPTY_RUN, MAX_PAGES, RESCAN = 60, 600, 40   # gazette pages fill in over days: re-read the last RESCAN pages every run


class Stop(Exception):
    """A source is down or the result looks wrong: the run fails and nothing is published."""


def jload(name, default=None):
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def jsave(name, d, indent=1):
    (HERE / name).write_text(json.dumps(d, ensure_ascii=False, indent=indent), encoding="utf-8")


# ---------- 1. bills of the sitting assembly
def check_bills(known_law_bills, forget=()):
    ns = rosters.current()
    listed = pbg.bills_search(rosters.ASSEMBLIES[ns]["start"], TODAY)
    if not listed:
        raise Stop("parliament.bg bill search returned nothing")
    bills = {b["id"]: b for b in state.load(state.BILLS, [])}
    ids = [b["L_Act_id"] for b in listed]
    todo = [i for i in ids if i not in bills or bills[i]["st"] == "pending" or i in forget
            or (bills[i]["st"] == "promulgated" and i not in known_law_bills)]
    with cf.ThreadPoolExecutor(4) as ex:
        full = [d for d in ex.map(pbg.bill_fresh, todo) if isinstance(d, dict) and d.get("L_ActL_title")]
    if todo and len(full) < 0.8 * len(todo):
        raise Stop(f"parliament.bg returned only {len(full)} of {len(todo)} bill records")
    changed = 0
    for d in full:
        c = state.compact_bill(d)
        changed += bills.get(c["id"]) != c
        bills[c["id"]] = c
    new = [d for d in full if d.get("L_Act_dv_iss") and d["L_Act_id"] not in known_law_bills]
    return bills, new, {"listed": len(ids), "checked": len(todo), "changed": changed}


# ---------- 2. State Gazette contents pages published since the last run
def scan_gazette(index, last):
    seen = {r["idMat"] for r in index}
    added, empty, o, newest = [], 0, last - RESCAN, last
    while empty < EMPTY_RUN and o - last < MAX_PAGES:
        o += 1
        rows = dv_issues.rows(dv_issues.fetch(o, fresh=True))
        if not rows:
            empty += 1
            continue
        empty, newest = 0, max(newest, o)
        for r in rows:
            if r["issuer"].startswith("Народно събрание") and r["idMat"] not in seen:
                seen.add(r["idMat"])
                r["idObj"] = o
                added.append(r)
    return added, newest


# ---------- 3. one new law, the same way the past assemblies were built (bill first, then its gazette text)
def make_law(b, index):
    ns = str(b.get("A_ns_folder") or rosters.current())
    d, score = backfill.gazette_match(b, index)
    if d:
        law = lawsmod.extract(d)
    else:
        adopted = (b.get("L_Act_date2") or "")[:10]
        if adopted[:4].isdigit() and adopted > (dt.date.today() - dt.timedelta(days=WAIT_DAYS)).isoformat():
            return None                                  # gazette page not found yet: try again next run
        law = {"idMat": None, "dv_issue": int(b["L_Act_dv_iss"]), "dv_date": None, "title": re.sub(r"^Законопроект", "Закон", b["L_ActL_title"]),
               "amends": None, "assembly": int(ns), "adopted": adopted or None, "body_chars": 0, "pzr_chars": 0, "pzr_other_laws": [],
               "url": f"https://www.parliament.bg/bg/bills/ID/{b['L_Act_id']}"}
    law["dv_year"] = b.get("L_Act_dv_year")
    law["match_method"] = "bill_first"
    backfill.enrich(law, b, ns)
    if not law.get("idMat"):
        law["idMat"] = -law["bill_id"]
    law["tl"] = state.journey(law, b, influence.first_reading_date)
    return law


def read_opinions(b):
    """Download the bill's opinions, extract text, OCR the scans. Returns (records, warnings)."""
    ops, warn = opinions.for_law(b), []
    for o in ops:
        t = opinions.fetch_text(o["path"])
        pdf = opinions.RAW / o["path"].rsplit("/", 1)[-1]
        if len(t.strip()) <= 300 and pdf.suffix.lower() == ".pdf" and pdf.exists():
            try:
                ocr.ocr(pdf)
                t = pdf.with_suffix(pdf.suffix + ".txt").read_text(encoding="utf-8")
            except Exception as e:
                warn.append(f"OCR failed for {pdf.name}: {e}")
        o["chars"] = len(t.strip())
    return ops, warn


def analyse(new_laws, new_ops):
    """Footprints, before/after blocks and cross-group pairs for the new laws only."""
    only = {l["idMat"] for l in new_laws}
    _, fps = influence.main(only=only, laws=new_laws, ops=new_ops, write=False)
    diffs, _ = diffparse.run(only=only, laws=new_laws, fps=fps, write=False)
    pairs = crossparty.main(only=only, laws=new_laws, write=False)
    return fps, diffs, pairs


# ---------- 4. people
def refresh_people(new_laws):
    cur = rosters.refresh()
    prof = state.load(state.PROFILES, {})
    ids = set(cur)
    for l in new_laws:
        ids.update(i for p in (l.get("second_reading") or {}).get("proposals", []) for i in p["mp_ids"])
        ids.update(s["id"] for s in l.get("sponsors_mp", []))
    new_ids = sorted(i for i in ids if str(i) not in prof)
    with cf.ThreadPoolExecutor(4) as ex:
        got = dict(zip(sorted(ids), ex.map(lambda i: pbg.get_fresh(f"mp-profile/bg/{i}"), sorted(ids))))
    for i, p in got.items():
        if p:
            prof[str(i)] = state.compact_profile(p)
    state.save(state.PROFILES, prof)
    return new_ids


def company_ties(report):
    """ЩРАК lookups for people who have none yet, and role dates for new sector leads. Never fatal."""
    try:
        import shtrack_links, shtrack_roles
        before = (jload("shtrack_links.json", {}), jload("shtrack_roles.json", {}))
        mps = jload("site_data.json")["mps"]
        missing = [i for i in mps if "f" not in before[0].get(i, {})]
        if 0 < len(missing) <= 60:
            shtrack_links.run()
        elif missing:
            report["warnings"].append(f"{len(missing)} people have no ЩРАК lookup; too many for one run, skipped")
        shtrack_roles.run()
        after = (jload("shtrack_links.json", {}), jload("shtrack_roles.json", {}))
        report["shtrack_new_people"] = len(after[0]) - len(before[0])
        return after != before
    except Exception as e:
        report["warnings"].append(f"ЩРАК step skipped: {type(e).__name__}: {e}")
        return False


# ---------- 5. checks
def sanity(before, after, n_new):
    bad = []
    for k in ("laws", "props", "opinions", "orgs", "fp", "mps", "bills"):
        if after[k] < before[k]:
            bad.append(f"{k} went down: {before[k]} -> {after[k]}")
    if after["laws"] != before["laws"] + n_new:
        bad.append(f"laws: expected {before['laws'] + n_new}, got {after['laws']}")
    if after["m"]["resolved_pct"] < before["m"]["resolved_pct"] - 2:
        bad.append(f"share of amendments linked to an MP fell: {before['m']['resolved_pct']}% -> {after['m']['resolved_pct']}%")
    if after["m"]["unclear_pct"] > before["m"]["unclear_pct"] + 2:
        bad.append(f"unclear outcomes rose: {before['m']['unclear_pct']}% -> {after['m']['unclear_pct']}%")
    size = (HERE / "deploy" / "index.html").stat().st_size
    if size < 3_000_000:
        bad.append(f"site page is suspiciously small ({size} bytes)")
    return bad


def law_line(l, n_ops, n_fp):
    sr = l.get("second_reading") or {}
    return (f"{l['title'][:110]} — ДВ бр. {l.get('dv_issue')}/{l.get('dv_year')}, "
            f"{len(sr.get('proposals', []))} amendments, {n_ops} opinions, {n_fp} footprints")


def write_report(report, ok=True):
    lines = [f"## Law Trail update — {TODAY}", "", ("**Result: OK**" if ok else "**Result: STOPPED, nothing was published**"), ""]
    for k, label in (("bills", "Bills of the sitting assembly"), ("gazette", "State Gazette"), ("people", "MPs")):
        if k in report:
            lines.append(f"- {label}: {report[k]}")
    lines += ["", f"### New laws: {len(report.get('new', []))}"] + [f"- {x}" for x in report.get("new", [])]
    if report.get("waiting"):
        lines += ["", "### Waiting for their State Gazette page"] + [f"- {x}" for x in report["waiting"]]
    if report.get("totals"):
        lines += ["", "### Totals", report["totals"]]
    if report.get("warnings"):
        lines += ["", "### Warnings"] + [f"- {x}" for x in report["warnings"]]
    if report.get("errors"):
        lines += ["", "### Errors"] + [f"- {x}" for x in report["errors"]]
    text = "\n".join(lines) + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"new_laws={len(report.get('new', []))}\n")


# ---------- the run
def run():
    report = {"warnings": [], "new": [], "waiting": []}
    laws = jload("laws.json")
    import build
    before = build.main()          # the site as the stored data describes it; the comparison point for the checks
    st = state.load(state.STATE, {"dv_last_obj": 12744})
    known = {l["bill_id"] for l in laws if l.get("bill_id")}

    bills, new_bills, info = check_bills(known)
    report["bills"] = f"{info['listed']} listed, {info['checked']} re-checked, {info['changed']} changed"

    index = jload("dv_ns_index.json", [])
    added, newest = scan_gazette(index, st["dv_last_obj"])
    index += added
    report["gazette"] = f"contents pages scanned up to {newest}, {len(added)} new National Assembly items"

    new_laws, new_ops = [], []
    for b in sorted(new_bills, key=lambda b: b["L_Act_id"]):
        law = make_law(b, index)
        if law is None:
            report["waiting"].append(f"{b['L_ActL_title'][:110]} (ДВ бр. {b.get('L_Act_dv_iss')}/{b.get('L_Act_dv_year')})")
            continue
        ops, warn = read_opinions(b)
        report["warnings"] += warn
        new_laws.append(law)
        new_ops += ops
    fps, diffs, pairs = analyse(new_laws, new_ops) if new_laws else ([], {}, [])
    for l in new_laws:
        report["new"].append(law_line(l, sum(o.get("law_bill", o["bill_id"]) == l["bill_id"] for o in new_ops), sum(f["idMat"] == l["idMat"] for f in fps)))

    new_people = refresh_people(new_laws)
    report["people"] = f"roster re-read, {len(new_people)} new profile(s)"

    # ---- merge and write
    if new_laws:
        jsave("laws.json", new_laws + laws)
        all_ops = jload("opinions.json", [])
        have = {(o["bill_id"], o["path"]) for o in all_ops}
        jsave("opinions.json", all_ops + [o for o in new_ops if (o["bill_id"], o["path"]) not in have])
        ids = {l["idMat"] for l in new_laws}
        allf = [f for f in jload("footprints.json", []) if f["idMat"] not in ids] + fps
        allf.sort(key=lambda f: (-f["run_words"], -f["coverage"]))
        jsave("footprints.json", allf)
        alld = jload("diffs.json", {})
        alld.update(diffs)
        jsave("diffs.json", alld, indent=None)
        allp = jload("crossparty.json", []) + pairs
        allp.sort(key=lambda e: -e["shared"])
        jsave("crossparty.json", allp)
    jsave("dv_ns_index.json", index, indent=None)
    state.save(state.BILLS, sorted(bills.values(), key=lambda b: b["id"]))

    after = build.main()
    if company_ties(report):
        after = build.main()
    bad = sanity(before, after, len(new_laws))
    if bad:
        report["errors"] = bad
        raise Stop("; ".join(bad))
    state.save(state.STATE, {"dv_last_obj": newest, "last_run": TODAY})
    report["totals"] = (f"{after['laws']} laws (+{after['laws'] - before['laws']}), {after['props']} amendments (+{after['props'] - before['props']}), "
                        f"{after['opinions']} opinions (+{after['opinions'] - before['opinions']}), {after['fp']} footprints (+{after['fp'] - before['fp']}), "
                        f"{after['mps']} MPs (+{after['mps'] - before['mps']}), {after['bills']} bills (+{after['bills'] - before['bills']})")
    with open(HERE / "UPDATES.md", "a", encoding="utf-8") as f:
        f.write(f"| {TODAY} | {len(new_laws)} | {after['laws']} | {after['props']} | {after['opinions']} | {after['bills']} | {'; '.join(report['warnings'])[:120] or '–'} |\n")
    return report


def selftest(n):
    """Forget the n newest laws that have a gazette page, rebuild them from the live sources, compare."""
    laws = jload("laws.json")
    ns = rosters.current()
    pool = sorted((l for l in laws if l.get("ns") == ns and l.get("bill_id") and l["idMat"] > 0 and l.get("second_reading")),
                  key=lambda l: l.get("adopted") or "", reverse=True)[:n]
    if not pool:
        raise Stop("no law to test with")
    forget = {l["bill_id"] for l in pool}
    known = {l["bill_id"] for l in laws if l.get("bill_id")} - forget
    bills, new_bills, info = check_bills(known, forget=forget)
    found = {b["L_Act_id"]: b for b in new_bills}
    index = jload("dv_ns_index.json", [])
    added, newest = scan_gazette(index, state.load(state.STATE, {"dv_last_obj": 12744})["dv_last_obj"])
    index += added
    stored_ops, stored_fp, stored_diffs = jload("opinions.json", []), jload("footprints.json", []), jload("diffs.json", {})
    rows, ok = [], True
    print(f"Self-test: bill search listed {info['listed']} bills; gazette scanned to page {newest} ({len(added)} new items)\n")
    for old in pool:
        b = found.get(old["bill_id"])
        if not b:
            rows.append((old["title"][:60], "NOT RE-FOUND as a new law")); ok = False
            continue
        law = make_law(b, index)
        if law is None:
            rows.append((old["title"][:60], "gazette page not matched")); ok = False
            continue
        ops, _ = read_opinions(b)
        fps, diffs, _ = analyse([law], ops)
        osr, nsr = old["second_reading"]["proposals"], (law.get("second_reading") or {}).get("proposals", [])
        checks = {
            "gazette id": (old["idMat"], law["idMat"]),
            "title": (old["title"], law["title"]),
            "amendments": (len(osr), len(nsr)),
            "outcomes": ([p["outcome"] for p in osr], [p["outcome"] for p in nsr]),
            "authors": ([sorted(p["mp_ids"]) for p in osr], [sorted(p["mp_ids"]) for p in nsr]),
            "other laws changed": (len(old.get("pzr_other_laws") or []), len(law.get("pzr_other_laws") or [])),
            "opinions": (sum(o.get("law_bill", o["bill_id"]) == old["bill_id"] for o in stored_ops), len(ops)),
            "readable opinions": (sum(o.get("law_bill", o["bill_id"]) == old["bill_id"] and (o.get("chars") or 0) > 300 for o in stored_ops), sum(o["chars"] > 300 for o in ops)),
            "footprints": (sum(f["idMat"] == old["idMat"] for f in stored_fp), len(fps)),
            "before/after blocks": (len(stored_diffs.get(str(old["idMat"]), [])), len(diffs.get(str(law["idMat"]), []))),
        }
        diff = [f"{k}: stored {str(a)[:50]} vs now {str(c)[:50]}" for k, (a, c) in checks.items() if a != c]
        ok = ok and not diff
        rows.append((old["title"][:60], "identical (" + ", ".join(f"{k} {v[1] if not isinstance(v[1], list) else len(v[1])}" for k, v in checks.items() if k in ("amendments", "opinions", "footprints", "before/after blocks")) + ")" if not diff else "DIFFERENT — " + "; ".join(diff)))
    text = "## Law Trail self-test — " + TODAY + "\n\nForgot the newest laws, found and processed them again from parliament.bg and the State Gazette, compared with the stored data.\n\n| Law | Result |\n|---|---|\n" + "\n".join(f"| {a} | {r} |" for a, r in rows) + f"\n\n**{'PASSED' if ok else 'FAILED'}** — nothing was written.\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text)
    return ok


if __name__ == "__main__":
    try:
        if "--selftest" in sys.argv:
            k = sys.argv.index("--selftest")
            sys.exit(0 if selftest(int(sys.argv[k + 1]) if len(sys.argv) > k + 1 else 2) else 1)
        write_report(run())
    except Stop as e:
        write_report({"warnings": [], "errors": [str(e)]}, ok=False)
        sys.exit(1)
    except Exception:
        write_report({"warnings": [], "errors": [traceback.format_exc()[-1500:]]}, ok=False)
        sys.exit(1)
