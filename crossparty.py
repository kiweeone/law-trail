"""Near-identical amendments filed on the same law by MPs from different parliamentary groups (a sign of a shared drafter)."""
import itertools, json, pathlib, re
import pbg, extract, rosters

HERE = pathlib.Path(__file__).parent
N, MIN_SHARED, MIN_SIM = 8, 15, 0.6


def shingles(t):
    t = re.sub(r"\((?:обн|Обн)\.[^)]*?(?:\)|$)", " ", t, flags=re.S)
    w = re.findall(r"\w+", t.lower())
    return {" ".join(w[i:i + N]) for i in range(len(w) - N + 1)}


def main(only=None, laws=None, write=True):
    """Cross-group pairs for every law, or only for the idMat values in `only` (returned, not merged)."""
    laws = laws if laws is not None else json.loads((HERE / "laws.json").read_text(encoding="utf-8"))
    out = []
    for l in laws:
        if not l.get("bill_id") or not l.get("second_reading") or (only is not None and l["idMat"] not in only):
            continue
        text, _ = extract.report_for(pbg.bill(l["bill_id"]))
        heads = list(extract.HEAD.finditer(text))
        P = []
        for k, h in enumerate(heads):
            end = heads[k + 1].start() if k + 1 < len(heads) else len(text)
            ch = text[h.end():end]
            o = extract.OUTCOME.search(ch)
            body = ch[:o.start()] if o else ch[:3000]
            body = re.split(r"\n\s*Комисията\b", body)[0]          # never compare the committee's own text
            body = re.sub(r"https?://\S+|№\s*[\d-]+", " ", body)    # links to attached PDFs carry no wording
            names, _ = extract.split_names(h.group("who"))
            ids = [i for i in (rosters.resolve(n, l["ns"]) for n in names) if i]
            date = (l["second_reading"].get("report_date") or "9999")[:10]
            grp = {rosters.short_group(rosters.group_at(i, date, l["ns"]) or "").strip() for i in ids} - {""}
            P.append({"who": names, "grp": grp, "out": extract.OUTCOME_LABEL.get(o.group(1)) if o else "unclear", "body": body, "sh": shingles(body)})
        for a, b in itertools.combinations(P, 2):
            if not a["grp"] or not b["grp"] or a["grp"] & b["grp"] or len(a["sh"]) < MIN_SHARED or len(b["sh"]) < MIN_SHARED:
                continue
            inter = len(a["sh"] & b["sh"])
            sim = inter / min(len(a["sh"]), len(b["sh"]))
            if inter >= MIN_SHARED and sim > MIN_SIM:
                out.append({"jac": round(sim, 2), "shared": inter, "law": l["title"], "ns": l["ns"],
                            "a": {"who": a["who"], "grp": sorted(a["grp"]), "out": a["out"]},
                            "b": {"who": b["who"], "grp": sorted(b["grp"]), "out": b["out"]},
                            "text": re.sub(r"\s+", " ", a["body"])[:500]})
    out.sort(key=lambda e: -e["shared"])
    if write and only is None:
        (HERE / "crossparty.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    from collections import Counter
    out = main()
    print(len(out), "cross-group pairs;", Counter(e["ns"] for e in out))
    print(Counter(tuple(sorted([e["a"]["grp"][0], e["b"]["grp"][0]])) for e in out).most_common(12))
