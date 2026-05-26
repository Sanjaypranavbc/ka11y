// ─────────────────────────────────────────────────────────────────────────────
// ka11y frontend translations
// Add a new language by adding a key matching BCP-47 (e.g. "de") and filling
// every key.  Missing keys fall back to English automatically.
// ─────────────────────────────────────────────────────────────────────────────

export type Lang = "en" | "ja";

export type TranslationKey = keyof typeof translations.en;

export const translations = {
  en: {
    // ── Navigation ──────────────────────────────────────────────────────────
    "nav.dashboard":          "Dashboard",
    "nav.violations":         "Violations",
    "nav.needsReview":        "Needs Review",
    "nav.passes":             "Passes",
    "nav.imageVisualiser":    "Image Visualiser",
    "nav.wcagRules":          "WCAG Rules",
    "nav.settings":           "Settings",
    "nav.ruleEvaluator":      "Individual Rule Tester",

    // ── Sidebar ─────────────────────────────────────────────────────────────
    "sidebar.ariaLabel":      "Audit controls",
    "sidebar.navAriaLabel":   "Main navigation",
    "sidebar.closeSidebar":   "Close sidebar",
    "sidebar.tagline":        "a11y diagnostic",
    "sidebar.newAudit":       "New Audit",
    "sidebar.targetUrl":      "Target URL",
    "sidebar.urlPlaceholder": "https://example.com",
    "sidebar.maxDepth":       "Max Depth",
    "sidebar.maxPages":       "Max Pages",
    "sidebar.internalLinks":  "Internal links only",
    "sidebar.crawlNote":      "Depth 0 audits the single URL. Depth > 0 crawls same-domain links up to Max Pages.",
    "sidebar.depthHintSingle": "Single page only — raise Max Depth to crawl and score linked pages.",
    "sidebar.depthHintMulti":  "Multi-page crawl: up to {pages} same-domain pages, {depth} level(s) deep.",
    "sidebar.wcagLevel":      "WCAG Level",
    "sidebar.wcagLevelNote":  "`1.4.6 Contrast (Enhanced)` is AAA. Selecting `AA` or `A` hides higher-level findings.",
    "sidebar.runAudit":       "Run Audit",
    "sidebar.running":        "Running…",
    "sidebar.auditLanguage":  "Audit Language",
    "sidebar.footer":         "WCAG 2.1 A / AA / AAA · axe-core + Python",

    // ── Audit toggles ────────────────────────────────────────────────────────
    "toggle.ocr":             "OCR",
    "toggle.imageAudit":      "Image Audit",
    "toggle.formAudit":       "Form Audit",
    "toggle.labelInName":     "Label in Name",
    "toggle.mediaAudit":      "Media Audit",
    "toggle.captionsAudit":   "Captions Audit",
    "toggle.sensoryAudit":    "Sensory Audit",
    "toggle.pauseStop":       "Pause/Stop",
    "toggle.targetSize":      "Target Size",
    "toggle.resizeText":      "Resize Text",
    "toggle.reflow":          "Reflow",
    "toggle.textSpacing":     "Text Spacing",
    "toggle.orientation":     "Orientation",
    "toggle.hoverFocus":      "Hover/Focus",
    "toggle.focusObscured":   "Focus Obscured",
    "toggle.focusObscuredPlus": "Focus Obscured+",

    // ── Job status ───────────────────────────────────────────────────────────
    "status.pending":         "pending",
    "status.running":         "running",
    "status.completed":       "completed",
    "status.failed":          "failed",

    // ── Stage labels (sidebar compact) ────────────────────────────────────────
    "stage.axe_core":              "axe-core scan",
    "stage.image_audit":           "Image audit",
    "stage.form_audit":            "Form audit",
    "stage.label_in_name":         "Label in name",
    "stage.media_audit":           "Media audit",
    "stage.sensory_audit":         "Sensory audit",
    "stage.pause_stop_hide":       "Moving content",
    "stage.target_size":           "Target size",
    "stage.text_spacing":          "Text spacing",
    "stage.rendered_layout_audit": "Rendered layout",

    // ── Stage labels (progress panel full) ───────────────────────────────────
    "stageFull.axe_core":              "axe-core WCAG scan",
    "stageFull.image_audit":           "Image alt-text (1.1.1)",
    "stageFull.form_audit":            "Form fields (3.3.1 / 3.3.2)",
    "stageFull.label_in_name":         "Label in name (2.5.3)",
    "stageFull.media_audit":           "Media audit (1.2.1)",
    "stageFull.sensory_audit":         "Sensory characteristics (1.3.3)",
    "stageFull.pause_stop_hide":       "Moving content (2.2.2)",
    "stageFull.target_size":           "Target size (2.5.8)",
    "stageFull.text_spacing":          "Text spacing (1.4.12)",
    "stageFull.rendered_layout_audit": "Rendered layout checks",

    // ── Progress panel ───────────────────────────────────────────────────────
    "progress.title":         "Audit Progress",
    "progress.initialising":  "Initialising audit…",
    "progress.findings":      "findings",

    // ── States ───────────────────────────────────────────────────────────────
    "state.auditFailed":      "Audit Failed",
    "state.unknownError":     "An unknown error occurred.",
    "state.welcomeHint":      "Enter a URL in the sidebar and run an audit to see accessibility findings.",
    "state.warnings":         "Warnings",

    // ── Header ───────────────────────────────────────────────────────────────
    "header.openNav":         "Open navigation",
    "header.target":          "target",
    "header.toLightMode":     "Switch to light mode",
    "header.toDarkMode":      "Switch to dark mode",
    "header.light":           "Light",
    "header.dark":            "Dark",
    "header.export":          "Export",
    "header.reportLanguage":  "Report language",

    // ── Dashboard ────────────────────────────────────────────────────────────
    "dashboard.totalFindings":     "Total Findings",
    "dashboard.violations":        "Violations",
    "dashboard.needsReview":       "Needs Review",
    "dashboard.passes":            "Passes",
    "dashboard.bySeverity":        "Violations by Severity",
    "dashboard.bySource":          "Findings by Source",
    "dashboard.byPage":            "Findings by Page",
    "dashboard.pageColumn":        "Page",
    "dashboard.levelBreakdown":    "WCAG Level Breakdown",
    "dashboard.topFailing":        "Top Failing WCAG Criteria",
    "dashboard.score":             "Compliance Score",
    "dashboard.scoreColumn":       "Score",
    "dashboard.scoreHint":         "Pass rate = passes / (passes + violations); needs-review excluded.",
    "dashboard.scoreAcrossPages":  "Aggregated across {n} crawled pages",
    "dashboard.findingsColumn":    "Findings",

    // ── Page scope selector (multi-page crawls, max_depth > 0) ───────────────
    "pageScope.label":         "Page",
    "pageScope.allPages":      "All pages (aggregated)",
    "pageScope.pagesCrawled":  "{n} pages crawled",
    "pageScope.score":         "Score",
    "pageScope.findings":      "Findings",
    "pageScope.violations":    "Violations",
    "pageScope.needsReview":   "Needs review",
    "pageScope.passes":        "Passes",
    "pageScope.images":        "Images",

    // ── Table shared ─────────────────────────────────────────────────────────
    "table.severity":         "Severity",
    "table.source":           "Source",
    "table.sc":               "SC",
    "table.criterion":        "Criterion",
    "table.level":            "Level",
    "table.reason":           "Reason",
    "table.element":          "Element",
    "table.tag":              "Tag",
    "table.fix":              "Fix",
    "table.ruleId":           "Rule ID",
    "table.clear":            "Clear",
    "table.searchPlaceholder": "Search reason or HTML...",
    "table.filterSeverity":   "Filter by severity",
    "table.filterSource":     "Filter by source",
    "table.filterSC":         "Filter by WCAG success criterion",
    "table.filterLevel":      "Filter by WCAG level",
    "table.imageRef":         "Image",
    "table.imageSrc":         "Source",
    "table.imageText":        "OCR Text",

    // ── Needs Review tab manual note ────────────────────────────────────────
    "needsReview.manualNote": "These items require manual verification — automated tools could not determine pass/fail.",

    // ── Passes search placeholder ─────────────────────────────────────────────
    "passes.searchPlaceholder": "Search rule, SC, criterion, reason...",

    // ── Violations tab ───────────────────────────────────────────────────────
    "violations.showing":     "Showing {visible} of {total} violations",
    "violations.showingFiltered": "Showing {visible} of {total} violations ({all} total)",
    "violations.noMatch":     "No violations match the current filters.",
    "violations.showMore":    "Show more ({n} remaining)",

    // ── Needs Review tab ─────────────────────────────────────────────────────
    "needsReview.showing":    "Showing {visible} of {total} items",
    "needsReview.showingFiltered": "Showing {visible} of {total} items ({all} total)",
    "needsReview.noMatch":    "No manual-review items match the current filters.",
    "needsReview.showMore":   "Show more ({n} remaining)",

    // ── Passes tab ───────────────────────────────────────────────────────────
    "passes.showing":         "Showing {n} passes",
    "passes.showingFiltered": "Showing {n} passes ({all} total)",
    "passes.noMatch":         "No passes match the current filters.",
    "passes.noMatchSource":   "No passes are available for this source.",
    "passes.showMore":        "Show more ({n} remaining)",
    "passes.badge":           "{n} passes",

    // ── Settings tab ─────────────────────────────────────────────────────────
    "settings.title":         "Settings",
    "settings.display":       "Display",
    "settings.maxRows":       "Max rows per table",
    "settings.theme":         "Theme",
    "settings.colorMode":     "Color mode",
    "settings.light":         "Light",
    "settings.dark":          "Dark",
    "settings.system":        "System",
    "settings.systemNote":    "System mode follows your device preference.",

    // ── WCAG Rules tab ───────────────────────────────────────────────────────
    "wcagRules.title":        "WCAG Rules Catalogue",
    "wcagRules.loading":      "Loading WCAG rules…",
    "wcagRules.count":        "{n} of {total} rules",
    "wcagRules.langLabel":    "Language",
    "wcagRules.all":          "All",
    "wcagRules.searchPlaceholder": "Search by ID, name, or description…",
    "wcagRules.noMatch":      "No rules match your search.",
    "wcagRules.description":  "Description",
    "wcagRules.suggestedFix": "Suggested Fix",

    // ── Contrast report ──────────────────────────────────────────────────────
    "contrast.title":         "Contrast Analysis — WCAG 1.4.3 / 1.4.6",
    "contrast.regionsAnalysed":   "Regions Analysed",
    "contrast.violations":    "Contrast Violations",
    "contrast.imagesAffected": "Images Affected",
    "contrast.passRate":      "Pass Rate",
    "contrast.withViolations": "Images with Violations",
    "contrast.passingImages": "{n} image passed contrast check",
    "contrast.passingImagesPlural": "{n} images passed contrast check",
    "contrast.noImages":      "No images were analysed for contrast.",
    "contrast.failsAA":       "Fails AA",
    "contrast.failsAAA":      "Fails AAA",

    // ── Fix modal ────────────────────────────────────────────────────────────
    "modal.suggestedFix":     "Suggested Fix",
    "modal.elementDetails":   "Element Details",
    "modal.elementHtml":      "Element HTML",
    "modal.elementSelector":  "Element Selector",
    "modal.fullView":         "Full view",
    "modal.copy":             "Copy",
    "modal.copied":           "Copied to clipboard",
    "modal.copyFailed":       "Copy failed — please copy manually",
    "modal.learnMore":        "Learn more",
  },

  ja: {
    // ── Navigation ──────────────────────────────────────────────────────────
    "nav.dashboard":          "ダッシュボード",
    "nav.violations":         "違反",
    "nav.needsReview":        "要確認",
    "nav.passes":             "合格",
    "nav.imageVisualiser":    "画像ビジュアライザ",
    "nav.wcagRules":          "WCAGルール",
    "nav.settings":           "設定",
    "nav.ruleEvaluator":      "個別ルール監査",

    // ── Sidebar ─────────────────────────────────────────────────────────────
    "sidebar.ariaLabel":      "監査コントロール",
    "sidebar.navAriaLabel":   "メインナビゲーション",
    "sidebar.closeSidebar":   "サイドバーを閉じる",
    "sidebar.tagline":        "アクセシビリティ診断",
    "sidebar.newAudit":       "新規監査",
    "sidebar.targetUrl":      "対象URL",
    "sidebar.urlPlaceholder": "https://example.com",
    "sidebar.maxDepth":       "最大深度",
    "sidebar.maxPages":       "最大ページ数",
    "sidebar.internalLinks":  "同一ドメインのみ",
    "sidebar.crawlNote":      "深度0は単一URLを監査します。深度1以上は同一ドメインのリンクを最大ページ数までクロールします。",
    "sidebar.depthHintSingle": "単一ページのみ — 最大深度を上げるとリンク先ページもクロールしてスコア化します。",
    "sidebar.depthHintMulti":  "複数ページクロール：同一ドメイン最大{pages}ページ、深度{depth}レベル。",
    "sidebar.wcagLevel":      "WCAGレベル",
    "sidebar.wcagLevelNote":  "「1.4.6 コントラスト（強化）」はAAA。AAまたはAを選択すると上位レベルの検出が非表示になります。",
    "sidebar.runAudit":       "監査実行",
    "sidebar.running":        "実行中…",
    "sidebar.auditLanguage":  "監査言語",
    "sidebar.footer":         "WCAG 2.1 A / AA / AAA · axe-core + Python",

    // ── Audit toggles ────────────────────────────────────────────────────────
    "toggle.ocr":             "OCR",
    "toggle.imageAudit":      "画像監査",
    "toggle.formAudit":       "フォーム監査",
    "toggle.labelInName":     "名前内のラベル",
    "toggle.mediaAudit":      "メディア監査",
    "toggle.captionsAudit":   "字幕監査",
    "toggle.sensoryAudit":    "感覚的特徴監査",
    "toggle.pauseStop":       "一時停止/停止",
    "toggle.targetSize":      "ターゲットサイズ",
    "toggle.resizeText":      "テキストリサイズ",
    "toggle.reflow":          "リフロー",
    "toggle.textSpacing":     "テキスト間隔",
    "toggle.orientation":     "画面の向き",
    "toggle.hoverFocus":      "ホバー/フォーカス",
    "toggle.focusObscured":   "フォーカス隠蔽",
    "toggle.focusObscuredPlus": "フォーカス隠蔽+",

    // ── Job status ───────────────────────────────────────────────────────────
    "status.pending":         "待機中",
    "status.running":         "実行中",
    "status.completed":       "完了",
    "status.failed":          "失敗",

    // ── Stage labels (sidebar compact) ────────────────────────────────────────
    "stage.axe_core":              "axe-coreスキャン",
    "stage.image_audit":           "画像監査",
    "stage.form_audit":            "フォーム監査",
    "stage.label_in_name":         "名前内のラベル",
    "stage.media_audit":           "メディア監査",
    "stage.sensory_audit":         "感覚的特徴監査",
    "stage.pause_stop_hide":       "動くコンテンツ",
    "stage.target_size":           "ターゲットサイズ",
    "stage.text_spacing":          "テキスト間隔",
    "stage.rendered_layout_audit": "レンダリングレイアウト",

    // ── Stage labels (progress panel full) ───────────────────────────────────
    "stageFull.axe_core":              "axe-core WCAGスキャン",
    "stageFull.image_audit":           "画像代替テキスト (1.1.1)",
    "stageFull.form_audit":            "フォームフィールド (3.3.1 / 3.3.2)",
    "stageFull.label_in_name":         "名前内のラベル (2.5.3)",
    "stageFull.media_audit":           "メディア監査 (1.2.1)",
    "stageFull.sensory_audit":         "感覚的特徴 (1.3.3)",
    "stageFull.pause_stop_hide":       "動くコンテンツ (2.2.2)",
    "stageFull.target_size":           "ターゲットサイズ (2.5.8)",
    "stageFull.text_spacing":          "テキスト間隔 (1.4.12)",
    "stageFull.rendered_layout_audit": "レンダリングレイアウトチェック",

    // ── Progress panel ───────────────────────────────────────────────────────
    "progress.title":         "監査進捗",
    "progress.initialising":  "監査を初期化中…",
    "progress.findings":      "件の検出",

    // ── States ───────────────────────────────────────────────────────────────
    "state.auditFailed":      "監査に失敗しました",
    "state.unknownError":     "不明なエラーが発生しました。",
    "state.welcomeHint":      "サイドバーにURLを入力して監査を実行し、アクセシビリティの検出結果を確認してください。",
    "state.warnings":         "警告",

    // ── Header ───────────────────────────────────────────────────────────────
    "header.openNav":         "ナビゲーションを開く",
    "header.target":          "対象",
    "header.toLightMode":     "ライトモードに切り替え",
    "header.toDarkMode":      "ダークモードに切り替え",
    "header.light":           "ライト",
    "header.dark":            "ダーク",
    "header.export":          "エクスポート",
    "header.reportLanguage":  "レポート言語",

    // ── Dashboard ────────────────────────────────────────────────────────────
    "dashboard.totalFindings":     "総検出数",
    "dashboard.violations":        "違反",
    "dashboard.needsReview":       "要確認",
    "dashboard.passes":            "合格",
    "dashboard.bySeverity":        "重大度別違反",
    "dashboard.bySource":          "ソース別検出",
    "dashboard.byPage":            "ページ別検出",
    "dashboard.pageColumn":        "ページ",
    "dashboard.levelBreakdown":    "WCAGレベル内訳",
    "dashboard.topFailing":        "上位失敗WCAGクライテリア",
    "dashboard.score":             "準拠スコア",
    "dashboard.scoreColumn":       "スコア",
    "dashboard.scoreHint":         "合格率 = 合格 /（合格＋違反）。要確認は除外。",
    "dashboard.scoreAcrossPages":  "クロールした{n}ページ全体の集計",
    "dashboard.findingsColumn":    "検出数",

    // ── Page scope selector (multi-page crawls, max_depth > 0) ───────────────
    "pageScope.label":         "ページ",
    "pageScope.allPages":      "全ページ（集計）",
    "pageScope.pagesCrawled":  "{n}ページをクロール",
    "pageScope.score":         "スコア",
    "pageScope.findings":      "検出数",
    "pageScope.violations":    "違反",
    "pageScope.needsReview":   "要確認",
    "pageScope.passes":        "合格",
    "pageScope.images":        "画像",

    // ── Table shared ─────────────────────────────────────────────────────────
    "table.severity":         "重大度",
    "table.source":           "ソース",
    "table.sc":               "SC",
    "table.criterion":        "クライテリア",
    "table.level":            "レベル",
    "table.reason":           "理由",
    "table.element":          "要素",
    "table.tag":              "タグ",
    "table.fix":              "修正",
    "table.ruleId":           "ルールID",
    "table.clear":            "クリア",
    "table.searchPlaceholder": "理由またはHTMLを検索...",
    "table.filterSeverity":   "重大度でフィルタ",
    "table.filterSource":     "ソースでフィルタ",
    "table.filterSC":         "WCAGクライテリアでフィルタ",
    "table.filterLevel":      "WCAGレベルでフィルタ",
    "table.imageRef":         "画像",
    "table.imageSrc":         "ソース",
    "table.imageText":        "OCRテキスト",

    // ── Needs Review tab manual note ────────────────────────────────────────
    "needsReview.manualNote": "これらの項目は手動での確認が必要です — 自動ツールでは合否を判定できませんでした。",

    // ── Passes search placeholder ─────────────────────────────────────────────
    "passes.searchPlaceholder": "ルール、SC、クライテリア、理由で検索...",

    // ── Violations tab ───────────────────────────────────────────────────────
    "violations.showing":     "{total}件中{visible}件の違反を表示",
    "violations.showingFiltered": "{all}件中{visible}件の違反を表示（フィルタ済み：{total}件）",
    "violations.noMatch":     "現在のフィルタに一致する違反はありません。",
    "violations.showMore":    "さらに表示（残り{n}件）",

    // ── Needs Review tab ─────────────────────────────────────────────────────
    "needsReview.showing":    "{total}件中{visible}件の項目を表示",
    "needsReview.showingFiltered": "{all}件中{visible}件の項目を表示（フィルタ済み：{total}件）",
    "needsReview.noMatch":    "現在のフィルタに一致する要確認項目はありません。",
    "needsReview.showMore":   "さらに表示（残り{n}件）",

    // ── Passes tab ───────────────────────────────────────────────────────────
    "passes.showing":         "{n}件の合格を表示",
    "passes.showingFiltered": "{n}件の合格を表示（全{all}件）",
    "passes.noMatch":         "現在のフィルタに一致する合格はありません。",
    "passes.noMatchSource":   "このソースに利用可能な合格はありません。",
    "passes.showMore":        "さらに表示（残り{n}件）",
    "passes.badge":           "{n}件の合格",

    // ── Settings tab ─────────────────────────────────────────────────────────
    "settings.title":         "設定",
    "settings.display":       "表示",
    "settings.maxRows":       "テーブルの最大行数",
    "settings.theme":         "テーマ",
    "settings.colorMode":     "カラーモード",
    "settings.light":         "ライト",
    "settings.dark":          "ダーク",
    "settings.system":        "システム",
    "settings.systemNote":    "システムモードはデバイスの設定に従います。",

    // ── WCAG Rules tab ───────────────────────────────────────────────────────
    "wcagRules.title":        "WCAGルールカタログ",
    "wcagRules.loading":      "WCAGルールを読み込み中…",
    "wcagRules.count":        "{total}件中{n}件のルール",
    "wcagRules.langLabel":    "言語",
    "wcagRules.all":          "全て",
    "wcagRules.searchPlaceholder": "ID、名前、または説明で検索…",
    "wcagRules.noMatch":      "検索に一致するルールはありません。",
    "wcagRules.description":  "説明",
    "wcagRules.suggestedFix": "推奨修正",

    // ── Contrast report ──────────────────────────────────────────────────────
    "contrast.title":         "コントラスト分析 — WCAG 1.4.3 / 1.4.6",
    "contrast.regionsAnalysed":   "分析領域",
    "contrast.violations":    "コントラスト違反",
    "contrast.imagesAffected": "影響画像",
    "contrast.passRate":      "合格率",
    "contrast.withViolations": "違反のある画像",
    "contrast.passingImages": "{n}件の画像がコントラストチェックを合格",
    "contrast.passingImagesPlural": "{n}件の画像がコントラストチェックを合格",
    "contrast.noImages":      "コントラスト分析に使用された画像がありません。",
    "contrast.failsAA":       "AA失敗",
    "contrast.failsAAA":      "AAA失敗",

    // ── Fix modal ────────────────────────────────────────────────────────────
    "modal.suggestedFix":     "推奨修正",
    "modal.elementDetails":   "要素の詳細",
    "modal.elementHtml":      "要素HTML",
    "modal.elementSelector":  "要素セレクタ",
    "modal.fullView":         "全表示",
    "modal.copy":             "コピー",
    "modal.copied":           "クリップボードにコピーしました",
    "modal.copyFailed":       "コピーに失敗しました。手動でコピーしてください。",
    "modal.learnMore":        "詳細を見る",
  },
} as const;
