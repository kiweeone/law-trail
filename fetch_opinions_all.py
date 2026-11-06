import json, pathlib, opinions
HERE = pathlib.Path(__file__).parent
cur = [l["bill_id"] for l in json.loads((HERE / "laws_52.json").read_text(encoding="utf-8")) if l.get("bill_id")] if (HERE / "laws_52.json").exists() else \
      [l["bill_id"] for l in json.loads((HERE / "laws.json").read_text(encoding="utf-8")) if l.get("bill_id") and l.get("ns", "52") == "52"]
past = [b["id"] for b in json.loads((HERE / "backfill_bills.json").read_text(encoding="utf-8")) if b["dv"] and b["ns"] in {"47","48","49","50","51"}]
ops = opinions.main(list(dict.fromkeys(cur + past)))
print(len(ops), "opinions;", sum(1 for o in ops if o["chars"] > 300), "with text layer")
