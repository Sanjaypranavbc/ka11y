+# a11y-python Execution Flow

This document details the end-to-end execution flow of the `a11y-python` accessibility audit system, from the initial API request to the final generated report.

## 1. Entry Point: API Request
The execution starts when a client sends a `POST` request to the `/api/v1/combined/` endpoint.

*   **File:** `a11y/main.py` & `a11y/api/v1/combined/routes.py`
*   **Process:**
    1.  **FastAPI Initialization:** `main.py` starts the server and applies global middleware (Rate Limiting, Security Headers, CORS).
    2.  **Request Validation:** `routes.py` receives the `CombinedRequest` payload (containing the target `url` and audit configurations).
    3.  **SSRF Guard:** The URL is validated against a blacklist of private/reserved IP ranges to prevent Server-Side Request Forgery.
    4.  **Job Creation:** A unique `job_id` is generated. A job entry is initialized in the in-memory `_jobs` store with status `pending`.
    5.  **Background Dispatch:** The actual audit is spawned as an asynchronous background task using `asyncio.create_task(_run_job(...))`.
    6.  **Immediate Response:** The API immediately returns the `job_id` to the client with an HTTP 202 (Accepted) status.

## 2. Orchestration Layer
The orchestrator manages the lifecycle of the audit job and coordinates different audit engines.

*   **File:** `a11y/api/v1/combined/runner.py`
*   **Process:**
    1.  **Environment Setup:** Creates a timestamped output directory (under `crawled_images/`) to store screenshots and JSON logs.
    2.  **Parallel Execution:** Orchestrates two primary audit branches concurrently:
        *   **axe-core (Node.js):** Calls an external Node service to run standard axe-core rules.
        *   **Python Pipeline:** Calls `_run_python_stages` to execute custom Python-based accessibility rules.
    3.  **Status Updates:** Broadcasts "stage_start" and "stage_complete" events via Server-Sent Events (SSE) so the frontend can show real-time progress.

## 3. Python Audit Pipeline
The core of `a11y-python` is a multi-stage pipeline where each stage evaluates a specific set of WCAG criteria.

*   **File:** `a11y/api/v1/combined/stages.py`
*   **Process:**
    Seven specialized stages run in parallel, each following a **Crawl → Audit → Convert** pattern:
    1.  **`image_audit`**: OCR, alt-text (1.1.1), and contrast (1.4.3, 1.4.6, 1.4.11).
    2.  **`form_audit`**: Input labels and error handling (3.3.1, 3.3.2).
    3.  **`label_in_name`**: Consistency between visible labels and accessible names (2.5.3).
    4.  **`pause_stop_hide`**: Moving, blinking, or scrolling content (2.2.2).
    5.  **`target_size`**: Adequate touch target dimensions (2.5.8).
    6.  **`text_spacing`**: Robustness against custom text spacing (1.4.12).
    7.  **`rendered_layout_audit`**: Complex rendering rules (Reflow 1.4.10, Orientation 1.3.4, Hover/Focus content 1.4.13, etc.).

## 4. The Audit Loop: Deep Dive
Each stage performs the following three steps:

### A. Crawling (Data Collection)
*   **Tools:** Playwright (Headless Chromium).
*   **Action:** Specialized crawlers (e.g., `AsyncImageCrawler`, `RenderedLayoutCrawler`) visit the page.
*   **Logic:**
    *   Trigger lazy-loading by scrolling the page.
    *   Click interactive elements (tabs, accordions) to reveal hidden content.
    *   Collect element metadata (HTML snippets, computed styles, accessible names).
    *   Capture high-resolution screenshots of specific components for visual analysis.

### B. Auditing (Rule Evaluation)
*   **Tools:** `AltTextAccessibilityAuditor`, `FormAccessibilityAuditor`, OpenCV, EasyOCR.
*   **Action:** The auditor processes the crawled data against WCAG Success Criteria.
*   **Logic:**
    *   **Vision Rules:** Use `easyocr` to detect text inside images and `opencv` to calculate contrast ratios between foreground and background pixels.
    *   **Structural Rules:** Analyze the relationship between labels and inputs, or the presence of specific ARIA attributes.
    *   **Heuristics:** Apply rich heuristics to distinguish between decorative and informative images (e.g., checking for "placeholder" in filenames).

### C. Converting (Standardization)
*   **File:** `a11y/api/v1/combined/findings.py`
*   **Action:** Transforms raw audit records into standardized "findings."
*   **Result:** A list of dictionaries containing `wcag_sc`, `severity`, `status` (pass/fail/needs_review), `reason`, `suggested_fix`, and the target `element` data.

## 5. Result Merging and Reporting
Once all branches (Node and Python) complete, the system finalizes the results.

*   **Process:**
    1.  **Deduplication:** `_merge_findings` combines Node and Python results. If both flag the same element for the same rule, the **Python finding takes precedence** because it contains richer OCR/Visual data.
    2.  **Report Generation:** `report.py` aggregates all findings, calculates a summary of totals (passes vs. violations), and attaches a detailed `contrast_report`.
    3.  **Persistence:** The final JSON report is saved to the job's output directory.
    4.  **Completion:** The job status in `_jobs` is updated to `completed`, and a `job_complete` event is broadcasted.

## 7. Pin-to-Pin Code Trace

| Sequence | Logic Component | Primary File | Key Function |
| :--- | :--- | :--- | :--- |
| **1. Entry** | Request Handler | `routes.py` | `submit_combined_audit()` |
| **2. Guard** | SSRF Protection | `routes.py` | `assert_public_url()` |
| **3. Job** | Async Dispatch | `routes.py` | `asyncio.create_task(_run_job)` |
| **4. Orchestrator** | Main Background Task | `runner.py` | `_run_job()` |
| **5. Branching** | Concurrent engines | `runner.py` | `gather(node_task, python_task)` |
| **6. Python Pipe** | Multi-stage gathering | `stages.py` | `_run_python_stages()` |
| **7. Layout Stage** | Scenario Management | `stages.py` | `_stage_rendered_layout_audit()` |
| **8. Playwright** | Scenario Execution | `rendered_layout_crawler.py` | `_run_all_scenarios()` |
| **9. Snapshots** | Viewport/CSS/JS State | `rendered_layout_crawler.py` | `_snapshot_*` |
| **10. Evaluator** | SC-Specific Logic | `evaluators/reflow.py` etc. | `evaluate()` |
| **11. Findings** | Converter Layer | `findings.py` | `_sc_to_findings()` |
| **12. Merge** | Results De-duplication | `runner.py` | `_merge_findings()` |
| **13. Finalize** | JSON Report Generation | `report.py` | `_build_report()` |
| **14. Delivery** | SSE / Polling | `routes.py` | `stream_combined_audit()` |

### Data Flow Transformation
`Payload (URL)` ➔ `Job ID` ➔ `Page Snapshots (Geometric/Image)` ➔ `Audit Records (Raw)` ➔ `Standard Findings (JSON)` ➔ `Final Consolidated Report`

---
> [!NOTE]
> For rules implemented in both layers (Axe & Python), **Python findings take precedence** in the merge logic to leverage richer CV/Layout diagnostics.
