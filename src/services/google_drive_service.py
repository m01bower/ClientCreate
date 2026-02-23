"""
Google Drive service for ClientCreate.

Handles authentication and all Drive operations including:
- OAuth authentication
- Folder creation and checking
- File copying with renaming
- App data folder access for config/logs
"""

import os
import re
import json
from typing import Optional, List, Dict, Tuple, Callable
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from logger_setup import get_logger, log_info, log_error, log_warning, log_debug


# Google API scopes - shared across BostonHCP projects
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/userinfo.email',
]


class GoogleDriveService:
    """Service for Google Drive operations."""

    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize Google Drive service.

        Args:
            credentials_path: Path to credentials.json file.
                            If None, uses credentials in project's config/ folder.
        """
        self.logger = get_logger()

        # Path configuration - relative to project structure
        # src/services/google_drive_service.py -> up 3 levels = project root
        self._project_root = Path(__file__).parent.parent.parent

        # Shared credentials in _shared_config/clients/BostonHCP/
        self._credentials_base = self._project_root.parent / "_shared_config" / "clients" / "BostonHCP"
        self.credentials_path = credentials_path or str(self._credentials_base / "credentials.json")

        # Token stored in shared BostonHCP folder
        self._token_base = self._credentials_base
        self.token_path = str(self._token_base / "token.json")

        self.creds: Optional[Credentials] = None
        self.drive_service = None
        self.gmail_service = None

    def _get_token_path(self) -> str:
        """Get path for storing user token."""
        # Ensure config directory exists
        self._token_base.mkdir(parents=True, exist_ok=True)
        return str(self._token_base / "token.json")

    def has_credentials_file(self) -> bool:
        """Check if credentials.json exists."""
        return os.path.exists(self.credentials_path)

    def is_authenticated(self) -> bool:
        """Check if user is authenticated with valid token."""
        if self.creds and self.creds.valid:
            return True

        # Try to load existing token
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(
                    self.token_path, SCOPES
                )
                if self.creds.valid:
                    return True
                if self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                    self._save_token()
                    return True
            except Exception as e:
                log_warning(f"Failed to load existing token: {e}")

        return False

    def authenticate(self, force_new: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Authenticate with Google.

        Args:
            force_new: Force new authentication even if token exists

        Returns:
            Tuple of (success, error_message)
        """
        if not self.has_credentials_file():
            return False, f"credentials.json not found at {self.credentials_path}"

        try:
            if not force_new and self.is_authenticated():
                self._build_services()
                return True, None

            # Need new authentication
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_path, SCOPES
            )
            self.creds = flow.run_local_server(port=0)
            self._save_token()
            self._build_services()

            log_info("Google authentication successful")
            return True, None

        except Exception as e:
            log_error(f"Google authentication failed: {e}")
            return False, str(e)

    def _save_token(self):
        """Save credentials token to file."""
        if self.creds:
            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())

    def _build_services(self):
        """Build Google API service objects."""
        if self.creds:
            self.drive_service = build('drive', 'v3', credentials=self.creds)
            self.gmail_service = build('gmail', 'v1', credentials=self.creds)

    def get_user_email(self) -> Optional[str]:
        """Get the authenticated user's email address."""
        if not self.creds:
            log_warning("No credentials - cannot get user email")
            return None
        try:
            # Use OAuth2 userinfo API to get email
            from googleapiclient.discovery import build
            oauth2_service = build('oauth2', 'v2', credentials=self.creds)
            user_info = oauth2_service.userinfo().get().execute()
            email = user_info.get('email')
            log_debug(f"Got user email: {email}")
            return email
        except Exception as e:
            log_error(f"Failed to get user email: {e}")
            return None

    # =========================================================================
    # Config Folder Operations (stored in destination folder, shared across users)
    # =========================================================================

    _config_folder_id: Optional[str] = None
    CONFIG_FOLDER_NAME = "_ClientCreate_Config"

    def _get_or_create_config_folder(self, destination_folder_id: str) -> Optional[str]:
        """
        Get or create the config folder in the destination folder.

        Args:
            destination_folder_id: The destination folder ID to store config in

        Returns:
            Config folder ID or None on failure
        """
        if self._config_folder_id:
            return self._config_folder_id

        if not self.drive_service:
            return None

        try:
            # Check if config folder exists
            exists, folder_id = self.folder_exists(self.CONFIG_FOLDER_NAME, destination_folder_id)
            if exists:
                self._config_folder_id = folder_id
                return folder_id

            # Create config folder
            success, folder_id, error = self.create_folder(
                self.CONFIG_FOLDER_NAME,
                destination_folder_id
            )
            if success:
                self._config_folder_id = folder_id
                log_info(f"Created config folder: {self.CONFIG_FOLDER_NAME}")
                return folder_id

            log_error(f"Failed to create config folder: {error}")
            return None

        except Exception as e:
            log_error(f"Error getting/creating config folder: {e}")
            return None

    def set_config_folder(self, destination_folder_id: str) -> bool:
        """
        Initialize config folder in the given destination folder.

        Args:
            destination_folder_id: Destination folder ID

        Returns:
            True if config folder is ready
        """
        folder_id = self._get_or_create_config_folder(destination_folder_id)
        return folder_id is not None

    def get_app_data_file(self, filename: str, destination_folder_id: Optional[str] = None) -> Optional[str]:
        """
        Get content of a config file from the config folder.

        Args:
            filename: Name of file to read
            destination_folder_id: Destination folder ID (required if not already set)

        Returns:
            File content as string, or None if not found
        """
        if not self.drive_service:
            return None

        config_folder_id = self._config_folder_id
        if not config_folder_id and destination_folder_id:
            config_folder_id = self._get_or_create_config_folder(destination_folder_id)

        if not config_folder_id:
            log_error("Config folder not initialized - need destination_folder_id")
            return None

        try:
            # Search for file in config folder
            query = f"name = '{filename}' and '{config_folder_id}' in parents and trashed = false"
            results = self.drive_service.files().list(
                q=query,
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])
            if not files:
                return None

            file_id = files[0]['id']

            # Download content
            content = self.drive_service.files().get_media(
                fileId=file_id
            ).execute()

            return content.decode('utf-8')

        except HttpError as e:
            log_debug(f"Error reading config file {filename}: {e}")
            return None

    def save_app_data_file(self, filename: str, content: str, destination_folder_id: Optional[str] = None) -> bool:
        """
        Save content to a config file in the config folder.

        Args:
            filename: Name of file to save
            content: Content to write
            destination_folder_id: Destination folder ID (required if not already set)

        Returns:
            True on success
        """
        if not self.drive_service:
            return False

        config_folder_id = self._config_folder_id
        if not config_folder_id and destination_folder_id:
            config_folder_id = self._get_or_create_config_folder(destination_folder_id)

        if not config_folder_id:
            log_error("Config folder not initialized - need destination_folder_id")
            return False

        try:
            # Check if file exists
            query = f"name = '{filename}' and '{config_folder_id}' in parents and trashed = false"
            results = self.drive_service.files().list(
                q=query,
                fields='files(id)'
            ).execute()

            files = results.get('files', [])

            from googleapiclient.http import MediaInMemoryUpload
            media = MediaInMemoryUpload(
                content.encode('utf-8'),
                mimetype='application/json'
            )

            if files:
                # Update existing file
                self.drive_service.files().update(
                    fileId=files[0]['id'],
                    media_body=media
                ).execute()
            else:
                # Create new file
                file_metadata = {
                    'name': filename,
                    'parents': [config_folder_id]
                }
                self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

            return True

        except HttpError as e:
            log_error(f"Error saving config file {filename}: {e}")
            return False

    def append_to_app_data_file(self, filename: str, content: str, destination_folder_id: Optional[str] = None) -> bool:
        """
        Append content to a config file in the config folder.

        Args:
            filename: Name of file to append to
            content: Content to append
            destination_folder_id: Destination folder ID (required if not already set)

        Returns:
            True on success
        """
        existing = self.get_app_data_file(filename, destination_folder_id) or ""
        new_content = existing + content + "\n"
        return self.save_app_data_file(filename, new_content, destination_folder_id)

    # =========================================================================
    # Folder Operations
    # =========================================================================

    def test_folder_access(self, folder_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Test if a folder is accessible.

        Args:
            folder_id: Google Drive folder ID

        Returns:
            Tuple of (accessible, folder_name, error_message)
        """
        if not self.drive_service:
            return False, None, "Not authenticated"

        try:
            folder = self.drive_service.files().get(
                fileId=folder_id,
                fields='id, name, mimeType'
            ).execute()

            if folder.get('mimeType') != 'application/vnd.google-apps.folder':
                return False, None, "ID does not point to a folder"

            return True, folder.get('name'), None

        except HttpError as e:
            if e.resp.status == 404:
                return False, None, "Folder not found"
            return False, None, f"Access error: {e}"

    def folder_exists(self, folder_name: str, parent_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a folder with given name exists in parent.

        Args:
            folder_name: Name of folder to find
            parent_id: Parent folder ID

        Returns:
            Tuple of (exists, folder_id if exists)
        """
        if not self.drive_service:
            return False, None

        try:
            query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"

            results = self.drive_service.files().list(
                q=query,
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])
            if files:
                return True, files[0]['id']

            return False, None

        except HttpError as e:
            log_error(f"Error checking folder existence: {e}")
            return False, None

    def create_folder(self, folder_name: str, parent_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Create a new folder.

        Args:
            folder_name: Name for the new folder
            parent_id: Parent folder ID

        Returns:
            Tuple of (success, folder_id, error_message)
        """
        if not self.drive_service:
            return False, None, "Not authenticated"

        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }

            folder = self.drive_service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()

            folder_id = folder.get('id')
            log_info(f"Created folder: {folder_name}")
            return True, folder_id, None

        except HttpError as e:
            log_error(f"Error creating folder: {e}")
            return False, None, str(e)

    def get_folder_url(self, folder_id: str) -> str:
        """Get the web URL for a folder."""
        return f"https://drive.google.com/drive/folders/{folder_id}"

    # =========================================================================
    # File Operations
    # =========================================================================

    def list_folder_contents(self, folder_id: str) -> List[Dict]:
        """
        List all files and folders in a folder.

        Args:
            folder_id: Folder ID to list

        Returns:
            List of file/folder metadata dicts
        """
        if not self.drive_service:
            return []

        try:
            results = []
            page_token = None

            while True:
                response = self.drive_service.files().list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields='nextPageToken, files(id, name, mimeType)',
                    pageToken=page_token
                ).execute()

                results.extend(response.get('files', []))
                page_token = response.get('nextPageToken')

                if not page_token:
                    break

            return results

        except HttpError as e:
            log_error(f"Error listing folder: {e}")
            return []

    def copy_file(self, file_id: str, new_name: str, dest_folder_id: str) -> Tuple[bool, Optional[str]]:
        """
        Copy a file to a new location with a new name.

        Args:
            file_id: Source file ID
            new_name: New name for the copy
            dest_folder_id: Destination folder ID

        Returns:
            Tuple of (success, new_file_id)
        """
        if not self.drive_service:
            return False, None

        try:
            file_metadata = {
                'name': new_name,
                'parents': [dest_folder_id]
            }

            copied_file = self.drive_service.files().copy(
                fileId=file_id,
                body=file_metadata,
                fields='id'
            ).execute()

            return True, copied_file.get('id')

        except HttpError as e:
            log_error(f"Error copying file: {e}")
            return False, None

    def copy_folder_contents(
        self,
        source_folder_id: str,
        dest_folder_id: str,
        company_name: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        dry_run: bool = False
    ) -> Tuple[bool, List[str], Optional[str]]:
        """
        Recursively copy all contents from source to destination folder.
        Replaces "Client" in filenames with company name (case-insensitive).

        Args:
            source_folder_id: Source folder ID (template)
            dest_folder_id: Destination folder ID (new client folder)
            company_name: Company name to replace "Client" with
            progress_callback: Optional callback(filename, current, total)
            dry_run: If True, don't actually copy, just report what would happen

        Returns:
            Tuple of (success, list_of_copied_files, error_message)
        """
        if not self.drive_service:
            return False, [], "Not authenticated"

        copied_files = []

        try:
            contents = self.list_folder_contents(source_folder_id)
            total = len(contents)

            for i, item in enumerate(contents):
                item_name = item['name']
                item_id = item['id']
                item_type = item['mimeType']

                # Determine new name (replace Client with company name, case-insensitive)
                new_name = re.sub(
                    r'(?i)client',
                    company_name,
                    item_name
                )

                if progress_callback:
                    progress_callback(item_name, i + 1, total)

                if item_type == 'application/vnd.google-apps.folder':
                    # It's a folder - create it and recurse
                    if dry_run:
                        log_info(f"[DRY RUN] Would create folder: {item_name}")
                        copied_files.append(f"[FOLDER] {item_name}")
                    else:
                        success, new_folder_id, error = self.create_folder(
                            item_name,  # Keep original folder name
                            dest_folder_id
                        )
                        if not success:
                            return False, copied_files, f"Failed to create folder {item_name}: {error}"

                        # Recurse into subfolder
                        success, sub_files, error = self.copy_folder_contents(
                            item_id,
                            new_folder_id,
                            company_name,
                            progress_callback,
                            dry_run
                        )
                        if not success:
                            return False, copied_files, error

                        copied_files.extend(sub_files)
                else:
                    # It's a file - copy it
                    if dry_run:
                        log_info(f"[DRY RUN] Would copy: {item_name} → {new_name}")
                        copied_files.append(f"{item_name} → {new_name}")
                    else:
                        success, _ = self.copy_file(item_id, new_name, dest_folder_id)
                        if not success:
                            log_warning(f"Failed to copy file: {item_name}")
                        else:
                            log_info(f"Copied: {item_name} → {new_name}")
                            copied_files.append(f"{item_name} → {new_name}")

            return True, copied_files, None

        except Exception as e:
            log_error(f"Error copying folder contents: {e}")
            return False, copied_files, str(e)


# Singleton instance
_drive_service: Optional[GoogleDriveService] = None


def get_drive_service() -> GoogleDriveService:
    """Get or create the Google Drive service instance."""
    global _drive_service
    if _drive_service is None:
        _drive_service = GoogleDriveService()
    return _drive_service
