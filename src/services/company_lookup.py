"""
Company name lookup and verification service for ClientCreate.

Attempts to find the formal/legal company name and address by:
1. Scraping the website for meta tags, title, footer, Contact Us page
2. Checking SSL certificate organization
3. Using Google Places API (if configured)
4. Checking MA Corp database (Massachusetts corporations)
"""

import re
import ssl
import socket
import json
from typing import Optional, List, Tuple, Dict
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from logger_setup import log_info, log_warning, log_debug, log_error


@dataclass
class CompanyAddress:
    """Company address information."""
    line1: str = ""
    line2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = "USA"

    def is_empty(self) -> bool:
        """Check if address is empty."""
        return not any([self.line1, self.city, self.state, self.postal_code])

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'line1': self.line1,
            'line2': self.line2,
            'city': self.city,
            'state': self.state,
            'postal_code': self.postal_code,
            'country': self.country
        }

    def format_single_line(self) -> str:
        """Format as single line."""
        parts = []
        if self.line1:
            parts.append(self.line1)
        if self.line2:
            parts.append(self.line2)
        if self.city:
            parts.append(self.city)
        if self.state and self.postal_code:
            parts.append(f"{self.state} {self.postal_code}")
        elif self.state:
            parts.append(self.state)
        elif self.postal_code:
            parts.append(self.postal_code)
        return ", ".join(parts)


@dataclass
class CompanyInfo:
    """Complete company information."""
    name: str = ""
    legal_name: str = ""
    address: CompanyAddress = field(default_factory=CompanyAddress)
    phone: str = ""
    email: str = ""
    found_names: List[str] = field(default_factory=list)
    source: str = ""  # Where the info was found


# Common legal suffixes to help identify formal names
LEGAL_SUFFIXES = [
    'Inc.', 'Inc', 'LLC', 'L.L.C.', 'Ltd.', 'Ltd', 'Limited',
    'Corp.', 'Corp', 'Corporation', 'Co.', 'Company',
    'LP', 'L.P.', 'LLP', 'L.L.P.', 'PC', 'P.C.',
    'PLLC', 'P.L.L.C.', 'PLC', 'P.L.C.'
]


class CompanyLookupService:
    """Service for looking up and verifying company names."""

    def __init__(self, places_api_key: Optional[str] = None):
        """
        Initialize company lookup service.

        Args:
            places_api_key: Google Places API key (optional)
        """
        self.places_api_key = places_api_key
        self.timeout = 10  # seconds

    def set_places_api_key(self, api_key: str):
        """Set or update the Google Places API key."""
        self.places_api_key = api_key

    def lookup_formal_name(self, url: str, entered_name: str) -> Tuple[Optional[str], List[str]]:
        """
        Attempt to find the formal company name from various sources.

        Args:
            url: Company website URL
            entered_name: Name entered by user (for comparison)

        Returns:
            Tuple of (best_match_name, list_of_all_found_names)
        """
        found_names = []

        # Try website scraping
        web_names = self._scrape_website(url)
        found_names.extend(web_names)

        # Try SSL certificate
        ssl_name = self._check_ssl_certificate(url)
        if ssl_name:
            found_names.append(ssl_name)

        # Try Google Places API
        if self.places_api_key:
            places_name = self._lookup_google_places(url, entered_name)
            if places_name:
                found_names.append(places_name)

        # Remove duplicates while preserving order
        seen = set()
        unique_names = []
        for name in found_names:
            normalized = name.lower().strip()
            if normalized not in seen and name.strip():
                seen.add(normalized)
                unique_names.append(name.strip())

        # Find best match (prefer names with legal suffixes, or closest to entered name)
        best_match = self._find_best_match(unique_names, entered_name)

        return best_match, unique_names

    def lookup_company_info(self, url: str, entered_name: str) -> CompanyInfo:
        """
        Look up complete company information including address.

        Args:
            url: Company website URL
            entered_name: Name entered by user

        Returns:
            CompanyInfo with name and address data
        """
        info = CompanyInfo()
        info.found_names = []

        # Try website scraping for name and address
        web_names, web_address = self._scrape_website_full(url)
        info.found_names.extend(web_names)
        if not info.address.is_empty() or web_address and not web_address.is_empty():
            info.address = web_address
            info.source = "website"

        # Try Contact Us page for address
        if info.address.is_empty():
            contact_address = self._scrape_contact_page(url)
            if contact_address and not contact_address.is_empty():
                info.address = contact_address
                info.source = "contact page"

        # Try SSL certificate for name
        ssl_name = self._check_ssl_certificate(url)
        if ssl_name:
            info.found_names.append(ssl_name)

        # Try Google Places API for name and address
        if self.places_api_key:
            places_name, places_address = self._lookup_google_places_full(url, entered_name)
            if places_name:
                info.found_names.append(places_name)
            if info.address.is_empty() and places_address and not places_address.is_empty():
                info.address = places_address
                info.source = "Google Places"

        # Try MA Corp database for address
        if info.address.is_empty():
            corp_address = self._lookup_ma_corp(entered_name)
            if corp_address and not corp_address.is_empty():
                info.address = corp_address
                info.source = "MA Corp database"

        # Remove duplicate names
        seen = set()
        unique_names = []
        for name in info.found_names:
            normalized = name.lower().strip()
            if normalized not in seen and name.strip():
                seen.add(normalized)
                unique_names.append(name.strip())
        info.found_names = unique_names

        # Find best match name
        info.name = self._find_best_match(unique_names, entered_name) or entered_name
        info.legal_name = info.name

        return info

    def _scrape_website_full(self, url: str) -> Tuple[List[str], CompanyAddress]:
        """
        Scrape website for company names and address.

        Returns:
            Tuple of (list of names, address)
        """
        found_names = []
        address = CompanyAddress()

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Get names (existing logic)
            og_site_name = soup.find('meta', property='og:site_name')
            if og_site_name and og_site_name.get('content'):
                found_names.append(og_site_name['content'])
                log_debug(f"Found og:site_name: {og_site_name['content']}")

            title = soup.find('title')
            if title and title.string:
                title_text = title.string.strip()
                title_parts = re.split(r'\s*[|\-–—]\s*', title_text)
                if title_parts:
                    found_names.append(title_parts[0].strip())
                    log_debug(f"Found title: {title_parts[0].strip()}")

            footer_names = self._extract_from_footer(soup)
            found_names.extend(footer_names)

            schema_names, schema_address = self._extract_from_schema_full(soup)
            found_names.extend(schema_names)
            if schema_address and not schema_address.is_empty():
                address = schema_address

        except Exception as e:
            log_warning(f"Error scraping website: {e}")

        return found_names, address

    def _scrape_contact_page(self, url: str) -> Optional[CompanyAddress]:
        """
        Try to find and scrape the Contact Us page for address.

        Args:
            url: Base website URL

        Returns:
            CompanyAddress if found
        """
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Common contact page paths
        contact_paths = [
            '/contact', '/contact-us', '/contactus', '/contact.html',
            '/about/contact', '/company/contact', '/get-in-touch',
            '/reach-us', '/locations', '/about'
        ]

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        for path in contact_paths:
            try:
                contact_url = urljoin(url, path)
                response = requests.get(contact_url, headers=headers, timeout=self.timeout)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')

                    # Try to extract address from schema.org
                    _, schema_address = self._extract_from_schema_full(soup)
                    if schema_address and not schema_address.is_empty():
                        log_debug(f"Found address on {path} via schema.org")
                        return schema_address

                    # Try to extract address from page text
                    address = self._extract_address_from_text(soup)
                    if address and not address.is_empty():
                        log_debug(f"Found address on {path}")
                        return address

            except Exception as e:
                continue

        return None

    def _extract_address_from_text(self, soup: BeautifulSoup) -> Optional[CompanyAddress]:
        """
        Try to extract US address from page text.

        Args:
            soup: BeautifulSoup parsed page

        Returns:
            CompanyAddress if found
        """
        # Look for common address patterns
        text = soup.get_text()

        # US address pattern: Street, City, ST ZIP
        # Example: 123 Main Street, Boston, MA 02101
        address_pattern = r'(\d+[^,\n]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Court|Ct|Place|Pl|Suite|Ste)[^,\n]*)[,\s]+([A-Za-z\s]+)[,\s]+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)'

        match = re.search(address_pattern, text, re.IGNORECASE)
        if match:
            return CompanyAddress(
                line1=match.group(1).strip(),
                city=match.group(2).strip(),
                state=match.group(3).upper(),
                postal_code=match.group(4)
            )

        # Try simpler pattern: City, ST ZIP
        simple_pattern = r'([A-Za-z\s]+)[,\s]+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)'
        match = re.search(simple_pattern, text)
        if match:
            return CompanyAddress(
                city=match.group(1).strip(),
                state=match.group(2).upper(),
                postal_code=match.group(3)
            )

        return None

    def _extract_from_schema_full(self, soup: BeautifulSoup) -> Tuple[List[str], Optional[CompanyAddress]]:
        """Extract company names and address from schema.org structured data."""
        found_names = []
        address = None

        scripts = soup.find_all('script', type='application/ld+json')

        for script in scripts:
            try:
                data = json.loads(script.string)

                if isinstance(data, list):
                    items = data
                else:
                    items = [data]

                for item in items:
                    if isinstance(item, dict):
                        # Check for Organization type
                        if item.get('@type') in ['Organization', 'Corporation', 'LocalBusiness', 'Company']:
                            name = item.get('name')
                            if name:
                                found_names.append(name)
                                log_debug(f"Found schema.org name: {name}")

                            legal_name = item.get('legalName')
                            if legal_name:
                                found_names.append(legal_name)
                                log_debug(f"Found schema.org legalName: {legal_name}")

                            # Extract address
                            addr_data = item.get('address')
                            if addr_data and isinstance(addr_data, dict):
                                address = CompanyAddress(
                                    line1=addr_data.get('streetAddress', ''),
                                    city=addr_data.get('addressLocality', ''),
                                    state=addr_data.get('addressRegion', ''),
                                    postal_code=addr_data.get('postalCode', ''),
                                    country=addr_data.get('addressCountry', 'USA')
                                )
                                log_debug(f"Found schema.org address: {address.format_single_line()}")

            except (json.JSONDecodeError, TypeError):
                continue

        return found_names, address

    def _lookup_google_places_full(self, url: str, company_name: str) -> Tuple[Optional[str], Optional[CompanyAddress]]:
        """
        Look up company using Google Places API, returning name and address.

        Returns:
            Tuple of (name, address)
        """
        if not self.places_api_key:
            return None, None

        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]

            search_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
            params = {
                'input': company_name,
                'inputtype': 'textquery',
                'fields': 'name,formatted_address,place_id',
                'key': self.places_api_key
            }

            response = requests.get(search_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if data.get('status') == 'OK' and data.get('candidates'):
                candidate = data['candidates'][0]
                places_name = candidate.get('name')
                formatted_address = candidate.get('formatted_address', '')

                # Parse the formatted address
                address = self._parse_formatted_address(formatted_address)

                log_debug(f"Found Google Places: {places_name}, {formatted_address}")
                return places_name, address

        except Exception as e:
            log_warning(f"Google Places lookup failed: {e}")

        return None, None

    def _parse_formatted_address(self, formatted: str) -> CompanyAddress:
        """Parse Google's formatted address string."""
        address = CompanyAddress()

        if not formatted:
            return address

        # Google format: "123 Main St, Boston, MA 02101, USA"
        parts = [p.strip() for p in formatted.split(',')]

        if len(parts) >= 4:
            address.line1 = parts[0]
            address.city = parts[1]
            # State and ZIP often together: "MA 02101"
            state_zip = parts[2].strip().split()
            if len(state_zip) >= 1:
                address.state = state_zip[0]
            if len(state_zip) >= 2:
                address.postal_code = state_zip[1]
            address.country = parts[3] if len(parts) > 3 else 'USA'
        elif len(parts) == 3:
            address.line1 = parts[0]
            address.city = parts[1]
            state_zip = parts[2].strip().split()
            if len(state_zip) >= 1:
                address.state = state_zip[0]
            if len(state_zip) >= 2:
                address.postal_code = state_zip[1]

        return address

    def _lookup_ma_corp(self, company_name: str) -> Optional[CompanyAddress]:
        """
        Look up company in Massachusetts Corporations database.

        Args:
            company_name: Company name to search

        Returns:
            CompanyAddress if found
        """
        try:
            # MA Corp search URL
            search_url = "https://corp.sec.state.ma.us/CorpWeb/CorpSearch/CorpSearchResults.aspx"

            # First, try to search for the company
            # Note: MA Corp website may require session handling
            # This is a simplified approach - may need enhancement

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            # Try the direct search API if available
            search_api = "https://corp.sec.state.ma.us/CorpWeb/CorpSearch/CorpSearchSvc.asmx/GetCorpSearchResults"

            # Clean company name for search
            clean_name = re.sub(r'[^\w\s]', '', company_name).strip()

            log_debug(f"Searching MA Corp database for: {clean_name}")

            # The MA Corp website uses AJAX, so we'd need to properly handle that
            # For now, log that we attempted and return None
            # A full implementation would require handling ASP.NET ViewState and AJAX calls

            log_debug("MA Corp database lookup - requires enhanced implementation")

        except Exception as e:
            log_debug(f"MA Corp lookup failed: {e}")

        return None

    def _scrape_website(self, url: str) -> List[str]:
        """
        Scrape website for potential company names.

        Args:
            url: Website URL

        Returns:
            List of potential company names found
        """
        found_names = []

        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Check og:site_name meta tag
            og_site_name = soup.find('meta', property='og:site_name')
            if og_site_name and og_site_name.get('content'):
                found_names.append(og_site_name['content'])
                log_debug(f"Found og:site_name: {og_site_name['content']}")

            # Check title tag
            title = soup.find('title')
            if title and title.string:
                # Clean up title (often has " - tagline" or " | page name")
                title_text = title.string.strip()
                title_parts = re.split(r'\s*[|\-–—]\s*', title_text)
                if title_parts:
                    found_names.append(title_parts[0].strip())
                    log_debug(f"Found title: {title_parts[0].strip()}")

            # Check footer for copyright text
            footer_names = self._extract_from_footer(soup)
            found_names.extend(footer_names)

            # Check schema.org Organization data
            schema_names = self._extract_from_schema(soup)
            found_names.extend(schema_names)

        except requests.exceptions.Timeout:
            log_warning(f"Timeout fetching website: {url}")
        except requests.exceptions.RequestException as e:
            log_warning(f"Error fetching website: {e}")
        except Exception as e:
            log_warning(f"Error parsing website: {e}")

        return found_names

    def _extract_from_footer(self, soup: BeautifulSoup) -> List[str]:
        """Extract company names from footer copyright text."""
        found_names = []

        # Look for footer elements
        footer = soup.find('footer')
        if not footer:
            footer = soup.find(class_=re.compile(r'footer', re.I))

        if footer:
            footer_text = footer.get_text()

            # Look for copyright patterns: © 2024 Company Name, Inc.
            copyright_pattern = r'©\s*\d{4}\s+([^.©]+(?:' + '|'.join(re.escape(s) for s in LEGAL_SUFFIXES) + r')[.]*)'
            matches = re.findall(copyright_pattern, footer_text, re.IGNORECASE)

            for match in matches:
                clean_name = match.strip()
                if clean_name and len(clean_name) < 100:  # Sanity check
                    found_names.append(clean_name)
                    log_debug(f"Found footer copyright: {clean_name}")

            # Also try simpler pattern: © 2024 Company Name
            simple_pattern = r'©\s*\d{4}\s+([A-Z][A-Za-z\s&]+?)(?:\.|All Rights|$)'
            matches = re.findall(simple_pattern, footer_text)

            for match in matches:
                clean_name = match.strip()
                if clean_name and len(clean_name) < 100 and len(clean_name) > 2:
                    found_names.append(clean_name)

        return found_names

    def _extract_from_schema(self, soup: BeautifulSoup) -> List[str]:
        """Extract company names from schema.org structured data."""
        found_names = []

        # Look for JSON-LD script tags
        scripts = soup.find_all('script', type='application/ld+json')

        for script in scripts:
            try:
                import json
                data = json.loads(script.string)

                # Handle both single objects and arrays
                if isinstance(data, list):
                    items = data
                else:
                    items = [data]

                for item in items:
                    if isinstance(item, dict):
                        # Check for Organization type
                        if item.get('@type') in ['Organization', 'Corporation', 'LocalBusiness']:
                            name = item.get('name')
                            if name:
                                found_names.append(name)
                                log_debug(f"Found schema.org name: {name}")

                        # Check for legalName
                        legal_name = item.get('legalName')
                        if legal_name:
                            found_names.append(legal_name)
                            log_debug(f"Found schema.org legalName: {legal_name}")

            except (json.JSONDecodeError, TypeError):
                continue

        return found_names

    def _check_ssl_certificate(self, url: str) -> Optional[str]:
        """
        Check SSL certificate for organization name.

        Args:
            url: Website URL

        Returns:
            Organization name from certificate, or None
        """
        try:
            # Parse hostname from URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            parsed = urlparse(url)
            hostname = parsed.netloc or parsed.path.split('/')[0]
            hostname = hostname.split(':')[0]  # Remove port if present

            # Get SSL certificate
            context = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()

            # Look for organization in subject
            subject = dict(x[0] for x in cert.get('subject', []))
            org_name = subject.get('organizationName')

            if org_name:
                log_debug(f"Found SSL certificate org: {org_name}")
                return org_name

        except Exception as e:
            log_debug(f"Could not check SSL certificate: {e}")

        return None

    def _lookup_google_places(self, url: str, company_name: str) -> Optional[str]:
        """
        Look up company using Google Places API.

        Args:
            url: Company website URL
            company_name: Company name for search

        Returns:
            Official business name from Google Places, or None
        """
        if not self.places_api_key:
            return None

        try:
            # Extract domain for search
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]

            # Search using company name
            search_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
            params = {
                'input': company_name,
                'inputtype': 'textquery',
                'fields': 'name,formatted_address,website',
                'key': self.places_api_key
            }

            response = requests.get(search_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if data.get('status') == 'OK' and data.get('candidates'):
                candidate = data['candidates'][0]
                places_name = candidate.get('name')

                # Verify this is likely the right business by checking website
                candidate_website = candidate.get('website', '')
                if domain.lower() in candidate_website.lower() or not candidate_website:
                    log_debug(f"Found Google Places name: {places_name}")
                    return places_name

        except Exception as e:
            log_warning(f"Google Places lookup failed: {e}")

        return None

    def _find_best_match(self, names: List[str], entered_name: str) -> Optional[str]:
        """
        Find the best matching name from candidates.

        Prefers:
        1. Names with legal suffixes (Inc., LLC, etc.)
        2. Names similar to what user entered

        Args:
            names: List of candidate names
            entered_name: Name entered by user

        Returns:
            Best matching name, or None
        """
        if not names:
            return None

        entered_lower = entered_name.lower()

        # Score each name
        scored_names = []
        for name in names:
            score = 0
            name_lower = name.lower()

            # Bonus for having a legal suffix
            for suffix in LEGAL_SUFFIXES:
                if suffix.lower() in name_lower:
                    score += 10
                    break

            # Bonus for containing the entered name
            if entered_lower in name_lower:
                score += 5

            # Bonus for similarity in length
            len_diff = abs(len(name) - len(entered_name))
            if len_diff < 10:
                score += (10 - len_diff)

            # Penalty for very short or very long names
            if len(name) < 3 or len(name) > 100:
                score -= 20

            scored_names.append((name, score))

        # Sort by score (highest first)
        scored_names.sort(key=lambda x: x[1], reverse=True)

        # Return the best match if it has a reasonable score
        if scored_names and scored_names[0][1] > 0:
            return scored_names[0][0]

        return names[0] if names else None

    def is_name_similar(self, name1: str, name2: str) -> bool:
        """
        Check if two company names are similar enough.

        Args:
            name1: First company name
            name2: Second company name

        Returns:
            True if names are considered similar
        """
        # Normalize names
        def normalize(name):
            # Remove common suffixes for comparison
            for suffix in LEGAL_SUFFIXES:
                name = re.sub(r'\s*' + re.escape(suffix) + r'\s*$', '', name, flags=re.IGNORECASE)
            # Remove punctuation and extra spaces
            name = re.sub(r'[^\w\s]', '', name)
            name = ' '.join(name.split())
            return name.lower().strip()

        n1 = normalize(name1)
        n2 = normalize(name2)

        # Exact match after normalization
        if n1 == n2:
            return True

        # One contains the other
        if n1 in n2 or n2 in n1:
            return True

        # Simple word overlap check
        words1 = set(n1.split())
        words2 = set(n2.split())

        if not words1 or not words2:
            return False

        overlap = len(words1 & words2)
        total = min(len(words1), len(words2))

        # At least 50% word overlap
        return overlap >= total * 0.5


def test_places_api(api_key: str) -> Tuple[bool, Optional[str]]:
    """
    Test if a Google Places API key is valid.

    Args:
        api_key: API key to test

    Returns:
        Tuple of (success, error_message)
    """
    try:
        search_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        params = {
            'input': 'Google',
            'inputtype': 'textquery',
            'fields': 'name',
            'key': api_key
        }

        response = requests.get(search_url, params=params, timeout=10)
        data = response.json()

        if data.get('status') == 'OK':
            return True, None
        elif data.get('status') == 'REQUEST_DENIED':
            return False, "API key is invalid or Places API is not enabled"
        else:
            return False, f"API returned status: {data.get('status')}"

    except Exception as e:
        return False, str(e)


# Singleton instance
_lookup_service: Optional[CompanyLookupService] = None


def get_company_lookup_service() -> CompanyLookupService:
    """Get or create the company lookup service instance."""
    global _lookup_service
    if _lookup_service is None:
        _lookup_service = CompanyLookupService()
    return _lookup_service
