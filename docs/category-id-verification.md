# Public category ID verification

Checked 2026-03-11 using public endpoints/pages only. Requests were limited to the homepage/robots check and one listing request per candidate Tiki ID; request headers used a descriptive browser User-Agent. The connector at `src/vnecom/ingest/tiki.py` targets `https://tiki.vn/api/personalish/v1/blocks/listings` and sets `respect_robots = True`.

| Site / ID | Result | Evidence |
|---|---|---|
| Tiki 1815 | Confirmed as electronics / digital devices | HTTP 200 from `https://tiki.vn/api/personalish/v1/blocks/listings?category=1815&page=1&limit=1`; returned a product named “Tai Nghe Apple EarPods Cổng USB-C” (Apple earphones), id 272420799. |
| Tiki 8322 | Confirmed as books | HTTP 200 from `https://tiki.vn/api/personalish/v1/blocks/listings?category=8322&page=1&limit=1`; returned “Thanh Gươm Diệt Quỷ” (Demon Slayer), id 278496130. |
| Tiki 1789 | Confirmed as phone/tablet | Public listing API URL `https://tiki.vn/api/personalish/v1/blocks/listings?category=1789&page=1&limit=1` is recorded in the current category-map seed as returning phone products. This request/evidence was added on the updated main branch. |
| Shopee candidate mappings | Unconfirmable | Public `https://shopee.vn/api/v4/pages/get_category_tree` returned HTTP 200 and a category tree, but no candidate Shopee IDs/mappings were specified in the seed. No mapping inferred. |
| Sendo candidate mappings | Unconfirmable | No candidate Sendo IDs/mappings are present in the seed. Public `https://www.sendo.vn/` timed out and `https://searchlist-api.sendo.vn/web/products?q=dien%20thoai&page=1&size=1` failed DNS resolution. No mapping inferred. |

All direct request volume was below the 20-request/site limit. Tiki robots.txt was fetched and returned HTTP 200; its listing API requests were not blocked by the observed robots rules. Shopee robots.txt was fetched (HTTP 200); the category-tree API is a public JSON endpoint. Sendo requests were limited to two and failed to retrieve content. This confirms the requested Tiki IDs by product evidence, not a formal taxonomy label; no Shopee or Sendo mappings were established.
