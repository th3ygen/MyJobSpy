# Hiredly fixtures

Real responses captured from `my-api.hiredly.com/api/job_seeker/v1/graphql`
on 2026-09-24, using the scraper's own `SEARCH_QUERY`, trimmed and committed so
the tests run offline and deterministically.

| File | Contains |
|---|---|
| `search_page.json` | 10 real records, chosen to cover every branch the parser has. `pageInfo.hasNextPage` is `true`. |
| `search_last_page.json` | 3 records from a real final page (`hasNextPage: false`) |
| `search_empty.json` | A real zero-result search; `endCursor` is `null` |
| `search_malformed.json` | Hand-built, 7 degradation cases (null id, empty title, all-null, unknown job type, bad timestamp, non-numeric salary, no company object) |

## Why these ten records

| Record | Why it is here |
|---|---|
| `a37fed3c` | Organic, `"5000 - 7000"`, full-time, protocol-relative logo, 4–7 years |
| `8f5ec12d` | Single-value salary `"400"`, internship, **no logo**, `minYearsExperience: -1` |
| `a13f6d67` | Organic but `"Undisclosed"`; title has a trailing space |
| `8c138a21` | **Aggregated** (`category: "scraped"`) with a Workday `externalJobUrl` |
| `3279048b` | `stateRegion: "Remote"`, city `"Petaling Jaya"` |
| `ae1b3068` | Internship, newest timestamp (18:54) — the hours_old test hinges on it |
| `c2cc7a2a` | Advertiser junk salary `"1700 - 5002500"`, must parse to `None`; `workingArrangementRemote: false` |
| `8fd5baae` | `workingArrangementRemote: true` with a real state |
| `7abd77e0` | `stateRegion: "Penang"` — the board's spelling, not the canonical one |
| `46843029` | **Singapore** posting: `stateRegion: "North-East"`, not `"Singapore"` |

`description`, `requirements` and `skills` were trimmed to their first few
elements to keep the file small. Nothing else was edited, with one exception:

`a37fed3c`'s `description` was hand-edited (2026-09-24) to append
"Entry-level hires may start from RM 3,000 per month." No captured
description contained a parseable MYR figure, so
`test_board_salary_is_not_overwritten_by_the_description_parser` would have
passed whether or not the board-wins guard exists. The board's 5000 and the
description's 3,000 now disagree, so the test can fail.

## Refreshing

Run `SEARCH_QUERY` from `jobspy/hiredly/constant.py` against the endpoint with
`{"keyword": "software engineer", "first": 30}`. A fixture that still passes
does not mean the board still works — `tests/test_hiredly_live.py` is the only
layer that catches the API changing.
