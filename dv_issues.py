"""Crawl State Gazette issue contents pages (materiali.faces?idObj=N) and list National Assembly materials."""
import html, json, pathlib, re, sys, time, urllib.request, concurrent.futures as cf
HERE = pathlib.Path(__file__).parent
RAW = HERE / "raw" / "dvidx"
RAW.mkdir(parents=True, exist_ok=True)
URL = "https://dv.parliament.bg/DVWeb/materiali.faces?idObj={}"
# the page number ("стр. 3") is missing while an issue is fresh, so it is optional
ROW = re.compile(r"\|([^|]{3,80})\|([^|]{6,600})\|\s*(?:стр\.\s*\d+\s*)?<a[^>]+idMat=(\d+)")

def fetch(o, fresh=False):
    """Contents page of one gazette object. Recent pages change after publication, so the update re-reads them (fresh=True)."""
    p = RAW / f"{o}.html"
    if p.exists() and not fresh:
        return p.read_text(encoding="utf-8", errors="replace")
    for a in range(3):
        try:
            with urllib.request.urlopen(URL.format(o), timeout=40) as r:
                s = r.read().decode("utf-8", errors="replace")
            p.write_text(s, encoding="utf-8"); return s
        except Exception:
            time.sleep(2 * (a + 1))
    return ""

def rows(s):
    s = re.sub(r"<script.*?</script>", "", s, flags=re.S)
    s = re.sub(r"<(?!a )[^>]+>", "|", s)
    s = html.unescape(re.sub(r"\|[\s|]*", "|", s))
    return [{"issuer": m.group(1).strip(), "title": m.group(2).strip(), "idMat": int(m.group(3))} for m in ROW.finditer(s)]

if __name__ == "__main__":
    lo, hi = int(sys.argv[1]), int(sys.argv[2])
    out = []
    with cf.ThreadPoolExecutor(4) as ex:
        for o, s in zip(range(lo, hi), ex.map(fetch, range(lo, hi))):
            for r in rows(s):
                if r["issuer"].startswith("Народно събрание"):
                    r["idObj"] = o; out.append(r)
    (HERE / "dv_ns_index.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(len(out), "NS materials;", sum(1 for r in out if r["title"].startswith(("Закон", "Кодекс"))), "laws")
