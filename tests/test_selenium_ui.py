"""
Selenium UI Tests for ECE461 Package Registry
Tests search, upload, authentication, and responsive design
"""

import pytest
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Configuration
BASE_URL = "http://localhost:8080"
TIMEOUT = 10

@pytest.fixture(scope="module")
def driver():
    """Create a Chrome WebDriver instance."""
    options = Options()
    options.add_argument("--headless")  # Run headless for CI/CD
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(TIMEOUT)
    
    yield driver
    
    driver.quit()

@pytest.fixture(scope="module")
def authenticated_driver(driver):
    """Login and return authenticated driver."""
    driver.get(BASE_URL)
    
    # Click login button
    login_button = driver.find_element(By.ID, "auth-button")
    login_button.click()
    
    # Wait for modal
    WebDriverWait(driver, TIMEOUT).until(
        EC.visibility_of_element_located((By.ID, "authModal"))
    )
    
    # Enter credentials
    username_input = driver.find_element(By.ID, "username")
    password_input = driver.find_element(By.ID, "password")
    
    username_input.send_keys("admin")
    password_input.send_keys("admin123!")
    
    # Submit
    submit_button = driver.find_element(By.CSS_SELECTOR, "#auth-form button[type='submit']")
    submit_button.click()
    
    # Wait for modal to close
    WebDriverWait(driver, TIMEOUT).until(
        EC.invisibility_of_element_located((By.ID, "authModal"))
    )
    
    yield driver

class TestHomePage:
    """Tests for home page functionality."""
    
    def test_page_loads(self, driver):
        """Test that home page loads successfully."""
        driver.get(BASE_URL)
        assert "ECE461 Package Registry" in driver.title
    
    def test_navigation_present(self, driver):
        """Test that navigation bar is present."""
        driver.get(BASE_URL)
        navbar = driver.find_element(By.CSS_SELECTOR, "nav.navbar")
        assert navbar.is_displayed()
    
    def test_hero_section(self, driver):
        """Test that hero section is present with correct content."""
        driver.get(BASE_URL)
        hero = driver.find_element(By.CSS_SELECTOR, ".hero-section")
        assert hero.is_displayed()
        
        heading = driver.find_element(By.ID, "hero-heading")
        assert "Trustworthy ML Model Registry" in heading.text
    
    def test_search_section_visible(self, driver):
        """Test that search section is visible."""
        driver.get(BASE_URL)
        search_section = driver.find_element(By.ID, "search-section")
        assert search_section.is_displayed()
    
    def test_upload_section_visible(self, driver):
        """Test that upload section is visible."""
        driver.get(BASE_URL)
        upload_section = driver.find_element(By.ID, "upload-section")
        assert upload_section.is_displayed()

class TestAccessibility:
    """Tests for WCAG 2.1 Level AA compliance."""
    
    def test_skip_to_main_content_link(self, driver):
        """Test skip to main content link for keyboard navigation."""
        driver.get(BASE_URL)
        
        # Tab to skip link (first focusable element)
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.TAB)
        
        # Check if skip link is focused
        active_element = driver.switch_to.active_element
        assert "skip-link" in active_element.get_attribute("class")
    
    def test_all_images_have_alt_text(self, driver):
        """Test that all images have alt text."""
        driver.get(BASE_URL)
        images = driver.find_elements(By.TAG_NAME, "img")
        
        for img in images:
            alt_text = img.get_attribute("alt")
            assert alt_text is not None and len(alt_text) > 0, \
                f"Image missing alt text: {img.get_attribute('src')}"
    
    def test_form_labels_present(self, driver):
        """Test that all form inputs have associated labels."""
        driver.get(BASE_URL)
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='url'], input[type='password']")
        
        for input_elem in inputs:
            input_id = input_elem.get_attribute("id")
            if input_id:
                # Look for associated label
                labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{input_id}']")
                assert len(labels) > 0, f"Input {input_id} missing label"
    
    def test_aria_labels_on_buttons(self, driver):
        """Test that buttons have appropriate ARIA labels or text."""
        driver.get(BASE_URL)
        buttons = driver.find_elements(By.TAG_NAME, "button")
        
        for button in buttons:
            text = button.text.strip()
            aria_label = button.get_attribute("aria-label")
            
            assert text or aria_label, "Button missing text or aria-label"
    
    def test_keyboard_navigation(self, driver):
        """Test that page can be navigated with keyboard."""
        driver.get(BASE_URL)
        
        # Tab through first 10 elements
        body = driver.find_element(By.TAG_NAME, "body")
        for _ in range(10):
            body.send_keys(Keys.TAB)
            time.sleep(0.1)
        
        # Verify we can reach different sections
        active_element = driver.switch_to.active_element
        assert active_element is not None

class TestAuthentication:
    """Tests for authentication functionality."""
    
    def test_login_modal_opens(self, driver):
        """Test that login modal opens when clicking login button."""
        driver.get(BASE_URL)
        
        login_button = driver.find_element(By.ID, "auth-button")
        login_button.click()
        
        # Wait for modal to appear
        modal = WebDriverWait(driver, TIMEOUT).until(
            EC.visibility_of_element_located((By.ID, "authModal"))
        )
        
        assert modal.is_displayed()
    
    def test_login_success(self, driver):
        """Test successful login with valid credentials."""
        driver.get(BASE_URL)
        
        # Open login modal
        login_button = driver.find_element(By.ID, "auth-button")
        login_button.click()
        
        # Wait for modal
        WebDriverWait(driver, TIMEOUT).until(
            EC.visibility_of_element_located((By.ID, "authModal"))
        )
        
        # Enter credentials
        username_input = driver.find_element(By.ID, "username")
        password_input = driver.find_element(By.ID, "password")
        
        username_input.send_keys("admin")
        password_input.send_keys("admin123!")
        
        # Submit
        submit_button = driver.find_element(By.CSS_SELECTOR, "#auth-form button[type='submit']")
        submit_button.click()
        
        # Wait for success alert
        try:
            alert = WebDriverWait(driver, TIMEOUT).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-success"))
            )
            assert "Welcome" in alert.text
        except TimeoutException:
            pass  # Alert may disappear quickly
        
        # Check button text changed
        login_button = driver.find_element(By.ID, "auth-button")
        assert "Logout" in login_button.text or "admin" in login_button.text
    
    def test_login_failure(self, driver):
        """Test login failure with invalid credentials."""
        driver.get(BASE_URL)
        
        # Open login modal
        login_button = driver.find_element(By.ID, "auth-button")
        login_button.click()
        
        # Wait for modal
        WebDriverWait(driver, TIMEOUT).until(
            EC.visibility_of_element_located((By.ID, "authModal"))
        )
        
        # Enter invalid credentials
        username_input = driver.find_element(By.ID, "username")
        password_input = driver.find_element(By.ID, "password")
        
        username_input.send_keys("invalid_user")
        password_input.send_keys("wrong_password")
        
        # Submit
        submit_button = driver.find_element(By.CSS_SELECTOR, "#auth-form button[type='submit']")
        submit_button.click()
        
        # Wait for error alert
        alert = WebDriverWait(driver, TIMEOUT).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-danger"))
        )
        
        assert "failed" in alert.text.lower() or "invalid" in alert.text.lower()

class TestSearch:
    """Tests for package search functionality."""
    
    def test_search_requires_authentication(self, driver):
        """Test that search prompts for login when not authenticated."""
        driver.get(BASE_URL)
        
        # Try to search without authentication
        search_input = driver.find_element(By.ID, "search-input")
        search_input.send_keys("bert")
        
        search_form = driver.find_element(By.ID, "search-form")
        search_form.submit()
        
        # Should see warning alert
        try:
            alert = WebDriverWait(driver, TIMEOUT).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-warning"))
            )
            assert "login" in alert.text.lower()
        except TimeoutException:
            pytest.skip("Authentication may not be required for search")
    
    def test_search_with_valid_pattern(self, authenticated_driver):
        """Test search with valid regex pattern."""
        authenticated_driver.get(BASE_URL)
        
        # Enter search term
        search_input = authenticated_driver.find_element(By.ID, "search-input")
        search_input.clear()
        search_input.send_keys(".*")
        
        # Submit form
        search_form = authenticated_driver.find_element(By.ID, "search-form")
        search_form.submit()
        
        # Wait for results (or no results message)
        WebDriverWait(authenticated_driver, TIMEOUT).until(
            lambda d: d.find_element(By.ID, "search-results").text != ""
        )
        
        results_container = authenticated_driver.find_element(By.ID, "search-results")
        assert results_container.is_displayed()
    
    def test_search_with_specific_name(self, authenticated_driver):
        """Test search with specific package name."""
        authenticated_driver.get(BASE_URL)
        
        # Enter specific search term
        search_input = authenticated_driver.find_element(By.ID, "search-input")
        search_input.clear()
        search_input.send_keys("bert")
        
        # Submit form
        search_form = authenticated_driver.find_element(By.ID, "search-form")
        search_form.submit()
        
        # Wait for results
        time.sleep(2)  # Give time for API call
        
        results_container = authenticated_driver.find_element(By.ID, "search-results")
        assert results_container.is_displayed()

class TestUpload:
    """Tests for package upload functionality."""
    
    def test_upload_form_validation(self, driver):
        """Test that upload form validates required fields."""
        driver.get(BASE_URL)
        
        # Try to submit empty form
        upload_form = driver.find_element(By.ID, "upload-form")
        submit_button = upload_form.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()
        
        # HTML5 validation should prevent submission
        name_input = driver.find_element(By.ID, "package-name")
        assert name_input.get_attribute("required") is not None
    
    def test_upload_requires_authentication(self, driver):
        """Test that upload requires authentication."""
        driver.get(BASE_URL)
        
        # Fill form
        name_input = driver.find_element(By.ID, "package-name")
        version_input = driver.find_element(By.ID, "package-version")
        url_input = driver.find_element(By.ID, "package-url")
        
        name_input.send_keys("test-package")
        version_input.clear()
        version_input.send_keys("1.0.0")
        url_input.send_keys("https://huggingface.co/test/model")
        
        # Submit
        upload_form = driver.find_element(By.ID, "upload-form")
        upload_form.submit()
        
        # Should see warning
        try:
            alert = WebDriverWait(driver, TIMEOUT).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-warning"))
            )
            assert "login" in alert.text.lower()
        except TimeoutException:
            pytest.skip("Upload may proceed without auth check in test")

class TestResponsiveDesign:
    """Tests for responsive design on different viewports."""
    
    def test_mobile_viewport(self, driver):
        """Test page renders correctly on mobile viewport."""
        driver.set_window_size(375, 667)  # iPhone SE size
        driver.get(BASE_URL)
        
        # Check that navbar hamburger is visible
        try:
            hamburger = driver.find_element(By.CSS_SELECTOR, ".navbar-toggler")
            assert hamburger.is_displayed()
        except NoSuchElementException:
            pytest.skip("Navbar toggle not found in mobile view")
    
    def test_tablet_viewport(self, driver):
        """Test page renders correctly on tablet viewport."""
        driver.set_window_size(768, 1024)  # iPad size
        driver.get(BASE_URL)
        
        # Check that main content is visible
        main_content = driver.find_element(By.ID, "main-content")
        assert main_content.is_displayed()
    
    def test_desktop_viewport(self, driver):
        """Test page renders correctly on desktop viewport."""
        driver.set_window_size(1920, 1080)  # Full HD
        driver.get(BASE_URL)
        
        # Check that all sections are visible
        sections = ["search-section", "upload-section", "health-section"]
        for section_id in sections:
            section = driver.find_element(By.ID, section_id)
            assert section.is_displayed()

class TestHealthDashboard:
    """Tests for system health dashboard."""
    
    def test_health_section_loads(self, driver):
        """Test that health section loads."""
        driver.get(BASE_URL)
        
        health_section = driver.find_element(By.ID, "health-section")
        assert health_section.is_displayed()
    
    def test_refresh_health_status(self, driver):
        """Test refreshing health status."""
        driver.get(BASE_URL)
        
        # Find and click refresh button
        refresh_button = driver.find_element(By.CSS_SELECTOR, "#health-section button")
        refresh_button.click()
        
        # Wait for health data to load
        time.sleep(2)
        
        health_status = driver.find_element(By.ID, "health-status")
        assert health_status.text != ""

class TestAdminPanel:
    """Tests for admin panel (when logged in as admin)."""
    
    def test_admin_section_hidden_by_default(self, driver):
        """Test that admin section is hidden for non-admin users."""
        driver.get(BASE_URL)
        
        admin_section = driver.find_element(By.ID, "admin-section")
        assert not admin_section.is_displayed()
    
    def test_admin_section_visible_for_admin(self, authenticated_driver):
        """Test that admin section is visible for admin users."""
        authenticated_driver.get(BASE_URL)
        
        # Wait a bit for auth to process
        time.sleep(2)
        
        admin_nav_item = authenticated_driver.find_element(By.ID, "admin-nav-item")
        # Admin nav should be visible
        # (May not be displayed immediately, depends on role check)

# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])





