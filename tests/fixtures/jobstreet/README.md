# JobStreet MY fixtures

Real responses captured from `my.jobstreet.com` on 2026-09-23, trimmed and
committed so the parser tests run offline and deterministically.

| File | Captured from | Contains |
|---|---|---|
| `search_page.json` | `GET /api/jobsearch/v5/search` | 8 real records, chosen to cover every branch the parser has |
| `search_last_page.json` | same | 3 records — a partial final page |
| `search_empty.json` | same | Zero results; the paging loop must terminate |
| `job_details.json` | `POST /graphql` (`jobDetails`) | One description body, truncated to ~1KB |
| `search_malformed.json` | hand-built from observed shapes | 6 degradation cases |

## Why these eight records

Each covers a branch that real data actually exercises:

| Record | Why it is here |
|---|---|
| `94462128` | Remote, salaried — **and has no `companyName` key at all**, only `advertiser.description: "Private Advertiser"` |
| `94689504` | On-site, salaried — the nominal case |
| `94234551` | Hybrid, salaried |
| `94830903` | No `salaryLabel` (the ~30% case) — suburb location label: `"Bukit Bintang, Kuala Lumpur"` |
| `94831259` | Suburb location label: `"Cheras, Kuala Lumpur"` |
| `94586568` | Two `workTypes` on one posting: `["Casual/Vacation", "Full time"]` |
| `94333139` | Single-value salary: `"RM 1,000 per month"`, no range |
| `94553263` | Advertiser junk: `"$5,000 – $7,000 per month"` typed with `$`, must parse to `None` |

Salary strings retain their original **non-breaking spaces (` `)** and
**en-dashes (`–`)**. Do not "clean" these — reproducing them is the point,
since they are what the live board sends.

`94689504`'s `teaser` was hand-edited (2026-09-23, fix wave F7) to append
"Entry-level hires may start from RM 3,000 per month." — a deliberate
deviation from the raw capture. Every other teaser in this fixture set
contains no parseable MYR figure at all, which made
`test_board_salary_is_not_overwritten_by_the_description_parser` in
`tests/test_jobstreet_pipeline.py` pass regardless of whether the
board-wins guard it claims to test was even present. `94689504`'s
`salaryLabel` (RM 5,000-7,500/month) and its teaser's RM 3,000 now
genuinely disagree, so removing the guard changes the parsed amount and the
test can actually fail.

`solMetadata` and `tracking` were stripped. They are per-request tokens that
change on every capture, which would make fixture diffs unreadable, and no
parser code may read them.

## Refreshing

```bash
curl -s "https://my.jobstreet.com/api/jobsearch/v5/search\
?siteKey=MY-Main&sourcesystem=houston&where=Kuala+Lumpur\
&keywords=software+engineer&page=1&pageSize=100"
```

A fixture that still passes does not mean the board still works — it means the
parser still handles a shape captured in the past. The `@pytest.mark.live`
smoke test is the only layer that catches the API changing.
