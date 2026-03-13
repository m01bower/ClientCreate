"""
Configuration manager for ClientCreate.

Non-secret settings (Drive folder IDs, HubSpot portal/pipeline,
QBO realm_id, sandbox flag) come exclusively from the MasterConfig
Google Sheet.  MasterConfig is REQUIRED - there is no local fallback.

Secrets:
    - QBO client_id, client_secret (OS keyring, service "BosOpt")
    - HubSpot access token (OS keyring, service "BostonHCP")
    - Google Places API key (OS keyring, service "BosOpt")

Files stored in _shared_config/apps/ClientCreate/:
    - config.json (local secrets: trial_mode, opencorporates token)
    - client_history.json
    - activity_log.txt
    - qbo_tokens.json

Google credentials/tokens in _shared_config/clients/{ClientName}/
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict, field

import keyring

from logger_setup import get_logger, log_info, log_error, log_debug


# App-specific config in shared directory
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SHARED_CONFIG_DIR = _PROJECT_ROOT.parent / "_shared_config"
CONFIG_DIR = _SHARED_CONFIG_DIR / "apps" / "ClientCreate"
CONFIG_FILENAME = 'config.json'
KEYRING_SERVICE = "BostonHCP"
KEYRING_USERNAME = "HubSpot-AccessToken"
QBO_KEYRING_SERVICE = "BosOpt"
QBO_KEYRING_CLIENT_ID = "QBO-ClientID"
QBO_KEYRING_CLIENT_SECRET = "QBO-ClientSecret"
QBO_KEYRING_SANDBOX_CLIENT_ID = "QBO-Sandbox-ClientID"
QBO_KEYRING_SANDBOX_CLIENT_SECRET = "QBO-Sandbox-ClientSecret"
PLACES_KEYRING_SERVICE = "BosOpt"
PLACES_KEYRING_USERNAME = "GooglePlaces-APIKey"
HISTORY_FILENAME = 'client_history.json'
LOG_FILENAME = 'activity_log.txt'

# _SHARED_CONFIG_DIR defined above with CONFIG_DIR


def _get_master_config():
    """
    Import and instantiate MasterConfig from _shared_config.

    Raises RuntimeError if MasterConfig cannot be loaded - there is no
    local fallback for non-secret configuration.
    """
    try:
        # Add _shared_config to sys.path temporarily if needed
        shared_str = str(_SHARED_CONFIG_DIR)
        added = False
        if shared_str not in sys.path:
            sys.path.insert(0, shared_str)
            added = True

        from config_reader import MasterConfig
        mc = MasterConfig()

        if added:
            sys.path.remove(shared_str)

        return mc
    except Exception as e:
        raise RuntimeError(
            f"MasterConfig is required but could not be loaded: {e}\n"
            f"Ensure _shared_config is available at: {_SHARED_CONFIG_DIR}"
        ) from e


@dataclass
class GoogleDriveConfig:
    """Google Drive configuration (values from master config)."""
    template_folder_id: str = ""
    destination_folder_id: str = ""


@dataclass
class HubSpotConfig:
    """HubSpot configuration (non-secret values from master config)."""
    portal_id: str = ""
    deal_pipeline: str = ""
    deal_stage: str = ""


@dataclass
class GooglePlacesConfig:
    """Google Places API configuration (from OS keyring)."""
    api_key: str = ""

    def load_from_keyring(self) -> None:
        """Populate api_key from the OS keyring."""
        try:
            self.api_key = keyring.get_password(
                PLACES_KEYRING_SERVICE, PLACES_KEYRING_USERNAME
            ) or ""
        except Exception as e:
            from logger_setup import log_error as _log_error
            _log_error(f"Failed to read Google Places API key from keyring: {e}")
            self.api_key = ""


@dataclass
class OpenCorporatesConfig:
    """OpenCorporates API configuration (local secret)."""
    api_token: str = ""


@dataclass
class QuickBooksConfig:
    """QuickBooks Online configuration.

    realm_id and use_sandbox come from master config.
    client_id and client_secret come from the OS keyring.
    Sandbox clients use "QBO-Sandbox-ClientID" / "QBO-Sandbox-ClientSecret".
    Production clients use "QBO-ClientID" / "QBO-ClientSecret".
    """
    client_id: str = ""
    client_secret: str = ""
    realm_id: str = ""
    use_sandbox: bool = True
    trial_mode: bool = True  # Always start in trial mode for safety

    def load_credentials_from_keyring(self) -> None:
        """Populate client_id and client_secret from the OS keyring.

        Picks sandbox or production keys based on self.use_sandbox.
        """
        try:
            if self.use_sandbox:
                id_key = QBO_KEYRING_SANDBOX_CLIENT_ID
                secret_key = QBO_KEYRING_SANDBOX_CLIENT_SECRET
            else:
                id_key = QBO_KEYRING_CLIENT_ID
                secret_key = QBO_KEYRING_CLIENT_SECRET
            self.client_id = keyring.get_password(
                QBO_KEYRING_SERVICE, id_key
            ) or ""
            self.client_secret = keyring.get_password(
                QBO_KEYRING_SERVICE, secret_key
            ) or ""
        except Exception as e:
            from logger_setup import log_error as _log_error
            _log_error(f"Failed to read QBO credentials from keyring: {e}")
            self.client_id = ""
            self.client_secret = ""


@dataclass
class AppConfig:
    """Main application configuration.

    Combines master config (non-secret) with local secrets.
    """
    configuration_name: str = ""
    created_date: str = ""
    google_drive: GoogleDriveConfig = field(default_factory=GoogleDriveConfig)
    hubspot: HubSpotConfig = field(default_factory=HubSpotConfig)
    google_places: GooglePlacesConfig = field(default_factory=GooglePlacesConfig)
    quickbooks: QuickBooksConfig = field(default_factory=QuickBooksConfig)
    opencorporates: OpenCorporatesConfig = field(default_factory=OpenCorporatesConfig)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization.

        Only serializes local secrets - master config values are not saved
        to config.json since they come from the shared sheet.
        """
        return {
            'configuration_name': self.configuration_name,
            'created_date': self.created_date,
            'quickbooks': {
                'trial_mode': self.quickbooks.trial_mode,
            },
            'opencorporates': asdict(self.opencorporates),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AppConfig':
        """Create from dictionary (local secrets only).

        Only reads secret fields from config.json.  Non-secret values
        (Drive folders, HubSpot portal/pipeline, QBO realm/sandbox)
        come exclusively from MasterConfig via _merge_master_config().
        """
        config = cls()
        config.configuration_name = data.get('configuration_name', '')
        config.created_date = data.get('created_date', '')

        config.google_places = GooglePlacesConfig()
        config.google_places.load_from_keyring()

        qb = data.get('quickbooks', {})
        config.quickbooks = QuickBooksConfig(
            trial_mode=qb.get('trial_mode', True)
        )
        config.quickbooks.load_credentials_from_keyring()

        oc = data.get('opencorporates', {})
        config.opencorporates = OpenCorporatesConfig(
            api_token=oc.get('api_token', '')
        )

        return config


@dataclass
class ClientRecord:
    """Record of a created client."""
    created_date: str
    company_name: str
    domain: str
    google_drive_folder_id: str = ""
    google_drive_folder_url: str = ""
    hubspot_company_id: str = ""
    hubspot_company_url: str = ""
    hubspot_deal_id: str = ""
    hubspot_deal_url: str = ""
    quickbooks_customer_id: str = ""
    quickbooks_customer_url: str = ""
    created_by: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ClientRecord':
        """Create from dictionary."""
        return cls(
            created_date=data.get('created_date', ''),
            company_name=data.get('company_name', ''),
            domain=data.get('domain', ''),
            google_drive_folder_id=data.get('google_drive_folder_id', ''),
            google_drive_folder_url=data.get('google_drive_folder_url', ''),
            hubspot_company_id=data.get('hubspot_company_id', ''),
            hubspot_company_url=data.get('hubspot_company_url', ''),
            hubspot_deal_id=data.get('hubspot_deal_id', ''),
            hubspot_deal_url=data.get('hubspot_deal_url', ''),
            quickbooks_customer_id=data.get('quickbooks_customer_id', ''),
            quickbooks_customer_url=data.get('quickbooks_customer_url', ''),
            created_by=data.get('created_by', '')
        )


class ConfigManager:
    """Manager for application configuration.

    Merges shared master config (non-secret settings from Google Sheet)
    with local secrets (config/config.json + OS keyring).
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize config manager.

        Args:
            config_dir: Directory for config files (default: <project_root>/config/)
        """
        self.logger = get_logger()
        self.config_dir = config_dir or CONFIG_DIR
        self._config: Optional[AppConfig] = None
        self._history: List[ClientRecord] = []
        self._master_config = None  # MasterConfig instance (lazy loaded)
        self._master_config_loaded = False  # Sentinel: True once load attempted
        self._available_clients: List[str] = []

        # Ensure config directory exists
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """Ensure the config directory exists."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log_error(f"Failed to create config directory: {e}")

    def _get_config_path(self) -> Path:
        """Get path to config file."""
        return self.config_dir / CONFIG_FILENAME

    def _get_history_path(self) -> Path:
        """Get path to history file."""
        return self.config_dir / HISTORY_FILENAME

    def _get_log_path(self) -> Path:
        """Get path to activity log file."""
        return self.config_dir / LOG_FILENAME

    # =========================================================================
    # Master Config Integration
    # =========================================================================

    def _load_master_config(self):
        """Load the shared MasterConfig (lazy, one-time).

        Raises RuntimeError if MasterConfig cannot be loaded.
        """
        if self._master_config_loaded:
            return
        self._master_config_loaded = True
        self._master_config = _get_master_config()  # raises on failure
        self._available_clients = self._master_config.list_clients()
        log_info(f"Master config loaded: {len(self._available_clients)} clients available")

    def get_available_clients(self) -> List[str]:
        """Get list of client keys from the master config.

        Returns:
            List of client key strings (e.g., ["BostonHCP", "OtherClient"])
        """
        self._load_master_config()
        return list(self._available_clients)

    def _merge_master_config(self, config: AppConfig) -> AppConfig:
        """
        Overlay master config values onto an AppConfig.

        Non-secret values (Drive folders, HubSpot portal/pipeline,
        QBO realm/sandbox) are pulled from the master sheet for the
        client identified by config.configuration_name.

        Local secrets (QBO client_id/secret, Places API key, etc.)
        are preserved from the local config.

        Args:
            config: AppConfig with local secrets loaded

        Returns:
            The same AppConfig, updated with master config values

        Raises:
            RuntimeError: If MasterConfig is unavailable
            KeyError: If configuration_name is not found in master config
        """
        self._load_master_config()  # raises on failure

        client_key = config.configuration_name
        if not client_key:
            raise ValueError(
                "configuration_name is not set in config.json - "
                "cannot look up client in master config"
            )

        try:
            client_cfg = self._master_config.get_client(client_key)
        except KeyError:
            raise KeyError(
                f"Client '{client_key}' not found in master config. "
                f"Available: {self._available_clients}"
            )

        # Google Drive - from master config
        if client_cfg.drive.template_folder_id:
            config.google_drive.template_folder_id = client_cfg.drive.template_folder_id
        if client_cfg.drive.destination_folder_id:
            config.google_drive.destination_folder_id = client_cfg.drive.destination_folder_id

        # HubSpot - from master config
        if client_cfg.hubspot.portal_id:
            config.hubspot.portal_id = client_cfg.hubspot.portal_id
        if client_cfg.hubspot.deal_pipeline:
            config.hubspot.deal_pipeline = client_cfg.hubspot.deal_pipeline
        if client_cfg.hubspot.deal_stage:
            config.hubspot.deal_stage = client_cfg.hubspot.deal_stage

        # QBO - realm_id and environment from master config
        if client_cfg.qbo.realm_id:
            config.quickbooks.realm_id = client_cfg.qbo.realm_id
        if client_cfg.qbo.environment:
            config.quickbooks.use_sandbox = (
                client_cfg.qbo.environment.lower() == "sandbox"
            )

        log_info(f"Merged master config for client '{client_key}'")
        return config

    # =========================================================================
    # Config Load / Save
    # =========================================================================

    def has_config(self) -> bool:
        """Check if configuration exists locally."""
        return self._get_config_path().exists()

    def load_config(self) -> Optional[AppConfig]:
        """
        Load configuration from local file, then merge master config.

        Local config.json provides secrets (QBO client_id/secret,
        Places API key, etc.). Master config provides non-secret
        settings (Drive folders, HubSpot portal, QBO realm).

        Returns:
            AppConfig if found, None otherwise
        """
        config_path = self._get_config_path()

        if not config_path.exists():
            log_debug("No config file found locally")
            return None

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._config = AppConfig.from_dict(data)

            # Merge non-secret values from master config
            self._config = self._merge_master_config(self._config)

            log_info(f"Loaded configuration: {self._config.configuration_name}")
            return self._config

        except json.JSONDecodeError as e:
            log_error(f"Invalid config JSON: {e}")
            return None
        except Exception as e:
            log_error(f"Error loading config: {e}")
            return None

    def save_config(self, config: AppConfig) -> bool:
        """
        Save configuration to local file.

        Only saves local secrets - master config values are not persisted
        locally since they come from the shared Google Sheet.

        Args:
            config: Configuration to save

        Returns:
            True on success
        """
        try:
            self._ensure_config_dir()
            config_path = self._get_config_path()

            content = json.dumps(config.to_dict(), indent=2)
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)

            self._config = config
            log_info(f"Saved configuration: {config.configuration_name}")
            return True

        except Exception as e:
            log_error(f"Error saving config: {e}")
            return False

    def get_config(self) -> Optional[AppConfig]:
        """Get current configuration, loading if necessary."""
        if self._config is None:
            self.load_config()
        return self._config

    def update_hubspot_token(self, new_token: str) -> bool:
        """
        Update HubSpot access token in the OS keyring.

        Args:
            new_token: New access token

        Returns:
            True on success
        """
        return self.set_hubspot_token(new_token)

    # =========================================================================
    # Keyring Token Management
    # =========================================================================

    def get_hubspot_token(self) -> Optional[str]:
        """
        Retrieve the HubSpot access token from the OS keyring.

        Returns:
            The token string, or None if not stored
        """
        try:
            token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            return token
        except Exception as e:
            log_error(f"Error reading token from keyring: {e}")
            return None

    def set_hubspot_token(self, token: str) -> bool:
        """
        Store the HubSpot access token in the OS keyring.

        Args:
            token: The access token to store

        Returns:
            True on success, False on error
        """
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
            log_info("HubSpot token saved to OS keyring")
            return True
        except Exception as e:
            log_error(f"Error saving token to keyring: {e}")
            return False

    def migrate_hubspot_token(self) -> None:
        """
        One-time migration: move token from config.json to OS keyring.

        If config.json contains a hubspot.access_token field, this method
        stores it in the keyring and removes it from the JSON file. Runs
        silently - no-ops if there is no token to migrate.
        """
        config_path = self._get_config_path()
        if not config_path.exists():
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return

        hs = data.get('hubspot', {})
        old_token = hs.get('access_token')
        if not old_token:
            return

        # Store in keyring
        if not self.set_hubspot_token(old_token):
            log_error("Migration failed: could not save token to keyring")
            return

        # Remove from JSON and rewrite
        del data['hubspot']['access_token']
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            log_info("Migrated HubSpot token from config.json to OS keyring")
        except Exception as e:
            log_error(f"Migration warning: token saved to keyring but could not update config.json: {e}")

    def migrate_qbo_credentials(self) -> None:
        """
        One-time migration: move QBO client_id/client_secret from
        config.json to the OS keyring.

        If config.json contains quickbooks.client_id and/or
        quickbooks.client_secret, this method stores them in the keyring
        and removes them from the JSON file. No-ops if nothing to migrate.
        """
        config_path = self._get_config_path()
        if not config_path.exists():
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return

        qb = data.get('quickbooks', {})
        old_id = qb.get('client_id')
        old_secret = qb.get('client_secret')
        if not old_id and not old_secret:
            return

        # Store in keyring
        try:
            if old_id:
                keyring.set_password(QBO_KEYRING_SERVICE, QBO_KEYRING_CLIENT_ID, old_id)
            if old_secret:
                keyring.set_password(QBO_KEYRING_SERVICE, QBO_KEYRING_CLIENT_SECRET, old_secret)
        except Exception as e:
            log_error(f"QBO migration failed: could not save credentials to keyring: {e}")
            return

        # Remove from JSON and rewrite
        changed = False
        if 'client_id' in qb:
            del data['quickbooks']['client_id']
            changed = True
        if 'client_secret' in qb:
            del data['quickbooks']['client_secret']
            changed = True

        if changed:
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                log_info("Migrated QBO credentials from config.json to OS keyring")
            except Exception as e:
                log_error(
                    f"QBO migration warning: credentials saved to keyring "
                    f"but could not update config.json: {e}"
                )

    def update_places_api_key(self, new_key: str) -> bool:
        """
        Update Google Places API key in the OS keyring.

        Args:
            new_key: New API key

        Returns:
            True on success
        """
        try:
            keyring.set_password(PLACES_KEYRING_SERVICE, PLACES_KEYRING_USERNAME, new_key)
            # Update in-memory config if loaded
            config = self.get_config()
            if config:
                config.google_places.api_key = new_key
            log_info("Google Places API key saved to OS keyring")
            return True
        except Exception as e:
            log_error(f"Error saving Google Places API key to keyring: {e}")
            return False

    def migrate_places_api_key(self) -> None:
        """
        One-time migration: move Google Places API key from config.json
        to the OS keyring.

        If config.json contains a google_places.api_key field, this method
        stores it in the keyring and removes it from the JSON file.
        No-ops if nothing to migrate.
        """
        config_path = self._get_config_path()
        if not config_path.exists():
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return

        gp = data.get('google_places', {})
        old_key = gp.get('api_key')
        if not old_key:
            return

        # Store in keyring
        try:
            keyring.set_password(PLACES_KEYRING_SERVICE, PLACES_KEYRING_USERNAME, old_key)
        except Exception as e:
            log_error(f"Places migration failed: could not save key to keyring: {e}")
            return

        # Remove from JSON and rewrite
        del data['google_places']
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            log_info("Migrated Google Places API key from config.json to OS keyring")
        except Exception as e:
            log_error(
                f"Places migration warning: key saved to keyring "
                f"but could not update config.json: {e}"
            )

    # =========================================================================
    # Client History
    # =========================================================================

    def load_history(self) -> List[ClientRecord]:
        """
        Load client history from local file.

        Returns:
            List of client records
        """
        history_path = self._get_history_path()

        if not history_path.exists():
            return []

        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._history = [
                ClientRecord.from_dict(r) for r in data.get('clients', [])
            ]
            return self._history

        except Exception as e:
            log_error(f"Error loading history: {e}")
            return []

    def add_client_record(self, record: ClientRecord) -> bool:
        """
        Add a new client record to history.

        Args:
            record: Client record to add

        Returns:
            True on success
        """
        try:
            # Load current history
            self.load_history()

            # Add new record
            self._history.insert(0, record)  # Add to beginning

            # Save updated history
            self._ensure_config_dir()
            history_path = self._get_history_path()

            data = {
                'clients': [r.to_dict() for r in self._history]
            }
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            log_info(f"Added client to history: {record.company_name}")
            return True

        except Exception as e:
            log_error(f"Error adding client record: {e}")
            return False

    def get_history(self) -> List[ClientRecord]:
        """Get client history, loading if necessary."""
        if not self._history:
            self.load_history()
        return self._history

    # =========================================================================
    # Activity Logging
    # =========================================================================

    def log_activity(self, message: str) -> bool:
        """
        Append a message to the activity log.

        Args:
            message: Message to log

        Returns:
            True on success
        """
        try:
            self._ensure_config_dir()
            log_path = self._get_log_path()

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_line = f"{timestamp} | {message}\n"

            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)

            return True

        except Exception as e:
            log_error(f"Error logging activity: {e}")
            return False


# Singleton instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get or create the config manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def init_config_manager(config_dir: Optional[Path] = None) -> ConfigManager:
    """
    Initialize config manager.

    Args:
        config_dir: Optional custom config directory

    Returns:
        Initialized config manager
    """
    global _config_manager
    _config_manager = ConfigManager(config_dir)
    return _config_manager
