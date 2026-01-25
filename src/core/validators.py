"""
Input validation and cleanup utilities for ClientCreate.
"""

import re
from typing import Tuple, Optional


def clean_company_name(name: str) -> str:
    """
    Clean and normalize company name for use as folder name.

    - Trims leading/trailing whitespace
    - Removes trailing periods
    - Removes invalid folder characters: \\ / : * ? " < > |

    Args:
        name: Raw company name input

    Returns:
        Cleaned company name safe for folder creation
    """
    if not name:
        return ""

    # Trim whitespace
    cleaned = name.strip()

    # Remove trailing periods
    while cleaned.endswith('.'):
        cleaned = cleaned[:-1].strip()

    # Remove invalid folder characters
    invalid_chars = r'[\\/:*?"<>|]'
    cleaned = re.sub(invalid_chars, '', cleaned)

    # Collapse multiple spaces into one
    cleaned = re.sub(r'\s+', ' ', cleaned)

    return cleaned.strip()


def validate_company_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate company name input.

    Args:
        name: Company name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name or not name.strip():
        return False, "Company name is required"

    cleaned = clean_company_name(name)

    if not cleaned:
        return False, "Company name contains only invalid characters"

    if len(cleaned) < 2:
        return False, "Company name must be at least 2 characters"

    if len(cleaned) > 255:
        return False, "Company name must be less than 255 characters"

    return True, None


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate URL input.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url or not url.strip():
        return False, "Website URL is required"

    url = url.strip()

    # Basic URL pattern check (loose validation)
    # Accepts with or without protocol
    pattern = r'^(https?://)?([\w\-]+\.)+[\w\-]+(/.*)?$'

    if not re.match(pattern, url, re.IGNORECASE):
        return False, "Invalid URL format. Example: acmecorp.com or https://acmecorp.com"

    return True, None


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate email address.

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email or not email.strip():
        return False, "Email address is required"

    email = email.strip()

    # Basic email pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(pattern, email):
        return False, "Invalid email format"

    return True, None


def validate_emails(emails_str: str) -> Tuple[bool, Optional[str], list]:
    """
    Validate comma-separated list of email addresses.

    Args:
        emails_str: Comma-separated email addresses

    Returns:
        Tuple of (is_valid, error_message, list_of_valid_emails)
    """
    if not emails_str or not emails_str.strip():
        return False, "At least one email address is required", []

    emails = [e.strip() for e in emails_str.split(',') if e.strip()]

    if not emails:
        return False, "At least one email address is required", []

    valid_emails = []
    invalid_emails = []

    for email in emails:
        is_valid, _ = validate_email(email)
        if is_valid:
            valid_emails.append(email)
        else:
            invalid_emails.append(email)

    if invalid_emails:
        return False, f"Invalid email(s): {', '.join(invalid_emails)}", valid_emails

    return True, None, valid_emails


def validate_api_key(key: str, key_name: str = "API key") -> Tuple[bool, Optional[str]]:
    """
    Basic validation for API keys.

    Args:
        key: API key to validate
        key_name: Name of the key for error messages

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not key or not key.strip():
        return False, f"{key_name} is required"

    key = key.strip()

    if len(key) < 10:
        return False, f"{key_name} appears to be too short"

    return True, None


def validate_folder_id(folder_id: str, folder_name: str = "Folder ID") -> Tuple[bool, Optional[str]]:
    """
    Basic validation for Google Drive folder IDs.

    Args:
        folder_id: Folder ID to validate
        folder_name: Name for error messages

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not folder_id or not folder_id.strip():
        return False, f"{folder_name} is required"

    folder_id = folder_id.strip()

    # Google Drive IDs are typically alphanumeric with some special chars
    if len(folder_id) < 10:
        return False, f"{folder_name} appears to be too short"

    # Basic pattern check - Google IDs are usually base64-like
    pattern = r'^[a-zA-Z0-9_-]+$'
    if not re.match(pattern, folder_id):
        return False, f"{folder_name} contains invalid characters"

    return True, None
