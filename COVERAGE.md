# ka11y WCAG Coverage Metadata Report / ka11y WCAGカバレッジメタデータ報告書

This report is based on direct code inspection of `ka11y-node` and `ka11y-python`, plus the validated proof run completed on 2026-03-25. It is intentionally bilingual at the metadata and explanation level so both the engineering team and non-specialists can read it. English WCAG criterion names are kept canonical; the plain-language explanation is shown in English and Japanese.

## Validation Snapshot / 検証スナップショット

| Item / 項目 | Value / 値 |
| --- | --- |
| Report date / レポート日 | 2026-03-25 |
| Repositories inspected / 対象リポジトリ | `ka11y-node`, `ka11y-python` |
| Proof artifacts / 証拠ファイル | `ka11y-node/logs/evidence-report.md`, `ka11y-node/logs/evidence-report.json`, `ka11y-node/junit.xml`, `ka11y-python/tests/report/ka11y_test_report.html` |
| Node validation / Node検証 | `164` tests passed |
| Python validation / Python検証 | `515` tests passed |
| Feedback loop result / フィードバックループ結果 | `0` bugs after `1` evidence-loop attempt |
| Counting rule / 集計ルール | Only WCAG 2.2 success criteria are counted. axe `best-practice` rules are tracked separately and are not included in the `87` SC total. / WCAG 2.2の達成基準のみを集計対象とし、axeの`best-practice`は87件の合計には含めません。 |

## Coverage Totals / カバレッジ総計

| Level / レベル | Total SC / 総達成基準 | Node | Python | Overlap / 重複 | Combined covered / 合計カバー | Missing / 未対応 | Coverage / カバー率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 31 | 24 | 6 | 5 | 25 | 6 | 81% |
| AA | 26 | 17 | 10 | 5 | 22 | 4 | 85% |
| AAA | 30 | 3 | 1 | 0 | 4 | 26 | 13% |
| Total | 87 | 44 | 17 | 10 | 51 | 36 | 59% |

## Confidence Totals / 信頼度総計

Confidence here means "how reliable the current automation is for this rule", not "how important the WCAG rule is". / ここでの信頼度は「その規則に対する自動検出の確からしさ」を示し、「WCAG上の重要度」ではありません。

| Level / レベル | High / 高 | Medium / 中 | Low / 低 | Covered / カバー済み |
| --- | ---: | ---: | ---: | ---: |
| A | 13 | 9 | 3 | 25 |
| AA | 11 | 10 | 1 | 22 |
| AAA | 2 | 2 | 0 | 4 |
| Total | 26 | 21 | 4 | 51 |

## Confidence Legend / 信頼度の意味

| Rating / 評価 | Meaning / 意味 |
| --- | --- |
| High / 高 | Deterministic or strongly repeatable automation with evidence-backed pass/fail behaviour. / 証拠付きで再現しやすく、合否が安定している自動検出。 |
| Medium / 中 | Useful automation, but partly heuristic or dependent on runtime/context. / 有用だが、ヒューリスティックや画面文脈に一部依存する自動検出。 |
| Low / 低 | Proxy coverage or manual-review-leaning automation. / 代理指標に近く、手動確認寄りの自動検出。 |
| `-` | Not covered today. / 現時点では未対応。 |

## Technique Legend / 技術凡例

| Code | Meaning / 意味 |
| --- | --- |
| `N-AXE` | Node-side `axe-core` or DOM rule mapping. / Node側の`axe-core`またはDOMマッピング。 |
| `N-CUSTOM` | Node-side custom pluggable rule. / Node側の独自プラグイン型ルール。 |
| `P-OCR` | Python OCR or image-analysis pipeline. / Python側のOCRや画像解析パイプライン。 |
| `P-RENDER` | Python real-browser rendered layout, focus, hover, or interaction evaluator. / Python側の実ブラウザ描画・フォーカス・ホバー・操作評価。 |
| `P-CRAWL` | Python crawler or multi-page collector. / Python側のクローラや複数ページ収集。 |
| `NEXT-MEDIA` | Add caption, transcript, audio-description, or flash-analysis pipeline. / 字幕、書き起こし、音声解説、点滅解析の仕組みを追加。 |
| `NEXT-CROSS` | Add cross-page diff for repeated navigation/components. / ページ間差分で繰り返しナビや部品の一貫性を比較。 |
| `NEXT-FLOW` | Add stateful multi-step form or authentication replay. / 状態付きの複数ステップフォームや認証の再実行を追加。 |
| `NEXT-NLP` | Add text, language, or instruction parser. / テキスト、言語、説明文の解析器を追加。 |
| `NEXT-MOTION` | Add gesture, animation, or device-motion instrumentation. / ジェスチャー、アニメーション、端末モーションの計測を追加。 |
| `NEXT-TIME` | Add timeout, interruption, and session-state instrumentation. / タイムアウト、中断、セッション状態の計測を追加。 |
| `NEXT-LAYOUT` | Add stronger outline, geometry, or presentation heuristics. / 見出し構造、幾何情報、表示制御の強化ヒューリスティックを追加。 |
| `NEXT-INTERACT` | Add deeper keyboard, pointer, or input-path simulation. / キーボード、ポインター、入力経路のより深いシミュレーションを追加。 |

## Missing Rules Summary / 未対応規則の要約

| Level / レベル | Missing count / 未対応数 | Missing SC / 未対応達成基準 | Main next techniques / 主な次手法 |
| --- | ---: | --- | --- |
| A | 6 | `1.2.3`, `1.3.3`, `2.3.1`, `2.5.1`, `2.5.4`, `3.3.7` | `NEXT-MEDIA`, `NEXT-NLP`, `NEXT-MOTION`, `NEXT-FLOW` |
| AA | 4 | `1.2.4`, `1.2.5`, `3.2.3`, `3.2.4` | `NEXT-MEDIA`, `NEXT-CROSS` |
| AAA | 26 | `1.2.6`, `1.2.7`, `1.2.8`, `1.2.9`, `1.3.6`, `1.4.7`, `1.4.8`, `1.4.9`, `2.1.3`, `2.2.3`, `2.2.4`, `2.2.5`, `2.2.6`, `2.3.2`, `2.3.3`, `2.4.10`, `2.5.5`, `2.5.6`, `3.1.3`, `3.1.4`, `3.1.5`, `3.1.6`, `3.2.5`, `3.3.5`, `3.3.6`, `3.3.9` | `NEXT-MEDIA`, `NEXT-NLP`, `NEXT-TIME`, `NEXT-MOTION`, `NEXT-LAYOUT`, `NEXT-INTERACT`, `NEXT-FLOW`, `P-CRAWL` upgrade |

## High-Value Next Coverage Candidates / 次に実装価値が高い候補

| Priority / 優先度 | SC | Why it matters / 重要性 | Technique to add / 追加手法 | Expected confidence / 期待信頼度 |
| --- | --- | --- | --- | --- |
| P1 | `3.3.7` Redundant Entry | High user pain in long forms and checkout flows. / 長いフォームや購入導線で負担が大きい。 | `NEXT-FLOW` with multi-step memory graph | Medium to High |
| P2 | `3.2.3` Consistent Navigation | Very suitable for crawl-based automation across repeated templates. / 繰り返しテンプレート間の自動比較に向く。 | `NEXT-CROSS` navigation diff | High |
| P3 | `3.2.4` Consistent Identification | Same component consistency is measurable across pages. / 同一部品の一貫性はページ横断で計測しやすい。 | `NEXT-CROSS` component diff | High |
| P4 | `2.5.1` Pointer Gestures | Mobile/touch usability gap with clear runtime signals. / モバイル操作で価値が高く、実行時シグナルも取りやすい。 | `NEXT-MOTION` gesture listener inspection | Medium |
| P5 | `2.5.4` Motion Actuation | Device-motion API use can be detected directly. / 端末モーションAPIの使用検知が可能。 | `NEXT-MOTION` device API instrumentation | Medium |
| P6 | `2.5.5` Target Size | Current `2.5.8` crawler can be upgraded to AAA threshold. / 既存の`2.5.8`クローラをAAA基準へ拡張しやすい。 | `P-CRAWL` upgrade to `44x44` threshold | High |
| P7 | `1.4.9` Images of Text (No Exception) | Existing OCR stack already provides a base. / 既存OCR基盤を流用しやすい。 | `P-OCR` + stricter exception classifier | Medium |
| P8 | `2.2.6` Timeouts | Real-world data-loss issue with clear product impact. / 実務上のデータ損失リスクが高い。 | `NEXT-TIME` timeout detector | Medium |
| P9 | `2.4.10` Section Headings | Strong document-outline heuristic can cover many cases. / 見出し構造ヒューリスティックで多くのケースを拾える。 | `NEXT-LAYOUT` outline analyzer | Medium |
| P10 | `3.3.5` Help | Current help consistency logic can be extended. / 既存ヘルプ整合性ロジックを拡張できる。 | `NEXT-FLOW` or `NEXT-CROSS` help locator | Medium |
| P11 | `3.3.9` Accessible Authentication (Enhanced) | Builds naturally on the current `3.3.8` rule. / 現在の`3.3.8`検査を自然に拡張できる。 | `NEXT-FLOW` auth pattern extension | Medium |
| P12 | `1.2.3` and `1.2.5` media alternatives | One media pipeline can unlock several missing SCs. / 一つのメディア解析基盤で複数SCを増やせる。 | `NEXT-MEDIA` transcript and audio-description analysis | Medium |

## Complete Rule Inventory / 完全な規則一覧

### Level A

| SC | Criterion / 達成基準 | Lv | Plain meaning / やさしい説明 | Current implementation / 現在の実装 | Confidence / 信頼度 | Evidence or next technique / 根拠または次の手法 |
| --- | --- | --- | --- | --- | --- | --- |
| 1.1.1 | Non-text Content | A | Images, icons, and charts need text alternatives. / 画像やアイコンや図表には代替テキストが必要。 | Both | High | `N-AXE` + `P-OCR` |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | A | Pre-recorded audio-only or video-only media needs an equivalent alternative. / 録音音声のみ・録画映像のみのコンテンツには同等の代替手段が必要。 | Node | Medium | `N-AXE` |
| 1.2.2 | Captions (Prerecorded) | A | Pre-recorded video with sound needs captions. / 音声付きの録画動画には字幕が必要。 | Node | High | `N-AXE` |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | A | Pre-recorded video needs audio description or a full text alternative. / 録画動画には音声解説または完全な代替テキストが必要。 | Missing | - | `NEXT-MEDIA` |
| 1.3.1 | Info and Relationships | A | Headings, labels, and tables must be coded so assistive tech can understand them. / 見出し、ラベル、表の構造は支援技術が理解できるように実装する必要。 | Node | High | `N-AXE` |
| 1.3.2 | Meaningful Sequence | A | Reading order must still make sense when the page is read linearly. / ページを順番に読んでも意味が通る並びである必要。 | Node | Medium | `N-AXE` |
| 1.3.3 | Sensory Characteristics | A | Instructions must not depend only on shape, size, color, or position. / 説明を色、形、位置だけに頼ってはいけない。 | Missing | - | `NEXT-NLP` |
| 1.4.1 | Use of Color | A | Color alone must not carry the message. / 情報伝達を色だけに頼ってはいけない。 | Node | Medium | `N-AXE` |
| 1.4.2 | Audio Control | A | Auto-playing sound must be stoppable or controllable. / 自動再生音声は停止または音量調整できる必要。 | Node | Medium | `N-AXE` |
| 2.1.1 | Keyboard | A | All functionality must work with a keyboard. / すべての操作はキーボードで使える必要。 | Node | High | `N-AXE` |
| 2.1.2 | No Keyboard Trap | A | Keyboard users must be able to move focus away. / キーボード操作でフォーカスから抜け出せる必要。 | Node | Medium | `N-AXE` |
| 2.1.4 | Character Key Shortcuts | A | Single-key shortcuts need disable, remap, or focus-only behaviour. / 単一文字ショートカットは無効化、変更、またはフォーカス時限定が必要。 | Node | Medium | `N-CUSTOM` |
| 2.2.1 | Timing Adjustable | A | Users need enough time or a way to extend it. / 制限時間は延長や停止などで調整できる必要。 | Node | Low | `N-AXE` |
| 2.2.2 | Pause, Stop, Hide | A | Moving or auto-updating content must be pausable or stoppable. / 動く、点滅する、自動更新する内容は停止や非表示にできる必要。 | Both | High | `N-AXE` + `P-RENDER` |
| 2.3.1 | Three Flashes or Below Threshold | A | Content must not flash in a seizure-risk pattern. / 発作リスクのある点滅を避ける必要。 | Missing | - | `NEXT-MEDIA` |
| 2.4.1 | Bypass Blocks | A | Users need a way to skip repeated blocks. / 繰り返し部分を飛ばす手段が必要。 | Node | High | `N-AXE` |
| 2.4.2 | Page Titled | A | Each page needs a clear title. / 各ページには分かりやすいタイトルが必要。 | Node | High | `N-AXE` |
| 2.4.3 | Focus Order | A | Keyboard focus should move in a sensible order. / キーボードのフォーカス順は自然である必要。 | Node | Low | `N-AXE` |
| 2.4.4 | Link Purpose (In Context) | A | Link purpose should be clear from its text or nearby context. / リンクの目的が文脈から分かる必要。 | Node | High | `N-AXE` |
| 2.5.1 | Pointer Gestures | A | Complex gestures need a simple pointer alternative. / 複雑なジェスチャーには単純な代替操作が必要。 | Missing | - | `NEXT-MOTION` |
| 2.5.2 | Pointer Cancellation | A | Pointer actions should not trigger unexpectedly on the down event. / ポインター操作は押した瞬間に確定しないなど誤操作防止が必要。 | Node | Low | `N-AXE` |
| 2.5.3 | Label in Name | A | Visible label text should also exist in the accessible name. / 画面に見えるラベルは支援技術向けの名前にも含まれる必要。 | Both | High | `N-AXE` + `P-RENDER` |
| 2.5.4 | Motion Actuation | A | Motion-based actions need an alternative and an off switch. / 端末の動きで行う操作には代替手段と無効化が必要。 | Missing | - | `NEXT-MOTION` |
| 3.1.1 | Language of Page | A | The main page language must be declared. / ページの主言語を宣言する必要。 | Node | High | `N-AXE` |
| 3.2.1 | On Focus | A | Focusing an element should not unexpectedly change context. / フォーカスしただけで予期しない画面変化を起こしてはいけない。 | Node | Medium | `N-AXE` |
| 3.2.2 | On Input | A | Changing a field should not unexpectedly submit or navigate. / 入力変更だけで予期しない送信や遷移を起こしてはいけない。 | Node | Medium | `N-AXE` |
| 3.3.1 | Error Identification | A | Input errors must be identified clearly. / 入力エラーは明確に示す必要。 | Python | High | `P-CRAWL` |
| 3.3.2 | Labels or Instructions | A | Controls need labels or instructions before use. / 入力欄や操作には事前にラベルや説明が必要。 | Both | High | `N-AXE` + `P-CRAWL` |
| 3.3.7 | Redundant Entry | A | Users should not have to re-enter the same data in one process. / 同じ手続き内で同じ情報を繰り返し入力させない。 | Missing | - | `NEXT-FLOW` |
| 4.1.1 | Parsing | A | Markup should not break because of duplicate IDs or invalid structure. / 重複IDや壊れた構造でマークアップが破綻してはいけない。 | Node | Medium | `N-CUSTOM` |
| 4.1.2 | Name, Role, Value | A | Custom controls need correct name, role, state, and value. / カスタムUIには正しい名前、役割、状態、値が必要。 | Both | High | `N-AXE` + `P-RENDER` |

### Level AA

| SC | Criterion / 達成基準 | Lv | Plain meaning / やさしい説明 | Current implementation / 現在の実装 | Confidence / 信頼度 | Evidence or next technique / 根拠または次の手法 |
| --- | --- | --- | --- | --- | --- | --- |
| 1.2.4 | Captions (Live) | AA | Live audio or video needs captions. / ライブ配信の音声には字幕が必要。 | Missing | - | `NEXT-MEDIA` |
| 1.2.5 | Audio Description (Prerecorded) | AA | Recorded video needs audio description for important visuals. / 録画動画の重要な視覚情報には音声解説が必要。 | Missing | - | `NEXT-MEDIA` |
| 1.3.4 | Orientation | AA | Content should work in portrait and landscape unless essential. / 必須でない限り縦向きと横向きの両方で使える必要。 | Both | High | `N-AXE` + `P-RENDER` |
| 1.3.5 | Identify Input Purpose | AA | Common personal-data fields should expose machine-readable purpose. / 氏名や住所などの一般的な入力欄は目的を機械可読で示す必要。 | Node | High | `N-AXE` |
| 1.4.3 | Contrast (Minimum) | AA | Text contrast must reach the minimum readability ratio. / 文字コントラストは最低基準を満たす必要。 | Both | High | `N-AXE` + `P-OCR` |
| 1.4.4 | Resize Text | AA | Text should stay usable when enlarged to 200 percent. / 文字を200パーセント拡大しても使える必要。 | Both | High | `N-AXE` + `P-RENDER` |
| 1.4.5 | Images of Text | AA | Use real text instead of text baked into images where possible. / 可能な限り画像化文字ではなく本物のテキストを使う。 | Python | Medium | `P-OCR` |
| 1.4.10 | Reflow | AA | Content should work without two-dimensional scrolling at small viewport or zoom. / 小さい画面や拡大時に縦横両方向スクロールへ依存しない必要。 | Python | High | `P-RENDER` |
| 1.4.11 | Non-text Contrast | AA | UI parts and graphics need enough contrast against surrounding colors. / UI部品や図形は周囲に対して十分なコントラストが必要。 | Python | Low | `P-OCR` |
| 1.4.12 | Text Spacing | AA | Pages should remain usable when line, letter, and word spacing increase. / 行間や文字間を広げても壊れず使える必要。 | Both | High | `N-AXE` + `P-RENDER` |
| 1.4.13 | Content on Hover or Focus | AA | Hover or focus popups must be dismissible and stable. / ホバーやフォーカスで出る内容は閉じられ、安定して表示される必要。 | Python | High | `P-RENDER` |
| 2.4.5 | Multiple Ways | AA | More than one way should exist to find a page. / ページへ到達する手段は複数あることが望ましい。 | Node | Medium | `N-AXE` |
| 2.4.6 | Headings and Labels | AA | Headings and labels should describe their purpose clearly. / 見出しやラベルは内容を分かりやすく示す必要。 | Node | High | `N-AXE` |
| 2.4.7 | Focus Visible | AA | The keyboard focus indicator must be visible. / キーボードフォーカスは見える必要。 | Node | Medium | `N-AXE` |
| 2.4.11 | Focus Not Obscured (Minimum) | AA | Focused items should not be fully hidden behind overlays. / フォーカス要素は重なり物で完全に隠れてはいけない。 | Python | High | `P-RENDER` |
| 2.4.13 | Focus Appearance | AA | Focus indicator size and contrast must be strong enough. / フォーカス表示は十分な大きさとコントラストが必要。 | Node | Medium | `N-AXE` |
| 2.5.7 | Dragging Movements | AA | Drag operations need a simpler non-drag alternative. / ドラッグ操作にはドラッグ不要の代替手段が必要。 | Node | Medium | `N-CUSTOM` |
| 2.5.8 | Target Size (Minimum) | AA | Tap and click targets need minimum size or safe spacing. / タップ対象は最小サイズまたは十分な間隔が必要。 | Both | High | `N-AXE` + `P-CRAWL` |
| 3.1.2 | Language of Parts | AA | Passages in another language should be marked with that language. / 異なる言語の部分はその言語を明示する必要。 | Node | High | `N-AXE` |
| 3.2.3 | Consistent Navigation | AA | Repeated navigation should stay in a consistent order. / 繰り返し出るナビゲーションは一貫した順序である必要。 | Missing | - | `NEXT-CROSS` |
| 3.2.4 | Consistent Identification | AA | The same component should be identified consistently across pages. / 同じ機能の部品は一貫した名前や見せ方にする必要。 | Missing | - | `NEXT-CROSS` |
| 3.2.6 | Consistent Help | AA | Repeated help mechanisms should appear consistently. / ヘルプ手段はページ間で一貫して見つけられる必要。 | Node | Medium | `N-CUSTOM` |
| 3.3.3 | Error Suggestion | AA | When possible, tell users how to fix an error. / 可能ならエラーの直し方を示す必要。 | Node | Medium | `N-AXE` |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | AA | Important submissions need review, confirmation, or reversal. / 重要な送信は確認、見直し、取り消しが必要。 | Node | Medium | `N-AXE` |
| 3.3.8 | Accessible Authentication (Minimum) | AA | Login should not depend only on hard memory or cognitive tests. / 認証が過度な記憶や認知負荷だけに依存してはいけない。 | Node | Medium | `N-CUSTOM` |
| 4.1.3 | Status Messages | AA | Important status updates must reach assistive tech without stealing focus. / 状態メッセージはフォーカス移動なしで支援技術に伝わる必要。 | Node | Medium | `N-AXE` |

### Level AAA

| SC | Criterion / 達成基準 | Lv | Plain meaning / やさしい説明 | Current implementation / 現在の実装 | Confidence / 信頼度 | Evidence or next technique / 根拠または次の手法 |
| --- | --- | --- | --- | --- | --- | --- |
| 1.2.6 | Sign Language (Prerecorded) | AAA | Recorded video should provide sign language for spoken content. / 録画動画の音声内容には手話の提供が望ましい。 | Missing | - | `NEXT-MEDIA` |
| 1.2.7 | Extended Audio Description (Prerecorded) | AAA | Recorded video should offer extended audio description when needed. / 必要に応じて拡張音声解説を提供する必要。 | Missing | - | `NEXT-MEDIA` |
| 1.2.8 | Media Alternative (Prerecorded) | AAA | Recorded media should have a full text alternative. / 録画メディアには完全な代替テキストが必要。 | Missing | - | `NEXT-MEDIA` |
| 1.2.9 | Audio-only (Live) | AAA | Live audio-only content should have a text alternative. / ライブ音声のみコンテンツには代替テキストが必要。 | Missing | - | `NEXT-MEDIA` |
| 1.3.6 | Identify Purpose | AAA | More UI elements should expose programmatic purpose. / より多くのUI要素で目的を機械可読に示す必要。 | Missing | - | `NEXT-NLP` |
| 1.4.6 | Contrast (Enhanced) | AAA | Text needs higher-than-AA contrast. / 文字はAAより高いコントラストが必要。 | Node | High | `N-AXE` |
| 1.4.7 | Low or No Background Audio | AAA | Background audio should be absent or very low behind speech. / 音声の背後にあるBGMは無いか非常に小さい必要。 | Missing | - | `NEXT-MEDIA` |
| 1.4.8 | Visual Presentation | AAA | Users should have strong control over text presentation. / テキスト表示に対する利用者の調整余地が大きい必要。 | Missing | - | `NEXT-LAYOUT` |
| 1.4.9 | Images of Text (No Exception) | AAA | Avoid images of text except where truly essential. / 本当に必要な場合を除き文字画像を避ける必要。 | Missing | - | `P-OCR` + stricter exception classifier |
| 2.1.3 | Keyboard (No Exception) | AAA | Everything must work by keyboard with no exceptions. / 例外なくすべての機能がキーボードで使える必要。 | Missing | - | `NEXT-INTERACT` |
| 2.2.3 | No Timing | AAA | Tasks should not depend on time limits. / 作業が時間制限に依存しないことが望ましい。 | Missing | - | `NEXT-TIME` |
| 2.2.4 | Interruptions | AAA | Interruptions should be postponable or suppressible. / 中断は延期または抑制できる必要。 | Missing | - | `NEXT-TIME` |
| 2.2.5 | Re-authenticating | AAA | Re-authentication should not cause data loss. / 再認証で入力内容を失わない必要。 | Missing | - | `NEXT-TIME` |
| 2.2.6 | Timeouts | AAA | Users should be warned about data-loss timeouts. / データ消失につながるタイムアウトは事前警告が必要。 | Missing | - | `NEXT-TIME` |
| 2.3.2 | Three Flashes | AAA | Content should avoid any unsafe flashing. / 危険な点滅を避ける必要。 | Missing | - | `NEXT-MEDIA` |
| 2.3.3 | Animation from Interactions | AAA | Motion triggered by interaction should be disableable. / 操作に伴うアニメーションは無効化できる必要。 | Missing | - | `NEXT-MOTION` |
| 2.4.8 | Location | AAA | Users should know where they are within the site structure. / サイト内で現在地が分かる必要。 | Node | Medium | `N-AXE` |
| 2.4.9 | Link Purpose (Link Only) | AAA | Link text alone should make the purpose clear. / リンク単体の文言だけで目的が分かる必要。 | Node | Medium | `N-AXE` |
| 2.4.10 | Section Headings | AAA | Sections should use helpful headings. / 各セクションには役立つ見出しが必要。 | Missing | - | `NEXT-LAYOUT` |
| 2.4.12 | Focus Not Obscured (Enhanced) | AAA | Focused items should not be obscured at all. / フォーカス要素は少しも隠れてはいけない。 | Python | High | `P-RENDER` |
| 2.5.5 | Target Size | AAA | Targets should use the larger AAA minimum size. / 操作対象はAAAのより大きな最小サイズが必要。 | Missing | - | `P-CRAWL` upgrade to `44x44` threshold |
| 2.5.6 | Concurrent Input Mechanisms | AAA | Different input methods should remain available together. / 異なる入力方法を同時に使える必要。 | Missing | - | `NEXT-INTERACT` |
| 3.1.3 | Unusual Words | AAA | Uncommon words should be explained. / 珍しい語句には説明が必要。 | Missing | - | `NEXT-NLP` |
| 3.1.4 | Abbreviations | AAA | Abbreviations should be explained. / 略語には説明が必要。 | Missing | - | `NEXT-NLP` |
| 3.1.5 | Reading Level | AAA | Content should be readable at lower reading complexity or have support. / 内容は低い読解難度で読めるか補助が必要。 | Missing | - | `NEXT-NLP` |
| 3.1.6 | Pronunciation | AAA | When pronunciation affects meaning, it should be provided. / 発音で意味が変わる場合は発音情報が必要。 | Missing | - | `NEXT-NLP` |
| 3.2.5 | Change on Request | AAA | Context changes should happen only when requested. / 画面変化は利用者の要求時だけ起こす必要。 | Missing | - | `NEXT-INTERACT` |
| 3.3.5 | Help | AAA | Context-sensitive help should be available for complex tasks. / 複雑な作業には状況に応じたヘルプが必要。 | Missing | - | `NEXT-FLOW` |
| 3.3.6 | Error Prevention (All) | AAA | More workflows should prevent irreversible mistakes. / より広い操作で取り返しのつかないミスを防ぐ必要。 | Missing | - | `NEXT-FLOW` |
| 3.3.9 | Accessible Authentication (Enhanced) | AAA | Authentication should avoid cognitive barriers more strongly. / 認証は認知的負荷をさらに強く避ける必要。 | Missing | - | `NEXT-FLOW` |

## Interpretation Notes / 読み方メモ

- `Both` means the rule is emitted by both `ka11y-node` and `ka11y-python`. `Node` or `Python` means only that stack currently emits the SC. `Missing` means neither stack currently produces that SC in the flattened result set.
- `best-practice` axe rules are valuable, but they are not WCAG success criteria. They were kept out of the `87`-SC coverage percentage to avoid inflating the compliance number.
- The current gap pattern is clear: ka11y is already strong on Level A and AA structure, contrast, focus, and form basics, but still thin on AAA content-heavy rules, media alternatives, and cross-page workflow rules.
- The most efficient path to grow coverage is not "one rule at a time". It is to add a few reusable technique families: `NEXT-MEDIA`, `NEXT-CROSS`, `NEXT-FLOW`, `NEXT-MOTION`, and `NEXT-TIME`. Each of those unlocks multiple missing SCs.
- Node custom rules are already pluggable through file-based discovery, so future coverage expansion should add three things together: the new rule file, the WCAG metadata entry, and one proof scenario in the evidence loop.

