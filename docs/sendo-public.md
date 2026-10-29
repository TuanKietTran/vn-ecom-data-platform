# Sendo public connector status

The connector targets `https://searchlist-api.sendo.vn/web/products` and labels
its observations `source_tier=public`. It checks the API host's `robots.txt`
before search requests, uses the configured HTTP rate limit, and stops gracefully
on a `BlockedError`. A blocked endpoint or network failure stops paging and returns
any rows yielded earlier in that run. DNS/network failure does not trigger an
alternate host, user-agent change, or other access workaround.

## Verification status

**Status as of 2026-10-26: unverified; no live product rows or endpoint availability
have been verified.** The connector remains unverified until the host resolves,
robots policy can be checked, and an allowed request yields product rows.

The repository's 2026-10-26 status record reports that DNS checks returned
`NXDOMAIN` for `searchlist-api.sendo.vn`, while the parent `sendo.vn` resolved to
`103.137.187.129`. A request to `https://www.sendo.vn/robots.txt` timed out. No
Sendo web pages or search endpoint were fetched during that recorded attempt, and
no alternative API host was guessed.

PR #9 additionally records a separate verification attempt dated 2026-03-14
(using Python 3.12.13 in an isolated virtual environment). Its first request was
only for `https://searchlist-api.sendo.vn/robots.txt`, using a descriptive
User-Agent; it reports no search endpoint request and this exact DNS failure:
`urllib.error.URLError: <urlopen error [Errno 8] nodename nor servname provided, or not known>`.
That PR-recorded attempt could not establish robots policy or endpoint availability,
and reported no live row count. These are separately dated reports; neither is
represented here as a successful live verification.

The field-mapping fixture in `tests/test_sources_market.py` is a mocked shape,
not a current live payload. No endpoint result or row count is inferred from it.
Retry live verification only after the host is resolvable and robots policy has
been checked; do not disable robots handling or work around access controls.
