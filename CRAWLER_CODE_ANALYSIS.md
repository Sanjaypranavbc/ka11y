# Crawler Code Analysis

- Generated at (UTC): `2026-03-28 15:52:04Z`
- Scope: Node crawl engine + Python crawler modules
- Method: static source analysis (module metrics + output pattern detection)

## Crawler Inventory

| Crawler File | Role | LOC (code/total) | Functions | Classes | Decisions | Output Patterns |
|---|---|---:|---:|---:|---:|---|
| `ka11y-node/src/services/accessibility.service.js` | Node Puppeteer page audit/crawl engine | 274/375 | 17 | 8 | 39 | - |
| `ka11y-python/ka11y/crawler/_ssrf_guard.py` | Outbound request SSRF guard | 65/82 | 3 | 0 | 17 | - |
| `ka11y-python/ka11y/crawler/crawler.py` | Image crawling and metadata extraction | 1068/1275 | 12 | 4 | 172 | json output, image output, directory creation |
| `ka11y-python/ka11y/crawler/forms_crawler.py` | Form/input crawling | 209/257 | 4 | 2 | 24 | json output, directory creation |
| `ka11y-python/ka11y/crawler/interactive_crawler.py` | Interactive element crawling | 246/293 | 4 | 2 | 46 | json output, directory creation |
| `ka11y-python/ka11y/crawler/moving_content_crawler.py` | Moving/auto-updating content crawling | 551/627 | 5 | 2 | 99 | json output, directory creation |
| `ka11y-python/ka11y/crawler/rendered_layout_crawler.py` | Rendered layout crawl snapshots | 565/684 | 17 | 1 | 65 | image output |
| `ka11y-python/ka11y/crawler/target_size_crawler.py` | Target-size measurement crawling | 281/338 | 4 | 2 | 35 | json output, directory creation |
| `ka11y-python/ka11y/crawler/text_spacing_crawler.py` | Text-spacing snapshot crawling | 130/195 | 4 | 2 | 14 | json output, directory creation |

## Highest Complexity Crawler Modules

| File | Decisions | Code Lines |
|---|---:|---:|
| `ka11y-python/ka11y/crawler/crawler.py` | 172 | 1068 |
| `ka11y-python/ka11y/crawler/moving_content_crawler.py` | 99 | 551 |
| `ka11y-python/ka11y/crawler/rendered_layout_crawler.py` | 65 | 565 |
| `ka11y-python/ka11y/crawler/interactive_crawler.py` | 46 | 246 |
| `ka11y-node/src/services/accessibility.service.js` | 39 | 274 |
| `ka11y-python/ka11y/crawler/target_size_crawler.py` | 35 | 281 |
| `ka11y-python/ka11y/crawler/forms_crawler.py` | 24 | 209 |
| `ka11y-python/ka11y/crawler/_ssrf_guard.py` | 17 | 65 |
| `ka11y-python/ka11y/crawler/text_spacing_crawler.py` | 14 | 130 |
