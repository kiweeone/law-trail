"""Influence signals: outside organisations per bill, and text fingerprints of their opinions in MPs' amendments."""
import json, re, pathlib, collections
import pbg, extract

HERE = pathlib.Path(__file__).parent
OPN = HERE / "raw" / "opinions"
N = 7          # words per shingle
MIN_SHARED = 6 # shared shingles (~ one 12-word run) to count as a footprint

# Strip publication-history citations and legal boilerplate that every legal text shares.
BOILER = [r"\((?:обн|Обн)\.[^)]*?\)", r"(?:Държавен вестник|ДВ),? бр\.\s*\d+[^;.)]*",
          r"Създава се (?:нов )?(?:§|чл\.|ал\.|т\.)\s*\S+", r"(?:думите|думата|текстът|текста) .{0,4}"]
STOP_SHINGLE = re.compile(r"^(?:\S+ ){0,6}(?:закона за|изменение и допълнение|народни представители|законопроект)")

# prefix (lowercase) -> (canonical name, type). Types: public, business, union, professional, civil.
ORG_ALIASES = [
    ("американска търговска камара", "Американска търговска камара (AmCham)", "business"),
    ("америк. търг. камара", "Американска търговска камара (AmCham)", "business"),
    ("асоциация застрахователи", "Асоциация на българските застрахователи", "business"),
    ("асоциация на българските застрахователи", "Асоциация на българските застрахователи", "business"),
    ("птицевъдите", "Съюз на птицевъдите", "business"), ("съюз на птицевъдите", "Съюз на птицевъдите", "business"),
    ("асоциация млекопреработватели", "Асоциация на млекопреработвателите", "business"),
    ("нац.асоциация млекопреработватели", "Асоциация на млекопреработвателите", "business"),
    ("търговци нехранителни", "Асоциация на търговците на нехранителни стоки", "business"),
    ("асоциация на търговците на нехранителни", "Асоциация на търговците на нехранителни стоки", "business"),
    ("сдружение за модерна търговия", "Сдружение за модерна търговия", "business"),
    ("сдружение \"българската предприемаческа", "BESCO", "business"), ("besco", "BESCO", "business"),
    ("бск", "БСК (Българска стопанска камара)", "business"), ("българска стопанска камара", "БСК (Българска стопанска камара)", "business"),
    ("криб", "КРИБ", "business"), ("конфедерация на работодателите", "КРИБ", "business"),
    ("аикб", "АИКБ", "business"), ("бтпп", "БТПП", "business"),
    ("българската асоциация по рециклиране", "Българска асоциация по рециклиране", "business"),
    ("българската асоцияция по рециклиране", "Българска асоциация по рециклиране", "business"),
    ("кнсб", "КНСБ", "union"), ("позиция на кнсб", "КНСБ", "union"), ("кт подкрепа", "КТ „Подкрепа“", "union"),
    ("кт\"подкрепа", "КТ „Подкрепа“", "union"),
    ("висш адвокатски съвет", "Висш адвокатски съвет", "professional"), ("висшия адвокатски съвет", "Висш адвокатски съвет", "professional"),
    ("камара на следователите", "Камара на следователите", "professional"), ("камарата на следователите", "Камара на следователите", "professional"),
    ("съвет на ректорите", "Съвет на ректорите", "public"), ("съвета на ректорите", "Съвет на ректорите", "public"),
    ("омбудсман", "Омбудсман", "public"), ("нсорб", "НСОРБ (сдружение на общините)", "public"),
    ("националното сдружение на общините", "НСОРБ (сдружение на общините)", "public"),
    ("национално сдружение на общините", "НСОРБ (сдружение на общините)", "public"),
    ("министерство на културата", "Министерство на културата", "public"), ("дaнс", "ДАНС", "public"), ("данс", "ДАНС", "public"),
    ("министерство на здравеопазването", "Министерство на здравеопазването", "public"),
    ("министерството на здравеопазването", "Министерство на здравеопазването", "public"),
    ("министерство на труда", "Министерство на труда и социалната политика", "public"),
    ("министерството на труда", "Министерство на труда и социалната политика", "public"),
    ("мф", "Министерство на финансите", "public"), ("министерство на финансите", "Министерство на финансите", "public"),
    ("министерството на финансите", "Министерство на финансите", "public"),
    ("миии", "Министерство на икономиката", "public"), ("министерство на икономиката", "Министерство на икономиката", "public"),
    ("мзх", "Министерство на земеделието", "public"), ("министерството на земеделието", "Министерство на земеделието", "public"),
    ("м-во на енергетиката", "Министерство на енергетиката", "public"), ("министерство на енергетиката", "Министерство на енергетиката", "public"),
    ("мвр", "МВР", "public"), ("министерството на вътрешните работи", "МВР", "public"),
    ("министерство на правосъдието", "Министерство на правосъдието", "public"),
    ("кфн", "Комисия за финансов надзор", "public"), ("комисията за финансов надзор", "Комисия за финансов надзор", "public"),
    ("комисия за защита от дискриминация", "Комисия за защита от дискриминация", "public"),
    ("комисията за защита от дискриминация", "Комисия за защита от дискриминация", "public"),
    ("фс", "Фискален съвет", "public"), ("фискален съвет", "Фискален съвет", "public"),
    ("вкс", "Върховен касационен съд", "public"), ("върховен касационен съд", "Върховен касационен съд", "public"),
    ("върховния касационен съд", "Върховен касационен съд", "public"),
    ("асоциация памет за утре", "Асоциация „Памет за утре“", "civil"), ("асоциация \"памет за утре", "Асоциация „Памет за утре“", "civil"),
]
PUBLIC = re.compile(r"(?i)^(министерств|комиси|агенци|съвет|висш съдебен|инспекторат|прокуратур|пленум|председатели|национален институт|кевр|кзк|кзп|мосв|мррб|доклад от|обществен съвет|регионална библиотека|академичн|варненски свободен)")
BUSINESS = re.compile(r"(?i)(\b(е?ад|еоод|оод)\b|асоциаци|камара|сдружение за|съюз на птиц|конфедерация на автоб|федерация|^б[а-я]{1,4}$|^[a-z]+)")
UNION = re.compile(r"(?i)(синдикат|подкрепа|кнсб)")
PROFESSIONAL = re.compile(r"(?i)(адвокат|съди|съюз на юристите|блс|бзс|камара на)")


TYPE_OVERRIDE = {
    "СЪВЕТ НА ЖЕНИТЕ В БИЗНЕСА В БЪЛГАРИЯ": "business", "БХК": "civil", "БГФармА": "business", "АРФАРМ": "business",
    "АЗПБ": "business", "СпиритсБългария": "business", "Храни и напитки": "business", "Омега Софт": "business",
    "Трансинс Технорециклираща компания": "business", "БАДДПО": "business", "НСОПЛБ": "professional",
    "Адв. Весела Андонова": "professional", "адв. Добри Ковачев": "professional", "Българска библиотечно - информационна асоциация": "civil",
    "Българска музикална асоциация": "civil", "Сдружение за правна помощ на потребителите": "civil", "Българо- американска асоциация Чикаго": "civil",
    "Асоциация на българските анимационни продуценти": "business", "Земеделски производители": "business",
}


def org_name(sub):
    name, typ = _org_name(sub)
    if name in ("", "Допълнено", "Допълнително", "Българската асоциация", "Българската асоцияция"):
        name = "(unnamed attachment)"
    return name, TYPE_OVERRIDE.get(name, typ)


def _org_name(sub):
    """Return (canonical name, type) for a standpoint subject line."""
    s = re.sub(r"(?i)^\s*(?:становище|позиция)\s+(?:на|от)\s+", "", sub.strip())
    s = re.sub(r"(?i)^отворено писмо от\s+", "", s)
    s = re.sub(r"\s*-?\s*Вх\.?\s*№.*$", "", s)
    s = re.sub(r",?\s*№\s*[\wА-Я-]+.*$", "", s)
    s = re.sub(r"\s*[-–]\s*(?:коментари|бележки|допълнение|допълнително).*$", "", s, flags=re.I)
    s = re.sub(r"(?i)\s*-?\s*становище.*$", "", s)
    s = re.sub(r"(?i)\s+(?:относно|отностно|във връзка)\b.*$", "", s)
    s = re.sub(r"\s+по\s+.*$", "", s)
    s = re.sub(r"\s+за\s+(?:плаж|изменение).*$", "", s)
    s = s.strip(" -,.\"'")
    s = re.sub(r'^"?([^"]+)"\s*(Е?АД|ЕООД|ООД)$', r'„\1“ \2', s)
    low = s.lower()
    for k, name, typ in ORG_ALIASES:
        if low == k or low.startswith(k + " ") or low.startswith(k + ",") or (len(k) > 6 and low.startswith(k)):
            return name, typ
    if UNION.search(s):
        return s, "union"
    if PUBLIC.search(s):
        return s, "public"
    if PROFESSIONAL.search(s):
        return s, "professional"
    if BUSINESS.search(s):
        return s, "business"
    return s, "civil"


def norm_text(t):
    t = t.replace("­", "").replace("-\n", "")
    for b in BOILER:
        t = re.sub(b, " ", t)
    return t


def shingles(t):
    w = re.findall(r"[а-яa-z0-9]+", norm_text(t).lower())
    out = set()
    for i in range(len(w) - N + 1):
        s = " ".join(w[i:i + N])
        if not STOP_SHINGLE.match(s) and not re.fullmatch(r"[\d ]+", s):
            out.add(s)
    return out


def longest_run(a_text, shared):
    """Return the longest contiguous passage of the proposal covered by shared shingles."""
    w = re.findall(r"[а-яa-z0-9]+", norm_text(a_text).lower())
    best, cur_start, run = (0, 0), None, 0
    for i in range(len(w) - N + 1):
        if " ".join(w[i:i + N]) in shared:
            if cur_start is None:
                cur_start = i
            run = i - cur_start + N
            if run > best[0]:
                best = (run, cur_start)
        else:
            cur_start = None
    n, s = best
    return n, " ".join(w[s:s + n])


BILL_PARA = re.compile(r"^\s*§\s*\d+\w?\.(.*?)(?=^\s*(?:Предложени[ея] (?:на|от)|Комисията|Работната група|§\s*\d+\w?\.)|\Z)", re.M | re.S)


def bill_baseline(bill):
    """Shingles of the bill as introduced: each '§ N.' block in the report up to the first proposal/committee note."""
    text, _ = extract.report_for(bill)
    if not text:
        return set()
    base = " ".join(m.group(1) for m in BILL_PARA.finditer(text))
    return shingles(base)


def first_reading_date(bill):
    """Date the plenary adopted the bill at first reading (from the bill's activity log)."""
    ds = [a["L_Act_St_date"] for a in bill.get("activity") or []
          if a.get("L_Act_St_date") and a.get("L_Act_St2_name") == "зала първо гласуване" and a.get("L_Act_St_name") == "приет"]
    return min(ds) if ds else ""


def proposal_bodies(bill):
    text, _ = extract.report_for(bill)
    if not text:
        return []
    heads = list(extract.HEAD.finditer(text))
    out = []
    for k, h in enumerate(heads):
        end = heads[k + 1].start() if k + 1 < len(heads) else len(text)
        ch = text[h.end():end]
        o = extract.OUTCOME.search(ch)
        names, _ = extract.split_names(h.group("who"))
        out.append({"k": k, "who": names, "outcome": extract.OUTCOME_LABEL.get(o.group(1)) if o else "unclear",
                    "mp_ids": [r["id"] for r in map(extract.resolve, names) if r],
                    "body": ch[:o.start()] if o else ch[:4000]})
    return out


def first_reading_attendees(bill):
    """Organisations named as attending the lead committee's first-reading sitting."""
    rows = bill.get("stan_list") or []
    if not rows:
        return ""
    r = pbg.get(f"com-stan/bg/{rows[0]['A_Cm_Stanid']}") or {}
    t = extract.clean(r.get("A_Cm_Stan_text") or "")
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"(?:На|В) (?:заседанието|него)[^.:]{0,40}(?:присъстваха|участваха|присъства)[^:]{0,60}:?(.{0,1200}?)(?:Законопроектът (?:беше|бе) представен|Законопроектът е представен|От името на вносител)", t)
    return m.group(1).strip() if m else ""


def with_text(ops):
    """Opinion records with their extracted text and normalised organisation (copies; the stored records stay as they are)."""
    out = []
    for o in ops:
        f = OPN / (o["path"].rsplit("/", 1)[-1] + ".txt")
        on, ot = org_name(o["org"])
        out.append({**o, "text": f.read_text(encoding="utf-8") if f.exists() else "", "org": on, "org_type": ot})
    return out


def main(only=None, laws=None, ops=None, write=True):
    """Footprints for every law, or only for the laws whose idMat is in `only` (returned, not merged)."""
    laws = laws if laws is not None else json.loads((HERE / "laws.json").read_text(encoding="utf-8"))
    ops = ops if ops is not None else json.loads((HERE / "opinions.json").read_text(encoding="utf-8"))
    by_bill = collections.defaultdict(list)
    want = None if only is None else {l.get("bill_id") for l in laws if l["idMat"] in only}
    for o in with_text([o for o in ops if want is None or o["bill_id"] in want]):
        by_bill[o["bill_id"]].append(o)
    footprints = []
    for law in laws:
        if not law.get("bill_id") or (only is not None and law["idMat"] not in only):
            continue
        b = pbg.bill(law["bill_id"])
        extract.CTX.update(ns=law.get("ns"), date=((law.get("second_reading") or {}).get("report_date") or "9999")[:10])
        law["attendees"] = first_reading_attendees(b)
        bill_ops = by_bill.get(law["bill_id"], [])
        law["opinions"] = [{"org": o["org"], "type": o["org_type"], "date": o["date"], "stage": o["stage"], "readable": len(o["text"].strip()) > 300,
                            "url": "https://www.parliament.bg" + o["path"]} for o in bill_ops]
        if not bill_ops or not law.get("second_reading"):
            continue
        base = bill_baseline(b)
        window = first_reading_date(b)
        op_sh = [(o, shingles(o["text"]) - base) for o in bill_ops if len(o["text"].strip()) > 300]
        for p in proposal_bodies(b):
            ps = shingles(p["body"]) - base
            if len(ps) < MIN_SHARED:
                continue
            for o, osh in op_sh:
                # Skip opinions filed after the proposal could have copied them? Order unknown at proposal level; keep all, show dates.
                shared = ps & osh
                if len(shared) >= MIN_SHARED:
                    n, passage = longest_run(p["body"], shared)
                    if n < 12:
                        continue
                    footprints.append({
                        "law": law["title"], "idMat": law["idMat"], "org": o["org"], "org_type": o["org_type"], "opinion_date": o["date"],
                        "opinion_stage": o["stage"], "opinion_url": "https://www.parliament.bg" + o["path"],
                        # Second-reading proposals are filed after the first-reading vote, so an opinion dated
                        # before that vote must have come first; anything later may be quoting the MP.
                        "order": "opinion_first" if window[:4].isdigit() and (o["date"] or "9999") < window else "unclear",
                        "first_reading": window,
                        "proposers": p["who"], "mp_ids": p["mp_ids"], "outcome": p["outcome"],
                        "shared_shingles": len(shared), "coverage": round(len(shared) / len(ps), 2),
                        "run_words": n, "passage": passage[:500], "proposal": re.sub(r"\s+", " ", p["body"]).strip()[:500],
                    })
    footprints.sort(key=lambda f: (-f["run_words"], -f["coverage"]))
    if write and only is None:
        (HERE / "laws.json").write_text(json.dumps(laws, ensure_ascii=False, indent=1), encoding="utf-8")
        (HERE / "footprints.json").write_text(json.dumps(footprints, ensure_ascii=False, indent=1), encoding="utf-8")
    return laws, footprints


if __name__ == "__main__":
    laws, fps = main()
    print(len(fps), "footprints")
    for f in fps[:25]:
        print(f"{f['run_words']:4d}w cov {f['coverage']:.2f} | {f['org'][:35]:35} → {', '.join(f['proposers'][:2])[:40]:40} [{f['outcome']}] | {f['law'][:40]}")
    print("attendee text found for", sum(1 for l in laws if l.get("attendees")), "laws")
