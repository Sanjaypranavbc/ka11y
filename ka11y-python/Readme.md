# Accessbility Checker Backend API

This is an mimic of a11y of axe-core + lighthouse + visual accessbility test

## Installation
```
poetry install
```

## Rules to cover

----------------------------


## Perceivable 

- 1.1.1 Non Text Content
  - Check alt text presence 
  - if the image is functional check the alt text represent the accessible name of functionality (regex)
  - if the text is present over image it should reflect in alt text (regex, nltk)
  

- 1.2.1 Time Based Media 
  - Audio only video only (Prerecorded) (Transcript must match with description of the video or audio)


- 1.2.2 Captions (Prerecorded)
  - Have to check captions accuracy with the transcript


- 1.2.3 Audio Descriptions or Media alternative (Prerecorded)
  - Verify audio descriptions accurately describe visual content


- 1.2.4. Live captions 
  - Presence of live captions 


- 1.2.5 Audio Descriptions Prerecorded 
  - Evaluate Quality and Accuracy of Audio Descriptions 


- 2.1.1 Keyboard 
  - Check if custom interactive elements have tab index or role and if access keys are unique 
  - it should check drag drop , custom widgets and complex interractions 


- 2.2.2 Pause, Stop, Hide
  - Check all css animations and js whether the control is present for moving contents 



## Output format

------------------------------------------------


| Total Passed | Total Failed | Total Warnings |
|--------------|--------------|----------------|
| 20%          | 70%          | 10%            |

| Violations        | Suggesstion Fix | Level | Rule  | Element      |
|-------------------|-----------------|-------|-------|--------------|
| Missing Alt text  | add alt text    | A     | 1.1.1 | <img src=""> |
...



## Project Strucutre 

```
ka11y-python/
├── pyproject.toml
├── poetry.lock
├── README.md
├── .env.example
├── .gitignore
│
├── ka11y/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app entrypoint
│   ├── config.py                      # App settings via pydantic-settings
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py                  # Root API router
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── audit.py               # POST /audit, GET /audit/{id}
│   │       ├── crawl.py               # POST /crawl, GET /crawl/{id}/status
│   │       └── reports.py             # GET /reports, GET /reports/{id}
│   │
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── engine.py                  # Playwright crawler orchestrator
│   │   ├── page_worker.py             # Per-page visit logic
│   │   ├── link_extractor.py          # Extract & normalize hrefs
│   │   └── depth_limiter.py           # BFS/DFS depth control
│   │
│   ├── accessibility/
│   │   ├── __init__.py
│   │   ├── runner.py                  # Orchestrates all checkers
│   │   ├── axe_checker.py             # axe-core via Playwright injection
│   │   ├── contrast_checker.py        # Color contrast rules
│   │   ├── aria_checker.py            # ARIA roles & attributes
│   │   ├── keyboard_checker.py        # Focus/tab order checks
│   │   └── rules/
│   │       ├── __init__.py
│   │       ├── wcag_aa.py             # WCAG 2.1 AA rule definitions
│   │       └── wcag_aaa.py            # WCAG 2.1 AAA rule definitions
│   │
│   ├── metadata/
│   │   ├── __init__.py
│   │   ├── models.py                  # CrawlConfig, PageMeta, AuditMeta
│   │   ├── store.py                   # Read/write metadata JSON/DB
│   │   └── serializer.py              # Serialize crawler output
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── requests.py                # Pydantic request schemas
│   │   ├── responses.py               # Pydantic response schemas
│   │   └── domain.py                  # Internal domain models
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py                # SQLAlchemy / async engine setup
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── crawl_repo.py
│   │   │   ├── audit_repo.py
│   │   │   └── report_repo.py
│   │   └── migrations/                # Alembic migrations
│   │       └── env.py
│   │
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── worker.py                  # Celery / ARQ worker setup
│   │   ├── crawl_task.py              # Async crawl task
│   │   └── audit_task.py              # Async audit task
│   │
│   └── utils/
│       ├── __init__.py
│       ├── url.py                     # URL normalization helpers
│       ├── html.py                    # HTML parsing utilities
│       └── logger.py                  # Structured logging setup
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_crawler.py
│   │   ├── test_accessibility.py
│   │   └── test_metadata.py
│   └── integration/
│       ├── test_crawl_api.py
│       └── test_audit_api.py
│
└── scripts/
    ├── seed.py                        # Dev seed data
    └── run_audit.py                   # CLI one-shot audit runner
```