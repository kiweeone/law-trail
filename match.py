"""Match ДВ laws to parliament.bg bills via the bill's promulgation issue + title."""
import json, re, pathlib, difflib
import pbg

HERE = pathlib.Path(__file__).parent


def key(t):
    t = t.lower().replace("законопроект", "закон")
    return re.sub(r"[^а-яa-z0-9 ]", "", re.sub(r"\s+", " ", t)).strip()


def main():
    laws = json.loads((HERE / "laws.json").read_text(encoding="utf-8"))
    bl = pbg.bills("2026-04-01", "2026-11-04")
    det = [d for d in (pbg.bill(b["L_Act_id"]) for b in bl) if d]
    by_issue = {}
    for d in det:
        if d.get("L_Act_dv_iss"):
            by_issue.setdefault(int(d["L_Act_dv_iss"]), []).append(d)
    out = []
    for law in laws:
        cands = by_issue.get(law["dv_issue"], [])
        best, score = None, 0
        for d in cands:
            s = difflib.SequenceMatcher(None, key(law["title"]), key(d["L_ActL_title"])).ratio()
            if s > score:
                best, score = d, s
        if not best or score <= 0.8:
            # Fallback: bill's ДВ field not filled in yet -> title match among bills
            # submitted before adoption that have a second-reading report.
            best, score = None, 0
            for d in det:
                if d.get("L_Act_dv_iss") or not d.get("stan_list2_1"):
                    continue
                if law["adopted"] and d["L_Act_date"][:10] > law["adopted"]:
                    continue
                s = difflib.SequenceMatcher(None, key(law["title"]), key(d["L_ActL_title"])).ratio()
                if s > score:
                    best, score = d, s
            law["match_method"] = "title_fallback"
        else:
            law["match_method"] = "dv_issue"
        law["bill_id"] = best["L_Act_id"] if best and score > 0.8 else None
        law["match_score"] = round(score, 2)
        out.append(law)
    (HERE / "laws.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out, det


if __name__ == "__main__":
    out, det = main()
    m = [l for l in out if l["bill_id"]]
    print(f"matched {len(m)}/{len(out)}")
    for l in out:
        if not l["bill_id"]:
            print("  unmatched:", l["dv_issue"], l["title"][:90], l["match_score"])
