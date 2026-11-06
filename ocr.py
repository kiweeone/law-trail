"""OCR scanned stakeholder opinions (Bulgarian). Overwrites the empty .txt next to each PDF."""
import json, pathlib, subprocess, tempfile, concurrent.futures as cf

HERE = pathlib.Path(__file__).parent
RAW = HERE / "raw" / "opinions"
MAX_PAGES = 10


def ocr(pdf):
    txt = pdf.with_suffix(pdf.suffix + ".txt")
    if txt.exists() and len(txt.read_text(encoding="utf-8").strip()) > 300:
        return 0
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", "170", "-gray", "-l", str(MAX_PAGES), "-png", str(pdf), f"{d}/p"], timeout=300)
        pages = sorted(pathlib.Path(d).glob("p-*.png"))
        out = []
        for p in pages:
            r = subprocess.run(["tesseract", str(p), "-", "-l", "bul"], capture_output=True, text=True, timeout=180)
            out.append(r.stdout)
    txt.write_text("\n\f".join(out), encoding="utf-8")
    return len(pages)


if __name__ == "__main__":
    ops = json.loads((HERE / "opinions.json").read_text(encoding="utf-8"))
    pdfs = [RAW / o["path"].rsplit("/", 1)[-1] for o in ops if o["chars"] <= 300 and o["path"].lower().endswith(".pdf")]
    pdfs = [p for p in dict.fromkeys(pdfs) if p.exists()]
    done = 0
    with cf.ThreadPoolExecutor(2) as ex:
        for n in ex.map(ocr, pdfs):
            done += 1
            if done % 20 == 0:
                print(done, "/", len(pdfs), flush=True)
    for o in ops:
        t = (RAW / (o["path"].rsplit("/", 1)[-1] + ".txt"))
        o["chars"] = len(t.read_text(encoding="utf-8").strip()) if t.exists() else 0
    (HERE / "opinions.json").write_text(json.dumps(ops, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done", sum(1 for o in ops if o["chars"] > 300), "of", len(ops), "readable")
