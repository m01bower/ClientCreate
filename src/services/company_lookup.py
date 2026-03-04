"""
Company name lookup and verification service for ClientCreate.

Attempts to find the formal/legal company name and address by:
1. Scraping the website for meta tags, title, footer, Contact Us page
2. Checking SSL certificate organization
3. Using Google Knowledge Graph API for authoritative entity name
4. Using Google Places API (if configured)
5. Checking MA Corp database (Massachusetts corporations)
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
class Executive:
    """Executive/leadership team member."""
    name: str = ""
    title: str = ""           # CEO, CFO, COO, President, etc.
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""


@dataclass
class SocialMedia:
    """Company social media URLs."""
    linkedin_url: str = ""    # https://linkedin.com/company/...
    twitter_url: str = ""     # https://twitter.com/... or x.com/...
    facebook_url: str = ""
    instagram_url: str = ""
    youtube_url: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if v}


@dataclass
class CorpRegistration:
    """State corporate registration data."""
    state: str = ""               # MA, DE
    entity_name: str = ""
    entity_number: str = ""
    status: str = ""              # Active, Dissolved, etc.
    formation_date: str = ""
    registered_address: str = ""
    jurisdiction: str = ""        # us_ma, us_de
    opencorporates_url: str = ""


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
    executives: List[Executive] = field(default_factory=list)
    social_media: SocialMedia = field(default_factory=SocialMedia)
    corp_registration: Optional[CorpRegistration] = None


# Common legal suffixes to help identify formal names
LEGAL_SUFFIXES = [
    'Inc.', 'Inc', 'LLC', 'L.L.C.', 'Ltd.', 'Ltd', 'Limited',
    'Corp.', 'Corp', 'Corporation', 'Co.', 'Company',
    'LP', 'L.P.', 'LLP', 'L.L.P.', 'PC', 'P.C.',
    'PLLC', 'P.L.L.C.', 'PLC', 'P.L.C.'
]


class CompanyLookupService:
    """Service for looking up and verifying company names."""

    def __init__(self, places_api_key: Optional[str] = None, opencorporates_token: Optional[str] = None):
        """
        Initialize company lookup service.

        Args:
            places_api_key: Google Places API key (optional)
            opencorporates_token: OpenCorporates API token (optional, increases rate limits)
        """
        self.places_api_key = places_api_key
        self.opencorporates_token = opencorporates_token
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

        # Try Google Knowledge Graph for authoritative entity name
        if self.places_api_key:
            kg_name = self._lookup_knowledge_graph(entered_name, url)
            if kg_name:
                info.found_names.append(kg_name)

        # Try Google Places API for name and address
        if self.places_api_key:
            places_name, places_address = self._lookup_google_places_full(url, entered_name)
            if places_name:
                info.found_names.append(places_name)
            if info.address.is_empty() and places_address and not places_address.is_empty():
                info.address = places_address
                info.source = "Google Places"

        # State corp registration (MA first, then DE fallback)
        corp_reg, corp_address = self._lookup_state_corps(entered_name)
        if corp_reg:
            info.corp_registration = corp_reg
            if corp_reg.entity_name:
                info.found_names.append(corp_reg.entity_name)
            if info.address.is_empty() and corp_address and not corp_address.is_empty():
                info.address = corp_address
                info.source = f"{corp_reg.state} Secretary of State"

        # Social media from website
        info.social_media = self._scrape_social_media(url)

        # Executives from team/about pages
        info.executives = self._scrape_executives(url)

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

    def _lookup_knowledge_graph(self, company_name: str, url: str) -> Optional[str]:
        """
        Look up company using Google Knowledge Graph Search API.

        Returns the authoritative entity name if a high-confidence match is found.
        Uses the same API key as Google Places. If the initial query finds no match,
        retries with "headquarters" appended (helps surface smaller companies).

        Args:
            company_name: Company name to search
            url: Company website URL for domain matching

        Returns:
            Best matching company name, or None
        """
        if not self.places_api_key:
            return None

        try:
            # Extract domain for matching
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            parsed = urlparse(url)
            domain = (parsed.netloc or parsed.path.split('/')[0]).lower()
            if domain.startswith('www.'):
                domain = domain[4:]

            # Try the company name as-is first, then with "headquarters" appended
            queries = [company_name, f"{company_name} headquarters"]

            for query in queries:
                result = self._kg_search(query, domain)
                if result:
                    return result

            log_debug(f"Knowledge Graph: no match for '{company_name}' (tried {len(queries)} queries)")

        except Exception as e:
            log_warning(f"Knowledge Graph lookup failed: {e}")

        return None

    def _kg_search(self, query: str, domain: str) -> Optional[str]:
        """
        Execute a single Knowledge Graph search and check results.

        Args:
            query: Search query string
            domain: Company domain (without www.) for matching

        Returns:
            Matched entity name, or None
        """
        search_url = "https://kgsearch.googleapis.com/v1/entities:search"
        params = {
            'query': query,
            'types': 'Organization',
            'limit': 5,
            'key': self.places_api_key
        }

        response = requests.get(search_url, params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        elements = data.get('itemListElement', [])
        if not elements:
            log_debug(f"Knowledge Graph: no results for '{query}'")
            return None

        # Check for domain match first (any result)
        for element in elements:
            result = element.get('result', {})
            score = element.get('resultScore', 0)
            name = result.get('name', '')
            entity_url = result.get('url', '')
            description = result.get('description', '')

            if entity_url:
                entity_domain = urlparse(entity_url).netloc.lower()
                if entity_domain.startswith('www.'):
                    entity_domain = entity_domain[4:]

                if entity_domain == domain:
                    log_info(f"Knowledge Graph: found '{name}' (score={score}, domain match, desc='{description}')")
                    return name

        # No domain match — use the top result if it's clearly the best
        # (score is relative, not absolute; top result has highest score)
        top = elements[0]
        top_result = top.get('result', {})
        top_score = top.get('resultScore', 0)
        top_name = top_result.get('name', '')
        top_desc = top_result.get('description', '')

        # Second result score for comparison
        second_score = elements[1].get('resultScore', 0) if len(elements) > 1 else 0

        # Accept top result if it's dominant (10x the runner-up or sole result with score >= 0.5)
        if top_score > 0 and (top_score >= 10 * second_score or (len(elements) == 1 and top_score >= 0.5)):
            log_info(f"Knowledge Graph: found '{top_name}' (score={top_score}, desc='{top_desc}')")
            return top_name

        log_debug(f"Knowledge Graph: best result for '{query}': '{top_name}' (score={top_score}) not confident enough")

        return None

    def _lookup_google_places_full(self, url: str, company_name: str) -> Tuple[Optional[str], Optional[CompanyAddress]]:
        """
        Look up company using Google Places API (New), returning name and address.

        Uses the new Places API endpoint (places.googleapis.com/v1/).

        Returns:
            Tuple of (name, address)
        """
        if not self.places_api_key:
            return None, None

        try:
            search_url = "https://places.googleapis.com/v1/places:searchText"
            headers = {
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': self.places_api_key,
                'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.addressComponents,places.id'
            }
            body = {
                'textQuery': company_name
            }

            response = requests.post(search_url, headers=headers, json=body, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            places = data.get('places', [])
            if places:
                place = places[0]
                places_name = place.get('displayName', {}).get('text', '')
                formatted_address = place.get('formattedAddress', '')

                # Parse address from components if available, fall back to formatted
                components = place.get('addressComponents', [])
                if components:
                    address = self._parse_address_components(components)
                else:
                    address = self._parse_formatted_address(formatted_address)

                log_debug(f"Found Google Places: {places_name}, {formatted_address}")
                return places_name, address

        except Exception as e:
            log_warning(f"Google Places lookup failed: {e}")

        return None, None

    def _parse_address_components(self, components: list) -> CompanyAddress:
        """Parse address from Google Places API (New) addressComponents."""
        address = CompanyAddress()

        for comp in components:
            types = comp.get('types', [])
            text = comp.get('longText', '')

            if 'street_number' in types:
                address.line1 = text
            elif 'route' in types:
                address.line1 = f"{address.line1} {text}".strip()
            elif 'subpremise' in types:
                address.line2 = text
            elif 'locality' in types:
                address.city = text
            elif 'administrative_area_level_1' in types:
                address.state = comp.get('shortText', text)
            elif 'postal_code' in types:
                address.postal_code = text
            elif 'country' in types:
                address.country = comp.get('shortText', text)

        return address

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

    def _lookup_opencorporates(self, company_name: str, jurisdiction: str) -> Optional[CorpRegistration]:
        """
        Search OpenCorporates API for a company in a given jurisdiction.

        Args:
            company_name: Company name to search
            jurisdiction: Jurisdiction code (e.g., 'us_ma', 'us_de')

        Returns:
            CorpRegistration if found
        """
        try:
            clean_name = re.sub(r'[^\w\s]', '', company_name).strip()
            log_debug(f"Searching OpenCorporates for '{clean_name}' in {jurisdiction}")

            params = {
                'q': clean_name,
                'jurisdiction_code': jurisdiction,
                'per_page': 5
            }
            if self.opencorporates_token:
                params['api_token'] = self.opencorporates_token

            response = requests.get(
                'https://api.opencorporates.com/v0.4/companies/search',
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            companies = data.get('results', {}).get('companies', [])
            if not companies:
                log_debug(f"No results from OpenCorporates for {jurisdiction}")
                return None

            # Build candidate names for best-match scoring
            candidates = []
            for item in companies:
                company = item.get('company', {})
                name = company.get('name', '')
                if name:
                    candidates.append((name, company))

            if not candidates:
                return None

            # Use existing best-match logic to pick the best result
            candidate_names = [c[0] for c in candidates]
            best_name = self._find_best_match(candidate_names, company_name)

            # Find the company data that matches
            best_company = candidates[0][1]  # default to first
            if best_name:
                for name, company_data in candidates:
                    if name == best_name:
                        best_company = company_data
                        break

            state_code = jurisdiction.replace('us_', '').upper()
            reg = CorpRegistration(
                state=state_code,
                entity_name=best_company.get('name', ''),
                entity_number=best_company.get('company_number', ''),
                status=best_company.get('current_status', ''),
                formation_date=best_company.get('incorporation_date', ''),
                registered_address=best_company.get('registered_address_in_full', ''),
                jurisdiction=jurisdiction,
                opencorporates_url=best_company.get('opencorporates_url', '')
            )

            log_debug(f"Found OpenCorporates result: {reg.entity_name} ({reg.status})")
            return reg

        except requests.exceptions.RequestException as e:
            log_debug(f"OpenCorporates API request failed: {e}")
        except Exception as e:
            log_debug(f"OpenCorporates lookup failed: {e}")

        return None

    def _lookup_state_corps(self, company_name: str) -> Tuple[Optional[CorpRegistration], Optional[CompanyAddress]]:
        """
        Look up company in state corporate databases via OpenCorporates.
        Tries MA first, then falls back to DE.

        Args:
            company_name: Company name to search

        Returns:
            Tuple of (CorpRegistration, CompanyAddress parsed from registered address)
        """
        # Try MA first
        reg = self._lookup_opencorporates(company_name, 'us_ma')

        # Fall back to DE
        if not reg:
            reg = self._lookup_opencorporates(company_name, 'us_de')

        if not reg:
            return None, None

        # Try to parse registered address into CompanyAddress
        address = None
        if reg.registered_address:
            address = self._parse_opencorporates_address(reg.registered_address)

        return reg, address

    def _parse_opencorporates_address(self, address_str: str) -> Optional[CompanyAddress]:
        """
        Parse an OpenCorporates registered address string into CompanyAddress.

        Args:
            address_str: Free-text address string

        Returns:
            CompanyAddress if parseable
        """
        if not address_str:
            return None

        # Try to match: "Street, City, ST ZIP" or similar patterns
        # OpenCorporates often returns multi-line or comma-separated
        parts = [p.strip() for p in address_str.replace('\n', ', ').split(',')]
        parts = [p for p in parts if p]

        if not parts:
            return None

        address = CompanyAddress()

        # Try to find state+zip pattern in parts
        for i, part in enumerate(parts):
            state_zip_match = re.match(r'^([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', part.strip())
            if state_zip_match:
                address.state = state_zip_match.group(1)
                address.postal_code = state_zip_match.group(2)
                if i > 0:
                    address.city = parts[i - 1]
                if i > 1:
                    address.line1 = ', '.join(parts[:i - 1])
                return address

        # Fallback: just use US address regex on the full string
        match = re.search(
            r'(.+?),\s*([A-Za-z\s]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)',
            address_str
        )
        if match:
            return CompanyAddress(
                line1=match.group(1).strip(),
                city=match.group(2).strip(),
                state=match.group(3),
                postal_code=match.group(4)
            )

        return None

    def _extract_social_links(self, soup: BeautifulSoup) -> SocialMedia:
        """
        Extract social media URLs from a parsed page.

        Args:
            soup: BeautifulSoup parsed page

        Returns:
            SocialMedia with found URLs
        """
        social = SocialMedia()

        patterns = {
            'linkedin_url': re.compile(r'https?://(?:www\.)?linkedin\.com/company/[^\s"\'<>]+', re.I),
            'twitter_url': re.compile(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/[^\s"\'<>]+', re.I),
            'facebook_url': re.compile(r'https?://(?:www\.)?facebook\.com/[^\s"\'<>]+', re.I),
            'instagram_url': re.compile(r'https?://(?:www\.)?instagram\.com/[^\s"\'<>]+', re.I),
            'youtube_url': re.compile(r'https?://(?:www\.)?youtube\.com/(?:channel|c|user|@)[^\s"\'<>]+', re.I),
        }

        # Scan all <a href> tags
        for link in soup.find_all('a', href=True):
            href = link['href']
            for field_name, pattern in patterns.items():
                if not getattr(social, field_name) and pattern.search(href):
                    # Normalize to https
                    url = pattern.search(href).group(0)
                    if url.startswith('http://'):
                        url = 'https://' + url[7:]
                    setattr(social, field_name, url)

        # Also check <meta> tags (og:see_also, etc.)
        for meta in soup.find_all('meta', attrs={'property': re.compile(r'og:see_also', re.I)}):
            content = meta.get('content', '')
            for field_name, pattern in patterns.items():
                if not getattr(social, field_name) and pattern.search(content):
                    url = pattern.search(content).group(0)
                    if url.startswith('http://'):
                        url = 'https://' + url[7:]
                    setattr(social, field_name, url)

        found_count = sum(1 for v in vars(social).values() if v)
        if found_count:
            log_debug(f"Found {found_count} social media link(s)")

        return social

    def _scrape_social_media(self, url: str) -> SocialMedia:
        """
        Scrape social media links from a company website.

        Args:
            url: Company website URL

        Returns:
            SocialMedia with found URLs
        """
        if not url:
            return SocialMedia()

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            social = self._extract_social_links(soup)

            # If we didn't find all links, try contact/about pages
            if not all(vars(social).values()):
                for path in ['/contact', '/about', '/about-us']:
                    try:
                        page_url = urljoin(url, path)
                        resp = requests.get(page_url, headers=headers, timeout=self.timeout)
                        if resp.status_code == 200:
                            page_soup = BeautifulSoup(resp.text, 'html.parser')
                            page_social = self._extract_social_links(page_soup)
                            # Merge: fill in any blanks
                            for field_name in vars(social):
                                if not getattr(social, field_name) and getattr(page_social, field_name):
                                    setattr(social, field_name, getattr(page_social, field_name))
                    except Exception:
                        continue

            return social

        except Exception as e:
            log_debug(f"Social media scraping failed: {e}")
            return SocialMedia()

    def _scrape_executives(self, url: str) -> List[Executive]:
        """
        Scrape executive/leadership information from company website.

        Args:
            url: Company website URL

        Returns:
            List of Executive found on team/leadership pages
        """
        if not url:
            return []

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        team_paths = [
            '/team', '/about-us', '/about', '/leadership', '/our-team',
            '/people', '/management', '/about/team', '/about/leadership',
            '/company/team'
        ]

        title_pattern = re.compile(
            r'\b(CEO|Chief Executive Officer|CFO|Chief Financial Officer|'
            r'COO|Chief Operating Officer|President|Founder|Co-Founder|'
            r'Managing Director|CTO|Chief Technology Officer|'
            r'CMO|Chief Marketing Officer|VP|Vice President|'
            r'General Manager|Partner|Principal|Director)\b',
            re.IGNORECASE
        )

        executives = []
        seen_names = set()

        for path in team_paths:
            if len(executives) >= 10:
                break

            try:
                page_url = urljoin(url, path)
                response = requests.get(page_url, headers=headers, timeout=self.timeout)

                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Try schema.org JSON-LD for Person data
                for script in soup.find_all('script', type='application/ld+json'):
                    try:
                        data = json.loads(script.string)
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if isinstance(item, dict) and item.get('@type') == 'Person':
                                job_title = item.get('jobTitle', '')
                                name = item.get('name', '')
                                if name and job_title and title_pattern.search(job_title):
                                    if name.lower() not in seen_names:
                                        seen_names.add(name.lower())
                                        executives.append(Executive(
                                            name=name,
                                            title=job_title,
                                            email=item.get('email', ''),
                                            linkedin_url=item.get('sameAs', '') if 'linkedin' in str(item.get('sameAs', '')) else ''
                                        ))
                    except (json.JSONDecodeError, TypeError):
                        continue

                # Scan page for title patterns near headings/names
                for tag in soup.find_all(['h2', 'h3', 'h4', 'strong', 'span', 'p', 'div']):
                    text = tag.get_text(strip=True)
                    if not text or len(text) > 200:
                        continue

                    title_match = title_pattern.search(text)
                    if not title_match:
                        continue

                    # The text might be "John Smith, CEO" or just "CEO"
                    title_str = title_match.group(0)

                    # Look for the name: either in this element or nearby
                    name = ""
                    full_text = text

                    # Pattern: "Name - Title" or "Name, Title"
                    name_title_match = re.match(
                        r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*[,\-–|]\s*(.+)$',
                        full_text
                    )
                    if name_title_match:
                        name = name_title_match.group(1).strip()
                        title_str = name_title_match.group(2).strip()
                    else:
                        # Look in sibling/parent elements for a name
                        for sibling in [tag.find_previous_sibling(), tag.find_next_sibling(),
                                       tag.parent]:
                            if sibling and hasattr(sibling, 'get_text'):
                                sib_text = sibling.get_text(strip=True)
                                name_match = re.match(
                                    r'^([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Za-z]+)$',
                                    sib_text
                                )
                                if name_match and len(sib_text) < 50:
                                    name = name_match.group(1)
                                    break

                    if not name or name.lower() in seen_names:
                        continue

                    seen_names.add(name.lower())

                    # Look for email/phone/linkedin near this element
                    parent = tag.parent or tag
                    parent_html = str(parent)

                    email = ""
                    email_match = re.search(r'mailto:([^"\'<>\s]+)', parent_html)
                    if email_match:
                        email = email_match.group(1)

                    phone = ""
                    phone_match = re.search(r'tel:([^"\'<>\s]+)', parent_html)
                    if phone_match:
                        phone = phone_match.group(1)

                    linkedin = ""
                    li_match = re.search(r'https?://(?:www\.)?linkedin\.com/in/[^\s"\'<>]+', parent_html)
                    if li_match:
                        linkedin = li_match.group(0)

                    executives.append(Executive(
                        name=name,
                        title=title_str,
                        email=email,
                        phone=phone,
                        linkedin_url=linkedin
                    ))

                    if len(executives) >= 10:
                        break

                # If we found executives on this page, no need to try more pages
                if executives:
                    break

            except Exception as e:
                log_debug(f"Error scraping {path} for executives: {e}")
                continue

        if executives:
            log_debug(f"Found {len(executives)} executive(s)")

        return executives

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


@dataclass
class ClientData:
    """Unified client record for all output systems."""
    # Identity
    company_name: str = ""
    legal_name: str = ""
    domain: str = ""
    website_url: str = ""

    # Address
    address: CompanyAddress = field(default_factory=CompanyAddress)

    # Contact
    phone: str = ""
    email: str = ""

    # Corporate Registration
    corp_registration: Optional[CorpRegistration] = None

    # Executives
    executives: List[Executive] = field(default_factory=list)

    # Social Media
    social_media: SocialMedia = field(default_factory=SocialMedia)

    # Output results (filled after each system processes)
    hubspot_company_id: str = ""
    hubspot_deal_id: str = ""
    drive_folder_id: str = ""
    quickbooks_customer_id: str = ""

    def to_sheets_client_row(self) -> list:
        """Format as a row for Google Sheets Client Tab."""
        reg = self.corp_registration
        return [
            self.company_name, self.legal_name, self.domain, self.website_url,
            self.address.line1, self.address.line2, self.address.city,
            self.address.state, self.address.postal_code, self.address.country,
            self.phone, self.email,
            reg.state if reg else "", reg.entity_name if reg else "",
            reg.entity_number if reg else "", reg.status if reg else "",
            reg.formation_date if reg else "",
            self.social_media.linkedin_url, self.social_media.twitter_url,
            self.social_media.facebook_url, self.social_media.instagram_url,
            self.social_media.youtube_url,
            self.hubspot_company_id, self.drive_folder_id,
            self.quickbooks_customer_id,
        ]

    def to_sheets_contact_rows(self) -> list:
        """Format executives as rows for Google Sheets Contacts Tab."""
        rows = []
        for exec_ in self.executives:
            rows.append([
                self.company_name, exec_.name, exec_.title,
                exec_.email, exec_.phone, exec_.linkedin_url,
            ])
        return rows


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
