import functools
import os
import time
import weakref
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, BrowserContext, Locator, Page
from playwright.sync_api import Error as PlaywrightError

from scripts import validation_pack

# Actions that reach the page's own event handlers or read the state its scripts set up.
ACTIONS = (
    "check",
    "clear",
    "click",
    "dblclick",
    "dispatch_event",
    "drag_to",
    "evaluate",
    "fill",
    "focus",
    "hover",
    "press",
    "press_sequentially",
    "select_option",
    "set_checked",
    "set_input_files",
    "tap",
    "type",
    "uncheck",
)


NAVIGATIONS = ("go_back", "go_forward", "goto", "reload")
SAVES = "/preferences/"  # static/js/preferences.js: a person's settings, saved in the background
SAVE_WAIT_MS = 5_000
saving = weakref.WeakKeyDictionary()  # page -> preference saves not yet answered


def settle(page):
    """Wait for the page's preference saves: the next page the server renders must see them.

    Closing the help panel and then leaving the page at once could otherwise reach a server that
    has not yet stored "closed", and the panel would open again on the next page.
    """
    pending = saving.get(page)
    deadline = time.monotonic() + SAVE_WAIT_MS / 1000
    while pending and time.monotonic() < deadline:
        page.wait_for_timeout(20)


def after_page_scripts(action):
    """Act only once the current document's deferred scripts have run and its saves are answered.

    A visible element can be acted on while the page is still parsing, before app.js, controls.js
    or pagedocs.js attach their handlers on DOMContentLoaded; on a slow runner the action is then
    lost. Waiting for the document's DOMContentLoaded (immediate when already reached) closes
    that race for every test, whether it navigates by goto, link or form. A test marked
    ``before_page_scripts`` acts on a page whose scripts it holds back, on purpose.
    """

    @functools.wraps(action)
    def act(self, *args, **kwargs):
        page = self if isinstance(self, Page) else self.page
        if not ACTING_EARLY:
            page.wait_for_load_state("domcontentloaded")
        settle(page)
        result = action(self, *args, **kwargs)
        if action.__name__ == "click" and not ACTING_EARLY:
            settle_dialog(page)
        return result

    return act


# The form dialog is loading or saving, or its answer is taking the page elsewhere
# (static/js/form-dialog.js: aria-busy on #vr-form-content, data-vr-leaving on <html>).
DIALOG_IDLE = """() => !document.querySelector('#vr-form-content[aria-busy="true"]')
  && !document.documentElement.hasAttribute('data-vr-leaving')"""


def settle_dialog(page):
    """After a click, wait as a page's own navigation would be waited for: until the form dialog
    has loaded or answered, and until the page it sends the browser to has loaded."""
    try:
        page.wait_for_function(DIALOG_IDLE, timeout=15_000)
    except PlaywrightError:  # the page navigated away while waiting
        page.wait_for_load_state("domcontentloaded")


def after_saves(navigate):
    @functools.wraps(navigate)
    def go(self, *args, **kwargs):
        settle(self)
        return navigate(self, *args, **kwargs)

    return go


ACTING_EARLY = False


@pytest.fixture(autouse=True)
def before_page_scripts(request):
    global ACTING_EARLY
    ACTING_EARLY = request.node.get_closest_marker("before_page_scripts") is not None
    yield
    ACTING_EARLY = False


def watched(new_page):
    """Every new page records its preference saves in flight; E2E_CPU_THROTTLE=<rate> also slows
    its CPU like a busy CI runner (Chromium only)."""

    @functools.wraps(new_page)
    def make(self, *args, **kwargs):
        page = new_page(self, *args, **kwargs)
        pending = saving[page] = set()

        def started(request):
            if request.method == "POST" and urlsplit(request.url).path == SAVES:
                pending.add(request)

        def ended(request):
            pending.discard(request)

        page.on("request", started)
        page.on("requestfinished", ended)
        page.on("requestfailed", ended)
        if os.environ.get("E2E_CPU_THROTTLE"):
            page.context.new_cdp_session(page).send(
                "Emulation.setCPUThrottlingRate", {"rate": float(os.environ["E2E_CPU_THROTTLE"])}
            )
        return page

    return make


def pytest_configure(config):
    # Every browser action in the suite waits for the page's scripts and saves (see above).
    for cls in (Locator, Page):
        for name in ACTIONS:
            if hasattr(cls, name):
                setattr(cls, name, after_page_scripts(getattr(cls, name)))
    for name in NAVIGATIONS:
        setattr(Page, name, after_saves(getattr(Page, name)))
    for cls in (Browser, BrowserContext):
        cls.new_page = watched(cls.new_page)


def pytest_sessionstart(session):
    # The commit the tests run on goes into the JUnit file the validation pack is built from.
    validation_pack.record_checkout(session.config)


@pytest.fixture
def artifacts():
    """Directory for browser screenshots and failure pages: E2E_ARTIFACTS_DIR, or build/e2e."""
    path = Path(os.environ.get("E2E_ARTIFACTS_DIR") or "build/e2e")
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(autouse=True)
def source_static_assets(settings):
    # Django's static live-server handler resolves source paths, not hashed manifest names.
    # Production manifest delivery is independently checked by the container smoke job.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(scope="session")
def django_db_modify_db_settings():
    """The browser suite's own database: TEST_DATABASE_NAME when set, else test_<name>_browser.

    config/settings.py has already validated TEST_DATABASE_NAME (a separate test_ database), so
    sessions running at the same time with different names never share or drop each other's.
    """
    from django.conf import settings

    config = settings.DATABASES["default"]
    if not os.environ.get("TEST_DATABASE_NAME"):
        config.setdefault("TEST", {})["NAME"] = f"test_{config['NAME']}_browser"
    assert config["TEST"]["NAME"].startswith("test_")
    assert config["TEST"]["NAME"] != config["NAME"]
