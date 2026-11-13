"""parliament.bg JSON API client (undocumented API behind the site)."""
import json, pathlib, time, urllib.request, concurrent.futures as cf

API = "https://www.parliament.bg/api/v1"
RAW = pathlib.Path(__file__).parent / "raw" / "pbg"
RAW.mkdir(parents=True, exist_ok=True)


def _req(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


def cached(name, fn):
    p = RAW / f"{name}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    d = fn()
    if d is not None:
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def fresh(name, fn):
    """Fetch now and overwrite the cached copy (used by the scheduled update, where stale data would hide changes)."""
    d = fn()
    if d is not None:
        (RAW / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def bill_fresh(i):
    return fresh(f"bill_{i}", lambda: _req(f"{API}/bill/{i}"))


def get_fresh(path):
    return fresh(path.strip("/").replace("/", "_"), lambda: _req(f"{API}/{path.strip('/')}"))


def bills_search(date1, date2):
    """Uncached bill search for the current assembly."""
    q = {"A_ns_id": "", "L_Ses_id": "", "A_ns_C_id": "", "A_ns_MP_id": "", "L_Act_string": "",
         "L_Act_sign": "", "date1": date1, "date2": date2, "Pr_id": "", "impMin": ""}
    return _req(f"{API}/fn-bills", q)


def bills(date1, date2):
    q = {"A_ns_id": "", "L_Ses_id": "", "A_ns_C_id": "", "A_ns_MP_id": "", "L_Act_string": "",
         "L_Act_sign": "", "date1": date1, "date2": date2, "Pr_id": "", "impMin": ""}
    return cached(f"bills_{date1}_{date2}", lambda: _req(f"{API}/fn-bills", q))


def bill(i):
    return cached(f"bill_{i}", lambda: _req(f"{API}/bill/{i}"))


def get(path):
    return cached(path.strip("/").replace("/", "_"), lambda: _req(f"{API}/{path.strip('/')}"))


def bills_detail(ids, workers=4):
    with cf.ThreadPoolExecutor(workers) as ex:
        return list(ex.map(bill, ids))
