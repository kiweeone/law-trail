"""Download stakeholder opinions (становища) filed on bills and extract their text."""
import json, pathlib, subprocess, urllib.parse, urllib.request, concurrent.futures as cf
import pbg

HERE = pathlib.Path(__file__).parent
RAW = HERE / "raw" / "opinions"
RAW.mkdir(parents=True, exist_ok=True)


def fetch_text(path):
    name = path.rsplit("/", 1)[-1]
    p = RAW / name
    txt = p.with_suffix(p.suffix + ".txt")
    if txt.exists():
        return txt.read_text(encoding="utf-8")
    url = "https://www.parliament.bg" + urllib.parse.quote(path)
    try:
        if not p.exists():
            urllib.request.urlretrieve(url, p)
        if p.suffix.lower() == ".pdf":
            t = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, timeout=60).stdout
        elif p.suffix.lower() == ".docx":
            t = subprocess.run(["pandoc", "-t", "plain", str(p)], capture_output=True, text=True, timeout=60).stdout
        else:
            t = ""
    except Exception:
        t = ""
    txt.write_text(t, encoding="utf-8")
    return t


def opinions_for(bill):
    out = []
    for s in bill.get("standp_list") or []:
        r = pbg.get(f"com-stan/bg/{s['A_Cm_Stanid']}") or {}
        for f in r.get("files") or []:
            out.append({"id": s["A_Cm_Stanid"], "org": s["A_Cm_Stan_sub"].replace("Становище на", "").replace("Становище от", "").strip(),
                        "date": s["A_Cm_Stan_date"], "committee": s["A_ns_CL_value"], "stage": s["L_Act_St_name"],
                        "path": f["A_Cm_StanF_file"]})
    return out


def main(bill_ids):
    ops = []
    for bid in bill_ids:
        b = pbg.bill(bid)
        for o in opinions_for(b):
            o["bill_id"] = bid
            ops.append(o)
    with cf.ThreadPoolExecutor(6) as ex:
        for o, t in zip(ops, ex.map(lambda o: fetch_text(o["path"]), ops)):
            o["chars"] = len(t.strip())
    (HERE / "opinions.json").write_text(json.dumps(ops, ensure_ascii=False, indent=1), encoding="utf-8")
    return ops


if __name__ == "__main__":
    laws = json.loads((HERE / "laws.json").read_text(encoding="utf-8"))
    ops = main([l["bill_id"] for l in laws if l.get("bill_id")])
    print(len(ops), "opinions;", sum(1 for o in ops if o["chars"] > 300), "with extractable text")
