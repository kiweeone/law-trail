"""Look up MPs in ЩРАК (shtrack.net, BIRD.BG): person GUID, PEP role, linked companies with roles."""
import html, json, pathlib, re, time, urllib.parse, urllib.request

RAW = pathlib.Path(__file__).parent / "raw" / "shtrack"
RAW.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "LawTrail/1.0 (+https://law-trail.vercel.app)"}


def get(url, name):
    p = RAW / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        s = r.read().decode("utf-8", errors="replace")
    p.write_text(s, encoding="utf-8")
    time.sleep(1.5)  # be polite
    return s


def strip(s):
    s = re.sub(r"<style.*?</style>|<script.*?</script>", "", s, flags=re.S)
    return s


def search(name):
    url = "https://shtrack.net/search/" + urllib.parse.quote(name) + "/?bird_lang=bg"
    s = strip(get(url, "s_" + re.sub(r"\W+", "_", name) + ".html"))
    i = s.find("bird-tr-unified-search-results")
    out = []
    # each person card: name, "N свързани фирми", PEP text, profile link ?v=first&guid=
    for m in re.finditer(r"href=['\"]\?v=first&(?:amp;)?guid=([0-9a-f]+)[^'\"]*['\"][^>]*>(.*?)</a>(.*?)(?=href=['\"]\?v=first|\Z)", s[i:], re.S):
        guid, nm, rest = m.group(1), m.group(2), m.group(3)
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", nm + " " + rest[:1500]))).strip()
        firms = re.search(r"(\d+) свързани фирми", txt)
        pep = re.search(r"PEP:\s*(.*?)(?:\s+Лице\s|$)", txt)
        out.append({"guid": guid, "name": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", nm))).strip(),
                    "firms": int(firms.group(1)) if firms else 0, "pep": pep.group(1)[:300] if pep else "", "raw": txt[:400]})
    return out


if __name__ == "__main__":
    import sys
    for r in search(sys.argv[1])[:6]:
        print(r["name"], r["firms"], "|", r["pep"][:140], "|", r["guid"][:12])


def parse_rows(name):
    url = "https://shtrack.net/search/" + urllib.parse.quote(name) + "/?bird_lang=bg"
    s = strip(get(url, "s_" + re.sub(r"\W+", "_", name) + ".html"))
    i = s.find('id="bird-search-tab-0"')
    j = s.find('id="bird-search-tab-1"')
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", s[i:j if j > i else None], re.S):
        g = re.search(r"guid=([0-9a-f]{64})", tr)
        if not g:
            continue
        nm = re.search(r"<a href='\?v=first&guid=[0-9a-f]+'>([^<]+)</a>", tr)
        firms = re.search(r"(\d+) свързани фирми", tr)
        peps = [html.unescape(x) for x in re.findall(r">PEP: ([^<]+)</a>", tr)]
        rows.append({"guid": g.group(1), "name": nm.group(1).strip() if nm else "", "firms": int(firms.group(1)) if firms else 0, "pep": peps})
    return rows


def match_mp(full_name):
    """Return the ЩРАК person tagged as a sitting MP with this exact full name, or None."""
    rows = parse_rows(full_name)
    target = full_name.upper()
    mp = [r for r in rows if r["name"].upper() == target and any("Народен представител" in p or "народен представител" in p for p in r["pep"])]
    if len(mp) == 1:
        return {**mp[0], "status": "matched"}
    if len(mp) > 1:
        return {**max(mp, key=lambda r: r["firms"]), "status": "ambiguous"}
    same = [r for r in rows if r["name"].upper() == target]
    return {"status": "no_pep_record", "candidates": len(same)}


def run_all():
    """Look up every person in the site data (current and former MPs); keep earlier matches."""
    p = pathlib.Path(__file__).parent / "shtrack_mps.json"
    out = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    mps = json.loads((pathlib.Path(__file__).parent / "site_data.json").read_text(encoding="utf-8"))["mps"]
    have = {str(i) for i, v in out.items() if v.get("guid")}
    for m in mps.values():
        for mid in m.get("mand", [m["id"]]):
            if str(mid) in have:
                have.add(str(m["id"]))
    seen = {m["id"]: m["n"] for m in mps.values() if str(m["id"]) not in have}
    for i, name in seen.items():
        try:
            out[str(i)] = match_mp(name)
        except Exception as e:
            out[str(i)] = {"status": "error", "error": str(e)[:100]}
    (pathlib.Path(__file__).parent / "shtrack_mps.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(Counter(v["status"] for v in out.values()))
