"""
QuickBooks Online service for ClientCreate.

Handles QuickBooks Online (QBO) operations including:
- OAuth 2.0 authentication with Intuit
- Customer (client) creation
- Duplicate detection
- Default configuration application
- Partial failure handling
- Comprehensive logging

This module runs in TRIAL mode by default - no changes are made to QBO data.
"""

import json
import time
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs, urlparse
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List, Any
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

import requests
from requests_oauthlib import OAuth2Session

from logger_setup import log_info, log_error, log_warning, log_debug


# QuickBooks OAuth Configuration
QBO_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"

# QuickBooks API Base URLs
QBO_API_BASE_SANDBOX = "https://sandbox-quickbooks.api.intuit.com"
QBO_API_BASE_PRODUCTION = "https://quickbooks.api.intuit.com"

# OAuth Scopes
QBO_SCOPES = ["com.intuit.quickbooks.accounting"]

# Local redirect URI for OAuth callback
# Using port 5588 to avoid common port conflicts
REDIRECT_URI = "http://localhost:5588/callback"

# Token storage path - relative to project root
# Path: src/services/quickbooks_service.py -> go up 3 levels to project root, then config/
_PROJECT_ROOT = Path(__file__).parent.parent.parent
TOKEN_FILE = _PROJECT_ROOT / "config" / "qbo_tokens.json"


class QBOStatus(Enum):
    """Status codes for QBO operations."""
    EXISTS = "exists"
    CREATED = "created"
    CREATED_WITH_ISSUES = "created_with_issues"
    ERROR = "error"


class QBOErrorType(Enum):
    """Error type classifications."""
    AUTH = "auth"
    VALIDATION = "validation"
    API = "api"
    UNKNOWN = "unknown"


@dataclass
class QBOClientInput:
    """Input schema for creating a QBO client (customer)."""
    client_name: str  # Required
    client_legal_name: Optional[str] = None
    client_url: Optional[str] = None
    primary_email: Optional[str] = None
    phone: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_address_city: Optional[str] = None
    billing_address_state: Optional[str] = None
    billing_address_postal_code: Optional[str] = None
    billing_address_country: Optional[str] = None
    notes: Optional[str] = None
    source_system: Optional[str] = None
    external_client_id: Optional[str] = None


@dataclass
class QBOResult:
    """Output schema for QBO operations."""
    status: str
    quickbooks_customer_id: Optional[str] = None
    matched_on: Optional[str] = None
    issues: Optional[List[str]] = None
    error_type: Optional[str] = None
    message: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {"status": self.status, "timestamp": self.timestamp}
        if self.quickbooks_customer_id:
            result["quickbooks_customer_id"] = self.quickbooks_customer_id
        if self.matched_on:
            result["matched_on"] = self.matched_on
        if self.issues:
            result["issues"] = self.issues
        if self.error_type:
            result["error_type"] = self.error_type
        if self.message:
            result["message"] = self.message
        return result


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    def do_GET(self):
        """Handle OAuth callback GET request."""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        # Parse the callback URL
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        # Store the authorization code
        if 'code' in query_params:
            self.server.auth_code = query_params['code'][0]
            self.server.realm_id = query_params.get('realmId', [None])[0]
            message = """
            <html><body>
            <h1>Authorization Successful!</h1>
            <p>You can close this window and return to the application.</p>
            <script>window.close();</script>
            </body></html>
            """
        else:
            error = query_params.get('error', ['Unknown error'])[0]
            self.server.auth_code = None
            self.server.error = error
            message = f"""
            <html><body>
            <h1>Authorization Failed</h1>
            <p>Error: {error}</p>
            <p>Please close this window and try again.</p>
            </body></html>
            """

        self.wfile.write(message.encode())

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


class QuickBooksService:
    """Service for QuickBooks Online operations."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        realm_id: Optional[str] = None,
        use_sandbox: bool = True,
        trial_mode: bool = True
    ):
        """
        Initialize QuickBooks service.

        Args:
            client_id: Intuit OAuth client ID
            client_secret: Intuit OAuth client secret
            realm_id: QuickBooks company (realm) ID
            use_sandbox: Use sandbox environment (default True for safety)
            trial_mode: Run in trial mode - no actual changes (default True)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.realm_id = realm_id
        self.use_sandbox = use_sandbox
        self.trial_mode = trial_mode

        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None

        self._api_base = QBO_API_BASE_SANDBOX if use_sandbox else QBO_API_BASE_PRODUCTION

        # Load existing tokens if available
        self._load_tokens()

    def _get_api_url(self, endpoint: str) -> str:
        """Get full API URL for an endpoint."""
        return f"{self._api_base}/v3/company/{self.realm_id}/{endpoint}"

    def _load_tokens(self):
        """Load tokens from storage."""
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                self.access_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                self.realm_id = data.get('realm_id') or self.realm_id
                expiry_str = data.get('token_expiry')
                if expiry_str:
                    self.token_expiry = datetime.fromisoformat(expiry_str)
                log_debug("Loaded QBO tokens from storage")
            except Exception as e:
                log_warning(f"Could not load QBO tokens: {e}")

    def _save_tokens(self):
        """Save tokens to storage."""
        try:
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'realm_id': self.realm_id,
                'token_expiry': self.token_expiry.isoformat() if self.token_expiry else None
            }
            with open(TOKEN_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            log_debug("Saved QBO tokens to storage")
        except Exception as e:
            log_warning(f"Could not save QBO tokens: {e}")

    def is_configured(self) -> bool:
        """Check if service is configured with credentials."""
        return bool(self.client_id and self.client_secret)

    def is_authenticated(self) -> bool:
        """Check if we have valid authentication."""
        if not self.access_token or not self.realm_id:
            return False
        if self.token_expiry and datetime.now() >= self.token_expiry:
            # Token expired, try to refresh
            return self._refresh_access_token()
        return True

    def configure(self, client_id: str, client_secret: str, realm_id: Optional[str] = None):
        """
        Configure the service with OAuth credentials.

        Args:
            client_id: Intuit OAuth client ID
            client_secret: Intuit OAuth client secret
            realm_id: Optional QuickBooks company ID
        """
        self.client_id = client_id
        self.client_secret = client_secret
        if realm_id:
            self.realm_id = realm_id
        log_info("QuickBooks service configured")

    def set_trial_mode(self, enabled: bool):
        """Enable or disable trial mode."""
        self.trial_mode = enabled
        if enabled:
            log_info("QuickBooks TRIAL MODE enabled - no changes will be made")
        else:
            log_warning("QuickBooks TRIAL MODE disabled - changes WILL be made")

    # =========================================================================
    # OAuth Authentication
    # =========================================================================

    def start_oauth_flow(self) -> Tuple[bool, Optional[str]]:
        """
        Start the OAuth 2.0 authorization flow.

        Opens browser for user authorization and starts local callback server.

        Returns:
            Tuple of (success, error_message)
        """
        if not self.client_id or not self.client_secret:
            return False, "OAuth credentials not configured"

        try:
            # Create OAuth session
            oauth = OAuth2Session(
                self.client_id,
                redirect_uri=REDIRECT_URI,
                scope=QBO_SCOPES
            )

            # Generate authorization URL
            auth_url, state = oauth.authorization_url(QBO_AUTH_URL)

            log_info("Starting OAuth flow - opening browser...")
            log_info("Please authorize the application in your browser.")

            # Start local HTTP server for callback
            server = HTTPServer(('localhost', 5588), OAuthCallbackHandler)
            server.auth_code = None
            server.realm_id = None
            server.error = None
            server.timeout = 120  # 2 minute timeout

            # Open browser
            webbrowser.open(auth_url)

            # Wait for callback (with timeout)
            start_time = time.time()
            while server.auth_code is None and server.error is None:
                server.handle_request()
                if time.time() - start_time > 120:
                    return False, "Authorization timeout - no response received"

            server.server_close()

            if server.error:
                return False, f"Authorization failed: {server.error}"

            if not server.auth_code:
                return False, "No authorization code received"

            # Exchange code for tokens
            token = oauth.fetch_token(
                QBO_TOKEN_URL,
                code=server.auth_code,
                client_secret=self.client_secret
            )

            self.access_token = token['access_token']
            self.refresh_token = token.get('refresh_token')
            self.realm_id = server.realm_id
            self.token_expiry = datetime.now() + timedelta(seconds=token.get('expires_in', 3600))

            self._save_tokens()

            log_info(f"OAuth successful! Connected to company: {self.realm_id}")
            return True, None

        except Exception as e:
            log_error(f"OAuth flow failed: {e}")
            return False, str(e)

    def _refresh_access_token(self) -> bool:
        """
        Refresh the access token using the refresh token.

        Returns:
            True if refresh was successful
        """
        if not self.refresh_token:
            return False

        try:
            response = requests.post(
                QBO_TOKEN_URL,
                auth=(self.client_id, self.client_secret),
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': self.refresh_token
                },
                headers={'Accept': 'application/json'}
            )
            response.raise_for_status()
            token = response.json()

            self.access_token = token['access_token']
            self.refresh_token = token.get('refresh_token', self.refresh_token)
            self.token_expiry = datetime.now() + timedelta(seconds=token.get('expires_in', 3600))

            self._save_tokens()
            log_debug("Access token refreshed successfully")
            return True

        except Exception as e:
            log_error(f"Token refresh failed: {e}")
            return False

    def test_connection(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Test the QuickBooks connection.

        Returns:
            Tuple of (success, company_name, error_message)
        """
        if self.trial_mode:
            log_info("[TRIAL MODE] Would test QuickBooks connection")
            if self.is_configured():
                return True, "Trial Mode Company", None
            return False, None, "QuickBooks not configured"

        if not self.is_authenticated():
            return False, None, "Not authenticated - please complete OAuth flow"

        try:
            # Get company info
            url = self._get_api_url("companyinfo/" + self.realm_id)
            response = self._make_api_request("GET", url)

            if response.status_code == 200:
                data = response.json()
                company_name = data.get('CompanyInfo', {}).get('CompanyName', 'Unknown')
                log_info(f"Connected to QuickBooks company: {company_name}")
                return True, company_name, None
            else:
                return False, None, f"API error: {response.status_code}"

        except Exception as e:
            log_error(f"Connection test failed: {e}")
            return False, None, str(e)

    # =========================================================================
    # API Request Helpers
    # =========================================================================

    def _make_api_request(
        self,
        method: str,
        url: str,
        data: Optional[dict] = None
    ) -> requests.Response:
        """
        Make an authenticated API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full API URL
            data: Optional request body

        Returns:
            Response object
        """
        if not self.is_authenticated():
            raise Exception("Not authenticated")

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        if method.upper() == 'GET':
            return requests.get(url, headers=headers)
        elif method.upper() == 'POST':
            return requests.post(url, headers=headers, json=data)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    # =========================================================================
    # Customer Operations
    # =========================================================================

    def search_customer_by_name(self, client_name: str) -> Optional[Dict]:
        """
        Search for a customer by name (exact match, case-insensitive).

        Args:
            client_name: Customer name to search for

        Returns:
            Customer data dict if found, None otherwise
        """
        if self.trial_mode:
            log_info(f"[TRIAL MODE] Would search for customer: {client_name}")
            return None  # In trial mode, always return "not found"

        if not self.is_authenticated():
            log_error("Not authenticated - cannot search customers")
            return None

        try:
            # QBO query - case insensitive search
            # Note: QBO LIKE operator is case-insensitive
            clean_name = client_name.strip().replace("'", "\\'")
            query = f"SELECT * FROM Customer WHERE DisplayName = '{clean_name}'"

            url = self._get_api_url("query")
            response = self._make_api_request(
                "GET",
                f"{url}?query={requests.utils.quote(query)}"
            )

            if response.status_code == 200:
                data = response.json()
                customers = data.get('QueryResponse', {}).get('Customer', [])

                if customers:
                    customer = customers[0]
                    log_info(f"Found existing customer: {customer.get('DisplayName')}")
                    return {
                        'id': customer.get('Id'),
                        'name': customer.get('DisplayName'),
                        'company_name': customer.get('CompanyName'),
                        'email': customer.get('PrimaryEmailAddr', {}).get('Address'),
                        'phone': customer.get('PrimaryPhone', {}).get('FreeFormNumber'),
                        'active': customer.get('Active', True)
                    }

            return None

        except Exception as e:
            log_error(f"Customer search failed: {e}")
            return None

    def create_customer(self, client_input: QBOClientInput) -> QBOResult:
        """
        Create a new customer in QuickBooks Online.

        Implements the full workflow:
        1. Validate input
        2. Check for duplicates
        3. Create customer with defaults
        4. Handle partial failures

        Args:
            client_input: Client data to create

        Returns:
            QBOResult with operation status
        """
        module_name = "QBO_Create_Client"
        log_info(f"[{module_name}] Starting customer creation for: {client_input.client_name}")

        # Step 1: Validate input
        if not client_input.client_name or not client_input.client_name.strip():
            result = QBOResult(
                status=QBOStatus.ERROR.value,
                error_type=QBOErrorType.VALIDATION.value,
                message="client_name is required"
            )
            self._log_result(module_name, client_input.client_name, result)
            return result

        clean_name = client_input.client_name.strip()

        # Step 2: Check for duplicates
        if self.trial_mode:
            log_info(f"[TRIAL MODE] Would check for existing customer: {clean_name}")
            existing = None
        else:
            existing = self.search_customer_by_name(clean_name)

        if existing:
            result = QBOResult(
                status=QBOStatus.EXISTS.value,
                quickbooks_customer_id=existing['id'],
                matched_on="client_name"
            )
            log_info(f"[{module_name}] Customer already exists: {existing['id']}")
            self._log_result(module_name, clean_name, result)
            return result

        # Step 3: Create customer
        if self.trial_mode:
            log_info(f"[TRIAL MODE] Would create customer: {clean_name}")
            log_info(f"[TRIAL MODE] Customer data:")
            log_info(f"  - Display Name: {clean_name}")
            log_info(f"  - Company Name: {client_input.client_legal_name or clean_name}")
            if client_input.primary_email:
                log_info(f"  - Email: {client_input.primary_email}")
            if client_input.phone:
                log_info(f"  - Phone: {client_input.phone}")
            if client_input.client_url:
                log_info(f"  - Website: {client_input.client_url}")
            log_info(f"  - Payment Terms: Due on receipt (Net 0)")
            log_info(f"  - Status: Active")

            result = QBOResult(
                status=QBOStatus.CREATED.value,
                quickbooks_customer_id="TRIAL_MODE_ID"
            )
            self._log_result(module_name, clean_name, result)
            return result

        # Build customer object
        customer_data = self._build_customer_object(client_input)

        try:
            url = self._get_api_url("customer")
            response = self._make_api_request("POST", url, customer_data)

            if response.status_code in [200, 201]:
                data = response.json()
                customer_id = data.get('Customer', {}).get('Id')

                # Step 4: Apply defaults and check for issues
                issues = self._apply_defaults_and_check(customer_id)

                if issues:
                    result = QBOResult(
                        status=QBOStatus.CREATED_WITH_ISSUES.value,
                        quickbooks_customer_id=customer_id,
                        issues=issues
                    )
                    log_warning(f"[{module_name}] Customer created with issues: {issues}")
                else:
                    result = QBOResult(
                        status=QBOStatus.CREATED.value,
                        quickbooks_customer_id=customer_id
                    )
                    log_info(f"[{module_name}] Customer created successfully: {customer_id}")

                self._log_result(module_name, clean_name, result)
                return result

            else:
                # Parse error response
                error_data = response.json() if response.content else {}
                error_msg = self._parse_api_error(error_data)

                result = QBOResult(
                    status=QBOStatus.ERROR.value,
                    error_type=QBOErrorType.API.value,
                    message=error_msg
                )
                log_error(f"[{module_name}] API error: {error_msg}")
                self._log_result(module_name, clean_name, result)
                return result

        except requests.exceptions.RequestException as e:
            result = QBOResult(
                status=QBOStatus.ERROR.value,
                error_type=QBOErrorType.API.value,
                message=str(e)
            )
            log_error(f"[{module_name}] Request failed: {e}")
            self._log_result(module_name, clean_name, result)
            return result

        except Exception as e:
            result = QBOResult(
                status=QBOStatus.ERROR.value,
                error_type=QBOErrorType.UNKNOWN.value,
                message=str(e)
            )
            log_error(f"[{module_name}] Unexpected error: {e}")
            self._log_result(module_name, clean_name, result)
            return result

    def _build_customer_object(self, client_input: QBOClientInput) -> dict:
        """
        Build the QBO Customer object from input.

        Args:
            client_input: Client input data

        Returns:
            QBO Customer API object
        """
        clean_name = client_input.client_name.strip()

        customer = {
            "DisplayName": clean_name,
            "CompanyName": client_input.client_legal_name or clean_name,
            "Active": True,
            # Default payment terms: Due on receipt (Net 0)
            # Note: Payment terms may need to be configured in QBO first
        }

        # Optional fields
        if client_input.primary_email:
            customer["PrimaryEmailAddr"] = {"Address": client_input.primary_email}

        if client_input.phone:
            customer["PrimaryPhone"] = {"FreeFormNumber": client_input.phone}

        if client_input.client_url:
            customer["WebAddr"] = {"URI": client_input.client_url}

        if client_input.notes:
            customer["Notes"] = client_input.notes

        # Billing address
        if any([
            client_input.billing_address_line1,
            client_input.billing_address_city,
            client_input.billing_address_state,
            client_input.billing_address_postal_code
        ]):
            address = {}
            if client_input.billing_address_line1:
                address["Line1"] = client_input.billing_address_line1
            if client_input.billing_address_line2:
                address["Line2"] = client_input.billing_address_line2
            if client_input.billing_address_city:
                address["City"] = client_input.billing_address_city
            if client_input.billing_address_state:
                address["CountrySubDivisionCode"] = client_input.billing_address_state
            if client_input.billing_address_postal_code:
                address["PostalCode"] = client_input.billing_address_postal_code
            if client_input.billing_address_country:
                address["Country"] = client_input.billing_address_country

            customer["BillAddr"] = address

        return customer

    def _get_due_on_receipt_term_id(self) -> Optional[str]:
        """
        Look up the 'Due on receipt' payment term ID in QuickBooks.

        Returns:
            Term ID if found, None otherwise
        """
        try:
            # Query for payment terms
            query = "SELECT * FROM Term WHERE Name = 'Due on receipt'"
            url = self._get_api_url("query")
            response = self._make_api_request(
                "GET",
                f"{url}?query={requests.utils.quote(query)}"
            )

            if response.status_code == 200:
                data = response.json()
                terms = data.get('QueryResponse', {}).get('Term', [])
                if terms:
                    term_id = terms[0].get('Id')
                    log_debug(f"Found 'Due on receipt' term ID: {term_id}")
                    return term_id

            # Try alternate names
            for alt_name in ['Due on Receipt', 'Due On Receipt', 'Net 0']:
                query = f"SELECT * FROM Term WHERE Name = '{alt_name}'"
                response = self._make_api_request(
                    "GET",
                    f"{url}?query={requests.utils.quote(query)}"
                )
                if response.status_code == 200:
                    data = response.json()
                    terms = data.get('QueryResponse', {}).get('Term', [])
                    if terms:
                        term_id = terms[0].get('Id')
                        log_debug(f"Found '{alt_name}' term ID: {term_id}")
                        return term_id

        except Exception as e:
            log_warning(f"Could not look up payment terms: {e}")

        return None

    def _apply_defaults_and_check(self, customer_id: str) -> List[str]:
        """
        Apply default settings and check for issues.

        Args:
            customer_id: Created customer ID

        Returns:
            List of issue descriptions (empty if no issues)
        """
        issues = []

        try:
            # Get the customer first
            url = self._get_api_url(f"customer/{customer_id}")
            response = self._make_api_request("GET", url)

            if response.status_code != 200:
                issues.append("Could not retrieve customer to apply defaults")
                return issues

            customer_data = response.json().get('Customer', {})

            # Check if payment terms need to be applied
            if not customer_data.get('SalesTermRef'):
                term_id = self._get_due_on_receipt_term_id()

                if term_id:
                    # Update customer with payment terms
                    update_data = {
                        "Id": customer_id,
                        "SyncToken": customer_data.get('SyncToken', '0'),
                        "SalesTermRef": {
                            "value": term_id
                        }
                    }

                    update_url = self._get_api_url("customer")
                    update_response = self._make_api_request("POST", update_url, update_data)

                    if update_response.status_code in [200, 201]:
                        log_info("Applied payment terms: Due on receipt")
                    else:
                        error_msg = self._parse_api_error(update_response.json() if update_response.content else {})
                        issues.append(f"Could not apply payment terms: {error_msg}")
                else:
                    issues.append("Payment term 'Due on receipt' not found in QuickBooks - please create it or apply manually")

        except Exception as e:
            issues.append(f"Could not apply defaults: {str(e)}")

        return issues

    def _parse_api_error(self, error_data: dict) -> str:
        """Parse QBO API error response."""
        fault = error_data.get('Fault', {})
        errors = fault.get('Error', [])

        if errors:
            messages = [e.get('Message', '') + ' ' + e.get('Detail', '') for e in errors]
            return '; '.join(filter(None, messages)).strip()

        return "Unknown API error"

    def _log_result(self, module: str, client_name: str, result: QBOResult):
        """
        Log operation result.

        Args:
            module: Module name
            client_name: Client name
            result: Operation result
        """
        log_entry = {
            "module": module,
            "client_name": client_name,
            "result": result.to_dict(),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        log_info(f"[{module}] Result: {json.dumps(log_entry)}")

    def get_customer_url(self, customer_id: str) -> str:
        """Get the QuickBooks URL for a customer."""
        if self.use_sandbox:
            return f"https://app.sandbox.qbo.intuit.com/app/customerdetail?nameId={customer_id}"
        return f"https://qbo.intuit.com/app/customerdetail?nameId={customer_id}"


# Singleton instance
_quickbooks_service: Optional[QuickBooksService] = None


def get_quickbooks_service() -> QuickBooksService:
    """Get or create the QuickBooks service instance."""
    global _quickbooks_service
    if _quickbooks_service is None:
        _quickbooks_service = QuickBooksService()
    return _quickbooks_service


def init_quickbooks_service(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    realm_id: Optional[str] = None,
    use_sandbox: bool = True,
    trial_mode: bool = True
) -> QuickBooksService:
    """
    Initialize QuickBooks service with configuration.

    Args:
        client_id: Intuit OAuth client ID
        client_secret: Intuit OAuth client secret
        realm_id: QuickBooks company (realm) ID
        use_sandbox: Use sandbox environment
        trial_mode: Run in trial mode (no actual changes)

    Returns:
        Initialized QuickBooks service
    """
    global _quickbooks_service
    _quickbooks_service = QuickBooksService(
        client_id=client_id,
        client_secret=client_secret,
        realm_id=realm_id,
        use_sandbox=use_sandbox,
        trial_mode=trial_mode
    )
    return _quickbooks_service
