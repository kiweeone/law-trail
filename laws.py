"""Extract laws from parsed ДВ materials: adoption date, assembly, ПЗР, other laws amended via ПЗР."""
import json, re, pathlib
import dv

HERE = pathlib.Path(__file__).parent
MONTHS = {m: i + 1 for i, m in enumerate(
    "януари февруари март април май юни юли август септември октомври ноември декември".split())}

ADOPTED = re.compile(r"приет от (\d+)-?\w* Народно събрание на (\d{1,2}) (\w+) (\d{4})")
PZR_HEAD = re.compile(r"\n\s*(Преходни и заключителни разпоредби|Заключителни разпоредби|Преходни разпоредби|Допълнителни разпоредби)\s*\n")
# "§ 14. В Закона за ... (обн., ДВ" / "§ 3. В Кодекса на труда (обн."
AMEND = re.compile(r"§\s*(\d+)\.\s*(?:\(\d+\)\s*)?(?:В|Във)\s+([А-ЯA-Z][^()§\n]{4,220}?)\s*\((?:обн\.|ДВ)")
SECTION_SPLIT = re.compile(r"(?=§\s*\d+\.)")


def norm(name):
    name = re.sub(r"\s+", " ", name).strip(" ,.")
    # Accusative/locative forms in "В Закона за ..." -> nominative-ish key
    name = re.sub(r"^Закона\b", "Закон", name)
    name = re.sub(r"^Кодекса\b", "Кодекс", name)
    return name


def target_law(title):
    m = re.match(r"(?:Закон|Кодекс) за (?:изменение и допълнение|изменение|допълнение) на (.+)", title)
    return norm(m.group(1)) if m else None


def extract(r):
    t = r["text"]
    a = ADOPTED.search(t)
    adopted = None
    if a and a.group(3) in MONTHS:
        adopted = f"{a.group(4)}-{MONTHS[a.group(3)]:02d}-{int(a.group(2)):02d}"
    heads = list(PZR_HEAD.finditer(t))
    pzr_start = heads[0].start() if heads else None
    pzr = t[pzr_start:] if pzr_start is not None else ""
    own = target_law(r["title"])
    paras = [p for p in SECTION_SPLIT.split(pzr) if p.strip().startswith("§")]
    other = []
    for p in paras:
        m = AMEND.match(p.strip())
        if not m:
            continue
        name = norm(m.group(2))
        if own and name.lower().startswith(own.lower()[:40]):
            continue
        other.append({"para": int(m.group(1)), "law": name, "chars": len(p)})
    return {
        "idMat": r["idMat"], "dv_issue": r["issue"], "dv_date": r["date"],
        "title": r["title"], "amends": own,
        "assembly": int(a.group(1)) if a else None, "adopted": adopted,
        "body_chars": len(t), "pzr_chars": len(pzr),
        "pzr_other_laws": other, "url": r["url"],
    }


def main():
    rows = []
    for line in open(HERE / "dv_materials.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["issuer"].startswith("Народно събрание") and r["title"].startswith(("Закон", "Кодекс")):
            r = dv.parse(r["idMat"], dv.fetch(r["idMat"]))  # reparse with script stripping
            rows.append(extract(r))
    (HERE / "laws.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


if __name__ == "__main__":
    for x in main():
        o = x["pzr_other_laws"]
        print(x["idMat"], x["adopted"], x["assembly"], f"{len(o):2d} other", "|", x["title"][:70])
        for a in o:
            print("      §", a["para"], a["law"][:90], a["chars"])
