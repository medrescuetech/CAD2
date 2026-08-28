import os
import sys
import time
import json
import unittest
import requests
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('test_ampds_api')

# Default credentials
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"

class TestAMPDSAPI(unittest.TestCase):
    """Tests for the AMPDS API endpoints"""
    
    @classmethod
    def setUpClass(cls):
        """Setup before any tests are run"""
        cls.base_url = "http://127.0.0.1:5000"
        cls.session = requests.Session()
        
        # Login to get authenticated session
        cls.login()
    
    @classmethod
    def login(cls):
        """Login to get an authenticated session"""
        login_url = f"{cls.base_url}/login"
        
        # Get login page to retrieve CSRF token
        try:
            response = cls.session.get(login_url)
            
            # Check if we can access the login page
            if response.status_code != 200:
                logger.error(f"Failed to access login page: {response.status_code}")
                return False
            
            # Extract CSRF token if present
            csrf_token = None
            if 'csrf_token' in response.text:
                import re
                match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
                if match:
                    csrf_token = match.group(1)
            
            # Prepare login data
            login_data = {
                'username': DEFAULT_USERNAME,
                'password': DEFAULT_PASSWORD
            }
            
            if csrf_token:
                login_data['csrf_token'] = csrf_token
            
            # Submit login
            response = cls.session.post(login_url, data=login_data, allow_redirects=True)
            
            # Check if login was successful
            if 'dashboard' in response.url or 'home' in response.url or 'incidents' in response.url:
                logger.info("Login successful")
                return True
            else:
                logger.error(f"Login failed, redirected to {response.url}")
                return False
                
        except Exception as e:
            logger.error(f"Error during login: {str(e)}")
            return False
    
    def test_01_ampds_categories_endpoint(self):
        """Test the AMPDS categories endpoint"""
        endpoint = f"{self.base_url}/api/ampds/categories"
        response = self.session.get(endpoint)
        
        # Check status code
        self.assertEqual(response.status_code, 200, f"Expected 200 OK, got {response.status_code}")
        
        # Check response content
        data = response.json()
        self.assertIn('categories', data, "Response should contain 'categories' key")
        self.assertIn('count', data, "Response should contain 'count' key")
        
        # We should have at least one category
        self.assertGreater(data['count'], 0, "Expected at least one AMPDS category")
        logger.info(f"Found {data['count']} AMPDS categories")
    
    def test_02_ampds_cards_endpoint(self):
        """Test the AMPDS cards endpoint"""
        endpoint = f"{self.base_url}/api/ampds/cards"
        response = self.session.get(endpoint)
        
        # Check status code
        self.assertEqual(response.status_code, 200, f"Expected 200 OK, got {response.status_code}")
        
        # Check response content
        data = response.json()
        self.assertIn('card_numbers', data, "Response should contain 'card_numbers' key")
        self.assertIn('count', data, "Response should contain 'count' key")
        
        # We should have at least one card
        self.assertGreater(data['count'], 0, "Expected at least one AMPDS card")
        logger.info(f"Found {data['count']} AMPDS cards")
    
    def test_03_ampds_suggest_by_type_endpoint(self):
        """Test the AMPDS suggest_by_type endpoint"""
        # Test with medical incident type
        endpoint = f"{self.base_url}/api/ampds/suggest_by_type?type=MEDICAL"
        response = self.session.get(endpoint)
        
        # Check status code
        self.assertEqual(response.status_code, 200, f"Expected 200 OK, got {response.status_code}")
        
        # Check response content
        data = response.json()
        self.assertIn('protocols', data, "Response should contain 'protocols' key")
        
        # Log what we found
        protocol_count = len(data['protocols'])
        logger.info(f"Found {protocol_count} suggested protocols for MEDICAL type")
        
        # Test with fire incident type (might return empty protocols if configured that way)
        endpoint = f"{self.base_url}/api/ampds/suggest_by_type?type=FIRE"
        response = self.session.get(endpoint)
        
        # Check status code
        self.assertEqual(response.status_code, 200, f"Expected 200 OK, got {response.status_code}")
        
        # Check response format (even if empty)
        data = response.json()
        self.assertIn('protocols', data, "Response should contain 'protocols' key")
        logger.info(f"Found {len(data['protocols'])} suggested protocols for FIRE type")
    
    def test_04_client_logs_api_anonymous(self):
        """Test client logs API with anonymous user"""
        # Create a new session without login
        anon_session = requests.Session()
        
        # Prepare test log data
        log_data = {
            "level": "info",
            "message": "Test log message from anonymous user",
            "source": "test_ampds_api.py",
            "context": {"test": True, "anonymous": True},
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Post to client logs API
        endpoint = f"{self.base_url}/api/client-logs"
        response = anon_session.post(
            endpoint,
            json=log_data,
            headers={"Content-Type": "application/json"}
        )
        
        # Check status code
        self.assertEqual(response.status_code, 200, f"Expected 200 OK, got {response.status_code}")
        
        # Check response content
        data = response.json()
        self.assertTrue(data.get('success'), "Expected success=True in response")
        logger.info("Anonymous client logs API test successful")

if __name__ == '__main__':
    # Run the tests
    unittest.main()
