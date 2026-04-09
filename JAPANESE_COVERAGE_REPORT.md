# Japanese Language Coverage Report

> Generated: 2026-04-09  
> Scope: ka11y-node (24 custom checks + axe-core) and ka11y-python (18 WCAG rules)  
> Target: Japanese websites (lang="ja", CJK character content, Japanese UI patterns)

This report documents how well each rule handles Japanese-language websites — where keyword matching, text analysis, or language-specific patterns are needed.

---

## Coverage Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ Full | Japanese keywords/patterns implemented and tested |
| ⚠️ Partial | Some Japanese support but gaps exist |
| ❌ None | No Japanese-specific handling; may produce false negatives or false positives |
| N/A | Rule is language-agnostic (DOM structure, CSS, numeric values) |

---

## Summary Table

| WCAG ID | Rule Name | Service | Japanese Coverage | Notes |
|---------|-----------|---------|------------------|-------|
| 1.1.1 | Non-text Content | Python | ⚠️ Partial | OCR supports CJK; alt text matching uses cosine similarity which handles Unicode but no JP-specific heuristics |
| 1.1.1 | Non-text Content | Node (axe-core) | ✅ Full | axe-core uses AccName algorithm — language-agnostic |
| 1.2.1 | Audio-only/Video-only | Python | ⚠️ Partial | transcript keyword list is English-only; nearby_text not parsed for 書き起こし |
| 1.2.1 | Audio Transcript | Node | ⚠️ Partial | No 書き起こし or トランスクリプト keywords in transcript detection |
| 1.3.2 | Meaningful Sequence | Node | N/A | Pure CSS/DOM structure check |
| 1.3.3 | Sensory Characteristics | Python | ✅ Full | Full Japanese word taxonomy implemented; CJK regex path; spaCy ja_core_news_sm |
| 1.3.4 | Orientation | Python | N/A | CSS/viewport check, no text analysis |
| 1.3.4 | Orientation | Node | N/A | CSS/viewport check, no text analysis |
| 1.4.1 | Use of Color | Node | N/A | Pure CSS computed style comparison |
| 1.4.4 | Resize Text | Python | N/A | Rendered pixel measurement |
| 1.4.5 | Images of Text | Python | ✅ Full | PaddleOCR supports Japanese text detection in images |
| 1.4.5 | Images of Text | Node | N/A | Heuristic scoring on src/class/alt — language-agnostic |
| 1.4.10 | Reflow | Python | N/A | Pixel overflow check at 320px |
| 1.4.11 | Non-text Contrast | Python | N/A | Color contrast is numeric |
| 1.4.12 | Text Spacing | Python | ❌ None | CJK text has different spacing norms (no letter-spacing, tate-chu-yoko); WCAG spacing values may not apply to vertical JP text |
| 2.1.2 | Keyboard Trap | Node | N/A | Focus/Tab navigation is language-agnostic |
| 2.1.4 | Character Key Shortcuts | Node | N/A | accesskey and keyCode are language-agnostic |
| 2.2.2 | Pause, Stop, Hide | Python | N/A | DOM attribute check |
| 2.4.5 | Multiple Ways | Node | ✅ Full | Regex includes 検索, 検索結果; sitemap detection is language-agnostic |
| 2.4.7 | Focus Visible | Node | N/A | CSS computed style comparison |
| 2.4.8 | Location | Node | ⚠️ Partial | breadcrumb/aria-current detection is language-agnostic; JP `パンくず` class pattern not detected |
| 2.4.9 | Link Purpose | Node | ⚠️ Partial | Generic link patterns are English-only (click here, read more); JP equivalents (こちら, 詳細, もっと見る) not in regex |
| 2.4.11/12 | Focus Not Obscured | Python | N/A | Pixel overlap check |
| 2.4.13 | Focus Appearance | Node | N/A | Numeric contrast and pixel measurements |
| 2.5.2 | Pointer Cancellation | Node | ⚠️ Partial | CJK regex present for handler content but action patterns (クリック, 送信) incomplete |
| 2.5.3 | Label in Name | Python | ✅ Full | CJK substring match (no \b boundary); handles Japanese label text correctly |
| 2.5.7 | Dragging Movements | Node | N/A | data-* attribute and DOM structure check |
| 2.5.8 | Target Size | Python | N/A | Pixel measurement; exception detection is DOM-structural |
| 3.1.6 | Pronunciation | Node | ✅ Full | Specifically targets `<ruby>` / `<rt>` — the standard JP pronunciation annotation |
| 3.2.1 | On Focus | Node | N/A | URL change detection |
| 3.2.2 | On Input | Node | N/A | URL change detection |
| 3.2.6 | Consistent Help | Node | ⚠️ Partial | ヘルプ keyword present; 助け not confirmed; JP chat widget selectors (e.g. LINE chat) not included |
| 3.3.1 | Error Identification | Python | ⚠️ Partial | Structural ARIA check is language-agnostic; error message text is not analyzed for JP |
| 3.3.2 | Labels or Instructions | Python | ⚠️ Partial | 必須 (required) keyword detected in placeholder heuristic; other JP instruction patterns may be missed |
| 3.3.3 | Error Suggestion | Node | ❌ None | Suggestion patterns are English-only (must, should, please, try, enter); JP equivalents (入力してください, 確認, やり直し) not included |
| 3.3.4 | Error Prevention | Node | ✅ Full | JP keywords: 支払い, 購入, 利用規約, 削除, キャンセル, 確認, 見直し all present |
| 3.3.7 | Redundant Entry | Node | ✅ Full | 確認 (confirmation) pattern included in re-entry detection |
| 3.3.8 | Accessible Auth | Node | ✅ Full | サインイン, ログイン login keywords; 認証 auth keyword present |
| 4.1.1 | HTML Parsing | Node | N/A | ID and ARIA reference check — DOM structure |
| 4.1.2 | Name, Role, Value | Python (axe-core) | N/A | AccName algorithm is language-agnostic |
| 4.1.3 | Status Messages | Node | ✅ Full | 検索結果 in search result selector; 通知, トースト class patterns included |

---

## Detailed Gap Analysis

### Gap 1: Link Purpose — Missing Japanese Generic Link Patterns
**Rule:** 2.4.9 custom-link-purpose (ka11y-node)  
**WCAG Level:** AAA

**Missing Japanese equivalents:**

| English (implemented) | Japanese (missing) | Romaji |
|----------------------|-------------------|--------|
| click here | こちら, ここをクリック | kochira, koko wo kurikku |
| read more | 続きを読む, もっと読む | tsuzuki wo yomu |
| more | もっと見る, さらに | motto miru |
| learn more | 詳しくはこちら, 詳細 | kuwashiku wa kochira |
| details | 詳細, 詳しく | shousai |
| here | こちら | kochira |
| link | リンク | rinku |

**Impact:** Japanese sites using こちら or 詳細 as link text will not be flagged.

---

### Gap 2: Error Suggestion — No Japanese Suggestion Patterns
**Rule:** 3.3.3 custom-error-suggestion (ka11y-node)  
**WCAG Level:** AA

**Missing Japanese suggestion keywords:**

| English (implemented) | Japanese (missing) |
|----------------------|-------------------|
| please | ください, お願いします |
| must | 必須, しなければなりません |
| should | べきです |
| try | 試してください |
| enter | 入力してください, 入力 |
| example | 例, 例えば |
| provide | 提供してください |
| correct | 修正してください |

**Impact:** Japanese error messages will appear to have no correction guidance even when they do.

---

### Gap 3: Text Spacing — CJK Typography Not Considered
**Rule:** 1.4.12 Text Spacing (ka11y-python)  
**WCAG Level:** AA

**Issues specific to Japanese:**
- WCAG 1.4.12 specifies `letter-spacing: 0.12em` — in Japanese typography, `letter-spacing` is not conventionally used; JP fonts have built-in spacing
- Vertical Japanese text (`writing-mode: vertical-rl`) uses `word-spacing` differently — character spacing in vertical text uses `letter-spacing` on the block axis
- `word-spacing: 0.16em` doesn't apply to CJK since Japanese has no spaces between words
- Setting WCAG spacing overrides on Japanese text may introduce false positives (text that clips under EN spacing won't clip under JP rendering, and vice versa)

**Current behavior:** The same spacing override is applied to all text regardless of `lang` attribute — this can cause false positive clipping reports on Japanese content.

---

### Gap 4: Audio/Video Transcript — Japanese Keywords Not in Detection
**Rule:** 1.2.1 audio-transcript (ka11y-node) + MediaAuditor (ka11y-python)  
**WCAG Level:** A

**Missing Japanese transcript keywords for nearby-link detection:**

| English (partial) | Japanese (missing) |
|------------------|-------------------|
| transcript | 書き起こし, トランスクリプト, 文字起こし |
| caption | 字幕 |
| description | 説明, 音声解説 |
| audio description | 音声ガイド |

**Impact:** Japanese audio elements with Japanese-labeled transcript links will not be recognized as having text alternatives.

---

### Gap 5: Consistent Help — JP Chat/Support Patterns
**Rule:** 3.2.6 custom-consistent-help (ka11y-node)  
**WCAG Level:** A

**Missing Japanese help mechanism patterns:**
- LINE Official Account chat widget (common in JP)
- SmartHR support widget
- Japanese help link text: サポート (support), 問い合わせ (inquiry), お問合せ, よくある質問 (FAQ = よくある質問 / FAQ)
- Japanese toll-free patterns: フリーダイヤル, 0120-XXX-XXX

**Partially implemented:** ヘルプ keyword present.

---

### Gap 6: Location — Japanese Breadcrumb Class Patterns
**Rule:** 2.4.8 custom-location (ka11y-node)  
**WCAG Level:** AA

**Missing patterns:**
- Japanese breadcrumb CSS class: `パンくず`, `pan-kuzu`, `panku-zu`
- JSON-LD BreadcrumbList already detected (language-agnostic ✅)
- `aria-current="page"` already detected (language-agnostic ✅)

---

## What Works Well on Japanese Sites

| Rule | Why It Works |
|------|-------------|
| 1.3.3 Sensory Characteristics | Full Japanese word taxonomy; CJK regex; spaCy ja model |
| 2.5.3 Label in Name | CJK substring match (no word-boundary issue) |
| 3.1.6 Pronunciation | Explicitly checks `<ruby>/<rt>` — the JP standard |
| 3.3.4 Error Prevention | JP risk keywords: 支払い, 購入, 削除, 利用規約 |
| 3.3.7 Redundant Entry | 確認 pattern included |
| 3.3.8 Accessible Auth | ログイン, サインイン keywords |
| 2.4.5 Multiple Ways | 検索 in search regex |
| 4.1.3 Status Messages | 検索結果 in result selectors |
| 1.4.5 Images of Text | PaddleOCR supports Japanese OCR |
| 1.1.1 (axe-core path) | AccName algorithm is Unicode-safe |
| All CSS/layout rules | Pure numerical/CSS checks |
| All interactive rules (focus, keyboard, URL) | DOM behavior is language-agnostic |

---

## i18n Infrastructure

### ka11y-node i18n
- **`i18n/rules.yml`** — Canonical English WCAG rule catalog (name, description, suggested_fix, level, severity)
- **`i18n/locales/ja.yml`** — Full Japanese translations for all rule names, descriptions, and suggested fixes
- **`i18n/locales/de.yml`** — German locale
- **Usage:** Rules guide and API response messages are locale-aware

**Japanese locale coverage in rules.yml:**
All 23+ WCAG rules have Japanese translations in `locales/ja.yml`. The locale file is complete — no missing entries.

### ka11y-python i18n
- **`i18n/rules.yml`** — Identical canonical English catalog (shared structure)
- **`i18n/locales/ja.yml`** — Japanese translations (same structure as node)
- **`sensory_auditor.py`** — Embedded Japanese sensory word taxonomy
- **`label_in_name_auditor.py`** — CJK-aware substring matching

---

## Test Coverage for Japanese

### ka11y-node
No dedicated Japanese-language HTML fixture files exist in `tests/`. All existing test fixtures use English content. Japanese coverage is tested only through inline regex patterns in unit tests.

**Missing test coverage:**
- Japanese form with 必須 labels
- Japanese error messages with 入力してください
- Japanese navigation with 検索 and パンくず
- Japanese auth form with ログイン
- Japanese link text with こちら/詳細

### ka11y-python
No Japanese-language fixture pages in `tests/`. The sensory rule Japanese taxonomy is tested via unit tests on isolated text strings, not full-page crawls.

**Missing test coverage:**
- Full Japanese page crawl (e.g., yahoo.co.jp, nhk.or.jp)
- Forms with 必須 markers
- Images with Japanese text (kanji OCR path)

---

## Priority Fix Recommendations

| Priority | Gap | Effort | Service |
|----------|-----|--------|---------|
| High | 3.3.3 Error Suggestion — add JP suggestion patterns | Low (add to regex) | ka11y-node |
| High | 2.4.9 Link Purpose — add JP generic link patterns | Low (add to regex) | ka11y-node |
| High | 1.2.1 Audio Transcript — add JP transcript keywords | Low (add to keyword list) | Both |
| Medium | 3.2.6 Consistent Help — add JP help/support keywords | Low (add to regex) | ka11y-node |
| Medium | 2.4.8 Location — add パンくず breadcrumb class | Low (add to selector) | ka11y-node |
| Medium | 1.4.12 Text Spacing — skip letter/word-spacing override for CJK | Medium (lang detection) | ka11y-python |
| Low | Add Japanese HTML test fixtures | High (new fixtures) | Both |
| Low | 2.5.2 Pointer Cancellation — complete JP action patterns | Low (add to regex) | ka11y-node |
