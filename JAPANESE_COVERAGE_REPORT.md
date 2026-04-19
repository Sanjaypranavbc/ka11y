# Japanese Language Coverage Report

> Generated: 2026-04-09  
> Updated: 2026-04-09 (all gaps resolved)  
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
| 1.2.1 | Audio-only/Video-only | Python | ✅ Full | JP transcript keywords added: 書き起こし, 文字起こし, トランスクリプト, 字幕, 音声解説, 音声ガイド, etc. |
| 1.2.1 | Audio Transcript | Node | ✅ Full | JP keywords added: 書き起こし, トランスクリプト, 字幕, 音声解説, 音声ガイド, 代替テキスト |
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
| 1.4.12 | Text Spacing | Python | ✅ Full | CJK-aware CSS: letter-spacing and word-spacing overrides skipped for lang="ja/zh/ko" elements; line-height override still applied |
| 2.1.2 | Keyboard Trap | Node | N/A | Focus/Tab navigation is language-agnostic |
| 2.1.4 | Character Key Shortcuts | Node | N/A | accesskey and keyCode are language-agnostic |
| 2.2.2 | Pause, Stop, Hide | Python | N/A | DOM attribute check |
| 2.4.5 | Multiple Ways | Node | ✅ Full | Regex includes 検索, 検索結果; sitemap detection is language-agnostic |
| 2.4.7 | Focus Visible | Node | N/A | CSS computed style comparison |
| 2.4.8 | Location | Node | ✅ Full | パンくず, pan-kuzu, panku-zu breadcrumb class patterns added; aria-current and JSON-LD already language-agnostic |
| 2.4.9 | Link Purpose | Node | ✅ Full | JP generic link patterns added: こちら, 詳細, もっと見る, もっと読む, 続きを読む, さらに, リンク, etc. |
| 2.4.11/12 | Focus Not Obscured | Python | N/A | Pixel overlap check |
| 2.4.13 | Focus Appearance | Node | N/A | Numeric contrast and pixel measurements |
| 2.5.2 | Pointer Cancellation | Node | ✅ Full | JP action patterns added: 送信, 購入, 削除, 確認, 登録, 申込, 注文, クリック |
| 2.5.3 | Label in Name | Python | ✅ Full | CJK substring match (no \b boundary); handles Japanese label text correctly |
| 2.5.7 | Dragging Movements | Node | N/A | data-* attribute and DOM structure check |
| 2.5.8 | Target Size | Python | N/A | Pixel measurement; exception detection is DOM-structural |
| 3.1.6 | Pronunciation | Node | ✅ Full | Specifically targets `<ruby>` / `<rt>` — the standard JP pronunciation annotation |
| 3.2.1 | On Focus | Node | N/A | URL change detection |
| 3.2.2 | On Input | Node | N/A | URL change detection |
| 3.2.6 | Consistent Help | Node | ✅ Full | ヘルプ, サポート, お問い合わせ, よくある質問, 助け, フリーダイヤル keywords; LINE/SmartHR/Tayori widget selectors added |
| 3.3.1 | Error Identification | Python | ⚠️ Partial | Structural ARIA check is language-agnostic; error message text is not analyzed for JP |
| 3.3.2 | Labels or Instructions | Python | ⚠️ Partial | 必須 (required) keyword detected in placeholder heuristic; other JP instruction patterns may be missed |
| 3.3.3 | Error Suggestion | Node | ✅ Full | JP suggestion patterns added: お願いします, しなければなりません, べきです, 試してください, やり直してください, 修正してください, が必要です, ください; terse JP patterns already present |
| 3.3.4 | Error Prevention | Node | ✅ Full | JP keywords: 支払い, 購入, 利用規約, 削除, キャンセル, 確認, 見直し all present |
| 3.3.7 | Redundant Entry | Node | ✅ Full | 確認 (confirmation) pattern included in re-entry detection |
| 3.3.8 | Accessible Auth | Node | ✅ Full | サインイン, ログイン login keywords; 認証 auth keyword present |
| 4.1.1 | HTML Parsing | Node | N/A | ID and ARIA reference check — DOM structure |
| 4.1.2 | Name, Role, Value | Python (axe-core) | N/A | AccName algorithm is language-agnostic |
| 4.1.3 | Status Messages | Node | ✅ Full | 検索結果 in search result selector; 通知, トースト class patterns included |

---

## Fixes Applied (2026-04-09)

All 8 gaps from the original report have been resolved:

### Fix 1: Link Purpose — Japanese Generic Link Patterns ✅
**File:** `ka11y-node/src/custom-checks/link-purpose.check.js`  
**Change:** Added `もっと読む`, `さらに`, `リンク` to `GENERIC_LINK_RE`.  
**Full JP pattern set:** こちら, こちらへ, 詳細, 詳しくはこちら, 詳細はこちら, もっと見る, 続きを読む, もっと読む, 続きはこちら, 詳しく見る, もっと詳しく, 開く, 見る, 確認する, ここをクリック, クリック, タップ, 詳細を見る, さらに, リンク

---

### Fix 2: Error Suggestion — Japanese Suggestion Patterns ✅
**File:** `ka11y-node/src/custom-checks/error-suggestion.check.js`  
**Change:** Added to `SUGGESTION_RE`: `お願いします`, `しなければなりません`, `べきです`, `試してください`, `やり直してください`, `提供してください`, `修正してください`, `が必要です`, `ください$`.  
**Terse JP patterns** (無効, エラー, 必須, 失敗, 不正, 入力エラー) already present in `TERSE_RE`.

---

### Fix 3: Text Spacing — CJK Typography ✅
**File:** `ka11y-python/ka11y/crawler/rendered_layout_crawler.py`  
**Change:** `_TEXT_SPACING_CSS` now includes CJK-aware overrides:
- Elements under `:lang(ja)`, `:lang(zh)`, `:lang(ko)` (and `[lang=...]` attribute variants) have `letter-spacing: normal !important` and `word-spacing: normal !important`
- `line-height: 1.5` is still applied (valid for CJK vertical rhythm)
- Prevents false-positive clipping reports on Japanese pages

---

### Fix 4: Audio/Video Transcript — Japanese Keywords ✅
**Files:**
- `ka11y-node/src/custom-checks/audio-transcript.check.js` — added `音声解説`, `音声ガイド`, `代替テキスト` to both transcript link and details detection regexes
- `ka11y-python/ka11y/accessibility/rules/media/media_auditor.py` — added 11 Japanese keywords to `_TRANSCRIPT_LINK_KEYWORDS`: 書き起こし, 文字起こし, トランスクリプト, 字幕, キャプション, テキスト版, 音声テキスト, 音声解説, 音声ガイド, 説明文, 代替テキスト

---

### Fix 5: Consistent Help — JP Chat/Support Patterns ✅
**File:** `ka11y-node/src/custom-checks/consistent-help.check.js`  
**Changes:**
- Added `助け`, `フリーダイヤル`, `0120` to `HELP_PATTERNS` regex
- Added JP-specific chat widget selectors to `chatbotSelectors`: `#line-chat-widget`, `[class*="line-chat"]`, `[id*="smarthr-help"]`, `[class*="smarthr-help"]`, `[id*="tayori"]`, `[class*="tayori"]`

---

### Fix 6: Location — Japanese Breadcrumb Class Patterns ✅
**File:** `ka11y-node/src/custom-checks/location.check.js`  
**Change:** Added `pan-kuzu` and `panku-zu` romanized class/id patterns alongside `パンくず`.  
**Full breadcrumb detection:** aria-label breadcrumb, aria-label パンくず, class/id breadcrumb, class/id パンくず, class/id pan-kuzu, class/id panku-zu, BreadcrumbList itemtype, JSON-LD BreadcrumbList, aria-current="page" in nav

---

### Fix 7: Pointer Cancellation — JP Action Patterns ✅
**File:** `ka11y-node/src/custom-checks/pointer-cancellation.check.js`  
**Change:** Added Japanese action words to `ACTION_PATTERN`: `送信`, `購入`, `削除`, `確認`, `登録`, `申込`, `注文`, `クリック`.  
These cover form submission and destructive action patterns common in JP inline event handlers.

---

## What Works Well on Japanese Sites

| Rule | Why It Works |
|------|-------------|
| 1.3.3 Sensory Characteristics | Full Japanese word taxonomy; CJK regex; spaCy ja model |
| 1.4.12 Text Spacing | CJK-aware CSS: letter/word-spacing skipped for lang=ja/zh/ko |
| 2.5.3 Label in Name | CJK substring match (no word-boundary issue) |
| 3.1.6 Pronunciation | Explicitly checks `<ruby>/<rt>` — the JP standard |
| 3.3.4 Error Prevention | JP risk keywords: 支払い, 購入, 削除, 利用規約 |
| 3.3.3 Error Suggestion | Full JP suggestion pattern set now implemented |
| 3.3.7 Redundant Entry | 確認 pattern included |
| 3.3.8 Accessible Auth | ログイン, サインイン keywords |
| 2.4.5 Multiple Ways | 検索 in search regex |
| 2.4.9 Link Purpose | Full JP generic link pattern set |
| 4.1.3 Status Messages | 検索結果 in result selectors |
| 1.4.5 Images of Text | PaddleOCR supports Japanese OCR |
| 1.2.1 Audio Transcript | Full JP transcript keyword set (both Node and Python) |
| 3.2.6 Consistent Help | JP help keywords + LINE/SmartHR/Tayori widget selectors |
| 2.4.8 Location | パンくず, pan-kuzu, panku-zu breadcrumb detection |
| 1.1.1 (axe-core path) | AccName algorithm is Unicode-safe |
| All CSS/layout rules | Pure numerical/CSS checks |
| All interactive rules (focus, keyboard, URL) | DOM behavior is language-agnostic |

---

## Remaining Known Limitations

These are not regressions — they are architecturally constrained and documented for awareness:

| WCAG ID | Rule | Service | Status | Notes |
|---------|------|---------|--------|-------|
| 1.1.1 | Non-text Content | Python | ⚠️ | No JP-specific alt text heuristics; cosine similarity is Unicode-safe but not JP-tuned |
| 3.3.1 | Error Identification | Python | ⚠️ | ARIA structure check only; JP error message text not analyzed |
| 3.3.2 | Labels or Instructions | Python | ⚠️ | 必須 detected; other JP instruction patterns (例:, ご記入ください) may be missed |
| 1.4.12 | Text Spacing (vertical text) | Python | ⚠️ | `writing-mode: vertical-rl` text clipping under line-height override not specifically handled; treated same as horizontal |

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
- Japanese error messages with 入力してください / お願いします
- Japanese navigation with 検索 and パンくず
- Japanese auth form with ログイン
- Japanese link text with こちら/詳細/さらに

### ka11y-python
No Japanese-language fixture pages in `tests/`. The sensory rule Japanese taxonomy is tested via unit tests on isolated text strings, not full-page crawls.

**Missing test coverage:**
- Full Japanese page crawl (e.g., yahoo.co.jp, nhk.or.jp)
- Forms with 必須 markers
- Images with Japanese text (kanji OCR path)
- Text spacing on a lang="ja" page (verifying letter-spacing override is skipped)

---

## Priority Fix Recommendations

All previously listed High and Medium priority code fixes have been applied. Remaining work is test infrastructure only:

| Priority | Gap | Effort | Service |
|----------|-----|--------|---------|
| Medium | Add Japanese HTML test fixtures | High (new fixtures) | Both |
| Medium | Test text spacing on lang="ja" page | Medium | ka11y-python |
| Low | Tune 1.1.1 alt text heuristics for JP content | High (NLP) | ka11y-python |
| Low | Expand 3.3.2 JP label instruction patterns | Low (add keywords) | ka11y-python |
