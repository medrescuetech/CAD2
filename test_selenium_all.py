"""
Comprehensive headless Selenium test suite for the CAD System.
Tests all major pages, API endpoints, and user workflows.
"""
import sys
import os

# Remove CWD from sys.path so the local websocket/ package doesn't shadow
# the pip-installed websocket-client needed by selenium
_cwd = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p) != _cwd]

import json
import time
import logging
import traceback
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:5000"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
TIMEOUT = 12  # seconds

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE = "selenium_test_results.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("selenium_tests")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.errors = []          # (test_name, error_detail)
        self.console_errors = []  # browser console SEVERE entries

    def ok(self, name, detail=""):
        self.passed.append(name)
        log.info(f"  PASS  {name}" + (f" -- {detail}" if detail else ""))

    def fail(self, name, detail=""):
        self.failed.append(name)
        self.errors.append((name, detail))
        log.error(f"  FAIL  {name} -- {detail}")

    def summary(self):
        total = len(self.passed) + len(self.failed)
        log.info("=" * 60)
        log.info(f"RESULTS: {len(self.passed)} passed / {len(self.failed)} failed  (total {total})")
        if self.failed:
            log.info("-" * 60)
            log.info("FAILURES:")
            for name, detail in self.errors:
                log.info(f"  {name}: {detail}")
        if self.console_errors:
            log.info("-" * 60)
            log.info("BROWSER CONSOLE SEVERE ERRORS:")
            for entry in self.console_errors:
                log.info(f"  {entry}")
        log.info("=" * 60)
        return len(self.failed)


def make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts,
    )
    driver.set_page_load_timeout(TIMEOUT)
    driver.implicitly_wait(3)
    return driver


def wait_page_ready(driver, timeout=TIMEOUT):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def collect_console_errors(driver):
    """Return list of SEVERE browser‐console entries."""
    try:
        logs = driver.get_log("browser")
        return [e for e in logs if e.get("level") == "SEVERE"]
    except Exception:
        return []


def get_csrf_token(driver):
    """Extract a CSRF token from the page (meta tag or hidden input)."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, 'input[name="csrf_token"]')
        return el.get_attribute("value")
    except NoSuchElementException:
        pass
    try:
        el = driver.find_element(By.CSS_SELECTOR, 'meta[name="csrf-token"]')
        return el.get_attribute("content")
    except NoSuchElementException:
        return None


def fetch_json(driver, method, path, body=None):
    """Use fetch() inside the browser so cookies/session are included."""
    opts = f"method:'{method}',headers:{{'Content-Type':'application/json','X-CSRFToken':document.querySelector('meta[name=csrf-token]')?.content||''}}"
    if body is not None:
        opts += f",body:JSON.stringify({json.dumps(body)})"
    script = f"""
        var cb = arguments[arguments.length - 1];
        fetch('{path}', {{{opts}}})
          .then(r => r.text().then(t => cb(JSON.stringify({{status:r.status,body:t}}))))
          .catch(e => cb(JSON.stringify({{status:0,body:e.toString()}})));
    """
    raw = driver.execute_async_script(script)
    data = json.loads(raw)
    status = data["status"]
    try:
        body_parsed = json.loads(data["body"])
    except Exception:
        body_parsed = data["body"]
    return status, body_parsed


# ---------------------------------------------------------------------------
# Login helper
# ---------------------------------------------------------------------------
def do_login(driver, res):
    """Log in as admin. Returns True on success."""
    test = "Login"
    try:
        driver.get(f"{BASE_URL}/auth/login")
        wait_page_ready(driver)

        driver.find_element(By.ID, "username").clear()
        driver.find_element(By.ID, "username").send_keys(ADMIN_USER)
        driver.find_element(By.ID, "password").clear()
        driver.find_element(By.ID, "password").send_keys(ADMIN_PASS)
        driver.find_element(By.ID, "password").send_keys(Keys.RETURN)

        # Wait until we are redirected away from login
        WebDriverWait(driver, TIMEOUT).until(
            EC.url_changes(f"{BASE_URL}/auth/login")
        )
        wait_page_ready(driver)

        # Verify we are authenticated (not back on login page)
        if "/auth/login" in driver.current_url:
            res.fail(test, "Still on login page after submit")
            return False

        res.ok(test, f"Redirected to {driver.current_url}")
        return True
    except Exception as exc:
        res.fail(test, str(exc))
        return False


# ---------------------------------------------------------------------------
# Page‐level tests
# ---------------------------------------------------------------------------
PAGE_TESTS = [
    # (test_name, path, expected_title_fragment, required_element_css)
    ("Dashboard Page",    "/",           "Dashboard",  ".container"),
    ("Dashboard Page 2",  "/dashboard",  "Dashboard",  ".container"),
    ("Incidents Page",    "/incidents",  "Incidents",  ".container"),
    ("Units Page",        "/units",      "Units",      ".container"),
    ("Map Page",          "/map",        "Map",        "#map"),
    ("Daily Log Page",    "/daily_log",  "Daily Log",  ".container"),
    ("Monitor Page",      "/monitor",    "Monitor",    ".container"),
]


def run_page_tests(driver, res):
    for test_name, path, title_frag, css_sel in PAGE_TESTS:
        try:
            driver.get(f"{BASE_URL}{path}")
            wait_page_ready(driver)

            # Should not be redirected to login
            if "/auth/login" in driver.current_url:
                res.fail(test_name, "Redirected to login – session lost?")
                continue

            # Title check
            if title_frag and title_frag.lower() not in driver.title.lower():
                res.fail(test_name, f"Title '{driver.title}' missing '{title_frag}'")
                continue

            # Required element
            if css_sel:
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, css_sel))
                    )
                except TimeoutException:
                    res.fail(test_name, f"Element '{css_sel}' not found")
                    continue

            # Check for server-side error banner
            page_src = driver.page_source.lower()
            if "internal server error" in page_src or "500" in driver.title:
                res.fail(test_name, "Page returned 500")
                continue

            res.ok(test_name)
        except Exception as exc:
            res.fail(test_name, str(exc))

        # Collect console errors per page
        for entry in collect_console_errors(driver):
            res.console_errors.append(f"[{test_name}] {entry.get('message','')}")


# ---------------------------------------------------------------------------
# Map‐specific tests
# ---------------------------------------------------------------------------
def run_map_tests(driver, res):
    # Already on some page, navigate to map
    driver.get(f"{BASE_URL}/map")
    wait_page_ready(driver)
    time.sleep(2)  # let Leaflet initialize

    # Test: Leaflet map container rendered
    test = "Map - Leaflet Initialized"
    try:
        leaflet_container = driver.find_element(By.CSS_SELECTOR, ".leaflet-container")
        if leaflet_container:
            res.ok(test)
        else:
            res.fail(test, "No .leaflet-container found")
    except NoSuchElementException:
        res.fail(test, "No .leaflet-container element")

    # Test: Tile layer loaded (at least one tile image)
    test = "Map - Tiles Loaded"
    try:
        tiles = driver.find_elements(By.CSS_SELECTOR, ".leaflet-tile")
        if len(tiles) > 0:
            res.ok(test, f"{len(tiles)} tiles")
        else:
            res.fail(test, "No .leaflet-tile elements found")
    except Exception as exc:
        res.fail(test, str(exc))

    # Test: API /api/map/config
    test = "API - /api/map/config"
    try:
        status, body = fetch_json(driver, "GET", "/api/map/config")
        if status == 200 and isinstance(body, dict) and body.get("success"):
            res.ok(test, f"config keys: {list(body.get('config', {}).keys())}")
        else:
            res.fail(test, f"status={status} body={body}")
    except Exception as exc:
        res.fail(test, str(exc))

    # Test: API /api/map/data
    test = "API - /api/map/data"
    try:
        status, body = fetch_json(driver, "GET", "/api/map/data")
        if status == 200 and isinstance(body, dict) and body.get("success"):
            data = body.get("data", {})
            res.ok(test, f"units={len(data.get('units',[]))} incidents={len(data.get('incidents',[]))}")
        else:
            res.fail(test, f"status={status} body={body}")
    except Exception as exc:
        res.fail(test, str(exc))

    for entry in collect_console_errors(driver):
        res.console_errors.append(f"[Map] {entry.get('message','')}")


# ---------------------------------------------------------------------------
# API endpoint tests (run from browser context to keep session)
# ---------------------------------------------------------------------------
def run_api_tests(driver, res):
    # Make sure we're on a page with a valid session
    driver.get(f"{BASE_URL}/")
    wait_page_ready(driver)

    api_gets = [
        ("API - GET /api/locations",       "/api/locations"),
        ("API - GET /api/pickup-points",   "/api/pickup-points"),
        ("API - GET /api/ampds/categories", "/api/ampds/categories"),
    ]
    for test_name, path in api_gets:
        try:
            status, body = fetch_json(driver, "GET", path)
            if status == 200:
                res.ok(test_name, f"status={status}")
            elif status == 403:
                res.ok(test_name, f"status=403 (permission denied – expected for some roles)")
            else:
                res.fail(test_name, f"status={status} body={json.dumps(body)[:200]}")
        except Exception as exc:
            res.fail(test_name, str(exc))

    # POST /api/client-logs (CSRF exempt)
    test = "API - POST /api/client-logs (CSRF exempt)"
    try:
        status, body = fetch_json(driver, "POST", "/api/client-logs", {
            "level": "info",
            "message": "Selenium test log entry",
            "source": "selenium",
        })
        if status == 200:
            res.ok(test)
        else:
            res.fail(test, f"status={status} body={body}")
    except Exception as exc:
        res.fail(test, str(exc))

    # GET /api/websocket/status
    test = "API - GET /api/websocket/status"
    try:
        status, body = fetch_json(driver, "GET", "/api/websocket/status")
        if status == 200:
            res.ok(test, f"ws_available={body.get('websocket_available')}")
        else:
            res.fail(test, f"status={status}")
    except Exception as exc:
        res.fail(test, str(exc))

    for entry in collect_console_errors(driver):
        res.console_errors.append(f"[API] {entry.get('message','')}")


# ---------------------------------------------------------------------------
# Incident creation workflow
# ---------------------------------------------------------------------------
def run_incident_workflow(driver, res):
    test = "Incident Create Page Load"
    try:
        driver.get(f"{BASE_URL}/incidents/new")
        wait_page_ready(driver)
        if "/auth/login" in driver.current_url:
            res.fail(test, "Redirected to login")
            return
        if "500" in driver.title.lower() or "error" in driver.title.lower():
            res.fail(test, f"Error page: {driver.title}")
            return
        res.ok(test)
    except Exception as exc:
        res.fail(test, str(exc))
        return

    for entry in collect_console_errors(driver):
        res.console_errors.append(f"[Incident Create] {entry.get('message','')}")


# ---------------------------------------------------------------------------
# Unit detail page
# ---------------------------------------------------------------------------
def run_unit_detail_test(driver, res):
    test = "Unit Detail Page"
    try:
        driver.get(f"{BASE_URL}/unit/1")
        wait_page_ready(driver)
        if "/auth/login" in driver.current_url:
            res.fail(test, "Redirected to login")
            return
        page_src = driver.page_source.lower()
        if "not found" in page_src or "404" in driver.title:
            res.fail(test, "Unit 1 not found (404)")
            return
        if "internal server error" in page_src:
            res.fail(test, "500 error on unit detail")
            return
        res.ok(test)
    except Exception as exc:
        res.fail(test, str(exc))

    for entry in collect_console_errors(driver):
        res.console_errors.append(f"[Unit Detail] {entry.get('message','')}")


# ---------------------------------------------------------------------------
# JS globals sanity (run on dashboard)
# ---------------------------------------------------------------------------
def run_js_globals_tests(driver, res):
    driver.get(f"{BASE_URL}/")
    wait_page_ready(driver)
    time.sleep(1)

    checks = {
        "JS - jQuery loaded":    "typeof jQuery !== 'undefined'",
        "JS - Bootstrap loaded": "typeof bootstrap !== 'undefined'",
    }
    for test_name, expr in checks.items():
        try:
            val = driver.execute_script(f"return ({expr})")
            if val:
                res.ok(test_name)
            else:
                res.fail(test_name, f"Expression returned falsy")
        except Exception as exc:
            res.fail(test_name, str(exc))

    # Check for any unhandled JS errors captured by error handler
    test = "JS - No Unhandled Errors"
    try:
        errs = driver.execute_script("return window._cad_js_errors || []")
        if errs:
            res.fail(test, f"{len(errs)} JS errors: {errs[:3]}")
        else:
            res.ok(test)
    except Exception:
        res.ok(test, "no error tracking found (ok)")

    for entry in collect_console_errors(driver):
        res.console_errors.append(f"[JS Globals] {entry.get('message','')}")


# ---------------------------------------------------------------------------
# Auth edge cases
# ---------------------------------------------------------------------------
def run_auth_tests(driver, res):
    # Test: unauthenticated redirect
    test = "Auth - Unauthenticated Redirect"
    try:
        # Open a new incognito-like session
        driver2 = make_driver()
        driver2.get(f"{BASE_URL}/incidents")
        wait_page_ready(driver2)
        if "/auth/login" in driver2.current_url or "login" in driver2.title.lower():
            res.ok(test, "Correctly redirected to login")
        else:
            res.fail(test, f"Not redirected: {driver2.current_url}")
        driver2.quit()
    except Exception as exc:
        res.fail(test, str(exc))

    # Test: bad login
    test = "Auth - Bad Credentials"
    try:
        driver2 = make_driver()
        driver2.get(f"{BASE_URL}/auth/login")
        wait_page_ready(driver2)
        driver2.find_element(By.ID, "username").send_keys("wronguser")
        driver2.find_element(By.ID, "password").send_keys("wrongpass")
        driver2.find_element(By.ID, "password").send_keys(Keys.RETURN)
        time.sleep(2)
        wait_page_ready(driver2)
        # Should still be on login page
        if "/auth/login" in driver2.current_url or "login" in driver2.title.lower():
            res.ok(test, "Stayed on login page")
        else:
            res.fail(test, f"Unexpected redirect: {driver2.current_url}")
        driver2.quit()
    except Exception as exc:
        res.fail(test, str(exc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("=" * 60)
    log.info(f"CAD System Selenium Test Suite  --  {datetime.now().isoformat()}")
    log.info(f"Target: {BASE_URL}")
    log.info("=" * 60)

    res = TestResult()
    driver = None

    try:
        driver = make_driver()

        # 1. Login
        if not do_login(driver, res):
            log.error("Cannot continue without login. Aborting.")
            res.summary()
            return res

        # 2. Page tests
        run_page_tests(driver, res)

        # 3. Map tests
        run_map_tests(driver, res)

        # 4. API tests
        run_api_tests(driver, res)

        # 5. Incident workflow
        run_incident_workflow(driver, res)

        # 6. Unit detail
        run_unit_detail_test(driver, res)

        # 7. JS globals
        run_js_globals_tests(driver, res)

        # 8. Auth edge cases (uses separate drivers)
        run_auth_tests(driver, res)

    except Exception as exc:
        log.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    failures = res.summary()
    return res


if __name__ == "__main__":
    result = main()
    sys.exit(len(result.failed) if result else 1)
