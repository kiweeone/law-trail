"""Find State Gazette materials for a given (year, issue) without crawling everything.

idMat values are sequential across issues, so a binary search on idMat by (year, issue) finds an issue's
first material; laws from the National Assembly are at the start of the official section.
"""
import re
import dv

LO, HI = 166000, 247300
_cache = {}


def key_at(i):
    """(year, issue) of the nearest valid material at or after idMat i (skipping gaps)."""
    for j in range(i, i + 12):
        if j in _cache:
            k = _cache[j]
        else:
            d = dv.parse(j, dv.fetch(j))
            k = (int(d["date"].split(".")[-1]), d["issue"]) if d and d.get("issue") and d.get("date") else None
            _cache[j] = k
        if k:
            return k, j
    return None, i


def issue_start(year, issue):
    lo, hi = LO, HI
    target = (year, issue)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        k, _ = key_at(mid)
        if k is None or k < target:
            lo = mid
        else:
            hi = mid
    k, j = key_at(hi)
    return j if k == target else None


def ns_materials(year, issue, max_scan=60):
    """National Assembly materials (laws, decisions) in an issue."""
    start = issue_start(year, issue)
    if start is None:
        return []
    out = []
    for i in range(start, start + max_scan):
        d = dv.parse(i, dv.fetch(i))
        if not d:
            continue
        if d["issue"] != issue:
            break
        if d["issuer"].startswith("Народно събрание"):
            out.append(d)
    return out


if __name__ == "__main__":
    import sys
    for d in ns_materials(int(sys.argv[1]), int(sys.argv[2])):
        print(d["idMat"], d["title"][:100])
