# Law Trail prototype

Traces Bulgarian laws from the State Gazette back to their bills, sponsors and second-reading amendments.

## Run

```
python3 dv.py 244000 247260 dv_materials.jsonl   # crawl ДВ material pages by idMat (~6 min, cached in raw/dv)
python3 laws.py                                   # keep National Assembly laws, parse adoption date + final provisions
python3 match.py                                  # match each law to its parliament.bg bill (ДВ issue + title)
python3 extract.py                                # pull second-reading reports, extract proposals, classify riders
python3 opinions.py && python3 ocr.py              # download stakeholder opinions, OCR the scans (needs tesseract + bul)
python3 influence.py                              # text footprints (uses real first-reading vote dates)
python3 diffparse.py                              # before/after per paragraph from 2nd-reading reports
python3 -c "import shtrack; shtrack.run_all()"    # MP ↔ ЩРАК person match (rate-limited)
python3 build.py                                  # assemble data and render site/law-trail.html
```

Standard library only. Everything is cached under `raw/`, so reruns are fast.

## Files

- `dv.py` — ДВ crawler/parser. `showMaterialDV.jsp?idMat=N` is stateless; IDs are sequential (~70 per issue, both sections).
- `pbg.py` — client for parliament.bg's undocumented JSON API (`/api/v1`).
- `laws.py` — adoption date, assembly, final-provisions section, other laws amended there.
- `match.py` — bill ↔ law: bill record's `L_Act_dv_iss` + title similarity; title fallback when the field is empty.
- `extract.py` — committee report (`com-stan/bg/{id}`): proposals, proposers → MP IDs, outcome, final-provisions flag; origin of each other-law amendment (in bill as introduced vs added at second reading, and by whom).
- `laws.json` — the output: 48 laws, 663 proposals.
- `proposals.csv` — flat table of every proposal.

## Useful parliament.bg endpoints (found in the site's JS)

- `POST /fn-bills` — bill search (`date1`, `date2`, `L_Act_string`, `A_ns_MP_id`, …)
- `GET /bill/{id}` — sponsors, committees, ДВ issue, reports (`stan_list2_1` = final 2nd-reading report), stakeholder opinions (`standp_list`), proposals between readings (`proposal_12_list`), plenary/committee transcripts
- `GET /com-stan/bg/{id}` — full report text (HTML)
- `GET /coll-list-ns/bg` — current MP roster with group
- Not yet used: `/vote/{id}`, `/vote-list` (roll-call votes), `/pl-sten/` (plenary transcripts), `/conflict-register`, `/conflict-decl-list/{1,2}` (conflict-of-interest declarations), `/period-sebra/`, `/civil-contracts`

## Known gaps

- 2 of 48 laws unmatched (no separate second-reading report).
- 17 of 663 proposer names not resolved (MPs no longer on the roster, odd spellings).
- 6 of 83 other-law amendments have unclear origin; rule-based parsing misses unusual report layouts.

## Publishing

`python3 build.py` writes a ready-to-host static site to `deploy/`:
`index.html` (data inlined), `detail-47.json` … `detail-52.json` (loaded on demand), `vercel.json`, `robots.txt`.

Vercel: import this repository, set **Root Directory** to `deploy`, framework **Other**, no build command.
Custom domain: add it in Vercel → Domains, then in GoDaddy DNS add the CNAME record Vercel shows (for a subdomain, `cname.vercel-dns.com`).

The corrections address shown on the site is read from `contact.txt` (or the `LT_CONTACT` environment variable).
