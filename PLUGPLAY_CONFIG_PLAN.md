# Plug-and-Play Config Architecture Plan

> Generated: 2026-04-09  
> Scope: a11y-node + a11y-python  
> Goal: Make websites, languages, rules, and crawlers swappable via config — no code changes required

This is an architecture plan only. No code is changed. The goal is to define a configuration schema and system design that allows:

1. **Website plug-and-play** — Audit any site with any locale by changing config only
2. **Language compatibility** — Add/swap language support without touching rule logic
3. **Rule addition** — Register new WCAG rules by adding a config entry + implementation file
4. **Crawler addition** — Add new data extractors without modifying existing rules

---

## Current State Analysis

### What is hardcoded today

| Item | Location | Problem |
|------|----------|---------|
| CSS selectors (e.g. breadcrumb, chat widgets) | Inline in each check file | Adding JP `パンくず` means editing 5 files |
| Keyword lists (e.g. generic link text) | Inline regex strings | Adding JP こちら means editing each rule |
| Language detection | Partially in sensory_auditor.py | Only sensory rule is lang-aware |
| Rule registry | No central registry | Rules are imported and wired manually |
| Crawler registry | No central registry | Crawlers are instantiated manually in service |
| Target website | Passed as URL param | No per-site config or overrides |

### What already exists

| Item | Location | Notes |
|------|----------|-------|
| Rule metadata | `i18n/rules.yml` | WCAG ID, level, severity, name, description |
| Language translations | `i18n/locales/ja.yml`, `de.yml` | name, description, suggested_fix per rule |
| Rule sync script | `scripts/sync-i18n.sh` | Syncs rules.yml → locale files |

---

## Proposed Config Architecture

### Config File Hierarchy

```
a11y/
└── config/
    ├── rules.config.yml          # Master rule registry
    ├── crawlers.config.yml       # Master crawler registry
    ├── languages/
    │   ├── en.yml                # English keyword/selector config
    │   ├── ja.yml                # Japanese keyword/selector config
    │   ├── de.yml                # German keyword/selector config
    │   └── zh.yml                # Chinese (future)
    └── sites/
        ├── default.yml           # Default site config (no overrides)
        ├── yahoo-co-jp.yml       # JP site with lang=ja override
        └── example.yml           # Example custom site config
```

---

## 1. Rule Config (`rules.config.yml`)

Each rule entry declares what it needs from crawlers and what language config keys it uses.

```yaml
version: "2.0"

rules:

  "2.4.9":
    id: "custom-link-purpose"
    file: "src/custom-checks/link-purpose.check.js"   # Node
    python_file: null                                  # Not in Python
    enabled: true
    mode: static                                       # static | interactive
    crawlers_required: []                              # Node uses page.evaluate directly
    language_keys:
      - generic_link_patterns                          # → loaded from languages/{lang}.yml
    tags: ["wcag-aa", "wcag-2.4"]

  "3.3.3":
    id: "custom-error-suggestion"
    file: "src/custom-checks/error-suggestion.check.js"
    python_file: null
    enabled: true
    mode: static
    crawlers_required: []
    language_keys:
      - suggestion_patterns
      - error_message_patterns
    tags: ["wcag-aa", "wcag-3.3"]

  "1.3.3":
    id: "custom-sensory-characteristics"
    file: null                                         # Node: not custom
    python_file: "a11y/accessibility/rules/non_text/sensory_auditor.py"
    enabled: true
    mode: static
    crawlers_required: ["SensoryCrawler"]
    language_keys:
      - sensory_color_words
      - sensory_shape_words
      - sensory_size_words
      - sensory_position_words
      - sensory_orientation_words
      - sensory_sound_words
      - sensory_brightness_words
      - sensory_texture_words
    tags: ["wcag-a", "wcag-1.3"]

  "2.4.5":
    id: "custom-multiple-ways"
    file: "src/custom-checks/multiple-ways.check.js"
    python_file: null
    enabled: true
    mode: static
    crawlers_required: []
    language_keys:
      - search_keywords
      - sitemap_keywords
      - toc_keywords
    tags: ["wcag-aa", "wcag-2.4"]
```

**Key design decisions:**
- `language_keys` — named lists that the rule reads from the loaded language config
- `crawlers_required` — for Python, declares which crawlers must run before this rule
- `file` / `python_file` — null if the rule doesn't exist in that service
- `enabled` — allows disabling rules without removing files

---

## 2. Language Config (`languages/ja.yml`)

Each language file provides all keyword lists and selector sets for every rule that uses `language_keys`.

```yaml
version: "2.0"
lang: "ja"
writing_system: "cjk"         # latin | cjk | arabic | devanagari
word_boundary: "substring"    # regex | substring (CJK has no \b)
nlp_model: "ja_core_news_sm"  # spaCy model or null

keyword_lists:

  # 2.4.9 — Link Purpose
  generic_link_patterns:
    - "こちら"
    - "ここをクリック"
    - "続きを読む"
    - "もっと見る"
    - "もっと読む"
    - "詳しくはこちら"
    - "詳細"
    - "詳しく"
    - "リンク"
    - "クリック"

  # 3.3.3 — Error Suggestion
  suggestion_patterns:
    - "ください"
    - "入力してください"
    - "入力"
    - "確認"
    - "修正"
    - "やり直し"
    - "例"
    - "例えば"
    - "お願い"
    - "必須"

  # 2.4.5 — Multiple Ways
  search_keywords:
    - "検索"
    - "サーチ"
  sitemap_keywords:
    - "サイトマップ"
    - "sitemap"
  toc_keywords:
    - "目次"
    - "もくじ"

  # 1.2.1 — Audio Transcript
  transcript_keywords:
    - "書き起こし"
    - "文字起こし"
    - "トランスクリプト"
    - "字幕"
    - "テキスト"
    - "音声テキスト"

  # 3.2.6 — Consistent Help
  help_keywords:
    - "ヘルプ"
    - "サポート"
    - "問い合わせ"
    - "お問合せ"
    - "よくある質問"
    - "FAQ"
    - "助け"
  phone_patterns:
    - "フリーダイヤル"
    - "0120"

  # 3.3.4 — Error Prevention
  financial_keywords:
    - "支払い"
    - "購入"
    - "注文"
    - "クレジット"
    - "決済"
    - "お支払い"
  legal_keywords:
    - "利用規約"
    - "プライバシー"
    - "契約"
    - "同意"
  destructive_keywords:
    - "削除"
    - "キャンセル"
    - "無効"
    - "退会"
  review_keywords:
    - "確認"
    - "見直し"
    - "確認画面"
    - "プレビュー"

  # 3.3.8 — Accessible Auth
  auth_keywords:
    - "ログイン"
    - "サインイン"
    - "認証"
    - "パスワード"
    - "ユーザー登録"

  # 3.3.7 — Redundant Entry
  confirm_field_patterns:
    - "確認"
    - "再入力"
    - "もう一度"

  # 1.3.3 — Sensory Characteristics
  sensory_color_words:
    - "赤", "青", "緑", "黄色", "白", "黒", "ピンク", "紫", "橙", "茶"
  sensory_shape_words:
    - "丸", "四角", "円形", "三角", "長方形", "菱形"
  sensory_size_words:
    - "大きい", "小さい", "大きな", "小さな", "大型", "小型"
  sensory_position_words:
    - "左", "右", "上", "下", "中央", "前", "後", "隣", "横"
  sensory_orientation_words:
    - "横向き", "縦向き", "水平", "垂直"
  sensory_sound_words:
    - "音", "鳴る", "聞こえる", "サウンド"
  sensory_brightness_words:
    - "明るい", "暗い", "輝く", "光る"
  sensory_texture_words:
    - "滑らか", "粗い", "ざらざら", "すべすべ"

selectors:

  # 2.4.8 — Location (breadcrumb)
  breadcrumb_selectors:
    - "[aria-label*='breadcrumb']"
    - "[class*='breadcrumb']"
    - "[class*='パンくず']"
    - "[class*='pan-kuzu']"
    - "[itemtype*='BreadcrumbList']"
    - "nav [aria-current='page']"

  # 4.1.3 — Status Messages (search results)
  search_result_selectors:
    - "[role='region'][aria-label*='result']"
    - "[aria-live][id*='result']"
    - "[id*='検索結果']"
    - "[class*='検索結果']"
    - "[id*='search-result']"
    - "[class*='search-result']"

  # 3.2.6 — Consistent Help (chat widgets)
  chat_widget_selectors:
    - "#intercom-container"
    - "#drift-widget"
    - ".crisp-client"
    - "[id*='zendesk']"
    - "[id*='chat']"
    - "[class*='chat']"
    - "iframe[src*='chat']"
    # Japanese-specific:
    - "[id*='line-chat']"
    - "[class*='line-widget']"
    - "iframe[src*='linecorp.com']"

text_spacing:
  # 1.4.12 — Text Spacing
  apply_letter_spacing: false   # CJK: letter-spacing is built into glyph spacing
  apply_word_spacing: false     # CJK: no spaces between words
  apply_line_height: true       # Line height applies universally
  apply_paragraph_spacing: true # Paragraph margin applies universally
```

---

## 3. Crawler Config (`crawlers.config.yml`)

Registers available crawlers so new ones can be added without modifying service code.

```yaml
version: "2.0"

crawlers:

  # Python crawlers
  - id: "AsyncImageCrawler"
    file: "a11y/crawler/crawler.py"
    class: "AsyncImageCrawler"
    output_model: "ImageMetadata"
    output_key: "images"
    enabled: true
    language_aware: false
    tags: ["images", "visual"]

  - id: "AsyncFormCrawler"
    file: "a11y/crawler/forms_crawler.py"
    class: "AsyncFormCrawler"
    output_model: "FormInputData"
    output_key: "forms"
    enabled: true
    language_aware: true     # Reads label text, error messages
    language_keys:
      - confirm_field_patterns
    tags: ["forms", "interactive"]

  - id: "SensoryCrawler"
    file: "a11y/crawler/sensory_crawler.py"
    class: "SensoryCrawler"
    output_model: "SensoryElementData"
    output_key: "sensory"
    enabled: true
    language_aware: true
    language_keys: []         # lang= attribute read from DOM
    tags: ["text", "sensory"]

  - id: "MediaCrawler"
    file: "a11y/crawler/media_crawler.py"
    class: "MediaCrawler"
    output_model: "MediaElementData"
    output_key: "media"
    enabled: true
    language_aware: true
    language_keys:
      - transcript_keywords   # For nearby-text transcript detection
    tags: ["media", "audio", "video"]

  - id: "MovingContentCrawler"
    file: "a11y/crawler/moving_content_crawler.py"
    class: "MovingContentCrawler"
    output_model: "MovingContentData"
    output_key: "moving_content"
    enabled: true
    language_aware: false
    tags: ["animation", "video"]

  - id: "InteractiveElementCrawler"
    file: "a11y/crawler/interactive_crawler.py"
    class: "InteractiveElementCrawler"
    output_model: "InteractiveElementData"
    output_key: "interactive"
    enabled: true
    language_aware: false
    tags: ["interactive", "labels"]

  - id: "TargetSizeCrawler"
    file: "a11y/crawler/target_size_crawler.py"
    class: "TargetSizeCrawler"
    output_model: "TargetSizeData"
    output_key: "target_sizes"
    enabled: true
    language_aware: false
    tags: ["interactive", "pointer"]

  - id: "TextSpacingCrawler"
    file: "a11y/crawler/text_spacing_crawler.py"
    class: "TextSpacingCrawler"
    output_model: "TextSpacingData"
    output_key: "text_spacing"
    enabled: true
    language_aware: true
    language_keys: []         # Reads text_spacing block from lang config
    tags: ["text", "layout"]

  - id: "RenderedLayoutCrawler"
    file: "a11y/crawler/rendered_crawler.py"
    class: "RenderedLayoutCrawler"
    output_model: "PageSnapshot"
    output_key: "rendered"
    enabled: true
    language_aware: false
    tags: ["rendered", "visual", "layout"]

  # Example future crawler:
  - id: "ColorThemeCrawler"
    file: "a11y/crawler/color_theme_crawler.py"
    class: "ColorThemeCrawler"
    output_model: "ColorThemeData"
    output_key: "color_themes"
    enabled: false            # Disabled until implemented
    language_aware: false
    tags: ["color", "visual"]
```

---

## 4. Site Config (`sites/yahoo-co-jp.yml`)

Per-site overrides for audits that need site-specific configuration.

```yaml
version: "2.0"
site_id: "yahoo-co-jp"
base_url: "https://yahoo.co.jp"

# Language config to load
language: "ja"

# Override rule-level settings for this site
rule_overrides:
  "2.4.5":
    enabled: true
    # Site has a custom search widget
    extra_search_selectors:
      - "#srchtxt"
      - "[data-yjad-searchbox]"

  "3.2.6":
    enabled: true
    extra_help_selectors:
      - "a[href*='help.yahoo.co.jp']"

# Disable rules not applicable to this site
disabled_rules:
  - "3.3.8"    # No login page at this URL

# Crawler overrides
crawler_overrides:
  AsyncImageCrawler:
    # Exclude ad image paths from analysis
    excluded_src_patterns:
      - "s.yimg.jp/images/ad/"
      - "analytics.yahoo.co.jp"

# Viewport settings
viewport:
  width: 390
  height: 844
  device_scale_factor: 3

# Auth config (for post-login audits)
auth:
  type: null    # null | cookie | basic | form
```

---

## 5. Config Loader Design

### Python (`a11y/config/loader.py`)

```python
# Pseudocode — no implementation yet

class A11YConfig:
    """Central config resolver. Merges: defaults → language → site → request."""

    def __init__(self, site_id=None, lang=None, rule_overrides=None):
        self.rules = load_yaml("config/rules.config.yml")
        self.crawlers = load_yaml("config/crawlers.config.yml")
        self.lang_config = load_yaml(f"config/languages/{lang or 'en'}.yml")
        self.site_config = load_yaml(f"config/sites/{site_id}.yml") if site_id else {}
        self._merge()

    def get_keyword_list(self, key: str) -> List[str]:
        """Returns merged keyword list: lang_config[key] + site_config extras."""

    def get_selectors(self, key: str) -> List[str]:
        """Returns merged CSS selector list for the given key."""

    def get_enabled_rules(self) -> List[RuleConfig]:
        """Returns only enabled rules after applying site overrides."""

    def get_enabled_crawlers(self) -> List[CrawlerConfig]:
        """Returns only enabled crawlers needed by enabled rules."""

    def get_text_spacing_flags(self) -> TextSpacingFlags:
        """Returns CJK-aware text spacing behavior."""
```

### Node.js (`src/config/loader.js`)

```javascript
// Pseudocode — no implementation yet

class A11YConfig {
    constructor({ siteId, lang, ruleOverrides } = {}) {
        this.rules = loadYaml('config/rules.config.yml');
        this.langConfig = loadYaml(`config/languages/${lang || 'en'}.yml`);
        this.siteConfig = siteId ? loadYaml(`config/sites/${siteId}.yml`) : {};
    }

    getKeywordList(key) {
        // Returns merged array: langConfig.keyword_lists[key] + site extras
    }

    getSelectors(key) {
        // Returns merged selector array
    }

    getEnabledRules() {
        // Returns rules where enabled:true after site overrides
    }

    buildRegex(key, flags = 'i') {
        // Builds regex from keyword list with correct word boundary for lang
        // CJK: no \b, use alternation directly
        // Latin: use \b or lookahead/lookbehind
    }
}
```

---

## 6. Rule Implementation Contract

Each rule implementation reads config from the loader, not from hardcoded constants.

**Before (current):**
```javascript
const GENERIC_RE = /click here|read more|more|learn more|details|here|link/i;
```

**After (with config):**
```javascript
// Rule receives config from the service orchestrator
function check(page, config) {
    const genericPatterns = config.getKeywordList('generic_link_patterns');
    const GENERIC_RE = config.buildRegex('generic_link_patterns');
    // ... rest of check
}
```

**Python equivalent:**
```python
# Auditor constructor receives config
class LabelInNameAuditor:
    def __init__(self, config: A11YConfig):
        self.config = config

    def audit(self, elements):
        word_boundary = self.config.lang_config.get('word_boundary', 'regex')
        # Use substring match for CJK, regex \b for Latin
```

---

## 7. Adding a New Language — Step-by-Step

With this architecture, adding a new language (e.g., French) requires:

1. **Create `config/languages/fr.yml`** — Provide French keyword lists for all `language_keys` in rules.config.yml
2. **Set `word_boundary: regex`** and `writing_system: latin` (French uses standard word boundaries)
3. **Set `nlp_model: fr_core_news_sm`** if spaCy sentence tokenization is needed
4. **Verify `i18n/locales/fr.yml`** exists for rule description translations
5. **No code changes required**

---

## 8. Adding a New Rule — Step-by-Step

1. **Add entry to `config/rules.config.yml`** — WCAG ID, file path, crawlers_required, language_keys
2. **Add translations to `i18n/rules.yml`** — name, description, suggested_fix (English)
3. **Run `scripts/sync-i18n.sh`** — Propagates to locale files
4. **Implement the rule file** at the declared path
5. **Add language keyword lists to all `config/languages/*.yml`** for any `language_keys` declared
6. **No changes to service orchestrator required** — config loader discovers the new rule automatically

---

## 9. Adding a New Crawler — Step-by-Step

1. **Add entry to `config/crawlers.config.yml`** — id, file, class, output_model, output_key, language_aware
2. **Implement the crawler class** at the declared path, following the existing crawler contract:
   ```python
   async def crawl(self, page) -> List[Dict[str, Any]]:
       ...
   def save_raw_json(self, output_dir: Path) -> None:
       ...
   ```
3. **Declare `crawlers_required`** in any rules that need the new crawler's data
4. **No changes to AuditService required** — config loader resolves enabled crawlers and instantiates them

---

## 10. Tag-Based Filtering (Future)

The `tags` field on rules and crawlers enables partial audits:

```yaml
# Request: only run color-related checks
audit_tags: ["color", "visual"]

# Request: only WCAG AA
audit_tags: ["wcag-aa"]

# Request: only form checks
audit_tags: ["forms"]
```

This allows clients to request lightweight audits (e.g., "only check images") without running all 24 checks.

---

## Architecture Diagram

```
Request: { url, lang: "ja", site_id: "yahoo-co-jp" }
        │
        ▼
A11YConfig.resolve()
  ├── Load rules.config.yml       → rule registry
  ├── Load crawlers.config.yml    → crawler registry
  ├── Load languages/ja.yml       → keyword lists + selectors + text_spacing flags
  └── Load sites/yahoo-co-jp.yml → site-specific overrides + rule disables
        │
        ▼
AuditService / AccessibilityService
  ├── Instantiate enabled crawlers (from registry)
  ├── Pass config to each crawler (lang-aware selectors)
  ├── Run crawlers → typed data objects
  ├── Instantiate enabled rules (from registry)
  ├── Pass config + crawler data to each rule
  └── Return AuditReport
```

---

## Files to Create (Implementation Order)

| Order | File | Description |
|-------|------|-------------|
| 1 | `config/rules.config.yml` | Master rule registry |
| 2 | `config/crawlers.config.yml` | Master crawler registry |
| 3 | `config/languages/en.yml` | English keyword/selector defaults |
| 4 | `config/languages/ja.yml` | Japanese keyword/selector config |
| 5 | `a11y/config/loader.py` | Python config loader |
| 6 | `src/config/loader.js` | Node config loader |
| 7 | Refactor one rule (e.g. link-purpose) | Proof-of-concept migration |
| 8 | Migrate all rules | Full migration |
| 9 | `config/sites/default.yml` | Default site config |
| 10 | Add `lang=` / `site_id=` to API | Expose config to clients |

---

## Non-Goals

- This plan does not change any WCAG rule logic
- This plan does not change any crawler extraction logic
- This plan does not add new rules or crawlers
- This plan does not change the API contract
- This plan does not require a database

The entire configuration system is **file-based YAML** — no infrastructure changes needed.
