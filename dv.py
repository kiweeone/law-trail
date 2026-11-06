"""Fetch and parse State Gazette (ДВ) material pages by idMat."""
import html, json, re, sys, time, pathlib, concurrent.futures as cf
import urllib.request

RAW = pathlib.Path(__file__).parent / "raw" / "dv"
RAW.mkdir(parents=True, exist_ok=True)
URL = "https://dv.parliament.bg/DVWeb/showMaterialDV.jsp?idMat={}"


def fetch(i):
    p = RAW / f"{i}.html"
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(URL.format(i), timeout=30) as r:
                s = r.read().decode("utf-8", errors="replace")
            p.write_text(s, encoding="utf-8")
            return s
        except Exception:
            time.sleep(2 * (attempt + 1))
    return ""


def text(fragment):
    fragment = re.sub(r"<!--.*?-->", " ", fragment, flags=re.S)
    fragment = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment, flags=re.S | re.I)
    fragment = re.split(r"<script", fragment, flags=re.I)[0]
    fragment = re.sub(r"<(br|/p|/tr|/div)[^>]*>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    fragment = re.sub(r"[ \t\xa0]+", " ", fragment)
    return re.sub(r"\n\s*\n+", "\n", fragment).strip()


def parse(i, s):
    if "tdHead1" not in s:
        return None
    issuer = re.search(r'class="titleHead">.*?</div>(.*?)</div>', s, re.S)
    mark = re.search(r'class="mark">(.*?)</span>', s, re.S)
    title = re.search(r'class="tdHead1">(.*?)</span>', s, re.S)
    body_start = s.find("</span>", s.find("tdHead1"))
    m = text(mark.group(1)) if mark else ""
    issue = re.search(r"брой:\s*(\d+),\s*от дата\s*([\d.]+)", m)
    return {
        "idMat": i,
        "issuer": text(issuer.group(1)) if issuer else "",
        "issue": int(issue.group(1)) if issue else None,
        "date": issue.group(2) if issue else None,
        "section": m.split("/")[0].split("г.")[-1].strip() if "/" in m else "",
        "title": text(title.group(1)) if title else "",
        "url": URL.format(i),
        "text": text(s[body_start:]),
    }


def crawl(lo, hi, workers=6):
    out = []
    with cf.ThreadPoolExecutor(workers) as ex:
        for i, s in zip(range(lo, hi), ex.map(fetch, range(lo, hi))):
            d = parse(i, s)
            if d:
                out.append(d)
    return out


if __name__ == "__main__":
    lo, hi = int(sys.argv[1]), int(sys.argv[2])
    rows = crawl(lo, hi)
    dest = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None
    if dest:
        dest.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    for r in rows:
        print(r["idMat"], r["issue"], r["date"], r["issuer"][:30], "|", r["title"][:90])
