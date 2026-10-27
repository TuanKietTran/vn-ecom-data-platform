# Sendo public search connector

The connector targets `https://searchlist-api.sendo.vn/web/products` and labels
its observations `source_tier=public`. It checks the API host's `robots.txt` before
search requests, uses the configured HTTP rate limit, and stops gracefully on a
`BlockedError`. The endpoint is not considered live-verified until an allowed
request yields product rows.

## Verification record

Live verification was attempted on 2026-03-14 with Python 3.12.13 in an isolated
virtual environment. The first request was only for
`https://searchlist-api.sendo.vn/robots.txt`, using a descriptive User-Agent;
no search endpoint request was made. DNS resolution failed with
`urllib.error.URLError: <urlopen error [Errno 8] nodename nor servname provided, or not known>`.
Consequently, robots policy could not be read, endpoint availability could not be
validated, and no live row count is available. No endpoint result or row count
is inferred from the existing mocked connector test.

Retry live verification only after the host is resolvable and robots policy has
been checked; do not disable robots handling or work around access controls.
