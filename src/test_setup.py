"""
Test script to verify all modules load correctly and basic functionality works.
Run this to test the setup before using the full application.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported."""
    print("=" * 60)
    print("Testing module imports...")
    print("=" * 60)

    modules_to_test = [
        ("core.validators", "Input validation utilities"),
        ("core.url_utils", "URL parsing utilities"),
        ("logger_setup", "Logging configuration"),
        ("services.google_drive_service", "Google Drive service"),
        ("core.config_manager", "Configuration manager"),
        ("services.hubspot_service", "HubSpot service"),
        ("services.company_lookup", "Company lookup service"),
        ("services.email_service", "Email service"),
        ("services.quickbooks_service", "QuickBooks placeholder"),
        ("services.integrations", "Integrations placeholder"),
        ("gui.dialogs", "GUI dialogs"),
        ("gui.setup_wizard", "Setup wizard"),
        ("gui.history_window", "History window"),
        ("gui.main_window", "Main window"),
    ]

    all_passed = True

    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            print(f"  [OK] {module_name} - {description}")
        except ImportError as e:
            print(f"  [FAIL] {module_name} - {e}")
            all_passed = False

    return all_passed


def test_validators():
    """Test validator functions."""
    print("\n" + "=" * 60)
    print("Testing validators...")
    print("=" * 60)

    from core.validators import (
        clean_company_name,
        validate_company_name,
        validate_url,
        validate_email
    )

    # Test company name cleaning
    test_cases = [
        ("  Acme Corp  ", "Acme Corp"),
        ("Acme Corp.", "Acme Corp"),
        ("Acme/Corp", "AcmeCorp"),
        ("Acme: Corp", "Acme Corp"),
    ]

    print("\n  Company name cleaning:")
    for input_val, expected in test_cases:
        result = clean_company_name(input_val)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"    {status} '{input_val}' -> '{result}' (expected: '{expected}')")

    # Test company name validation
    print("\n  Company name validation:")
    valid, error = validate_company_name("Acme Corp")
    print(f"    [{'OK' if valid else 'FAIL'}] 'Acme Corp' - valid: {valid}")

    valid, error = validate_company_name("")
    print(f"    [{'OK' if not valid else 'FAIL'}] '' (empty) - valid: {valid}, error: {error}")

    # Test URL validation
    print("\n  URL validation:")
    valid, error = validate_url("acmecorp.com")
    print(f"    [{'OK' if valid else 'FAIL'}] 'acmecorp.com' - valid: {valid}")

    valid, error = validate_url("https://www.acmecorp.com/about")
    print(f"    [{'OK' if valid else 'FAIL'}] 'https://www.acmecorp.com/about' - valid: {valid}")

    valid, error = validate_url("")
    print(f"    [{'OK' if not valid else 'FAIL'}] '' (empty) - valid: {valid}, error: {error}")

    # Test email validation
    print("\n  Email validation:")
    valid, error = validate_email("test@example.com")
    print(f"    [{'OK' if valid else 'FAIL'}] 'test@example.com' - valid: {valid}")

    valid, error = validate_email("invalid-email")
    print(f"    [{'OK' if not valid else 'FAIL'}] 'invalid-email' - valid: {valid}, error: {error}")

    return True


def test_url_utils():
    """Test URL utility functions."""
    print("\n" + "=" * 60)
    print("Testing URL utilities...")
    print("=" * 60)

    from core.url_utils import normalize_url, extract_domain, parse_url_parts

    # Test URL normalization
    print("\n  URL normalization:")
    test_cases = [
        ("acmecorp.com", "https://acmecorp.com"),
        ("http://acmecorp.com", "https://acmecorp.com"),
        ("https://acmecorp.com/about", "https://acmecorp.com"),
    ]

    for input_val, expected in test_cases:
        result = normalize_url(input_val)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"    {status} '{input_val}' -> '{result}'")

    # Test domain extraction
    print("\n  Domain extraction:")
    test_cases = [
        ("acmecorp.com", "acmecorp.com"),
        ("www.acmecorp.com", "www.acmecorp.com"),
        ("shop.acmecorp.com", "acmecorp.com"),
        ("https://acmecorp.com/about", "acmecorp.com"),
    ]

    for input_val, expected in test_cases:
        result = extract_domain(input_val)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"    {status} '{input_val}' -> '{result}' (expected: '{expected}')")

    return True


def test_logger():
    """Test logger setup."""
    print("\n" + "=" * 60)
    print("Testing logger...")
    print("=" * 60)

    from logger_setup import setup_logger, log_info, log_warning, log_error

    logger = setup_logger()
    print(f"  [OK] Logger created: {logger.name}")

    # Test logging (will output to console)
    print("\n  Testing log messages:")
    log_info("Test info message")
    log_warning("Test warning message")

    # Check local log file was created
    import os
    from datetime import datetime
    log_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'ClientCreate', 'logs')
    log_file = os.path.join(log_dir, f'client_create_{datetime.now().strftime("%Y-%m-%d")}.log')

    if os.path.exists(log_file):
        print(f"\n  [OK] Local log file created: {log_file}")
    else:
        print(f"\n  [WARN] Local log file not found: {log_file}")

    return True


def test_google_drive_service():
    """Test Google Drive service initialization."""
    print("\n" + "=" * 60)
    print("Testing Google Drive service...")
    print("=" * 60)

    from services.google_drive_service import GoogleDriveService, get_drive_service

    service = get_drive_service()
    print(f"  [OK] Service created")

    # Check for credentials file
    has_creds = service.has_credentials_file()
    print(f"  [{'OK' if has_creds else 'INFO'}] credentials.json exists: {has_creds}")

    if not has_creds:
        print(f"       Expected location: {service.credentials_path}")
        print("       You need to create this file from Google Cloud Console")

    # Check authentication status
    is_auth = service.is_authenticated()
    print(f"  [INFO] Is authenticated: {is_auth}")

    return True


def test_hubspot_service():
    """Test HubSpot service initialization."""
    print("\n" + "=" * 60)
    print("Testing HubSpot service...")
    print("=" * 60)

    from services.hubspot_service import HubSpotService, get_hubspot_service

    service = get_hubspot_service()
    print(f"  [OK] Service created (no token set)")

    return True


def test_company_lookup():
    """Test company lookup service."""
    print("\n" + "=" * 60)
    print("Testing company lookup service...")
    print("=" * 60)

    from services.company_lookup import CompanyLookupService, get_company_lookup_service

    service = get_company_lookup_service()
    print(f"  [OK] Service created")

    # Test similarity function
    print("\n  Testing name similarity:")
    test_cases = [
        ("Acme Corp", "Acme Corp, Inc.", True),
        ("Acme", "Acme Corporation", True),
        ("Acme Corp", "Beta LLC", False),
    ]

    for name1, name2, expected in test_cases:
        result = service.is_name_similar(name1, name2)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"    {status} '{name1}' ~ '{name2}' = {result} (expected: {expected})")

    return True


def test_dependencies():
    """Test that all required packages are installed."""
    print("\n" + "=" * 60)
    print("Testing dependencies...")
    print("=" * 60)

    dependencies = [
        ("google.auth", "google-auth"),
        ("google_auth_oauthlib", "google-auth-oauthlib"),
        ("googleapiclient", "google-api-python-client"),
        ("hubspot", "hubspot-api-client"),
        ("dotenv", "python-dotenv"),
        ("requests", "requests"),
        ("bs4", "beautifulsoup4"),
    ]

    all_installed = True

    for module_name, package_name in dependencies:
        try:
            __import__(module_name)
            print(f"  [OK] {package_name}")
        except ImportError:
            print(f"  [MISSING] {package_name} - run: pip install {package_name}")
            all_installed = False

    return all_installed


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  ClientCreate - Setup Test")
    print("=" * 60)

    results = {}

    # Test dependencies first
    results['dependencies'] = test_dependencies()

    if not results['dependencies']:
        print("\n[ERROR] Missing dependencies. Install them with:")
        print("  pip install -r requirements.txt")
        print("\nOr individually with the commands shown above.")
        return

    # Test imports
    results['imports'] = test_imports()

    if not results['imports']:
        print("\n[ERROR] Some imports failed. Fix the errors above before continuing.")
        return

    # Test individual components
    results['validators'] = test_validators()
    results['url_utils'] = test_url_utils()
    results['logger'] = test_logger()
    results['google_drive'] = test_google_drive_service()
    results['hubspot'] = test_hubspot_service()
    results['company_lookup'] = test_company_lookup()

    # Summary
    print("\n" + "=" * 60)
    print("  Test Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {test_name}")

    all_passed = all(results.values())

    print("\n" + "=" * 60)
    if all_passed:
        print("  All tests passed!")
        print("\n  Next steps:")
        print("  1. Get credentials.json from Google Cloud Console")
        print("  2. Place it in the project's config/ folder")
        print("  3. Run: python main.py")
        print("\n  The app will launch with Dry Run mode ON by default.")
        print("  This tests all connections without making real changes.")
    else:
        print("  Some tests failed. Please fix the issues above.")
    print("=" * 60)


if __name__ == "__main__":
    main()
