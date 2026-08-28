import os
import sys
import time
import logging
import subprocess
import unittest
import requests
import argparse
from datetime import datetime

# Add Selenium imports for browser testing
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'logs', 'test_incident_system.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('test_incident_system')

# Default credentials
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"

# JavaScript console logger
def log_js_errors(driver):
    try:
        logs = driver.get_log('browser')
        for log_entry in logs:
            if log_entry['level'] == 'SEVERE':
                logger.error(f"JavaScript Error: {log_entry['message']}")
            else:
                logger.info(f"Browser Log: {log_entry['message']}")
    except Exception as e:
        logger.warning(f"Could not get browser logs: {str(e)}")

# Helper to take screenshots
def take_screenshot(driver, name):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
            
        screenshot_path = os.path.join(logs_dir, f"{name}_{timestamp}.png")
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot saved to {screenshot_path}")
    except Exception as e:
        logger.error(f"Failed to take screenshot: {str(e)}")

class ServerManager:
    def __init__(self, app_path=None):
        self.process = None
        self.app_path = app_path or os.path.dirname(os.path.abspath(__file__))
        self.url = 'http://127.0.0.1:5000'
        self.log_file = None

    def start_server(self):
        logger.info("Starting CAD System server...")
        try:
            # Make sure logs directory exists
            logs_dir = os.path.join(self.app_path, 'logs')
            if not os.path.exists(logs_dir):
                os.makedirs(logs_dir)
                
            # Open log file
            self.log_file = open(os.path.join(logs_dir, 'test_server.log'), 'w')
            
            # Use python app.py to start the server
            self.process = subprocess.Popen(
                [sys.executable, 'app.py'],
                cwd=self.app_path,
                stdout=self.log_file,
                stderr=subprocess.STDOUT
            )
            
            # Wait for server to be ready
            server_ready = False
            max_retries = 10
            retries = 0
            
            while not server_ready and retries < max_retries:
                try:
                    # Just check if server responds, ignore status code
                    response = requests.get(self.url + '/login')
                    if response.status_code in [200, 302, 401]:
                        server_ready = True
                        logger.info(f"Server is ready at {self.url}")
                    else:
                        logger.info(f"Server returned status code {response.status_code}, waiting...")
                except requests.exceptions.ConnectionError:
                    logger.info(f"Server not ready yet, waiting... (Attempt {retries+1}/{max_retries})")
                    
                if not server_ready:
                    retries += 1
                    time.sleep(2)
            
            if not server_ready:
                logger.error("Server failed to start after multiple attempts")
                self.stop_server()
                return False
                
            logger.info(f"Server process started with PID {self.process.pid}")
            return True
        except Exception as e:
            logger.error(f"Failed to start server: {str(e)}")
            return False

    def stop_server(self):
        if self.process:
            logger.info("Stopping CAD System server...")
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
                logger.info("Server stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping server: {str(e)}")
                try:
                    self.process.kill()
                    logger.info("Server forcefully killed")
                except Exception as e2:
                    logger.error(f"Failed to kill server: {str(e2)}")
        
        # Close log file
        if self.log_file:
            self.log_file.close()

class TestIncidentSystemRequests(unittest.TestCase):
    """Test incident system using HTTP requests - headless by default"""
    @classmethod
    def setUpClass(cls):
        # Start server if not already running
        cls.start_server = False
        try:
            response = requests.get('http://127.0.0.1:5000/login', timeout=5)
            if response.status_code in [200, 302, 401]:
                logger.info("Server already running, skipping server start")
            else:
                cls.start_server = True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            logger.info("Server not detected, will start a new instance")
            cls.start_server = True
            
        if cls.start_server:
            cls.server = ServerManager()
            if not cls.server.start_server():
                raise Exception("Server failed to start")
        else:
            # Server already running, create server object without starting
            cls.server = ServerManager()
            cls.server.process = None  # No process to manage
            
        # Set up session with login
        cls.session = requests.Session()
        if not cls.login_session():
            logger.error("Authentication failed during test setup")
            # Continue anyway - some tests might not need authentication
    
    @classmethod
    def tearDownClass(cls):
        # Stop the server
        if cls.start_server and hasattr(cls, 'server'):
            cls.server.stop_server()
    
    @classmethod
    def login_session(cls):
        """Log in to the server and establish a session"""
        try:
            login_url = f"{cls.server.url}/login"
            logger.info(f"Attempting to log in at {login_url}")
            response = cls.session.get(login_url)
            
            if response.status_code != 200:
                logger.error(f"Login failed, status code: {response.status_code}, URL: {login_url}")
                return False
                
            # Extract CSRF token if present
            csrf_token = None
            if 'csrf_token' in response.text:
                import re
                match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
                if match:
                    csrf_token = match.group(1)
                    logger.info(f"Found CSRF token: {csrf_token[:10]}...")
            
            # Prepare login data
            login_data = {
                'username': DEFAULT_USERNAME,
                'password': DEFAULT_PASSWORD
            }
            
            if csrf_token:
                login_data['csrf_token'] = csrf_token
            
            # Submit login
            logger.info(f"Submitting login with credentials: {DEFAULT_USERNAME} / {'*' * len(DEFAULT_PASSWORD)}")
            response = cls.session.post(login_url, data=login_data, allow_redirects=True)
            
            # Check if login was successful
            if response.status_code != 200 and response.status_code != 302:
                logger.error(f"Login form submission failed, status code: {response.status_code}")
                return False
                
            if 'dashboard' in response.url or 'home' in response.url or 'incidents' in response.url:
                logger.info(f"Login successful (redirected to {response.url})")
                return True
            elif response.status_code == 200 and 'login' not in response.url:
                logger.info("Login appears successful (status 200, not on login page)")
                return True
            else:
                logger.error(f"Login failed, status code: {response.status_code}, URL: {response.url}")
                return False
        except Exception as e:
            logger.error(f"Error during login: {str(e)}")
            return False
    
    def test_01_incident_routes(self):
        """Test that the incident routes respond correctly"""
        try:
            # Test incidents list page
            response = self.session.get(f"{self.server.url}/incidents")
            self.assertEqual(response.status_code, 200, "Incidents page should return 200 status code")
            logger.info("Incidents page returned 200 status code")
            
            # Test new incident page
            response = self.session.get(f"{self.server.url}/incident/new")
            self.assertEqual(response.status_code, 200, "New incident page should return 200 status code")
            logger.info("New incident page returned 200 status code")
            
            # Test incidents API
            response = self.session.get(f"{self.server.url}/api/incidents")
            self.assertEqual(response.status_code, 200, "Incidents API should return 200 status code")
            logger.info("Incidents API returned 200 status code")
            
            logger.info("All incident routes tests passed")
        except Exception as e:
            logger.error(f"Error in test_01_incident_routes: {str(e)}")
            raise
    
    def test_02_javascript_files(self):
        """Test that required JavaScript files load correctly"""
        try:
            # Test that alerts.js loads
            response = self.session.get(f"{self.server.url}/static/js/alerts.js")
            self.assertEqual(response.status_code, 200, "alerts.js should load correctly")
            logger.info("alerts.js loaded successfully")
            
            # Check the content of alerts.js to ensure it has a showAlert function
            self.assertIn('function showAlert', response.text, "alerts.js should contain showAlert function")
            logger.info("alerts.js contains showAlert function")
            
            # Test that incident_manager.js loads
            response = self.session.get(f"{self.server.url}/static/js/incident_manager.js")
            self.assertEqual(response.status_code, 200, "incident_manager.js should load correctly")
            logger.info("incident_manager.js loaded successfully")
            
            logger.info("All JavaScript file tests passed")
        except Exception as e:
            logger.error(f"Error in test_02_javascript_files: {str(e)}")
            raise
    
    def test_03_incident_template(self):
        """Test the incident template for correct script references"""
        try:
            # Get the incident template content
            response = self.session.get(f"{self.server.url}/incident/new")
            self.assertEqual(response.status_code, 200, "New incident page should return 200 status code")
            
            # Check that it includes alerts.js
            self.assertIn('alerts.js', response.text, "Incident template should include alerts.js")
            logger.info("Incident template includes alerts.js")
            
            # Check that it doesn't include duplicate showAlert function
            # This is a simplistic check - we're just ensuring there's only one showAlert definition
            # A better check would parse the HTML and JavaScript properly
            showAlert_count = response.text.count('function showAlert')
            self.assertLessEqual(showAlert_count, 1, 
                                f"Incident template should not contain duplicate showAlert function, found {showAlert_count}")
            logger.info(f"Found {showAlert_count} showAlert function definitions")
            
            logger.info("Incident template test passed")
        except Exception as e:
            logger.error(f"Error in test_03_incident_template: {str(e)}")
            raise

class TestIncidentSystemSelenium(unittest.TestCase):
    """Test incident system using Selenium for browser automation"""
    @classmethod
    def setUpClass(cls):
        # Start server if not already running
        cls.start_server = False
        try:
            response = requests.get('http://127.0.0.1:5000/login', timeout=5)
            if response.status_code in [200, 302, 401]:
                logger.info("Server already running, skipping server start")
            else:
                cls.start_server = True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            logger.info("Server not detected, will start a new instance")
            cls.start_server = True
            
        if cls.start_server:
            cls.server = ServerManager()
            cls.server.start_server()
        
        # Set up Selenium WebDriver with timeouts
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Add additional Chrome options for stability
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-dev-tools")
        chrome_options.add_argument("--no-zygote")
        chrome_options.add_argument("--single-process")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Initialize WebDriver with timeouts
        cls.driver = webdriver.Chrome(options=chrome_options)
        
        # Set explicit timeouts (10 seconds)
        cls.driver.set_page_load_timeout(10)  # 10 second page load timeout
        cls.driver.implicitly_wait(10)  # 10 second implicit wait for elements
        cls.driver.set_script_timeout(10)  # 10 second script timeout
        
        # Set window size for consistent testing
        cls.driver.set_window_size(1920, 1080)
        
        # Add WebDriverWait with 10 second timeout for explicit waits
        cls.wait = WebDriverWait(cls.driver, 10)
        
        # Log in
        cls._login()
    
    @classmethod
    def tearDownClass(cls):
        # Close browser
        if hasattr(cls, 'driver'):
            cls.driver.quit()
            logger.info("Browser closed")
        
        # Stop server if we started it
        if cls.start_server and hasattr(cls, 'server'):
            cls.server.stop_server()
    
    @classmethod
    def _login(cls):
        """Helper method to log in to the application with robust error handling"""
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                # Navigate to login page with retry
                try:
                    cls.driver.get(f"{cls.server.url}/login")
                    # Wait for document.readyState to be complete
                    WebDriverWait(cls.driver, 10).until(
                        lambda d: d.execute_script('return document.readyState') == 'complete'
                    )
                except TimeoutException:
                    logger.warning(f"Page load timed out (attempt {attempt + 1}/{max_attempts})")
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(2)  # Wait before retry
                    continue
                
                # Wait for login form to be present and interactive
                try:
                    username_field = cls.wait.until(
                        EC.element_to_be_clickable((By.ID, "username"))
                    )
                except TimeoutException:
                    logger.warning(f"Login form not found (attempt {attempt + 1}/{max_attempts})")
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(2)  # Wait before retry
                    continue
                
                try:
                    # Find and fill in login form with explicit waits
                    password_field = cls.wait.until(
                        EC.presence_of_element_located((By.ID, "password"))
                    )
                    login_button = cls.wait.until(
                        EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))
                    )
                    
                    # Clear fields and enter credentials
                    username_field.clear()
                    username_field.send_keys(DEFAULT_USERNAME)
                    password_field.clear()
                    password_field.send_keys(DEFAULT_PASSWORD)
                    
                    # Add a small delay before clicking to ensure fields are filled
                    time.sleep(0.5)
                    login_button.click()
                    
                    # Wait for login to complete and redirect to dashboard
                    try:
                        cls.wait.until(
                            EC.presence_of_element_located((By.ID, "dashboard"))
                        )
                        logger.info("Login successful")
                        return True
                    except TimeoutException:
                        # Check if login failed with error message
                        try:
                            error_msg = cls.driver.find_element(By.CLASS_NAME, "alert-danger").text
                            logger.warning(f"Login failed: {error_msg}")
                        except NoSuchElementException:
                            logger.warning("Login failed: Unknown error")
                        
                        if attempt == max_attempts - 1:
                            raise
                        
                        # Take screenshot and wait before retry
                        take_screenshot(cls.driver, f"login_attempt_{attempt}")
                        time.sleep(2)
                        
                except Exception as e:
                    logger.error(f"Error during login form submission: {str(e)}")
                    take_screenshot(cls.driver, f"login_error_attempt_{attempt}")
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"Login attempt {attempt + 1} failed: {str(e)}")
                take_screenshot(cls.driver, f"login_failure_attempt_{attempt}")
                if attempt == max_attempts - 1:
                    logger.error("All login attempts failed")
                    return False
                time.sleep(2)
        
        return False
    
    def test_01_incident_list_loads(self):
        """Test that incident list page loads and renders correctly"""
        # First log in with retry
        self.assertTrue(self._login(), "Login failed after multiple attempts")
        
        # Navigate to incidents page with retry
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                self.driver.get(f"{self.server.url}/incidents")
                # Wait for document.readyState to be complete
                WebDriverWait(self.driver, 10).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                break  # Success, exit retry loop
            except TimeoutException:
                if attempt == max_attempts - 1:
                    self.fail("Failed to load incidents page after multiple attempts")
                logger.warning(f"Page load timed out, retrying... (attempt {attempt + 1}/{max_attempts})")
        
        # Check that the page title is correct
        try:
            self.wait.until(
                lambda d: "Incidents" in d.title
            )
        except TimeoutException:
            self.fail("Page title does not contain 'Incidents'")
        
        # Check that the incidents table is present and visible
        try:
            table = self.wait.until(
                EC.visibility_of_element_located((By.ID, "incidents-table"))
            )
            self.assertTrue(table.is_displayed(), "Incidents table is not displayed")
            
            # Verify table has data (at least one row)
            rows = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#incidents-table tbody tr"))
            )
            self.assertGreater(len(rows), 0, "No incidents found in the table")
            
        except TimeoutException as e:
            take_screenshot(self.driver, "incident_table_load_failed")
            self.fail(f"Incidents table did not load correctly: {str(e)}")
        except Exception as e:
            take_screenshot(self.driver, "unexpected_error_incident_list")
            raise  # Re-raise any other exceptions
    
    def test_02_incident_create_page_loads(self):
        """Test that the create incident page loads correctly"""
        try:
            self.driver.get(f"{self.url}/incident/new")
            
            # Wait for form to appear
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "form"))
            )
            
            # Take screenshot for verification
            take_screenshot(self.driver, "incident_create")
            
            # Check for JavaScript errors
            log_js_errors(self.driver)
            logger.info("Create incident page loaded successfully")
        except Exception as e:
            logger.error(f"Error in test_02_incident_create_page_loads: {str(e)}")
            take_screenshot(self.driver, "incident_create_error")
            raise

    def test_03_alert_functions(self):
        """Test the alert functionality"""
        try:
            self.driver.get(f"{self.url}/incident/new")
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "form"))
            )
            
            # Execute JavaScript to test the showAlert function
            self.driver.execute_script(
                "window.showAlert('info', 'This is a test alert from Selenium', 2000);"
            )
            
            # Wait for alert to appear
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "alert-info"))
            )
            
            # Take screenshot showing the alert
            take_screenshot(self.driver, "alert_test")
            
            # Check for JavaScript errors
            log_js_errors(self.driver)
            logger.info("Alert function works correctly")
        except Exception as e:
            logger.error(f"Error in test_03_alert_functions: {str(e)}")
            take_screenshot(self.driver, "alert_test_error")
            raise

    def test_04_create_new_incident(self):
        """Test creating a new incident"""
        try:
            # Navigate to create incident page
            self.driver.get(f"{self.url}/incident/new")
            
            # Wait for form to load
            form = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "incidentForm"))
            )
            
            # Fill out incident form
            self.driver.find_element(By.ID, "location").send_keys("123 Test Street")
            self.driver.find_element(By.ID, "problem_description").send_keys("Test incident for automated testing")
            
            # Select incident type
            type_select = self.driver.find_element(By.ID, "type")
            for option in type_select.find_elements(By.TAG_NAME, "option"):
                if option.text == "MEDICAL_EMERGENCY" or option.text == "MEDICAL":
                    option.click()
                    break
            
            # Set priority
            priority_select = self.driver.find_element(By.ID, "priority")
            for option in priority_select.find_elements(By.TAG_NAME, "option"):
                if option.text == "HIGH":
                    option.click()
                    break
            
            # Fill caller info
            self.driver.find_element(By.ID, "caller").send_keys("Test Caller")
            self.driver.find_element(By.ID, "callback_number").send_keys("555-1234")
            
            # Take screenshot before submission
            take_screenshot(self.driver, "before_incident_submit")
            
            # Submit form
            save_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            save_button.click()
            
            # Wait for success message or redirect
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CLASS_NAME, "alert-success")),
                        EC.url_contains("/incident/")
                    )
                )
                logger.info("Successfully created new incident")
            except TimeoutException:
                logger.error("Failed to detect success message or redirect after incident creation")
                raise
            
            # Take screenshot after submission
            take_screenshot(self.driver, "after_incident_submit")
            
            # Get incident ID from URL or form data attribute
            incident_id = None
            try:
                current_url = self.driver.current_url
                if "/incident/" in current_url:
                    incident_id = current_url.split("/incident/")[1].split("/")[0]
                else:
                    form = self.driver.find_element(By.ID, "incidentForm")
                    incident_id = form.get_attribute("data-incident-id")
                logger.info(f"Created incident with ID: {incident_id}")
            except Exception as e:
                logger.warning(f"Could not determine incident ID: {str(e)}")
            
            # Save incident ID for later tests
            if incident_id:
                self.__class__.test_incident_id = incident_id
            
            # Check for any JavaScript errors
            log_js_errors(self.driver)
            
        except Exception as e:
            logger.error(f"Error in test_04_create_new_incident: {str(e)}")
            take_screenshot(self.driver, "incident_create_error")
            raise
    
    def test_05_add_log_entry(self):
        """Test adding a log entry to an incident"""
        try:
            # Skip if we don't have an incident ID from previous test
            if not hasattr(self.__class__, 'test_incident_id'):
                self.skipTest("No incident ID available from previous test")
            
            # Navigate to the incident page
            self.driver.get(f"{self.url}/incident/{self.__class__.test_incident_id}")
            
            # Wait for quick note form
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "quickNoteForm"))
            )
            
            # Fill out quick note form
            note_input = self.driver.find_element(By.ID, "quickNoteText")
            note_input.clear()
            note_input.send_keys("Automated test log entry")
            
            # Select note type
            type_select = self.driver.find_element(By.ID, "quickNoteType")
            for option in type_select.find_elements(By.TAG_NAME, "option"):
                if option.text.lower() == "info":
                    option.click()
                    break
            
            # Take screenshot before submission
            take_screenshot(self.driver, "before_log_entry")
            
            # Submit the quick note form
            submit_button = self.driver.find_element(By.XPATH, "//form[@id='quickNoteForm']//button[@type='submit']")
            submit_button.click()
            
            # Wait for the log entry to appear
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.text_to_be_present_in_element(
                        (By.ID, "liveLog"),
                        "Automated test log entry"
                    )
                )
                logger.info("Successfully added log entry")
            except TimeoutException:
                logger.error("Failed to detect new log entry after submission")
                raise
            
            # Take screenshot after submission
            take_screenshot(self.driver, "after_log_entry")
            
            # Check for any JavaScript errors
            log_js_errors(self.driver)
            
        except Exception as e:
            logger.error(f"Error in test_05_add_log_entry: {str(e)}")
            take_screenshot(self.driver, "log_entry_error")
            raise
    
    def test_06_modify_incident_status(self):
        """Test changing the incident status"""
        try:
            # Skip if we don't have an incident ID from previous test
            if not hasattr(self.__class__, 'test_incident_id'):
                self.skipTest("No incident ID available from previous test")
            
            # Navigate to the incident page
            self.driver.get(f"{self.url}/incident/{self.__class__.test_incident_id}")
            
            # Wait for status select to be present
            status_select = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "status"))
            )
            
            # Change the status to IN_PROGRESS
            for option in status_select.find_elements(By.TAG_NAME, "option"):
                if option.text == "IN_PROGRESS" or option.text == "IN PROGRESS":
                    option.click()
                    break
            
            # Take screenshot after status change
            take_screenshot(self.driver, "after_status_change")
            
            # Wait for auto-save to complete and check status badge
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".status-IN_PROGRESS"))
                )
                logger.info("Successfully changed incident status")
            except TimeoutException:
                # Try alternative class if the status has spaces
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".status-IN"))
                    )
                    logger.info("Successfully changed incident status (using partial class)")
                except TimeoutException:
                    logger.error("Failed to detect status change")
                    raise
            
            # Check for any JavaScript errors
            log_js_errors(self.driver)
            
        except Exception as e:
            logger.error(f"Error in test_06_modify_incident_status: {str(e)}")
            take_screenshot(self.driver, "status_change_error")
            raise
    
    def test_07_dispatch_unit(self):
        """Test assigning a unit to an incident"""
        try:
            # Skip if we don't have an incident ID from previous test
            if not hasattr(self.__class__, 'test_incident_id'):
                self.skipTest("No incident ID available from previous test")
            
            # Navigate to the incident page
            self.driver.get(f"{self.url}/incident/{self.__class__.test_incident_id}")
            
            # Wait for unit select to be present
            unit_select = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "unitSelect"))
            )
            
            # Select first available unit
            options = unit_select.find_elements(By.TAG_NAME, "option")
            if len(options) <= 1:  # Skip default/empty option
                self.skipTest("No units available for assignment")
            
            # Select the first non-empty option
            for option in options[1:]:  # Skip first (usually empty) option
                option.click()
                break
            
            # Get the unit ID/name for verification later
            selected_unit = unit_select.get_attribute("value")
            
            # Click dispatch button
            dispatch_button = self.driver.find_element(By.ID, "dispatchUnit")
            dispatch_button.click()
            
            # Take screenshot after dispatch
            take_screenshot(self.driver, "after_unit_dispatch")
            
            # Wait for assigned units list to update
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "assignedUnitsList"))
                )
                assigned_units = self.driver.find_element(By.ID, "assignedUnitsList")
                if "No units assigned" not in assigned_units.text:
                    logger.info("Successfully assigned unit to incident")
                else:
                    logger.error("Unit assignment failed - still showing 'No units assigned'")
                    raise Exception("Unit assignment did not update the UI")
            except TimeoutException:
                logger.error("Failed to detect unit assignment")
                raise
            
            # Check for any JavaScript errors
            log_js_errors(self.driver)
            
        except Exception as e:
            logger.error(f"Error in test_07_dispatch_unit: {str(e)}")
            take_screenshot(self.driver, "unit_dispatch_error")
            raise
    
    def test_08_test_auto_save(self):
        """Test the auto-save functionality for incident fields"""
        try:
            # Skip if we don't have an incident ID from previous test
            if not hasattr(self.__class__, 'test_incident_id'):
                self.skipTest("No incident ID available from previous test")
            
            # Navigate to the incident page
            self.driver.get(f"{self.url}/incident/{self.__class__.test_incident_id}")
            
            # Wait for form to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "incidentForm"))
            )
            
            # Update a field to trigger auto-save
            problem_field = self.driver.find_element(By.ID, "problem_description")
            original_text = problem_field.get_attribute("value")
            problem_field.clear()
            problem_field.send_keys(f"{original_text} - Updated by auto-save test")
            
            # Click outside the field to trigger blur event
            self.driver.find_element(By.TAG_NAME, "body").click()
            
            # Take screenshot after field update
            take_screenshot(self.driver, "after_field_update")
            
            # Wait a moment for auto-save to complete
            time.sleep(2)
            
            # Refresh the page to verify changes were saved
            self.driver.refresh()
            
            # Wait for form to reload
            problem_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "problem_description"))
            )
            
            # Check if the updated text is present
            updated_text = problem_field.get_attribute("value")
            if "Updated by auto-save test" in updated_text:
                logger.info("Auto-save functionality working correctly")
            else:
                logger.error(f"Auto-save test failed. Expected text not found. Found: '{updated_text}'")
                raise Exception("Auto-save did not persist the field change")
            
            # Check for any JavaScript errors
            log_js_errors(self.driver)
            
        except Exception as e:
            logger.error(f"Error in test_08_test_auto_save: {str(e)}")
            take_screenshot(self.driver, "auto_save_error")
            raise

    def test_09_ampds_protocol_suggestions(self):
        """Test that AMPDS protocol suggestions work correctly"""
        try:
            # Navigate to create incident page
            self.driver.get(f"{self.url}/incident/new")
            
            # Wait for form to load
            form = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "incidentForm"))
            )
            
            # Select incident type that should trigger AMPDS suggestions
            type_select = self.driver.find_element(By.ID, "type")
            for option in type_select.find_elements(By.TAG_NAME, "option"):
                if option.text == "MEDICAL_EMERGENCY" or option.text == "MEDICAL":
                    option.click()
                    break
            
            # Wait briefly for suggestions to load (if they appear in the UI)
            time.sleep(2)
            
            # Check console logs for AMPDS suggestion activity
            logs = self.driver.get_log('browser')
            ampds_suggestion_found = False
            for log in logs:
                if 'suggest_by_type' in log.get('message', '') or 'suggested protocols' in log.get('message', ''):
                    ampds_suggestion_found = True
                    logger.info(f"Found AMPDS suggestion log: {log.get('message')}")
                    break
            
            # If there's a specific UI element for protocol suggestions, check for it
            try:
                suggestion_elements = self.driver.find_elements(By.CLASS_NAME, "protocol-suggestion")
                if suggestion_elements:
                    logger.info(f"Found {len(suggestion_elements)} protocol suggestion elements in the UI")
                    ampds_suggestion_found = True
            except NoSuchElementException:
                # It's okay if suggestions don't appear in the UI yet
                pass
            
            # Test the API endpoint directly
            current_cookies = self.driver.get_cookies()
            cookie_dict = {cookie['name']: cookie['value'] for cookie in current_cookies}
            
            session = requests.Session()
            for name, value in cookie_dict.items():
                session.cookies.set(name, value)
            
            response = session.get(f"{self.url}/api/ampds/suggest_by_type?type=MEDICAL")
            
            if response.status_code == 200:
                data = response.json()
                if 'protocols' in data:
                    logger.info(f"AMPDS API returned {len(data['protocols'])} protocol suggestions")
                    ampds_suggestion_found = True
                else:
                    logger.warning("AMPDS API response didn't contain protocols key")
            else:
                logger.warning(f"AMPDS suggestion API returned status code {response.status_code}")
            
            # Assert that we found evidence of AMPDS suggestions working
            self.assertTrue(ampds_suggestion_found, "No evidence found of AMPDS protocol suggestions")
            
            # Take screenshot 
            take_screenshot(self.driver, "ampds_suggestions")
            
        except Exception as e:
            logger.error(f"Error in test_09_ampds_protocol_suggestions: {str(e)}")
            take_screenshot(self.driver, "ampds_suggestions_error")
            raise
    
    def test_10_client_logs_api(self):
        """Test the client logs API endpoint"""
        try:
            # Prepare test log data
            log_data = {
                "level": "info",
                "message": "Test log message from API test",
                "source": "test_incident_system.py",
                "context": {"test": True, "automated": True},
                "timestamp": datetime.now().isoformat()
            }
            
            # Test authenticated submission using session from login
            response = self.session.post(
                f"{self.server.url}/api/client-logs", 
                json=log_data,
                headers={"Content-Type": "application/json"}
            )
            
            logger.info(f"Client logs API authenticated response: {response.status_code}")
            
            # If logged in, check response status
            if response.status_code == 200:
                response_data = response.json()
                self.assertTrue(response_data.get('success'), "Expected success=True in response")
                logger.info("Client logs API test successful (authenticated)")
            else:
                logger.warning(f"Authenticated client logs submission returned {response.status_code} - this might be okay")
            
            # Test anonymous submission (simulating logged-out user)
            anon_session = requests.Session()
            anon_response = anon_session.post(
                f"{self.server.url}/api/client-logs", 
                json=log_data,
                headers={"Content-Type": "application/json"}
            )
            
            # Check anonymous response - this should always work even without authentication
            self.assertEqual(anon_response.status_code, 200, 
                            f"Expected 200 OK for anonymous log, got {anon_response.status_code}")
            
            anon_response_data = anon_response.json()
            self.assertTrue(anon_response_data.get('success'), "Expected success=True in anonymous response")
            
            logger.info("Anonymous client logs API test successful")
            
        except Exception as e:
            logger.error(f"Error in test_10_client_logs_api: {str(e)}")
            raise

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run tests for the CAD System incident functionality')
    parser.add_argument('--headless', action='store_true', default=True,
                        help='Run tests in headless mode (default: True)')
    parser.add_argument('--selenium', action='store_true', default=False,
                        help='Run Selenium browser tests (default: False)')
    parser.add_argument('--requests', action='store_true', default=True,
                        help='Run requests-based tests (default: True)')
    parser.add_argument('--username', type=str, default=DEFAULT_USERNAME,
                        help=f'Username for login (default: {DEFAULT_USERNAME})')
    parser.add_argument('--password', type=str, default=DEFAULT_PASSWORD,
                        help=f'Password for login (default: {DEFAULT_PASSWORD})')
    
    args = parser.parse_args()
    
    # Update login credentials if provided
    if args.username:
        DEFAULT_USERNAME = args.username
    if args.password:
        DEFAULT_PASSWORD = args.password
    
    # Ensure logs directory exists
    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add test classes based on arguments
    if args.requests:
        suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestIncidentSystemRequests))
    
    if args.selenium:
        suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestIncidentSystemSelenium))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with appropriate status code
    sys.exit(not result.wasSuccessful())
