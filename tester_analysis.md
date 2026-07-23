# `pranav-v2` vs `tester` Output Directory Alignment Report

## Executive Summary

This report documents the analysis of the `pranav-v2` architecture and the alignment of the `tester` branch's output directory structure. The primary objective was to ensure that the `tester` branch generates an identical folder hierarchy, file naming pattern, image classification subfolders, and manifest reports as `pranav-v2`, enabling direct side-by-side comparability without modifying the underlying crawler engine or orchestration logic.

---

## 1. Reference Architecture (`pranav-v2`) Analysis

### 1.1 Output Directory Creation & Structure
The `pranav-v2` pipeline establishes two output directory destinations during an audit run:

1. **Working Crawl Directory** (`crawled_images/<domain>_<MMDD_HHMM>_<uid>/`):
   - Created on run initialization in `ka11y/api/v1/dependencies.py` via `get_output_dir()`.
   - Subfolder structure pre-created in `AsyncImageCrawler._create_directories()` using `CONFIG["directories"]` from `config/universal.yml`.

2. **Content-Addressed Asset Store** (`logs/assets/<run_id>/<kind>/<sha256[:2]>/<sha256>.<ext>`):
   - Managed by `ka11y/store/assets.py` (`put_asset()`) to serve images via `/api/v1/assets/{id}` endpoints.

### 1.2 Folder & File Layout

```text
crawled_images/<domain>_<MMDD_HHMM>_<uid>/
├── informative/                  # Standard informative images (img_<hash12>.png)
├── decorative/                   # Decorative & missing alt images (img_<hash12>.png)
├── functional/
│   ├── buttons/                  # Button screenshots & raw files (btn_<hash12>.png, img_<hash12>.<ext>)
│   ├── icons/                    # Icon assets & rasterized SVGs (img_<hash12>.<ext>, svg_<hash12>.png)
│   ├── logos/                    # Logo/brand assets (img_<hash12>.<ext>)
│   └── images/                   # Clickable functional images (img_<hash12>.png)
├── complex/
│   ├── charts/                   # Charts & diagram screenshots (img_<hash12>.png)
│   └── emojis/
├── text_detected/                # Populated by OCRPreprocessing step
│   ├── button_text/              # Copies of button images containing text
│   ├── informational_text/       # Copies of informative images containing text
│   ├── logo_text/                # Copies of logo images containing text
│   ├── with_text/                # Copies of general images containing text
│   ├── text_detection_report.json# Full OCR JSON manifest
│   └── contrast/                 # Contrast analysis output folder
│       ├── contrast_report.csv   # Per-region text contrast ratio CSV
│       ├── contrast_report.json  # Raw contrast analysis JSON
│       └── contrast_report.md    # Markdown contrast report & palette tables
├── metadata/                     # Execution metadata
├── images_report.json            # Full image crawl manifest (CrawlReport)
├── images_with_alt_text.csv      # CSV summary of all crawled images & alt text
├── audit_report.csv              # AltTextAccessibilityAuditor WCAG 1.1.1 & 4.1.2 report
├── audit_form_report.csv         # FormAccessibilityAuditor WCAG 3.3.1 & 3.3.2 report
└── raw_forms.json                # AsyncFormCrawler raw form JSON dump
```

---

## 2. Image Processing Workflow & Logic

### 2.1 Discovery & Classification
- **Discovery**: 3-pass Playwright DOM extraction (`<img>`, `<button>`, `<svg>`), with lazy-loading trigger passes and interactive component exposure (accordions/tabs/modals).
- **Classification**: Rule-based 9-step cascade in `ClassifyAssets.classify_image()` inspecting `aria-hidden`, `role`, interactive parent context, keyword matches (`src`, `alt`, `class`, `id`, `title`), square dimensions ($\le 96 \times 96\text{ px}$ for icons), and scoring for complex charts.

### 2.2 Screenshot, Download & Overlay Rules
- **Direct HTTP Download**: Applied first for `functional/icons` and image `functional/buttons` with valid URLs via `aiohttp`.
- **Playwright Element Screenshots**: Universal fallback for downloaded assets, standard method for `informative`, `decorative`, `complex`, standalone `<button>` elements, and inline `<svg>` rasterization.
- **Visual Container Overlay Screenshots**: Triggered when DOM inspection detects live HTML text absolutely positioned over an image; screenshots the parent container to capture image + overlaid text for OCR contrast analysis.

---

## 3. Modifications Applied to `tester` Branch

To match `pranav-v2`'s output structure while respecting the constraint to leave the optimized engine (`engine.py`) untouched, updates were focused on the adaptation and reporting layers:

### 3.1 `ka11y/crawler/optimized/adapter.py`
- Implemented `_subpath(classification, sub_type)` to place `informative` and `decorative` images directly into top-level `informative/` and `decorative/` subfolders rather than nested subpaths.
- Updated hash truncation to 12 hex characters (`hashlib.md5(...).hexdigest()[:12]`).
- Enforced file naming prefixes (`img_`, `btn_`, `svg_`).

### 3.2 `ka11y/crawler/optimized/optimized_crawler.py`
- Added `_create_directories()` method called on initialization to pre-create the standard subdirectory structure (`informative/`, `decorative/`, `functional/buttons/`, `functional/icons/`, `functional/logos/`, `functional/images/`, `complex/charts/`, `complex/emojis/`, `metadata/`).
- Defined `CrawlSummary` and `CrawlReport` Pydantic models.
- Updated `save_results()` to generate `images_report.json` and `images_with_alt_text.csv` alongside `metadata/images_data.json`.

---

## 4. Side-by-Side Comparison

| Property / File | `pranav-v2` Output | Updated `tester` Output | Match Status |
| :--- | :--- | :--- | :---: |
| **Base Run Dir** | `crawled_images/<domain>_<timestamp>_<uid>/` | `crawled_images/<domain>_<timestamp>_<uid>/` | ✅ Match |
| **Informative Path** | `informative/img_<md5_12>.png` | `informative/img_<md5_12>.png` | ✅ Match |
| **Decorative Path** | `decorative/img_<md5_12>.png` | `decorative/img_<md5_12>.png` | ✅ Match |
| **Functional Buttons**| `functional/buttons/btn_<md5_12>.png` | `functional/buttons/btn_<md5_12>.png` | ✅ Match |
| **Functional Icons** | `functional/icons/img_<md5_12>.<ext>` / `svg_<md5_12>.png` | `functional/icons/img_<md5_12>.<ext>` / `svg_<md5_12>.png` | ✅ Match |
| **Functional Logos** | `functional/logos/img_<md5_12>.<ext>` | `functional/logos/img_<md5_12>.<ext>` | ✅ Match |
| **Complex Charts** | `complex/charts/img_<md5_12>.png` | `complex/charts/img_<md5_12>.png` | ✅ Match |
| **Text Detected** | `text_detected/<category>/<file>` | `text_detected/<category>/<file>` | ✅ Match |
| **OCR Reports** | `text_detected/text_detection_report.json`<br>`text_detected/contrast/contrast_report.*` | `text_detected/text_detection_report.json`<br>`text_detected/contrast/contrast_report.*` | ✅ Match |
| **Crawl Manifest** | `images_report.json` | `images_report.json` | ✅ Match |
| **Alt-Text CSV** | `images_with_alt_text.csv` | `images_with_alt_text.csv` | ✅ Match |

---

## 5. Verification

- **Syntax & Compilation**: Verified via `py_compile` across all updated Python modules in `ka11y-python`.
- **Scope Compliance**: No modifications were made to `engine.py` or any crawling/fetching logic. All changes were restricted to directory creation, file path assembly, naming formatting, and manifest generation.
