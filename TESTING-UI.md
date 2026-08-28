# UI Testing Guide

This document provides instructions for running and maintaining the UI tests for the CAD System application.

## Prerequisites

- Python 3.8+
- Chrome browser installed (for Chrome testing)
- [Optional] Firefox or Edge browser (for cross-browser testing)

## Setup

1. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements-ui-testing.txt
   ```

3. **Environment Variables**:
   Create a `.env` file in the project root with the following variables:
   ```
   TEST_BASE_URL=http://localhost:5000
   SELENIUM_BROWSER=chrome
   SELENIUM_HEADLESS=true
   ```

## Running Tests

### Basic Test Execution

Run all UI tests:
```bash
python run_ui_tests.py
```

Run a specific test file:
```bash
python run_ui_tests.py tests/test_admin.py
```

Run tests matching a keyword:
```bash
python run_ui_tests.py -k "test_login"
```

### Advanced Options

Run tests in parallel (4 workers):
```bash
python run_ui_tests.py -n 4
```

Run with visible browser:
```bash
python run_ui_tests.py --no-headless
```

Run with a different browser:
```bash
python run_ui_tests.py --browser firefox
```

Run with debug output:
```bash
python run_ui_tests.py -d
```

## Test Reports

After running tests, you can find the following reports in the `reports/` directory:

- `test_report.html` - Interactive HTML test report
- `junit.xml` - JUnit-compatible XML report (for CI/CD integration)
- `coverage/` - Code coverage report (HTML and XML)

## Writing Tests

### Test Structure

1. **Test Files**: Place test files in the `tests/` directory with the prefix `test_`.
2. **Test Classes**: Group related test methods in classes that inherit from `BaseSeleniumTest`.
3. **Test Methods**: Name test methods with the prefix `test_`.

### Example Test

```python
from tests.base_test import BaseSeleniumTest

class TestLogin(BaseSeleniumTest):
    def test_successful_login(self):
        """Test that a user can log in successfully."""
        # Navigate to login page
        self.navigate_to('/auth/login')
        
        # Fill in login form
        self.helper.type_text((By.NAME, 'username'), 'testuser')
        self.helper.type_text((By.NAME, 'password'), 'password123')
        
        # Submit form
        self.helper.click_element((By.CSS_SELECTOR, 'button[type="submit"]'))
        
        # Verify successful login
        self.helper.wait_for_element((By.ID, 'dashboard'))
        self.assertIn('dashboard', self.driver.current_url)
```

### Best Practices

1. **Use Page Object Model**: Consider creating page objects for complex pages.
2. **Use Explicit Waits**: Always wait for elements to be present/visible before interacting.
3. **Take Screenshots**: Use `self.helper.take_screenshot()` for debugging.
4. **Clean Up**: Ensure tests clean up after themselves.
5. **Isolate Tests**: Each test should be independent and not rely on state from other tests.

## Troubleshooting

### Common Issues

1. **Element Not Found**:
   - Check if the element is in an iframe
   - Wait for the element to be present/visible
   - Check for dynamic IDs/classes

2. **Browser Crashes**:
   - Update browser and WebDriver versions
   - Run with visible browser (`--no-headless`) to observe

3. **Slow Tests**:
   - Use explicit waits instead of `time.sleep()`
   - Run tests in parallel with `-n`

### Debugging

1. **View Screenshots**: Check the `logs/screenshots/` directory for screenshots taken on test failure.
2. **Check Logs**: Review `test_runner.log` for detailed execution logs.
3. **Interactive Debugging**:
   - Run with `-d` flag for debug output
   - Set breakpoints with `import pdb; pdb.set_trace()`

## CI/CD Integration

To run tests in a CI/CD pipeline, use the following command:

```yaml
# Example GitHub Actions workflow
name: UI Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      chrome:
        image: selenium/node-chrome:4.8.0-20230214
        env:
          - SE_EVENT_BUS_HOST=selenium-hub
          - SE_EVENT_BUS_PUBLISH_PORT=4442
          - SE_EVENT_BUS_SUBSCRIBE_PORT=4443
        ports:
          - "6900:5900"
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements-ui-testing.txt
    
    - name: Run UI Tests
      run: |
        export TEST_BASE_URL=http://localhost:5000
        export SELENIUM_BROWSER=chrome
        export SELENIUM_HEADLESS=true
        python run_ui_tests.py
    
    - name: Upload Test Results
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: test-reports
        path: |
          reports/
          logs/
```

## Maintenance

### Updating Dependencies

To update test dependencies:

1. Update the versions in `requirements-ui-testing.txt`
2. Test the changes locally
3. Update the CI/CD pipeline if needed

### Adding New Tests

1. Create a new test file in `tests/`
2. Follow the existing patterns and best practices
3. Add appropriate assertions and error handling
4. Update this documentation if necessary

## License

This testing framework is part of the CAD System project and follows the same license.
