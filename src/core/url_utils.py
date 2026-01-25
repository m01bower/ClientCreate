"""
URL parsing and domain extraction utilities for ClientCreate.
"""

import re
from urllib.parse import urlparse
from typing import Tuple, Optional


def normalize_url(url: str) -> str:
    """
    Normalize URL by ensuring it has a protocol and removing paths.

    Args:
        url: Raw URL input

    Returns:
        Normalized URL with https:// prefix
    """
    if not url:
        return ""

    url = url.strip()

    # Add https:// if no protocol specified
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Upgrade http to https
    if url.startswith('http://'):
        url = 'https://' + url[7:]

    # Parse and rebuild without path
    parsed = urlparse(url)
    normalized = f"https://{parsed.netloc}"

    return normalized


def extract_domain(url: str) -> str:
    """
    Extract the root domain from a URL, stripping subdomains (except www).

    Examples:
        acmecorp.com -> acmecorp.com
        www.acmecorp.com -> www.acmecorp.com
        shop.acmecorp.com -> acmecorp.com
        https://acmecorp.com/about -> acmecorp.com

    Args:
        url: URL to extract domain from

    Returns:
        Root domain suitable for HubSpot
    """
    if not url:
        return ""

    url = url.strip().lower()

    # Add protocol if missing for parsing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    parsed = urlparse(url)
    hostname = parsed.netloc or parsed.path.split('/')[0]

    # Remove port if present
    hostname = hostname.split(':')[0]

    if not hostname:
        return ""

    # Split into parts
    parts = hostname.split('.')

    # Handle special cases
    if len(parts) <= 2:
        # Already a root domain (e.g., acmecorp.com)
        return hostname

    # Check if it starts with www
    if parts[0] == 'www':
        # Keep www prefix (e.g., www.acmecorp.com)
        return hostname

    # Handle common TLDs with two parts (e.g., .co.uk, .com.au)
    two_part_tlds = ['co.uk', 'com.au', 'co.nz', 'co.jp', 'com.br', 'co.in']

    potential_tld = '.'.join(parts[-2:])
    if potential_tld in two_part_tlds:
        # Return last 3 parts (domain + two-part TLD)
        return '.'.join(parts[-3:])

    # Default: return last 2 parts (domain + TLD)
    return '.'.join(parts[-2:])


def extract_domain_for_hubspot(url: str) -> str:
    """
    Extract domain specifically formatted for HubSpot.
    HubSpot prefers domains with www if that's how the site is accessed.

    Args:
        url: URL to extract domain from

    Returns:
        Domain formatted for HubSpot
    """
    return extract_domain(url)


def get_base_url_for_fetch(url: str) -> str:
    """
    Get the base URL for fetching website content.
    Tries with www if the base domain doesn't include it.

    Args:
        url: URL to process

    Returns:
        Full URL suitable for HTTP requests
    """
    normalized = normalize_url(url)
    return normalized


def parse_url_parts(url: str) -> dict:
    """
    Parse URL into its component parts.

    Args:
        url: URL to parse

    Returns:
        Dictionary with url parts
    """
    if not url:
        return {
            'original': '',
            'normalized': '',
            'domain': '',
            'domain_for_hubspot': '',
            'fetch_url': ''
        }

    normalized = normalize_url(url)
    domain = extract_domain(url)

    return {
        'original': url,
        'normalized': normalized,
        'domain': domain,
        'domain_for_hubspot': extract_domain_for_hubspot(url),
        'fetch_url': get_base_url_for_fetch(url)
    }
