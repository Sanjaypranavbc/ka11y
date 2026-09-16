from __future__ import annotations

from types import SimpleNamespace

from ka11y.crawler import context_factory
from ka11y.i18n.loader import load_rules
from ka11y.utils.crawler_settings import get_localized_check_terms
from ka11y.utils.config_loader import load_config


class _FakeContext:
    def __init__(self, kwargs) -> None:
        self.kwargs = kwargs
        self.init_scripts = []

    async def add_init_script(self, script):
        self.init_scripts.append(script)


class _FakeBrowser:
    def __init__(self) -> None:
        self.calls = []

    async def new_context(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeContext(kwargs)


async def test_new_crawler_context_applies_https_default_and_installs_ssrf_guard(monkeypatch):
    browser = _FakeBrowser()
    installed = []

    async def _fake_install(context):
        installed.append(context)

    monkeypatch.setattr(context_factory, "install_ssrf_guard", _fake_install)

    context = await context_factory.new_crawler_context(browser, viewport={"width": 320, "height": 640})

    assert browser.calls[0]["ignore_https_errors"] is True
    assert browser.calls[0]["viewport"] == {"width": 320, "height": 640}
    assert installed == [context]
    # Stealth profile applied by default so pooled contexts are not served
    # bot-challenge pages (this used to exist only in the image engine).
    assert browser.calls[0]["user_agent"] == context_factory.STEALTH_UA
    assert browser.calls[0]["locale"] == context_factory.STEALTH_LOCALE
    assert browser.calls[0]["timezone_id"] == context_factory.STEALTH_TIMEZONE
    assert context.init_scripts == [context_factory.STEALTH_INIT_SCRIPT]
    assert "navigator, 'webdriver'" in context.init_scripts[0]


async def test_new_crawler_context_respects_explicit_override(monkeypatch):
    browser = _FakeBrowser()

    async def _fake_install(_context):
        return None

    monkeypatch.setattr(context_factory, "install_ssrf_guard", _fake_install)

    await context_factory.new_crawler_context(
        browser, ignore_https_errors=False, user_agent="custom-ua", locale="ja-JP",
    )

    assert browser.calls[0]["ignore_https_errors"] is False
    assert browser.calls[0]["user_agent"] == "custom-ua"
    assert browser.calls[0]["locale"] == "ja-JP"


def test_shared_config_is_loaded_by_default():
    config = load_config()

    assert config["browser"]["ignore_https_errors"] is True
    assert "ja" in config["crawler"]["language"]["cjk_langs"]


def test_shared_i18n_rules_are_loaded_by_default():
    rules = load_rules("ja")

    assert rules["1.1.1"].name == "非テキストコンテンツ"
    assert "alt" in rules["1.1.1"].suggested_fix


def test_shared_check_terms_are_loaded_from_universal_config():
    help_terms = get_localized_check_terms("consistent_help", "help_keywords")

    assert "help" in help_terms
    assert "お問い合わせ" in help_terms
