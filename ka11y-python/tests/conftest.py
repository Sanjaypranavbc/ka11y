"""
Shared pytest fixtures for ka11y-python test suite.
"""

import os
import tempfile

import pytest
from bs4 import BeautifulSoup

# ── Store isolation ──────────────────────────────────────────────────────────
# The run store is PostgreSQL (there is no SQLite any more). Tests that
# persist runs, assets, verdicts or telemetry need a database of their own —
# never the developer's ``ka11y`` database, whose history they would truncate.
# ``_test_database_url()`` below picks one, creates it when it does not
# exist, migrates it to head once per session, and exports it as
# DATABASE_URL before any test module imports the app. Without a reachable
# server the store-backed tests are skipped (``pg_db`` fixture) and the rest
# of the suite runs as before.
_STORE_TMP = tempfile.mkdtemp(prefix="ka11y-test-store-")
os.environ.setdefault("KA11Y_ASSET_DIR", os.path.join(_STORE_TMP, "assets"))
# Protected API routes need a signed-in OIDC user in production. The suite has
# no identity provider, so every protected dependency resolves to an anonymous
# caller instead of a 401/503. (test_auth overrides this per test.)
os.environ.setdefault("KA11Y_AUTH_DISABLED", "1")
# Never read the developer's ka11y-python/.env: it commonly holds a compose-only
# DATABASE_URL (host "postgres"), an https OIDC redirect URI (which turns on the
# http→https 308) and Arize credentials. Any of those changes which tests run
# or what they assert. (The POSTGRES_* lines are read below, on their own, to
# locate the compose database server.)
os.environ.setdefault("KA11Y_LOAD_DOTENV", "0")
# One connection per session, nothing pooled: every test runs on its own
# event loop and a pooled psycopg connection cannot be reused across loops.
os.environ.setdefault("KA11Y_DB_POOL_SIZE", "0")
# Artifact storage: keep test uploads inside the throwaway store (never the
# checkout's logs/artifacts) and skip the PDF render. The PDF is a Chromium
# job on the caller's event loop; in the suite that loop is a per-test one,
# and a browser pool left bound to it makes the next TestClient shutdown
# (browser pool teardown) wait forever. test_storage overrides per test.
os.environ.setdefault("KA11Y_ARTIFACT_DIR", os.path.join(_STORE_TMP, "artifacts"))
os.environ.setdefault("KA11Y_ARTIFACT_PDF", "0")


# ── PostgreSQL for the run store ─────────────────────────────────────────────


def _env_file_values(*names: str) -> dict:
    """POSTGRES_* from ka11y-python/.env without loading the whole file."""
    out = {}
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip() in names:
                        out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def _with_db_name(url: str, name: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{name}"))


def _candidate_urls() -> list:
    """Where a test database could live, most explicit first."""
    from urllib.parse import urlsplit, urlunsplit

    urls = []
    explicit = os.environ.get("KA11Y_TEST_DATABASE_URL", "").strip()
    if explicit:
        urls.append(explicit)
    shell = os.environ.get("DATABASE_URL", "").strip()
    if shell:
        parts = urlsplit(shell)
        # The compose URL names the "postgres" service; from the host that is 127.0.0.1.
        netloc = parts.netloc.replace("@postgres:", "@127.0.0.1:").replace("@postgres", "@127.0.0.1")
        base = urlunsplit(parts._replace(netloc=netloc))
        urls.append(_with_db_name(base, (parts.path.lstrip("/") or "ka11y") + "_test"))
    env = _env_file_values("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    if env.get("POSTGRES_USER") and env.get("POSTGRES_PASSWORD"):
        db = env.get("POSTGRES_DB") or "ka11y"
        urls.append(f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}@127.0.0.1:5432/{db}_test")
    return urls


def _ensure_database(url: str) -> bool:
    """Create the database named in *url* if the server is reachable. False when it is not."""
    import psycopg
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    name = parts.path.lstrip("/")
    admin = _with_db_name(url, "postgres").replace("postgresql+psycopg://", "postgresql://")
    try:
        with psycopg.connect(admin, connect_timeout=3, autocommit=True) as conn:
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{name}"')
        return True
    except Exception:  # noqa: BLE001
        return False


def _test_database_url() -> str:
    for url in _candidate_urls():
        if _ensure_database(url):
            return url
    return ""


TEST_DATABASE_URL = _test_database_url()
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    # Migrate once here; the app's lifespan will find nothing left to do.
    from ka11y.db.migrate import upgrade_head_sync

    upgrade_head_sync()
else:
    os.environ.pop("DATABASE_URL", None)

_RUN_TABLES = (
    "stage_timings", "finding_reviews", "audit_assets", "audit_results", "audit_fails", "audit_pages",
    "audit_logs", "crash_reports", "reports", "audit_summary", "audit_jobs",
)


def _truncate_runs() -> None:
    import psycopg

    with psycopg.connect(TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as conn:
        conn.execute("TRUNCATE " + ", ".join(_RUN_TABLES) + " CASCADE")


@pytest.fixture
def pg_db():
    """A clean run store for one test. Skips when no PostgreSQL is reachable
    (start the compose service: ``docker compose up -d postgres``)."""
    if not TEST_DATABASE_URL:
        pytest.skip("no PostgreSQL test database (docker compose up -d postgres)")
    from ka11y.store import writer

    _truncate_runs()
    yield TEST_DATABASE_URL
    writer.flush(timeout=5)


@pytest.fixture(scope="session", autouse=True)
def relax_post_rate_limit():
    """The in-process 30-POSTs-per-minute brake is shared by every TestClient
    in the session (one app object). With test_auth now running against the
    test database its ~40 sign-in POSTs left later modules' submit/review
    POSTs answered 429. The brake itself is covered by test_transport, which
    sets its own limit."""
    from ka11y.main import _RateLimitMiddleware

    saved = _RateLimitMiddleware._MAX_REQUESTS
    _RateLimitMiddleware._MAX_REQUESTS = 10_000
    yield
    _RateLimitMiddleware._MAX_REQUESTS = saved


@pytest.fixture(scope="session", autouse=True)
def fallback_bs4_parser():
    original_init = BeautifulSoup.__init__
    def patched_init(self, markup="", features=None, *args, **kwargs):
        if features == "lxml":
            try:
                original_init(self, markup, "lxml", *args, **kwargs)
            except Exception:
                original_init(self, markup, "html.parser", *args, **kwargs)
        else:
            original_init(self, markup, features, *args, **kwargs)
    BeautifulSoup.__init__ = patched_init
    yield
    BeautifulSoup.__init__ = original_init


@pytest.fixture
def tmp_output(tmp_path) -> str:
    """Isolated temporary output directory for each test."""
    return str(tmp_path)