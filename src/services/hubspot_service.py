"""
HubSpot service for ClientCreate.

Handles all HubSpot CRM operations including:
- Company search and creation
- Deal creation
- Authentication testing
"""

from datetime import datetime
from typing import Optional, Dict, Tuple, List
import time

from hubspot import HubSpot
from hubspot.crm.companies import SimplePublicObjectInputForCreate as CompanyInput
from hubspot.crm.deals import SimplePublicObjectInputForCreate as DealInput
from hubspot.crm.deals import PublicAssociationsForObject, AssociationSpec

from logger_setup import get_logger, log_info, log_error, log_warning, log_debug


class HubSpotService:
    """Service for HubSpot CRM operations."""

    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize HubSpot service.

        Args:
            access_token: HubSpot Private App access token
        """
        self.logger = get_logger()
        self.access_token = access_token
        self.client: Optional[HubSpot] = None
        self.portal_id: Optional[str] = None

        if access_token:
            self._init_client()

    def _init_client(self):
        """Initialize the HubSpot client."""
        if self.access_token:
            self.client = HubSpot(access_token=self.access_token)

    def set_access_token(self, token: str):
        """
        Set or update the access token.

        Args:
            token: New access token
        """
        self.access_token = token
        self._init_client()

    def test_connection(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Test the HubSpot connection.

        Returns:
            Tuple of (success, portal_name, error_message)
        """
        if not self.client:
            return False, None, "HubSpot client not initialized"

        try:
            # Test connection by fetching a single company (or empty list)
            self.client.crm.companies.basic_api.get_page(limit=1)

            log_info("HubSpot connection successful")
            return True, "Connected", None

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                return False, None, "Invalid or expired access token"
            if "403" in error_msg:
                return False, None, "Access token lacks required permissions"
            log_error(f"HubSpot connection test failed: {e}")
            return False, None, f"Connection failed: {error_msg}"

    # =========================================================================
    # Company Operations
    # =========================================================================

    def search_company_by_domain(self, domain: str) -> Optional[Dict]:
        """
        Search for a company by domain.

        Args:
            domain: Company domain to search for

        Returns:
            Company data dict if found, None otherwise
        """
        if not self.client:
            return None

        try:
            filter_group = {
                "filters": [
                    {
                        "propertyName": "domain",
                        "operator": "EQ",
                        "value": domain
                    }
                ]
            }

            search_request = {
                "filterGroups": [filter_group],
                "properties": ["name", "domain", "type", "address", "city", "state", "zip", "country"],
                "limit": 1
            }

            response = self.client.crm.companies.search_api.do_search(
                public_object_search_request=search_request
            )

            if response.results:
                company = response.results[0]
                return {
                    'id': company.id,
                    'name': company.properties.get('name'),
                    'domain': company.properties.get('domain'),
                    'type': company.properties.get('type'),
                    'address': company.properties.get('address'),
                    'city': company.properties.get('city'),
                    'state': company.properties.get('state'),
                    'zip': company.properties.get('zip'),
                    'country': company.properties.get('country')
                }

            return None

        except Exception as e:
            log_error(f"Error searching company by domain: {e}")
            return None

    def search_company_by_name(self, name: str) -> Optional[Dict]:
        """
        Search for a company by name.

        Args:
            name: Company name to search for

        Returns:
            Company data dict if found, None otherwise
        """
        if not self.client:
            return None

        try:
            filter_group = {
                "filters": [
                    {
                        "propertyName": "name",
                        "operator": "EQ",
                        "value": name
                    }
                ]
            }

            search_request = {
                "filterGroups": [filter_group],
                "properties": ["name", "domain", "type", "address", "city", "state", "zip", "country"],
                "limit": 1
            }

            response = self.client.crm.companies.search_api.do_search(
                public_object_search_request=search_request
            )

            if response.results:
                company = response.results[0]
                return {
                    'id': company.id,
                    'name': company.properties.get('name'),
                    'domain': company.properties.get('domain'),
                    'type': company.properties.get('type'),
                    'address': company.properties.get('address'),
                    'city': company.properties.get('city'),
                    'state': company.properties.get('state'),
                    'zip': company.properties.get('zip'),
                    'country': company.properties.get('country')
                }

            return None

        except Exception as e:
            log_error(f"Error searching company by name: {e}")
            return None

    def search_company(self, name: str, domain: str) -> Optional[Dict]:
        """
        Search for a company by both name and domain.

        Args:
            name: Company name
            domain: Company domain

        Returns:
            Company data dict if found, None otherwise
        """
        # Try domain first (more specific)
        result = self.search_company_by_domain(domain)
        if result:
            log_info(f"Found existing company by domain: {result['name']}")
            return result

        # Then try name
        result = self.search_company_by_name(name)
        if result:
            log_info(f"Found existing company by name: {result['name']}")
            return result

        return None

    def create_company(
        self,
        name: str,
        domain: str,
        company_type: str = "CLIENT",
        dry_run: bool = False
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Create a new company in HubSpot.

        Args:
            name: Company name
            domain: Company domain
            company_type: Type field value (default: "Client")
            dry_run: If True, don't actually create

        Returns:
            Tuple of (success, company_id, error_message)
        """
        if not self.client:
            return False, None, "HubSpot client not initialized"

        if dry_run:
            log_info(f"[DRY RUN] Would create company: {name} ({domain})")
            return True, "DRY_RUN_ID", None

        try:
            properties = {
                "name": name,
                "domain": domain,
                "type": company_type
            }

            company_input = CompanyInput(properties=properties)
            response = self.client.crm.companies.basic_api.create(
                simple_public_object_input_for_create=company_input
            )

            company_id = response.id
            log_info(f"Created HubSpot company: {name} (ID: {company_id})")
            return True, company_id, None

        except Exception as e:
            log_error(f"Error creating company: {e}")
            return False, None, str(e)

    def update_company_type(self, company_id: str, company_type: str = "CLIENT") -> bool:
        """
        Update a company's type field.

        Args:
            company_id: HubSpot company ID
            company_type: New type value

        Returns:
            True on success
        """
        if not self.client:
            return False

        try:
            properties = {"type": company_type}

            self.client.crm.companies.basic_api.update(
                company_id=company_id,
                simple_public_object_input={"properties": properties}
            )

            log_info(f"Updated company type to '{company_type}' for ID: {company_id}")
            return True

        except Exception as e:
            log_error(f"Error updating company type: {e}")
            return False

    def update_company_address(
        self,
        company_id: str,
        address: str = "",
        city: str = "",
        state: str = "",
        zip_code: str = "",
        country: str = ""
    ) -> Tuple[bool, Optional[str]]:
        """
        Update a company's address fields.

        Args:
            company_id: HubSpot company ID
            address: Street address (line 1 and line 2 combined)
            city: City name
            state: State/province
            zip_code: Postal/ZIP code
            country: Country name

        Returns:
            Tuple of (success, error_message)
        """
        if not self.client:
            return False, "HubSpot client not initialized"

        try:
            properties = {}

            # Only update non-empty fields
            if address:
                properties["address"] = address
            if city:
                properties["city"] = city
            if state:
                properties["state"] = state
            if zip_code:
                properties["zip"] = zip_code
            if country:
                properties["country"] = country

            if not properties:
                log_debug("No address fields to update")
                return True, None

            self.client.crm.companies.basic_api.update(
                company_id=company_id,
                simple_public_object_input={"properties": properties}
            )

            log_info(f"Updated company address for ID: {company_id}")
            return True, None

        except Exception as e:
            log_error(f"Error updating company address: {e}")
            return False, str(e)

    def company_has_address(self, company_data: Dict) -> bool:
        """
        Check if a company has address information.

        Args:
            company_data: Company dict from search results

        Returns:
            True if company has at least street address or city
        """
        if not company_data:
            return False

        address = company_data.get('address', '')
        city = company_data.get('city', '')

        return bool(address) or bool(city)

    def get_company_url(self, company_id: str) -> str:
        """Get the HubSpot URL for a company."""
        return f"https://app.hubspot.com/contacts/companies/{company_id}"

    # =========================================================================
    # Deal Operations
    # =========================================================================

    def get_deal_pipeline_stages(self) -> List[Dict]:
        """
        Get all deal pipeline stages.

        Returns:
            List of stage dicts with id, label, displayOrder
        """
        if not self.client:
            return []

        try:
            pipelines = self.client.crm.pipelines.pipelines_api.get_all(
                object_type="deals"
            )

            stages = []
            for pipeline in pipelines.results:
                for stage in pipeline.stages:
                    stages.append({
                        'pipeline_id': pipeline.id,
                        'pipeline_label': pipeline.label,
                        'stage_id': stage.id,
                        'stage_label': stage.label,
                        'display_order': stage.display_order
                    })

            return stages

        except Exception as e:
            log_error(f"Error getting pipeline stages: {e}")
            return []

    def find_stage_id(self, stage_label: str = "Closed Won") -> Optional[str]:
        """
        Find the stage ID for a given stage label.

        Args:
            stage_label: Stage label to find (e.g., "Closed Won")

        Returns:
            Stage ID if found, None otherwise
        """
        stages = self.get_deal_pipeline_stages()

        for stage in stages:
            if stage['stage_label'].lower() == stage_label.lower():
                return stage['stage_id']

        # If not found, return None and log available stages
        log_warning(f"Stage '{stage_label}' not found. Available stages:")
        for stage in stages:
            log_debug(f"  - {stage['stage_label']} (ID: {stage['stage_id']})")

        return None

    def deal_exists_today(self, company_name: str) -> bool:
        """
        Check if a deal for this company was already created today.

        Args:
            company_name: Company name to check

        Returns:
            True if deal exists for today
        """
        if not self.client:
            return False

        try:
            today = datetime.now().strftime('%Y-%m-%d')
            deal_name_pattern = f"{company_name} - {today}"

            filter_group = {
                "filters": [
                    {
                        "propertyName": "dealname",
                        "operator": "CONTAINS_TOKEN",
                        "value": deal_name_pattern
                    }
                ]
            }

            search_request = {
                "filterGroups": [filter_group],
                "limit": 1
            }

            response = self.client.crm.deals.search_api.do_search(
                public_object_search_request=search_request
            )

            return len(response.results) > 0

        except Exception as e:
            log_debug(f"Error checking existing deals: {e}")
            return False

    def create_deal(
        self,
        company_name: str,
        company_id: str,
        stage_id: Optional[str] = None,
        dry_run: bool = False
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Create a new deal in HubSpot.

        Args:
            company_name: Company name for deal name
            company_id: HubSpot company ID to associate
            stage_id: Deal stage ID (will look up "Closed Won" if not provided)
            dry_run: If True, don't actually create

        Returns:
            Tuple of (success, deal_id, error_message)
        """
        if not self.client:
            return False, None, "HubSpot client not initialized"

        # Generate deal name with date
        today = datetime.now()
        date_str = today.strftime('%Y-%m-%d')

        # Check if deal exists today, add time if so
        if self.deal_exists_today(company_name):
            time_str = today.strftime('%H:%M')
            deal_name = f"{company_name} - {date_str} {time_str}"
        else:
            deal_name = f"{company_name} - {date_str}"

        # Get stage ID if not provided
        if not stage_id:
            stage_id = self.find_stage_id("Closed Won")
            if not stage_id:
                log_warning("Could not find 'Closed Won' stage, using default")

        # Format dates for HubSpot (Unix timestamp in milliseconds)
        close_date = int(today.timestamp() * 1000)
        start_date = today.strftime('%Y-%m-%d')

        if dry_run:
            log_info(f"[DRY RUN] Would create deal: {deal_name}")
            return True, "DRY_RUN_ID", None

        try:
            properties = {
                "dealname": deal_name,
                "closedate": str(close_date),
                "dealtype": "newbusiness",
                "start_date": start_date,
                "non_solicit_length": "365",
                "closed_lost_reason": "Active"
            }

            if stage_id:
                properties["dealstage"] = stage_id

            # Create association with company
            associations = [
                PublicAssociationsForObject(
                    to={"id": company_id},
                    types=[
                        AssociationSpec(
                            association_category="HUBSPOT_DEFINED",
                            association_type_id=5  # Deal to Company
                        )
                    ]
                )
            ]

            deal_input = DealInput(
                properties=properties,
                associations=associations
            )

            response = self.client.crm.deals.basic_api.create(
                simple_public_object_input_for_create=deal_input
            )

            deal_id = response.id
            log_info(f"Created HubSpot deal: {deal_name} (ID: {deal_id})")
            return True, deal_id, None

        except Exception as e:
            log_error(f"Error creating deal: {e}")
            return False, None, str(e)

    def get_deal_url(self, deal_id: str) -> str:
        """Get the HubSpot URL for a deal."""
        return f"https://app.hubspot.com/contacts/deals/{deal_id}"


# Singleton instance
_hubspot_service: Optional[HubSpotService] = None


def get_hubspot_service() -> HubSpotService:
    """Get or create the HubSpot service instance."""
    global _hubspot_service
    if _hubspot_service is None:
        _hubspot_service = HubSpotService()
    return _hubspot_service


def init_hubspot_service(access_token: str) -> HubSpotService:
    """
    Initialize HubSpot service with access token.

    Args:
        access_token: HubSpot Private App access token

    Returns:
        Initialized HubSpot service
    """
    global _hubspot_service
    _hubspot_service = HubSpotService(access_token)
    return _hubspot_service
