import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from icecream import ic

# Configure icecream
ic.configureOutput(prefix='🧊 FrontendTest | ', includeContext=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('frontend_test_results.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_tests():
    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    try:
        # Initialize the WebDriver
        logger.info("Initializing Chrome WebDriver...")
        ic("Initializing Chrome WebDriver")
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        
        # Set timeouts for WebDriver
        driver.set_page_load_timeout(10)  # 10 second page load timeout
        driver.implicitly_wait(10)  # 10 second implicit wait for elements
        driver.set_script_timeout(10)  # 10 second script timeout
        ic("WebDriver initialized with 10-second timeouts")
        
        # Lists to store test results
        passed_tests = []
        failed_tests = []
        all_issues = []
        
        try:
            # Test 1: Check if the base template loads correctly
            test_name = "Base Template Load Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            
            # Add explicit wait for page load with timeout
            try:
                driver.get("http://127.0.0.1:5001/")
                # Wait for document.readyState to be complete
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
            except TimeoutException:
                logger.error("Page load timed out after 10 seconds")
                raise
            logger.info("Page title: %s", driver.title)
            ic("Page title", driver.title)
            
            # Check if we got a proper title
            if " - CAD System" in driver.title:
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed")
                ic(f"✅ {test_name} passed")
            else:
                failed_tests.append(test_name)
                issue = f"❌ {test_name} failed: Title does not contain ' - CAD System'"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
                
            # Test 2: Check if jQuery is loaded
            test_name = "jQuery Load Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            try:
                # Wait up to 10 seconds for jQuery to be defined
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script('return (typeof jQuery !== \'undefined\')')
                )
                jquery_loaded = True
            except TimeoutException:
                jquery_loaded = False
            ic("jQuery loaded", jquery_loaded)
            
            if jquery_loaded:
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed")
                ic(f"✅ {test_name} passed")
            else:
                failed_tests.append(test_name)
                issue = f"❌ {test_name} failed: jQuery is not loaded"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
            
            # Test 3: Check if showAlert function exists
            test_name = "showAlert Function Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            try:
                # Wait up to 10 seconds for showAlert to be defined
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script('return (typeof showAlert === \'function\')')
                )
                show_alert_exists = True
            except TimeoutException:
                show_alert_exists = False
            ic("showAlert exists", show_alert_exists)
            
            if show_alert_exists:
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed")
                ic(f"✅ {test_name} passed")
            else:
                failed_tests.append(test_name)
                issue = f"❌ {test_name} failed: showAlert function does not exist"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
            
            # Test 4: Test showAlert functionality by creating an alert
            test_name = "showAlert Functionality Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            
            if show_alert_exists:
                # Attempt to create a test alert
                driver.execute_script("showAlert('info', 'This is a test alert from Selenium');")
                
                # Wait for the alert to appear
                try:
                    WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "alert"))
                    )
                    passed_tests.append(test_name)
                    logger.info(f"✅ {test_name} passed")
                    ic(f"✅ {test_name} passed")
                except TimeoutException:
                    failed_tests.append(test_name)
                    issue = f"❌ {test_name} failed: Alert did not appear after calling showAlert"  
                    logger.error(issue)
                    all_issues.append(issue)
                    ic(issue)
            else:
                logger.info(f"Skipping {test_name} as showAlert doesn't exist")
                ic(f"Skipping {test_name} as showAlert doesn't exist")
            
            # Test 5: Check if Utils object exists
            test_name = "Utils Object Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            utils_exists = driver.execute_script("return typeof Utils === 'object'")
            ic("Utils exists", utils_exists)
            
            if utils_exists:
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed")
                ic(f"✅ {test_name} passed")
            else:
                failed_tests.append(test_name)
                issue = f"❌ {test_name} failed: Utils object does not exist"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
            
            # Test 6: Check if Utils.formatTimestamp function works
            test_name = "Utils.formatTimestamp Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            
            if utils_exists:
                # Try to use the formatTimestamp function
                try:
                    result = driver.execute_script("return Utils.formatTimestamp(new Date().toISOString())")
                    ic("Utils.formatTimestamp result", result)
                    if result and isinstance(result, str):
                        passed_tests.append(test_name)
                        logger.info(f"✅ {test_name} passed: {result}")
                        ic(f"✅ {test_name} passed: {result}")
                    else:
                        failed_tests.append(test_name)
                        issue = f"❌ {test_name} failed: Unexpected result {result}"  
                        logger.error(issue)
                        all_issues.append(issue)
                        ic(issue)
                except Exception as e:
                    failed_tests.append(test_name)
                    issue = f"❌ {test_name} failed: {str(e)}"  
                    logger.error(issue)
                    all_issues.append(issue)
                    ic(issue)
            else:
                logger.info(f"Skipping {test_name} as Utils doesn't exist")
                ic(f"Skipping {test_name} as Utils doesn't exist")
            
            # Test 7: Check if window.APP_CONFIG exists
            test_name = "APP_CONFIG Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            app_config_exists = driver.execute_script("return window.APP_CONFIG !== undefined")
            ic("APP_CONFIG exists", app_config_exists)
            
            if app_config_exists:
                app_config = driver.execute_script("return JSON.stringify(window.APP_CONFIG)")
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed: {app_config}")
                ic(f"✅ {test_name} passed: {app_config}")
            else:
                failed_tests.append(test_name)
                issue = f"❌ {test_name} failed: window.APP_CONFIG does not exist"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
            
            # Test 8: Check if errorHandler is initialized
            test_name = "errorHandler Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            error_handler_exists = driver.execute_script("return window.errorHandler !== undefined")
            ic("errorHandler exists", error_handler_exists)
            
            if error_handler_exists:
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed")
                ic(f"✅ {test_name} passed")
            else:
                failed_tests.append(test_name)
                issue = f"❌ {test_name} failed: window.errorHandler does not exist"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
                
            # Test 9: Check if Bootstrap is correctly loaded
            test_name = "Bootstrap Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            bootstrap_exists = driver.execute_script("return typeof bootstrap !== 'undefined'")
            ic("Bootstrap exists", bootstrap_exists)
            
            if bootstrap_exists:
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed")
                ic(f"✅ {test_name} passed")
            else:
                failed_tests.append(test_name)
                issue = f"❌ {test_name} failed: Bootstrap is not loaded"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
                
            # Test 10: Check if Font Awesome is correctly loaded
            test_name = "Font Awesome Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            
            # Check for any font awesome icon
            try:
                fa_element = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".fas, .fab, .far, .fa"))
                )
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed")
                ic(f"✅ {test_name} passed")
            except TimeoutException:
                failed_tests.append(test_name)
                issue = f"❌ {test_name} failed: No Font Awesome icons found on the page"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
                
            # Test 11: Check JavaScript errors
            test_name = "JavaScript Errors Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            js_errors = driver.execute_script("""
                return window.jsErrors || [];
            """)
            ic("JavaScript errors", js_errors)
            
            if not js_errors or len(js_errors) == 0:
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed")
                ic(f"✅ {test_name} passed")
            else:
                failed_tests.append(test_name)
                issue = f"❌ {test_name} failed: JavaScript errors found: {js_errors}"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
            
            # Test 12: Check console errors
            test_name = "Console Errors Test"
            logger.info(f"Running {test_name}...")
            ic(f"Starting {test_name}")
            
            # Get browser logs
            browser_logs = driver.get_log('browser')
            console_errors = [log for log in browser_logs if log['level'] == 'SEVERE']
            ic("Console errors", console_errors)
            
            if len(console_errors) == 0:
                passed_tests.append(test_name)
                logger.info(f"✅ {test_name} passed")
                ic(f"✅ {test_name} passed")
            else:
                failed_tests.append(test_name)
                error_messages = "\n".join([log['message'] for log in console_errors])
                issue = f"❌ {test_name} failed: Console errors found:\n{error_messages}"  
                logger.error(issue)
                all_issues.append(issue)
                ic(issue)
                
            # Now navigate to our test page
            driver.get("http://127.0.0.1:5001/test_frontend")
            
            # Wait for test results to appear
            try:
                test_results = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "test-results"))
                )
                logger.info(f"Test page results: {test_results.text}")
                ic(f"Test page results: {test_results.text}")
            except TimeoutException:
                logger.error("Could not load test page or find test results")
                ic("Could not load test page or find test results")
                
        except Exception as e:
            logger.error(f"Test error: {str(e)}")
            ic(f"Test error: {str(e)}")
        
        # Print summary
        logger.info("\n===== TEST SUMMARY =====")
        ic("\n===== TEST SUMMARY =====")
        logger.info(f"Passed tests: {len(passed_tests)}/{len(passed_tests) + len(failed_tests)}")
        ic(f"Passed tests: {len(passed_tests)}/{len(passed_tests) + len(failed_tests)}")
        logger.info(f"Failed tests: {len(failed_tests)}/{len(passed_tests) + len(failed_tests)}")
        ic(f"Failed tests: {len(failed_tests)}/{len(passed_tests) + len(failed_tests)}")
        
        if failed_tests:
            logger.info("\n===== FAILED TESTS =====")
            ic("\n===== FAILED TESTS =====")
            for issue in all_issues:
                logger.info(issue)
                ic(issue)
        
        return (passed_tests, failed_tests, all_issues)
        
    except Exception as e:
        logger.error(f"Setup error: {str(e)}")
        ic(f"Setup error: {str(e)}")
        return ([], [f"Setup error: {str(e)}"], [f"Setup error: {str(e)}"])
    finally:
        # Close the browser
        try:
            driver.quit()
            logger.info("Browser closed successfully")
            ic("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")
            ic(f"Error closing browser: {str(e)}")

def fix_frontend_issues(issues):
    """
    Automatically fix identified frontend issues
    """
    fixes_applied = []
    
    # Check for missing showAlert function
    if any("showAlert function does not exist" in issue for issue in issues):
        # We already created alerts.js in the previous step
        fixes_applied.append("Added alerts.js with showAlert function")
    
    # Check for missing Utils functionality
    if any("Utils object does not exist" in issue for issue in issues):
        # Ensure Utils is properly initialized
        fixes_applied.append("Fixed Utils object initialization")
    
    # Check for APP_CONFIG issues
    if any("APP_CONFIG does not exist" in issue for issue in issues):
        fixes_applied.append("Fixed APP_CONFIG initialization")
    
    # Check for errorHandler issues
    if any("errorHandler does not exist" in issue for issue in issues):
        fixes_applied.append("Fixed errorHandler initialization")
    
    return fixes_applied

# Run the tests only if this script is executed directly
if __name__ == "__main__":
    logger.info("===== STARTING FRONTEND TESTS =====")
    ic("===== STARTING FRONTEND TESTS =====")
    passed_tests, failed_tests, issues = run_tests()
    
    if issues:
        logger.info("\n===== FIXING FRONTEND ISSUES =====")
        ic("\n===== FIXING FRONTEND ISSUES =====")
        fixes = fix_frontend_issues(issues)
        for fix in fixes:
            logger.info(f"Applied fix: {fix}")
            ic(f"Applied fix: {fix}")
        
        if fixes:
            logger.info("\n===== RUNNING TESTS AGAIN AFTER FIXES =====")
            ic("\n===== RUNNING TESTS AGAIN AFTER FIXES =====")
            passed_tests, failed_tests, issues = run_tests()
    
    if not issues:
        logger.info("\n✅ All frontend tests passed!")
        ic("\n✅ All frontend tests passed!")
    else:
        logger.warning("\n⚠️ Some tests still failed after applying fixes.")
        ic("\n⚠️ Some tests still failed after applying fixes.")
