"""Company ties for every MP from ЩРАК (BIRD.BG).

Match levels (kept honest on the site):
  matched     ЩРАК itself tags the person as a Member of Parliament (PEP)
  ambiguous   several PEP-tagged records with the same name; the one with most firms is used
  name_only   exactly one person with this full name in the register, but without the MP tag
  namesakes   several people with this full name and none tagged as MP: cannot tell which one
  none        nobody with this full name in the register (usually: no company roles under that name)
Output: shtrack_links.json {person_id: {s, g?, k?, f:[{e, n, r:[roles]}]}}
"""
import html, json, pathlib, re, sys
import shtrack

HERE = pathlib.Path(__file__).parent


def connections(guid):
    url = f"https://shtrack.net/view/person/{guid}/?v=deploy&list_level=1"
    s = shtrack.get(url, f"d_{guid[:8]}.html")
    i = s.find("bird-tr-hierarchy")
    firms = {}
    def add(eik, name, rel):
        f = firms.setdefault(eik, {"e": eik, "n": html.unescape(name).strip(), "r": []})
        rel = html.unescape(rel).strip().lstrip("→").strip()
        if rel and rel not in f["r"]:
            f["r"].append(rel)
    # main tree rows and the "cross connections" block both have relation + company link
    for m in re.finditer(r'bird-tr-hierarchy-relation">([^<]*)</span>\s*<a class="bird-tr-hierarchy-entity" href="https://shtrack\.net/view/company/([^/]+)/">([^<]*)</a>', s[i:]):
        add(m.group(2), m.group(3), m.group(1))
    return list(firms.values())


def level(pid, name, prev):
    st = prev.get("status")
    if st in ("matched", "ambiguous"):
        return {"s": st, "g": prev["guid"]}
    rows = shtrack.parse_rows(name)
    if st in (None, "error"):          # never looked up (a new MP) or the lookup failed
        r = shtrack.match_mp(name)
        if r["status"] in ("matched", "ambiguous"):
            return {"s": r["status"], "g": r["guid"]}
    same = [r for r in rows if r["name"].upper() == name.upper()]
    if len(same) == 1:
        return {"s": "name_only", "g": same[0]["guid"]}
    if len(same) > 1:
        return {"s": "namesakes", "k": len(same)}
    return {"s": "none"}


def run():
    prev = json.loads((HERE / "shtrack_mps.json").read_text(encoding="utf-8"))
    mps = json.loads((HERE / "site_data.json").read_text(encoding="utf-8"))["mps"]
    outp = HERE / "shtrack_links.json"
    out = json.loads(outp.read_text(encoding="utf-8")) if outp.exists() else {}
    for k, (pid, m) in enumerate(mps.items()):
        if pid in out and "f" in out[pid]:
            continue
        try:
            r = level(pid, m["n"], prev.get(pid, {}))
            r["f"] = connections(r["g"]) if r.get("g") else []
        except Exception as e:
            print("err", pid, m["n"], e, flush=True)
            continue
        out[pid] = r
        if k % 25 == 0:
            outp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            print(k, len(out), flush=True)
    outp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    from collections import Counter
    print(Counter(v["s"] for v in out.values()), sum(len(v["f"]) for v in out.values()))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(connections(sys.argv[1]), ensure_ascii=False, indent=1)[:1500])
    else:
        run()
