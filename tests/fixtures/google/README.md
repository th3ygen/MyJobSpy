# Google fixtures

`js_challenge.html` is the page `google.com/search?...&udm=8` returned on
2026-09-24 to the request `jobspy/google/__init__.py` sends: status 200,
about 93KB, 99% script, no job results. Its `<noscript>` block meta-refreshes
non-JavaScript clients to `/httpservice/retry/enablejs`, which is how the
scraper recognises it.

Trimmed: the `<title>` and `<noscript>` block are verbatim; Google's inline
scripts were removed (each replaced by a comment) since nothing reads them.
