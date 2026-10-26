# Sendo public connector status

**Status as of 2026-10-26: unverified; configured API host does not resolve.**

The connector currently targets `https://searchlist-api.sendo.vn/web/products`. DNS checks on
2026-10-26 returned `NXDOMAIN` for `searchlist-api.sendo.vn`; the parent `sendo.vn` resolved to
`103.137.187.129`. A request for `https://www.sendo.vn/robots.txt` timed out, so no Sendo web
pages or search endpoint were fetched and no alternative API host was guessed. The connector remains
unverified until the domain and robots policy can be checked through permitted public pages.

When the configured endpoint is blocked or a network request fails, `sendo_public` logs the failure,
stops paging, and returns any rows yielded earlier in that run. DNS/network failure does not trigger
an alternate host, user-agent change, or other access workaround. The field mapping fixture in
`tests/test_sources_market.py` is a mocked shape, not a current live payload.
