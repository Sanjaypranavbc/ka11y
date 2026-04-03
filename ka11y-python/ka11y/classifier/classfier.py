import os
import hashlib
import aiohttp
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from ka11y.config.logger import setup_logger
from ka11y.crawler.models import ImageData



console = Console(force_terminal=True)
logger = setup_logger(name="KAC", tag="classify_assets")


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic output model
# ─────────────────────────────────────────────────────────────────────────────
class ImageClassification(BaseModel):
    classification: str = "informative"
    sub_type: str | None = None
    is_text_image: bool = False
    is_functional: bool = False
    is_decorative: bool = False
    is_complex: bool = False
    is_logo: bool = False
    is_icon: bool = False
    is_button: bool = False
    file_format: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Keyword constants (defined once, reused across methods)
# ─────────────────────────────────────────────────────────────────────────────
_LOGO_KEYWORDS = [
    "logo",
    "brand",
    "header-img",
    "site-logo",
    "company-logo",
    "wordmark",
    "logotype",
    "brand-mark",
    "site-brand",
    "navbar-brand",
    "nav-logo",
    "masthead",
    "identity",
    "ロゴ",
    "ブランド",
    "サイトロゴ",
    "企業ロゴ",
]

_ICON_KEYWORDS = [
    "icon",
    "ico",
    "symbol",
    "glyph",
    "sprite",
    "badge",
    "avatar",
    "アイコン",
    "シンボル",
    "バッジ",
    "アバター",
]

_FONT_ICON_PREFIXES = [
    "fa ",
    "fa-",
    "fas ",
    "fas-",
    "far ",
    "far-",
    "fab ",
    "fab-",  # FontAwesome
    "material-icons",
    "material-symbols",  # Material
    "bi bi-",
    "bi-",  # Bootstrap Icons
    "glyphicon",  # Bootstrap 3
    "feather",
    "lucide",  # Feather / Lucide
    "icon-",
    "-icon",  # Generic
]

_CHART_KEYWORDS = [
    "chart",
    "graph",
    "plot",
    "bar-chart",
    "line-chart",
    "pie-chart",
    "scatter",
    "histogram",
    "heatmap",
    "treemap",
    "funnel",
    "waterfall",
    "trend",
    "analytics",
    "metric",
    "kpi",
    "dashboard",
    "infographic",
    "diagram",
    "flowchart",
    "flow-chart",
    "architecture",
    "schema",
    "network",
    "topology",
    "mindmap",
    "gantt",
    "timeline",
    "statistics",
    "report",
    "data-viz",
    "visualization",
    "グラフ",
    "チャート",
    "図表",
    "統計",
    "インフォグラフィック",
    "ダッシュボード",
    "分析",
]

_CHART_LIBS = [
    "chart.js",
    "chartjs",
    "d3.js",
    "d3.min",
    "highcharts",
    "plotly",
    "echarts",
    "apexcharts",
    "recharts",
    "vega",
    "amcharts",
    "fusioncharts",
    "canvasjs",
    "chartist",
    "nivo",
    "victory",
    "c3.js",
    "c3.min",
]

# NOTE: generic terms ("figure", "caption") intentionally omitted to prevent
# false positives on news-article photos in <figure><figcaption> containers.
_CHART_PARENT_CLASSES = [
    "chart",
    "graph",
    "diagram",
    "viz",
    "visualization",
    "plot",
    "infographic",
    "canvas-wrap",
    "chart-container",
    "dashboard",
    "analytics",
    "data-chart",
    "chart-wrap",
    "グラフ",
    "チャート",
    "図表",
]


# ─────────────────────────────────────────────────────────────────────────────
class ClassifyAssets:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.images_data: list[ImageData] = []

    # ── helpers ──────────────────────────────────────────────────────────────

    def get_image_hash(self, src: str) -> str:
        return hashlib.md5(src.encode()).hexdigest()[:12]

    def _rich_result(self, label: str, cls: str, sub: str | None, color: str):
        """Print a compact one-line rich result for the classification."""
        sub_str = f"/{sub}" if sub else ""
        console.print(
            f"  [bold {color}]→ {label}[/bold {color}] " f"[dim]{cls}{sub_str}[/dim]"
        )

    # ── public: classify_image ────────────────────────────────────────────────

    async def classify_image(self, img_element, page=None) -> dict:
        """
        WCAG-based image classification cascade:

          STEP 0  aria-hidden / role=presentation  → decorative/presentational
          STEP 1a _is_button OR inButton           → functional/buttons
          STEP 1b _is_logo  AND inRealLink         → functional/logos
          STEP 1c _is_chart                        → complex/charts
          STEP 1d _is_icon  AND (inLink|hasClick)  → functional/icons
          STEP 1e inRealLink OR hasClick           → functional/images
          STEP 2  standalone _is_logo              → informative/logos
          STEP 3  standalone _is_icon  (has alt)   → informative/icons
                                       (no alt)    → decorative/decorative
          STEP 4  alt present                      → informative (sub-typed)
                  alt="" explicit                  → decorative/decorative
                  alt missing                      → decorative/missing_alt
        """
        c = ImageClassification()

        # ── gather basic attributes ──
        alt_text = await img_element.get_attribute("alt")  # None = missing
        src = await img_element.get_attribute("src") or ""
        role = (await img_element.get_attribute("role") or "").lower()
        aria_hidden = (await img_element.get_attribute("aria-hidden") or "").lower()

        # ── build context ──
        try:
            ctx = await img_element.evaluate("""el => {
                const a = el.closest("a");
                const href = a ? (a.getAttribute("href") || "").trim() : "";
                const deadHref = !href || href === "#" || href === "" ||
                                 href.startsWith("javascript:");
                return {
                    inButton:    el.closest("button, [role='button']") !== null,
                    inLink:      a !== null,
                    inRealLink:  a !== null && !deadHref,
                    linkHref:    href || null,
                    hasClick:    el.onclick !== null ||
                                 window.getComputedStyle(el).cursor === "pointer"
                };
            }""")
        except Exception:
            ctx = {
                "inButton": False,
                "inLink": False,
                "inRealLink": False,
                "linkHref": None,
                "hasClick": False,
            }

        logger.info(f"Context: {ctx}")

        src_lower = src.lower()
        alt_str = alt_text if alt_text is not None else ""  # '' = explicit empty
        alt_lower = alt_str.lower()

        # ─────────────────────────────────────────────────────────────
        # STEP 0 — explicitly hidden / presentational
        # ─────────────────────────────────────────────────────────────
        if aria_hidden == "true" or role in ("presentation", "none"):
            c.is_decorative = True
            c.classification = "decorative"
            c.sub_type = "presentational"
            logger.info("[STEP 0] Decorative — aria-hidden/role=presentation")
            self._rich_result(
                "STEP 0 · presentational", "decorative", "presentational", "dim"
            )
            return c.model_dump()

        # ─────────────────────────────────────────────────────────────
        # STEP 1a — button
        # ─────────────────────────────────────────────────────────────
        if ctx["inButton"] or await self._is_button(img_element):
            c.is_functional = True
            c.is_button = True
            c.classification = "functional"
            c.sub_type = "buttons"
            logger.info("[STEP 1a] functional/buttons")
            self._rich_result("STEP 1a · button", "functional", "buttons", "yellow")
            return c.model_dump()

        # ─────────────────────────────────────────────────────────────
        # STEP 1b — logo in a real navigation link
        # ─────────────────────────────────────────────────────────────
        if ctx["inRealLink"] and await self._is_logo(img_element, src, alt_str):
            c.is_functional = True
            c.is_logo = True
            c.is_text_image = True
            c.classification = "functional"
            c.sub_type = "logos"
            logger.info("[STEP 1b] functional/logos")
            self._rich_result(
                "STEP 1b · logo (nav link)", "functional", "logos", "cyan"
            )
            return c.model_dump()

        # ─────────────────────────────────────────────────────────────
        # STEP 1c — complex chart / diagram
        # ─────────────────────────────────────────────────────────────
        if await self._is_chart(img_element, src, alt_str, page):
            c.is_complex = True
            c.classification = "complex"
            c.sub_type = "charts"
            logger.info("[STEP 1c] complex/charts")
            self._rich_result("STEP 1c · chart/diagram", "complex", "charts", "magenta")
            return c.model_dump()

        # ─────────────────────────────────────────────────────────────
        # STEP 1d — icon in a clickable context
        # ─────────────────────────────────────────────────────────────
        if (ctx["inLink"] or ctx["hasClick"]) and await self._is_icon(img_element, src):
            c.is_functional = True
            c.is_icon = True
            c.classification = "functional"
            c.sub_type = "icons"
            logger.info("[STEP 1d] functional/icons")
            self._rich_result(
                "STEP 1d · icon (clickable)", "functional", "icons", "yellow"
            )
            return c.model_dump()

        # ─────────────────────────────────────────────────────────────
        # STEP 1e — any image in a real link / with click handler
        # ─────────────────────────────────────────────────────────────
        if ctx["inRealLink"] or ctx["hasClick"]:
            c.is_functional = True
            c.classification = "functional"
            c.sub_type = "images"
            logger.info("[STEP 1e] functional/images")
            self._rich_result(
                "STEP 1e · clickable image", "functional", "images", "yellow"
            )
            return c.model_dump()

        # ─────────────────────────────────────────────────────────────
        # STEP 2 — standalone logo (not in a link)
        # ─────────────────────────────────────────────────────────────
        if await self._is_logo(img_element, src, alt_str):
            c.is_logo = True
            c.is_text_image = True
            if alt_str.strip():
                c.classification = "informative"
                c.sub_type = "logos"
                logger.info("[STEP 2] informative/logos (standalone with alt)")
                self._rich_result(
                    "STEP 2 · logo (informative)", "informative", "logos", "green"
                )
            else:
                c.is_decorative = True
                c.classification = "decorative"
                c.sub_type = "decorative"
                logger.info("[STEP 2] decorative/logo (standalone, no alt)")
                self._rich_result(
                    "STEP 2 · logo (no alt → decorative)",
                    "decorative",
                    "decorative",
                    "dim",
                )
            return c.model_dump()

        # ─────────────────────────────────────────────────────────────
        # STEP 3 — standalone icon
        # ─────────────────────────────────────────────────────────────
        if await self._is_icon(img_element, src):
            c.is_icon = True
            if alt_str.strip():
                c.classification = "informative"
                c.sub_type = "icons"
                logger.info("[STEP 3] informative/icons (has alt)")
                self._rich_result(
                    "STEP 3 · icon (informative)", "informative", "icons", "green"
                )
            else:
                c.is_decorative = True
                c.classification = "decorative"
                c.sub_type = "decorative"
                logger.info("[STEP 3] decorative/icons (no alt)")
                self._rich_result(
                    "STEP 3 · icon (no alt → decorative)",
                    "decorative",
                    "decorative",
                    "dim",
                )
            return c.model_dump()

        # ─────────────────────────────────────────────────────────────
        # STEP 4 — alt text rule (the core WCAG 1.1.1 distinction)
        # ─────────────────────────────────────────────────────────────
        if alt_text is None:
            # alt attribute completely missing → WCAG violation
            c.is_decorative = True
            c.classification = "decorative"
            c.sub_type = "missing_alt"
            logger.info("[STEP 4] decorative/missing_alt (WCAG violation)")
            self._rich_result(
                "STEP 4 · missing alt (WCAG violation)",
                "decorative",
                "missing_alt",
                "red",
            )
            return c.model_dump()

        if alt_str == "":
            # Explicit alt="" → intentionally decorative
            c.is_decorative = True
            c.classification = "decorative"
            c.sub_type = "decorative"
            logger.info("[STEP 4] decorative (explicit alt='')")
            self._rich_result(
                "STEP 4 · decorative (alt='')", "decorative", "decorative", "dim"
            )
            return c.model_dump()

        # Has meaningful alt text → informative, sub-typed by length/context
        sub = self._informative_sub_type(alt_str)
        c.classification = "informative"
        c.sub_type = sub
        logger.info(f"[STEP 4] informative/{sub}")
        self._rich_result(f"STEP 4 · informative", "informative", sub, "green")
        return c.model_dump()

    # ─────────────────────────────────────────────────────────────────────────
    # Private detection helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _informative_sub_type(self, alt: str) -> str:
        words = len(alt.split())
        if words <= 3:
            return "succinct_information"
        if words <= 12:
            return "general_informative"
        return "extended_description"

    async def _is_button(self, element) -> bool:
        try:
            r = await element.evaluate("""el => {
                const tag  = el.tagName.toLowerCase();
                const type = (el.getAttribute("type") || "").toLowerCase();
                if (tag === "button") return true;
                if (tag === "input" && ["button","submit","reset"].includes(type)) return true;
                if (el.getAttribute("role") === "button") return true;
                if (el.onclick !== null || el.getAttribute("onclick") !== null) return true;
                // <img> inside a button ancestor
                if (tag === "img") {
                    if (el.closest("button, [role='button']") !== null) return true;
                    let p = el.parentElement, d = 0;
                    while (p && d < 4) {
                        const cls = (p.className || "").toLowerCase();
                        if (/\\bbtn\\b/.test(cls)) return true;
                        p = p.parentElement; d++;
                    }
                }
                return false;
            }""")
            return bool(r)
        except Exception:
            return False

    async def _is_logo(self, element, src: str, alt_text: str) -> bool:
        src_lower = src.lower()
        alt_lower = alt_text.lower()
        if any(k in src_lower for k in _LOGO_KEYWORDS):
            return True
        if any(k in alt_lower for k in _LOGO_KEYWORDS):
            return True
        try:
            cls = (await element.get_attribute("class") or "").lower()
            id_ = (await element.get_attribute("id") or "").lower()
            title = (await element.get_attribute("title") or "").lower()
            combined = f"{cls} {id_} {title}"
            if any(k in combined for k in _LOGO_KEYWORDS):
                return True
            # Homepage link inside header/nav carrying an aria-label with brand name
            return await element.evaluate("""el => {
                const a = el.closest("a");
                if (!a) return false;
                const href = (a.getAttribute("href") || "").trim();
                const isHome = href === "/" || href === "" || href === window.location.origin;
                const inHeader = el.closest("header, nav, [role='banner']") !== null;
                const aLabel  = (a.getAttribute("aria-label") || "").toLowerCase();
                const hasLogo = /logo|brand|home|ロゴ|ブランド|ホーム/.test(aLabel);
                return isHome && inHeader && hasLogo;
            }""")
        except Exception:
            return False

    async def _is_icon(self, element, src: str) -> bool:
        try:
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            cls = (await element.get_attribute("class") or "").lower()
            src_l = src.lower()

            # Font-icon: <i> or <span> with known icon class prefix
            if tag in ("i", "span"):
                return any(p in cls for p in _FONT_ICON_PREFIXES)

            # SVG icon: small size or icon class
            if tag == "svg":
                size = await element.evaluate(
                    "el => ({ w: el.getBoundingClientRect().width, "
                    "         h: el.getBoundingClientRect().height })"
                )
                if size["w"] <= 96 and size["h"] <= 96:
                    return True
                if any(k in cls for k in _ICON_KEYWORDS):
                    return True
                return False

            # <img>: keyword in src/class, or small square-ish image
            if any(k in src_l for k in _ICON_KEYWORDS):
                return True
            if any(k in cls for k in _ICON_KEYWORDS):
                return True
            size = await element.evaluate(
                "el => ({ w: el.getBoundingClientRect().width, "
                "         h: el.getBoundingClientRect().height })"
            )
            w, h = size["w"], size["h"]
            if 0 < w <= 96 and 0 < h <= 96:
                aspect = w / h
                if 0.33 <= aspect <= 3.0:
                    logger.info(f"Icon by size {w}×{h}, aspect={aspect:.2f}")
                    return True
        except Exception as e:
            logger.debug(f"is_icon error: {e}")
        return False

    async def _is_chart(self, element, src: str, alt_text: str, page=None) -> bool:
        """
        Scoring-based chart/diagram detector.
        Threshold = 3.  Signals (highest → lowest weight):
          +4  SVG has axis/legend
          +3  alt text contains chart keyword  |  SVG: many shapes+labels  |  caption text
          +3  large <canvas> element
          +2  page loads a chart JS library    |  src keyword  |  class keyword  |  <figure> ancestor
          +1  title attribute keyword  |  aspect-ratio heuristic
        """
        score = 0
        src_l = (src or "").lower()
        alt_l = (alt_text or "").lower()

        # ── 1. Chart JS library on page (strongest page-level signal) ──
        if page:
            try:
                scripts = await page.evaluate(
                    "() => Array.from(document.querySelectorAll('script[src]'))"
                    "     .map(s => s.src.toLowerCase())"
                )
                if any(lib in s for lib in _CHART_LIBS for s in scripts):
                    logger.info("Chart lib detected on page (+2)")
                    score += 2
            except Exception:
                pass

        # ── 2. Keyword in alt / src / class / title ──
        if any(kw in alt_l for kw in _CHART_KEYWORDS):
            logger.info("Chart keyword in alt (+3)")
            score += 3

        if any(kw in src_l for kw in _CHART_KEYWORDS):
            logger.info("Chart keyword in src (+2)")
            score += 2

        try:
            cls = (await element.get_attribute("class") or "").lower()
            title = (await element.get_attribute("title") or "").lower()
            if any(kw in cls for kw in _CHART_KEYWORDS):
                score += 2
            if any(kw in title for kw in _CHART_KEYWORDS):
                score += 1
        except Exception:
            pass

        # ── 3. Parent context ──
        try:
            ancestors = await element.evaluate("""el => {
                function info(n) {
                    if (!n) return null;
                    const fig = n.querySelector("figcaption");
                    const cap = n.querySelector(
                        "[class*=caption i],[class*=Caption],[id*=caption i]," +
                        "[class*=figure i],[class*=img-desc i],[class*=image-desc i]"
                    );
                    const capText = (fig || cap)
                        ? (fig || cap).textContent.trim().toLowerCase()
                        : "";
                    return {
                        tag:      n.tagName.toLowerCase(),
                        cls:      (n.className || "").toLowerCase(),
                        id:       (n.id || "").toLowerCase(),
                        capText:  capText
                    };
                }
                const p  = el.parentElement;
                const gp = p  ? p.parentElement  : null;
                const gg = gp ? gp.parentElement : null;
                return [info(p), info(gp), info(gg)];
            }""")

            figure_seen = False
            for anc in ancestors:
                if not anc:
                    continue
                combined = f"{anc['cls']} {anc['id']}"

                if anc["tag"] == "figure" and not figure_seen:
                    logger.info("Ancestor <figure> (+2)")
                    score += 2
                    figure_seen = True

                if any(kw in combined for kw in _CHART_PARENT_CLASSES):
                    logger.info(f"Chart class in ancestor: {combined[:60]} (+2)")
                    score += 2

                if anc["capText"] and any(
                    kw in anc["capText"] for kw in _CHART_KEYWORDS
                ):
                    logger.info(
                        f"Caption contains chart keyword: {anc['capText'][:60]} (+3)"
                    )
                    score += 3

        except Exception as e:
            logger.debug(f"Ancestor check error: {e}")

        # ── 4. SVG structural analysis ──
        try:
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            if tag == "svg":
                st = await element.evaluate("""svg => ({
                    rects:     svg.querySelectorAll("rect").length,
                    paths:     svg.querySelectorAll("path").length,
                    circles:   svg.querySelectorAll("circle").length,
                    texts:     svg.querySelectorAll("text").length,
                    groups:    svg.querySelectorAll("g").length,
                    hasAxis:   !!svg.querySelector(".axis,.tick,[class*=axis],[class*=tick]"),
                    hasLegend: !!svg.querySelector(".legend,[class*=legend]")
                })""")
                if st["hasAxis"] or st["hasLegend"]:
                    logger.info("SVG axis/legend (+4)")
                    score += 4
                shapes = st["rects"] + st["paths"] + st["circles"]
                if st["texts"] >= 3 and shapes > 5:
                    logger.info(f"SVG shapes={shapes} texts={st['texts']} (+3)")
                    score += 3
                if st["groups"] > 10 and st["texts"] >= 2:
                    logger.info("SVG complex group structure (+1)")
                    score += 1
        except Exception:
            pass

        # ── 5. Large <canvas> element ──
        try:
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            if tag == "canvas":
                sz = await element.evaluate(
                    "el => ({ w: el.getBoundingClientRect().width,"
                    "         h: el.getBoundingClientRect().height })"
                )
                if sz["w"] > 200 and sz["h"] > 150:
                    logger.info(f"Large canvas {sz['w']}×{sz['h']} (+3)")
                    score += 3
        except Exception:
            pass

        # ── 6. Aspect-ratio heuristic (large landscape or tall portrait) ──
        try:
            sz = await element.evaluate(
                "el => ({ w: el.getBoundingClientRect().width,"
                "         h: el.getBoundingClientRect().height })"
            )
            w, h = sz["w"], sz["h"]
            if w > 0 and h > 0:
                ratio = w / h
                if (w > 300 or h > 300) and (ratio > 1.3 or ratio < 0.6):
                    logger.info(f"Aspect-ratio heuristic {ratio:.2f} {w}×{h} (+1)")
                    score += 1
        except Exception:
            pass

        THRESHOLD = 3
        result = score >= THRESHOLD
        logger.info(f"_is_chart score={score} → {'YES' if result else 'no'}")
        return result

    # ── public aliases (backward compat) ──────────────────────────────────────
    async def is_logo(self, el, src, alt):
        return await self._is_logo(el, src, alt)

    async def is_icon(self, el, src, alt):
        return await self._is_icon(el, src)

    async def is_chart(self, el, src, alt, page=None):
        return await self._is_chart(el, src, alt, page)

    async def is_button_image(self, el):
        return await self._is_button(el)

    # ── overlay container detection ───────────────────────────────────────────
    async def get_visual_container(self, img_element, page):
        return await img_element.evaluate_handle("""img => {
            const imgRect = img.getBoundingClientRect();
            if (imgRect.width < 60 || imgRect.height < 60) return img;

            let cur = img.parentElement;
            for (let i = 0; i < 3; i++) {
                if (!cur || cur.tagName === "BODY" || cur.tagName === "HTML") break;
                const rect = cur.getBoundingClientRect();
                if ((rect.width * rect.height) / (imgRect.width * imgRect.height) > 2) break;
                const hasOverlay = Array.from(cur.children).some(ch => {
                    if (ch === img) return false;
                    const cs  = window.getComputedStyle(ch);
                    const cr  = ch.getBoundingClientRect();
                    const txt = (ch.innerText || "").trim();
                    const overlaps = !(cr.right  < imgRect.left  || cr.left > imgRect.right ||
                                       cr.bottom < imgRect.top   || cr.top  > imgRect.bottom);
                    return cs.position === "absolute" && overlaps &&
                           txt.length > 3 && txt.length < 200;
                });
                if (hasOverlay) return cur;
                cur = cur.parentElement;
            }
            return img;
        }""")

    # ── file download helper ──────────────────────────────────────────────────
    async def _download_file(
        self, session: aiohttp.ClientSession, url: str, path: str
    ) -> bool:
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb") as f:
                        f.write(await resp.read())
                    return True
                logger.warning(f"Download {resp.status}: {url}")
                return False
        except Exception as e:
            logger.error(f"Download error {url}: {e}")
            return False
