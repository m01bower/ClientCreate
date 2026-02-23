"""
Configuration manager for ClientCreate.

Manages configuration stored locally in the project's config/ folder.
Also handles client history and activity logging.

Configuration is stored in:
    <project_root>/config/config.json
    <project_root>/config/client_history.json
    <project_root>/config/activity_log.txt
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict, field

import keyring

from logger_setup import get_logger, log_info, log_error, log_debug


# Local config directory - relative to project root
# Path: src/core/config_manager.py -> go up 3 levels to project root, then config/
_PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = _PROJECT_ROOT / "config"
CONFIG_FILENAME = 'config.json'
KEYRING_SERVICE = "BostonHCP"
KEYRING_USERNAME = "HubSpot-AccessToken"
HISTORY_FILENAME = 'client_history.json'
LOG_FILENAME = 'activity_log.txt'


@dataclass
class GoogleDriveConfig:
    """Google Drive configuration."""
    template_folder_id: str = ""
    destination_folder_id: str = ""


@dataclass
class HubSpotConfig:
    """HubSpot configuration."""
    portal_id: str = ""


@dataclass
class GooglePlacesConfig:
    """Google Places API configuration."""
    api_key: str = ""


@dataclass
class QuickBooksConfig:
    """QuickBooks Online configuration."""
    client_id: str = ""
    client_secret: str = ""
    realm_id: str = ""
    use_sandbox: bool = True
    trial_mode: bool = True  # Always start in trial mode for safety


@dataclass
class AppConfig:
    """Main application configuration."""
    configuration_name: str = ""
    created_date: str = ""
    google_drive: GoogleDriveConfig = field(default_factory=GoogleDriveConfig)
    hubspot: HubSpotConfig = field(default_factory=HubSpotConfig)
    google_places: GooglePlacesConfig = field(default_factory=GooglePlacesConfig)
    quickbooks: QuickBooksConfig = field(default_factory=QuickBooksConfig)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'configuration_name': self.configuration_name,
            'created_date': self.created_date,
            'google_drive': asdict(self.google_drive),
            'hubspot': asdict(self.hubspot),
            'google_places': asdict(self.google_places),
            'quickbooks': asdict(self.quickbooks)
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AppConfig':
        """Create from dictionary."""
        config = cls()
        config.configuration_name = data.get('configuration_name', '')
        config.created_date = data.get('created_date', '')

        gd = data.get('google_drive', {})
        config.google_drive = GoogleDriveConfig(
            template_folder_id=gd.get('template_folder_id', ''),
            destination_folder_id=gd.get('destination_folder_id', '')
        )

        hs = data.get('hubspot', {})
        config.hubspot = HubSpotConfig(
            portal_id=hs.get('portal_id', '')
        )

        gp = data.get('google_places', {})
        config.google_places = GooglePlacesConfig(
            api_key=gp.get('api_key', '')
        )

        qb = data.get('quickbooks', {})
        config.quickbooks = QuickBooksConfig(
            client_id=qb.get('client_id', ''),
            client_secret=qb.get('client_secret', ''),
            realm_id=qb.get('realm_id', ''),
            use_sandbox=qb.get('use_sandbox', True),
            trial_mode=qb.get('trial_mode', True)
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
    """Manager for application configuration stored locally."""

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

    def has_config(self) -> bool:
        """Check if configuration exists locally."""
        return self._get_config_path().exists()

    def load_config(self) -> Optional[AppConfig]:
        """
        Load configuration from local file.

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

    def update_places_api_key(self, new_key: str) -> bool:
        """
        Update Google Places API key.

        Args:
            new_key: New API key

        Returns:
            True on success
        """
        config = self.get_config()
        if not config:
            return False

        config.google_places.api_key = new_key
        return self.save_config(config)

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
