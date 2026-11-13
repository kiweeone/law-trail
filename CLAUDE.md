# Law Trail

Public tool that traces Bulgarian laws from the State Gazette (ДВ) to their bills on parliament.bg: who sponsored and
amended them, what passed, which organisations filed opinions and where their wording ended up, and MPs' company ties
(ЩРАК / Commercial Register). Covers the 47th–52nd National Assemblies (Dec 2021 →). Owner: kiweeone.

- Live: https://law-trail.vercel.app (Vercel, deploys every push to `main`; output folder `deploy/`, see `vercel.json`)
- Weekly data update: `.github/workflows/update.yml` runs `update.py` on Mondays and commits; `UPDATES.md` logs runs.
  Manual run: Actions → Update data → Run workflow (mode `selftest` changes nothing).

## How it fits together
- `update.py` — incremental update: new laws only, merged into the JSON files, then `build.py`. Fails without
  publishing on bad data. Starts from an empty cache; compact state lives in `bills.json`, `mp_profiles.json`,
  `rosters.json`, `dv_ns_index.json`, `update_state.json`.
- `build.py` — assembles all data and renders `site/template.html` into `deploy/index.html` (+ `detail-NN.json`) and
  `site/law-trail.html` (Claude artifact preview). Run it after any template or data change.
- `site/template.html` — the whole UI (single file: CSS, HTML, JS). Bulgarian + English (`T(bg, en)`, `data-en`),
  light/dark, hash routing with history and filters in the URL.
- Analysis steps: `extract.py` (2nd-reading reports, amendments, outcomes), `influence.py` (text footprints),
  `diffparse.py` (before/after), `crossparty.py`, `topics.py` (law topics, company sectors), `shtrack_links.py` /
  `shtrack_roles.py` (company ties and dated roles).

## Rules for this project
- Signals are leads, not proof; the site says so. Same rules for every party. Don't add claims the data can't support.
- Every item links to its primary source. Corrections address: `contact.txt` (shown in footer, panels, method page).
- Name-only ЩРАК matches (`name_only`) are unconfirmed: never used for sector leads, always labelled.
- Be polite to sources: ~1.5 s between ЩРАК requests; parliament.bg API is undocumented, so check shape changes.
- Commits as `kiweeone <kiweeone@users.noreply.github.com>`. No personal email in the repo.
- Owner prefers concise communication and no over-engineering.
