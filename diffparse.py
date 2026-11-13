"""Split second-reading reports into paragraph blocks: bill text -> proposals -> committee decision -> final text.

Each block: {label, kind: unchanged|reworded|deleted|new|tweaked, before, after, proposals:[idx...], diff_html}
"""
import difflib, html, json, pathlib, re
import pbg, extract

HERE = pathlib.Path(__file__).parent

DECISION = re.compile(
    r"^\s*(?P<d>(?:Комисията|Работната група)\s[^\n]*?(?:"
    r"подкрепя\s+текста\s+на\s+вносителя[^\n]*|"
    r"подкрепя\s+по\s+принцип\s+текста\s+на\s+вносителя[^\n]*|"
    r"не\s+подкрепя\s+текста\s+на\s+вносителя[^\n]*|"
    r"предлага\s+(?:да\s+се\s+създад\w+|§\s*\d+\w*\s+да\s+бъде\s+отхвърлен)[^\n]*|"
    r"подкрепя\s+(?:по\s+принцип\s+)?предложението\s+и\s+предлага\s+да\s+се\s+създад\w+[^\n]*))\s*$",
    re.M)
PROP = re.compile(r"^\s*Предложени[ея] (?:на|от) ", re.M)
OUTCOME_LINE = re.compile(r"^\s*(?:Комисията (?:не )?подкрепя (?:по принцип |частично )?предложението|Предложението е оттеглено|.*недопустимост на предложението)[^\n]*$", re.M)


def classify(d):
    if re.search(r"отхвърлен", d) and "не подкрепя" in d or re.search(r"предлага\s+§\s*\S+\s+да\s+бъде\s+отхвърлен", d) or ("но предлага" in d and "отхвърлен" in d):
        return "deleted"
    if re.search(r"да\s+се\s+създад", d):
        return "new"
    if re.search(r"следната\s+редакция|да\s+се\s+измени\s+така|предлага\s+наименованието", d):
        return "reworded"
    if re.search(r",\s*като", d):
        return "tweaked"
    if "подкрепя текста на вносителя" in d:
        return "unchanged"
    return "other"


def label_of(d, before):
    m = re.search(r"(?:става\s+(?:нов\s+)?)(§\s*\d+\w*|чл\.\s*\d+\w*)", d)
    m0 = re.search(r"(§\s*\d+\w*|чл\.\s*\d+\w*|наименованието на (?:закона|подразделението)|Приложение\s*№\s*\d+)", d)
    head = re.match(r"\s*(§\s*\d+\w*\.|Чл\.\s*\d+\w*\.)", before or "")
    lab = (m0.group(1) if m0 else (head.group(1).rstrip(".") if head else ""))
    if m:
        lab = f"{lab} → {m.group(1)}" if lab and lab != m.group(1) else m.group(1)
    return re.sub(r"\s+", " ", lab).replace("наименованието на ", "наименование на ")


def clean_block(s):
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def tokens(s):
    return re.findall(r"\S+|\n", s)


def diff_html(a, b, max_len=6000):
    ta, tb = tokens(a[:max_len]), tokens(b[:max_len])
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    out, ins_words, del_words = [], 0, 0
    def j(ts):
        return html.escape(" ".join(ts)).replace(" \n ", "<br>").replace("\n", "<br>")
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(j(ta[i1:i2]))
        if op in ("delete", "replace"):
            out.append(f"<del>{j(ta[i1:i2])}</del>"); del_words += i2 - i1
        if op in ("insert", "replace"):
            out.append(f"<ins>{j(tb[j1:j2])}</ins>"); ins_words += j2 - j1
    return " ".join(out), ins_words, del_words, round(sm.ratio(), 3)


def parse(text):
    # Stop final-text capture at the next bill paragraph/article start or a proposal/decision line.
    article_mode = len(re.findall(r"текста на вносителя за чл\.", text)) > len(re.findall(r"текста на вносителя за §", text))
    start_pat = re.compile(r"^\s*(?:Чл\.\s*\d+\w*\.|Глава|Раздел|ДОПЪЛНИТЕЛН|ПРЕХОДН|ЗАКЛЮЧИТЕЛН|Допълнителн|Преходни|Заключителни)" if article_mode
                           else r"^\s*(?:§\s*\d+\w*\.|Допълнителн|Преходни|Заключителни|ДОПЪЛНИТЕЛН|ПРЕХОДН|ЗАКЛЮЧИТЕЛН)", re.M)
    decisions = list(DECISION.finditer(text))
    blocks, cursor = [], 0
    # skip report preamble: start at first bill paragraph/title decision
    first = re.search(r"^\s*(?:ЗАКОН|Закон|КОДЕКС|§\s*1\.|Чл\.\s*1\.)", text, re.M)
    cursor = first.start() if first else 0
    for k, m in enumerate(decisions):
        d = re.sub(r"\s+", " ", m.group("d"))
        kind = classify(d)
        seg = text[cursor:m.start()]
        p = PROP.search(seg)
        before = clean_block(seg[:p.start()] if p else seg)
        props_seg = seg[p.start():] if p else ""
        after, end = "", m.end()
        if kind == "reworded" and "наименование" in d:
            # new title is quoted on the decision line itself, or is the next non-empty line
            q = re.search(r"[„\"](.+?)[“\"]\s*\.?\s*$", m.group("d").strip())
            if q:
                after, end = q.group(1), m.end()
            else:
                nl = re.match(r"\s*\n?([^\n]+)", text[m.end():])
                after, end = (nl.group(1).strip(" „“\""), m.end() + nl.end()) if nl else ("", m.end())
        elif kind in ("reworded", "new"):
            nxt = decisions[k + 1].start() if k + 1 < len(decisions) else len(text)
            body = text[m.end():nxt]
            # final text ends at the next block start after its own first line, or at the next proposal
            first_line_end = body.find("\n", 1)
            cut = len(body)
            for pat in (start_pat, PROP):
                mm = pat.search(body, max(first_line_end, 0) + 1)
                if mm:
                    cut = min(cut, mm.start())
            after = clean_block(body[:cut])
            end = m.end() + cut
        elif kind == "unchanged":
            after = before
        elif kind == "deleted":
            after = ""
        if kind == "new":
            # a "new" decision has no bill text of its own; anything before is leftover proposals
            before = ""
        heads = [h.start() for h in PROP.finditer(props_seg)]
        blocks.append({"label": label_of(d, before), "kind": kind, "decision": d, "before": before[:8000], "after": after[:8000],
                       "props_text": props_seg[:200], "n_props": len(heads)})
        cursor = end
    return blocks


def attach_proposals(blocks, text, proposals):
    """Map extracted proposals (in report order) to blocks by position."""
    # proposals in law['second_reading']['proposals'] follow report order; blocks hold n_props each
    i = 0
    for b in blocks:
        b["props"] = list(range(i, min(i + b["n_props"], len(proposals))))
        i += b["n_props"]
    return blocks


def norm(s):
    return re.sub(r"[^\wа-я]+", " ", s.lower()).strip()


def run(only=None, laws=None, fps=None, write=True):
    """Before/after blocks for every law, or only for the idMat values in `only` (returned keyed by str(idMat), not merged)."""
    laws = laws if laws is not None else json.loads((HERE / "laws.json").read_text(encoding="utf-8"))
    fps = fps if fps is not None else json.loads((HERE / "footprints.json").read_text(encoding="utf-8"))
    out, stats = {}, {"blocks": 0, "reworded": 0, "found_in_dv": 0, "checked": 0}
    import dv
    for l in laws:
        if not l.get("bill_id") or not l.get("second_reading") or (only is not None and l["idMat"] not in only):
            continue
        text, _ = extract.report_for(pbg.bill(l["bill_id"]))
        blocks = attach_proposals(parse(text), text, l["second_reading"]["proposals"])
        dvd = dv.parse(l["idMat"], dv.fetch(l["idMat"])) if l["idMat"] and l["idMat"] > 0 else None
        dvtext = norm(dvd["text"]) if dvd else ""
        law_fps = [f for f in fps if f["idMat"] == l["idMat"]]
        for b in blocks:
            if b["kind"] in ("reworded", "new") and b["after"]:
                # verification: does the committee's final wording appear in the promulgated text?
                probe = norm(b["after"])[:160]
                probe = " ".join(probe.split()[2:14])  # skip "§ N." prefix whose numbering may shift
                if len(probe) > 40 and dvtext:
                    stats["checked"] += 1
                    b["in_dv"] = probe in dvtext
                    stats["found_in_dv"] += b["in_dv"]
            if b["kind"] in ("reworded", "new", "unchanged", "deleted"):
                h, ins, dele, ratio = diff_html(b["before"], b["after"])
                b.update(diff=h, ins=ins, dele=dele, sim=ratio)
            # footprints whose passage landed in this block's final text
            na = norm(b.get("after", ""))
            b["fp"] = sorted({f["org"] for f in law_fps if f["outcome"] in ("supported", "supported_in_principle", "partly_supported")
                              and " ".join(f["passage"].split()[:10]) in na})
            stats["blocks"] += 1
            stats["reworded"] += b["kind"] in ("reworded", "new")
        out[str(l["idMat"])] = blocks
    if write and only is None:
        (HERE / "diffs.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out, stats


if __name__ == "__main__":
    out, st = run()
    print(st)
    from collections import Counter
    print(Counter(b["kind"] for bl in out.values() for b in bl))
