"""Company lookup adapter for ClientCreate.

Wraps the shared company_lookup module and preserves the class-based
interface (CompanyLookupService) and dataclasses (CompanyInfo, ClientData)
that ClientCreate's GUI code imports.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# Ensure shared config is importable
_shared_path = str(Path(__file__).parent.parent.parent.parent / "_shared_config")
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

# Re-export shared dataclasses so existing imports keep working:
#   from services.company_lookup import CompanyAddress, Executive, SocialMedia, ...
from company_lookup import (
    CompanyAddress,
    CompanyLookupResult,
    CorpRegistration,
    Executive,
    LEGAL_SUFFIXES,
    SocialMedia,
    lookup_company as _shared_lookup,
    lookup_names_only as _shared_names_only,
    test_places_api,
)


# ── CompanyInfo: backward-compatible wrapper ─────────────────

@dataclass
class CompanyInfo:
    """Complete company information (ClientCreate-specific)."""
    name: str = ""
    legal_name: str = ""
    address: CompanyAddress = field(default_factory=CompanyAddress)
    phone: str = ""
    email: str = ""
    found_names: List[str] = field(default_factory=list)
    source: str = ""
    executives: List[Executive] = field(default_factory=list)
    social_media: SocialMedia = field(default_factory=SocialMedia)
    corp_registration: Optional[CorpRegistration] = None


# ── CompanyLookupService: thin wrapper ───────────────────────

class CompanyLookupService:
    """Service for looking up and verifying company names.

    Wraps the shared lookup module, preserving the class-based
    interface that ClientCreate's GUI code expects.
    """

    def __init__(self, places_api_key: Optional[str] = None,
                 opencorporates_token: Optional[str] = None):
        self.places_api_key = places_api_key or ""
        self.opencorporates_token = opencorporates_token or ""
        self.timeout = 10

    def set_places_api_key(self, api_key: str):
        """Set or update the Google Places API key."""
        self.places_api_key = api_key

    def lookup_company_info(self, url: str, entered_name: str) -> CompanyInfo:
        """Look up complete company information including address."""
        r = _shared_lookup(
            url, entered_name,
            api_key=self.places_api_key,
            oc_token=self.opencorporates_token,
        )
        return CompanyInfo(
            name=r.best_name,
            legal_name=r.best_name,
            address=r.address,
            found_names=r.found_names,
            source=r.addresses[0]["source"] if r.addresses else "",
            executives=r.executives,
            social_media=r.social,
            corp_registration=r.corp_registration,
        )

    def lookup_formal_name(self, url: str, entered_name: str) -> Tuple[Optional[str], List[str]]:
        """Lightweight lookup that only finds names (no address/executives)."""
        best, names = _shared_names_only(
            url, entered_name,
            api_key=self.places_api_key,
        )
        return best, names

    def is_name_similar(self, name1: str, name2: str) -> bool:
        """Check if two company names are similar enough."""
        from company_lookup import _names_similar
        return _names_similar(name1, name2)


# ── ClientData: stays here (ClientCreate-specific output) ────

@dataclass
class ClientData:
    """Unified client record for all output systems."""
    company_name: str = ""
    legal_name: str = ""
    domain: str = ""
    website_url: str = ""
    address: CompanyAddress = field(default_factory=CompanyAddress)
    phone: str = ""
    email: str = ""
    corp_registration: Optional[CorpRegistration] = None
    executives: List[Executive] = field(default_factory=list)
    social_media: SocialMedia = field(default_factory=SocialMedia)
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


# ── Singleton helper ─────────────────────────────────────────

_lookup_service: Optional[CompanyLookupService] = None


def get_company_lookup_service() -> CompanyLookupService:
    """Get or create the company lookup service instance."""
    global _lookup_service
    if _lookup_service is None:
        _lookup_service = CompanyLookupService()
    return _lookup_service
