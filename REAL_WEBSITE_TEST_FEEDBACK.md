# Real Website Test Feedback

Date: 2026-04-10

This run used the live combined pipeline against 5 public websites with the full stack enabled. The crawler, normalizer, auditors, rendered-layout stage, image/OCR stage, and `ka11y-node` axe/custom-check stage all ran against real pages. Rich-backed step logs were saved for the plan and for each combined run.

## Overall Result

| Site | URL | Result Shape | Violations | Needs Review | Passes | Snapshot Warnings | Primary Artifacts |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `bbc_home` | `https://www.bbc.com/` | Heavy failure volume on a large, complex page | 415 | 939 | 3964 | 17 | `crawled_images/bbc_com_0410_2035_35bc3e73_combined/combined_report.json` |
| `govuk_home` | `https://www.gov.uk/` | Cleanest full run in this batch | 50 | 193 | 1182 | 0 | `crawled_images/gov_uk_0410_2037_2f50d7bc_combined/combined_report.json` |
| `iana_home` | `https://www.iana.org/` | Moderate issue count, especially focus and target size | 111 | 40 | 325 | 0 | `crawled_images/iana_org_0410_2038_6150b868_combined/combined_report.json` |
| `drupal_home` | `https://www.drupal.org/` | Low-count run, but confidence is reduced by extraction limitations | 7 | 12 | 80 | 4 | `crawled_images/drupal_org_0410_2038_4902e8a1_combined/combined_report.json` |
| `yale_art_home` | `https://www.art.yale.edu/` | Strong failure-heavy signal on a visually dense page | 168 | 289 | 715 | 0 | `crawled_images/art_yale_edu_0410_2039_91f79abf_combined/combined_report.json` |

## What The Live Runs Confirmed

- The universal crawler path ran successfully across all 5 websites and normalized into the existing auditors without pipeline breakage.
- Rich step logs were persisted for the runner and for each combined job:
  - Runner summary: `/tmp/ka11y_real5_results/step_logs/live_stage_runner_steps_summary.json`
  - Runner event log: `/tmp/ka11y_real5_results/step_logs/live_stage_runner_steps.jsonl`
  - Per-site combined step logs: `crawled_images/*_combined/step_logs/combined_execution_steps.jsonl`
- Each site produced saved stage summaries for:
  - `form_audit_summary`
  - `label_in_name_summary`
  - `pause_stop_hide_summary`
  - `target_size_summary`
  - `text_spacing_summary`
  - `media_audit_summary`
  - `sensory_audit_summary`
  - `image_audit_summary`
  - `rendered_layout_audit_summary`
  - `axe_core_summary`
- Snapshot warnings from frame extraction were propagated into final reports instead of being trapped only inside raw crawler artifacts.

## Site-by-Site Feedback

### 1. BBC

Artifacts:
- `crawled_images/bbc_com_0410_2035_35bc3e73_combined/combined_report.json`
- `crawled_images/bbc_com_0410_2035_35bc3e73_combined/step_logs/combined_execution_steps.jsonl`

Observed from results:
- Top fail SCs were `2.5.3` with `172`, `2.4.12` with `87`, and `2.4.11` with `85`.
- Top `needs_review` bucket was `1.4.12` with `882`, which is a strong signal that the page has many focus/text-spacing/image-derived cases that need manual review or improved precision.
- This was the largest page in the batch by combined signal volume.

Observed from Rich logs:
- Universal snapshot extracted `362` interactive elements, `250` target-size candidates, `903` text-spacing candidates, and `1458` sensory candidates.
- Image stage processed `81` assets, generated `64` OCR results, and detected `16` contrast regions.
- Rendered-layout stage contributed `203` findings.
- Axe/custom-check stage produced `4337` raw findings before merge/dedup.
- Final warnings included `8` cross-origin frames skipped and `9` frame extraction failures.

Assessment:
- Good stress test for scale and complexity.
- Strong evidence that the crawler is capturing large real-world surfaces.
- Not a clean site. It is useful as a failure-heavy benchmark and as a frame/embedded-content stress case.

### 2. GOV.UK

Artifacts:
- `crawled_images/gov_uk_0410_2037_2f50d7bc_combined/combined_report.json`
- `crawled_images/gov_uk_0410_2037_2f50d7bc_combined/step_logs/combined_execution_steps.jsonl`

Observed from results:
- Top fail SCs were `2.5.3` with `30`, `1.4.6` with `5`, and `3.3.1` with `3`.
- Top `needs_review` bucket was `1.4.12` with `179`.
- No snapshot warnings were emitted.

Observed from Rich logs:
- Universal snapshot extracted `5` form fields, `122` interactive elements, `87` target-size candidates, `209` text-spacing candidates, and `370` sensory candidates.
- Image stage processed `17` assets, produced `12` OCR results, and found `5` contrast regions.
- Rendered-layout stage contributed `7` findings.
- Axe/custom-check stage produced `1255` raw findings before merge.

Assessment:
- This was the cleanest reliable full run in the batch.
- It still surfaced real issues, but the overall signal is much healthier than BBC or Yale Art.
- Best candidate in this set for a "passes better than most" reference page.

### 3. IANA

Artifacts:
- `crawled_images/iana_org_0410_2038_6150b868_combined/combined_report.json`
- `crawled_images/iana_org_0410_2038_6150b868_combined/step_logs/combined_execution_steps.jsonl`

Observed from results:
- Top fail SCs were `2.4.12` with `24`, `2.4.11` with `21`, `1.4.3` with `21`, and `2.5.8` with `20`.
- Top `needs_review` bucket was `1.4.12` with `28`.
- Image layer was clean compared with the more media-heavy sites.

Observed from Rich logs:
- Universal snapshot extracted `1` form field, `37` interactive elements, `34` target-size candidates, `29` text-spacing candidates, and `80` sensory candidates.
- Image stage processed `1` image with `0` OCR detections and `0` contrast regions.
- Rendered-layout stage contributed `175` findings, which is a strong sign that visible state/focus appearance rules are doing most of the work here.
- Axe/custom-check stage produced `398` raw findings before merge.

Assessment:
- Cleaner than BBC and Yale Art on image/media content.
- Still not a clean accessibility pass because focus appearance, contrast, and target size issues remain active.
- Good "moderately complex but still noisy" sample.

### 4. Drupal

Artifacts:
- `crawled_images/drupal_org_0410_2038_4902e8a1_combined/combined_report.json`
- `crawled_images/drupal_org_0410_2038_4902e8a1_combined/step_logs/combined_execution_steps.jsonl`

Observed from results:
- Top fail SCs were small-count: `1.3.1` with `2`, then `1.4.3`, `1.4.6`, `1.1.1`, and `2.5.3` with `1` each.
- Top `needs_review` bucket was `1.4.12` with `5`.
- Raw totals are low, but this should not be interpreted as a clean site.

Observed from Rich logs:
- Universal snapshot extracted only `5` interactive elements and `1` target-size candidate.
- Snapshot warnings were present: `2` cross-origin frames skipped and `2` frame extraction failures.
- Rendered-layout logging showed `hover_scan failed`.
- Image stage processed `1` asset, with `1` OCR result and `1` contrast region.
- Axe/custom-check stage produced `86` raw findings before merge.

Assessment:
- This is a partial-confidence run.
- The site is useful mainly because it proves the pipeline can finish under extraction limitations and still surface warnings.
- It is not the best benchmark for comparing overall rule quality because the extracted surface was much smaller than the other sites.

### 5. Yale Art

Artifacts:
- `crawled_images/art_yale_edu_0410_2039_91f79abf_combined/combined_report.json`
- `crawled_images/art_yale_edu_0410_2039_91f79abf_combined/step_logs/combined_execution_steps.jsonl`

Observed from results:
- Top fail SCs were `2.4.12` with `55`, `2.4.11` with `54`, `2.5.8` with `21`, and `2.5.3` with `15`.
- Top `needs_review` bucket was `1.4.12` with `209`.
- This site produced a strong fail-heavy signal despite being much smaller than BBC by total element count.

Observed from Rich logs:
- The crawler explicitly revealed hidden content by clicking `2` accordion controls before extraction.
- Universal snapshot extracted `83` interactive elements, `68` target-size candidates, `225` text-spacing candidates, and `418` sensory candidates.
- Image stage processed `26` assets, produced `11` OCR results, and found `10` contrast regions.
- OCR/image audit logs flagged contrast issues on multiple captured buttons such as `Pause animations`, `Editor details`, `More Events`, and related controls.
- Rendered-layout stage contributed `203` findings.
- Axe/custom-check stage produced `900` raw findings before merge.

Assessment:
- Strong real-world failure sample.
- Good target for validating contrast, focus appearance, target size, and image/text handling.
- Better than Drupal for failure reproduction because the signal is broad and consistent across stages.

## Best / Worst In This Batch

Best clean reference:
- `https://www.gov.uk/`
- Reason: lowest reliable issue volume with zero snapshot warnings and stable coverage across the full stack.

Best failure-heavy reference:
- `https://www.bbc.com/`
- Reason: highest overall issue volume plus frame/embedded-content stress.

Best visually noisy failure sample:
- `https://www.art.yale.edu/`
- Reason: strong contrast, focus appearance, and control-size signals with useful OCR/image evidence.

Lowest-confidence sample:
- `https://www.drupal.org/`
- Reason: completed successfully, but extraction limitations and very small captured surface reduce confidence in the final totals.

## Short Conclusion

The live run supports the current `CRAWLER_ANALYSIS.md` direction:

- Universal crawl plus normalization is working on real public websites.
- Full combined runs are stable across very different page shapes.
- Rich step logging is now preserving crawler-stage and auditor-stage outputs in a developer-usable way.
- Frame-related limitations are visible in final output.
- Real pages that are relatively clean and real pages that are obviously noisy can both be distinguished from the merged results.

If a follow-up batch is needed, the next useful step is to replace the low-confidence Drupal sample with another complex public site that does not present extraction limitations, then compare the same 5-stage evidence again.
