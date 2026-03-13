"""
Setup wizard for ClientCreate.

Multi-step wizard for initial configuration:
1. Configuration name
2. Google Drive authentication
3. Google Drive folder IDs
4. HubSpot authentication
5. Google Places API (optional)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Callable
import os

import keyring
from core.config_manager import (
    AppConfig, GoogleDriveConfig, HubSpotConfig, GooglePlacesConfig,
    QuickBooksConfig, get_config_manager, _get_master_config,
    QBO_KEYRING_SERVICE, QBO_KEYRING_CLIENT_ID, QBO_KEYRING_CLIENT_SECRET,
    QBO_KEYRING_SANDBOX_CLIENT_ID, QBO_KEYRING_SANDBOX_CLIENT_SECRET,
    PLACES_KEYRING_SERVICE, PLACES_KEYRING_USERNAME,
)
from services.google_drive_service import GoogleDriveService
from services.hubspot_service import HubSpotService
from services.company_lookup import test_places_api
from services.quickbooks_service import QuickBooksService
from logger_setup import log_info, log_error


class SetupWizard(tk.Toplevel):
    """Multi-step setup wizard dialog."""

    def __init__(self, parent, drive_service: GoogleDriveService, on_complete: Callable[[AppConfig], None]):
        """
        Initialize setup wizard.

        Args:
            parent: Parent window
            drive_service: Google Drive service (may need authentication)
            on_complete: Callback when setup is complete, receives AppConfig
        """
        super().__init__(parent)

        self.drive_service = drive_service
        self.on_complete = on_complete

        # Configuration being built
        self.config = AppConfig()
        self.config.google_drive = GoogleDriveConfig()
        self.config.hubspot = HubSpotConfig()
        self.config.google_places = GooglePlacesConfig()
        self.config.quickbooks = QuickBooksConfig()

        # Load available clients from master config
        self._master_config = _get_master_config()
        self._available_clients = (
            self._master_config.list_clients() if self._master_config else []
        )

        # Track validation state
        self.google_authenticated = False
        self.hubspot_validated = False
        self.quickbooks_validated = False
        self._hubspot_token = ""  # Stored in keyring, not in AppConfig

        # Window setup
        self.title("ClientCreate - Setup Wizard")
        self.geometry("550x450")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 550) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 450) // 2
        self.geometry(f"+{x}+{y}")

        # Current step (0-indexed)
        self.current_step = 0
        self.total_steps = 6

        # Build UI
        self._build_ui()
        self._show_step(0)

    def _build_ui(self):
        """Build the wizard UI."""
        # Main container
        self.main_frame = ttk.Frame(self, padding=20)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Header with step indicator
        self.header_frame = ttk.Frame(self.main_frame)
        self.header_frame.pack(fill=tk.X, pady=(0, 20))

        self.step_label = ttk.Label(
            self.header_frame,
            text="Step 1 of 5",
            font=('Segoe UI', 10)
        )
        self.step_label.pack(side=tk.LEFT)

        self.title_label = ttk.Label(
            self.header_frame,
            text="Configuration Name",
            font=('Segoe UI', 14, 'bold')
        )
        self.title_label.pack(side=tk.LEFT, padx=(20, 0))

        # Content frame (changes per step)
        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        # Button frame
        self.button_frame = ttk.Frame(self.main_frame)
        self.button_frame.pack(fill=tk.X, pady=(20, 0))

        self.exit_btn = ttk.Button(
            self.button_frame,
            text="Exit",
            command=self._on_exit
        )
        self.exit_btn.pack(side=tk.LEFT)

        self.cancel_btn = ttk.Button(
            self.button_frame,
            text="Cancel",
            command=self._on_cancel
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=(10, 0))

        self.next_btn = ttk.Button(
            self.button_frame,
            text="Next →",
            command=self._on_next
        )
        self.next_btn.pack(side=tk.RIGHT)

        self.back_btn = ttk.Button(
            self.button_frame,
            text="← Back",
            command=self._on_back,
            state=tk.DISABLED
        )
        self.back_btn.pack(side=tk.RIGHT, padx=(0, 10))

    def _clear_content(self):
        """Clear content frame."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _show_step(self, step: int):
        """Show the specified step."""
        self.current_step = step
        self._clear_content()

        # Update header
        self.step_label.config(text=f"Step {step + 1} of {self.total_steps}")

        # Update buttons
        self.back_btn.config(state=tk.NORMAL if step > 0 else tk.DISABLED)
        self.next_btn.config(text="Finish" if step == self.total_steps - 1 else "Next →")

        # Show appropriate step content
        step_methods = [
            self._show_step_name,
            self._show_step_google_auth,
            self._show_step_google_folders,
            self._show_step_hubspot,
            self._show_step_places,
            self._show_step_quickbooks
        ]

        step_methods[step]()

    def _show_step_name(self):
        """Step 1: Configuration name (client selection)."""
        self.title_label.config(text="Client Configuration")

        if self._available_clients:
            ttk.Label(
                self.content_frame,
                text="Select the client configuration to use.\n"
                     "Settings will be loaded from the master config sheet.",
                wraplength=480
            ).pack(anchor=tk.W, pady=(0, 20))

            ttk.Label(self.content_frame, text="Client:").pack(anchor=tk.W)

            self.name_var = tk.StringVar(value=self.config.configuration_name)
            self.name_combo = ttk.Combobox(
                self.content_frame,
                textvariable=self.name_var,
                values=self._available_clients,
                width=47,
                state='readonly'
            )
            self.name_combo.pack(anchor=tk.W, pady=(5, 0))

            # Pre-select if we already have a value
            if self.config.configuration_name in self._available_clients:
                self.name_combo.set(self.config.configuration_name)
            elif self._available_clients:
                self.name_combo.current(0)

            self.name_combo.focus()

            # Bind selection change to pre-populate later steps
            self.name_combo.bind('<<ComboboxSelected>>', self._on_client_selected)
        else:
            # Fallback: free text entry if master config unavailable
            ttk.Label(
                self.content_frame,
                text="Master config not available. Enter a configuration name manually.",
                wraplength=480
            ).pack(anchor=tk.W, pady=(0, 5))

            ttk.Label(
                self.content_frame,
                text="(e.g., your company name or client name)",
                foreground='gray'
            ).pack(anchor=tk.W, pady=(0, 20))

            ttk.Label(self.content_frame, text="Configuration Name:").pack(anchor=tk.W)

            self.name_var = tk.StringVar(value=self.config.configuration_name)
            self.name_entry = ttk.Entry(self.content_frame, textvariable=self.name_var, width=50)
            self.name_entry.pack(anchor=tk.W, pady=(5, 0))
            self.name_entry.focus()

    def _on_client_selected(self, event=None):
        """Pre-populate config fields when a client is selected from the dropdown."""
        client_key = self.name_var.get().strip()
        if not client_key or not self._master_config:
            return

        try:
            client_cfg = self._master_config.get_client(client_key)

            # Pre-populate Drive folder IDs
            if client_cfg.drive.template_folder_id:
                self.config.google_drive.template_folder_id = client_cfg.drive.template_folder_id
            if client_cfg.drive.destination_folder_id:
                self.config.google_drive.destination_folder_id = client_cfg.drive.destination_folder_id

            # Pre-populate HubSpot
            if client_cfg.hubspot.portal_id:
                self.config.hubspot.portal_id = client_cfg.hubspot.portal_id
            if client_cfg.hubspot.deal_pipeline:
                self.config.hubspot.deal_pipeline = client_cfg.hubspot.deal_pipeline
            if client_cfg.hubspot.deal_stage:
                self.config.hubspot.deal_stage = client_cfg.hubspot.deal_stage

            # Pre-populate QBO realm/environment
            if client_cfg.qbo.realm_id:
                self.config.quickbooks.realm_id = client_cfg.qbo.realm_id
            if client_cfg.qbo.environment:
                self.config.quickbooks.use_sandbox = (
                    client_cfg.qbo.environment.lower() == "sandbox"
                )

            log_info(f"Pre-populated config from master for client '{client_key}'")
        except KeyError:
            log_warning(f"Client '{client_key}' not found in master config")

    def _show_step_google_auth(self):
        """Step 2: Google Drive authentication."""
        self.title_label.config(text="Google Drive Authentication")

        ttk.Label(
            self.content_frame,
            text="Authenticate with Google to access Drive.",
            wraplength=480
        ).pack(anchor=tk.W, pady=(0, 20))

        # Status
        status_text = "✓ Authenticated" if self.google_authenticated else "⚠ Not authenticated"
        status_color = 'green' if self.google_authenticated else 'orange'

        self.google_status_label = ttk.Label(
            self.content_frame,
            text=status_text,
            foreground=status_color,
            font=('Segoe UI', 11)
        )
        self.google_status_label.pack(anchor=tk.W, pady=(0, 20))

        # Auth button
        auth_btn = ttk.Button(
            self.content_frame,
            text="Authenticate with Google",
            command=self._authenticate_google
        )
        auth_btn.pack(anchor=tk.W)

        # Instructions
        instructions = ttk.LabelFrame(self.content_frame, text="Instructions", padding=10)
        instructions.pack(fill=tk.X, pady=(30, 0))

        ttk.Label(
            instructions,
            text="1. Click 'Authenticate with Google'\n"
                 "2. A browser window will open\n"
                 "3. Sign in with your Google account\n"
                 "4. Grant the requested permissions",
            wraplength=460,
            justify=tk.LEFT
        ).pack(anchor=tk.W)

    def _show_step_google_folders(self):
        """Step 3: Google Drive folder IDs."""
        self.title_label.config(text="Google Drive Folders")

        # Check if values came from master config
        from_master = bool(
            self._master_config
            and self.config.google_drive.template_folder_id
        )

        if from_master:
            ttk.Label(
                self.content_frame,
                text="Google Drive folder IDs loaded from master config.\n"
                     "You can test access below.",
                wraplength=480
            ).pack(anchor=tk.W, pady=(0, 20))
        else:
            ttk.Label(
                self.content_frame,
                text="Enter the Google Drive folder IDs for template and destination folders.",
                wraplength=480
            ).pack(anchor=tk.W, pady=(0, 20))

        # Template folder
        ttk.Label(self.content_frame, text="Template Folder ID:").pack(anchor=tk.W)

        self.template_var = tk.StringVar(value=self.config.google_drive.template_folder_id)
        template_frame = ttk.Frame(self.content_frame)
        template_frame.pack(fill=tk.X, pady=(5, 15))

        entry_state = 'readonly' if from_master else 'normal'
        self.template_entry = ttk.Entry(
            template_frame, textvariable=self.template_var,
            width=45, state=entry_state
        )
        self.template_entry.pack(side=tk.LEFT)

        ttk.Button(
            template_frame,
            text="Test",
            command=lambda: self._test_folder('template'),
            width=8
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.template_status = ttk.Label(template_frame, text="")
        self.template_status.pack(side=tk.LEFT, padx=(10, 0))

        # Destination folder
        ttk.Label(self.content_frame, text="Destination Folder ID:").pack(anchor=tk.W)

        self.dest_var = tk.StringVar(value=self.config.google_drive.destination_folder_id)
        dest_frame = ttk.Frame(self.content_frame)
        dest_frame.pack(fill=tk.X, pady=(5, 15))

        self.dest_entry = ttk.Entry(
            dest_frame, textvariable=self.dest_var,
            width=45, state=entry_state
        )
        self.dest_entry.pack(side=tk.LEFT)

        ttk.Button(
            dest_frame,
            text="Test",
            command=lambda: self._test_folder('dest'),
            width=8
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.dest_status = ttk.Label(dest_frame, text="")
        self.dest_status.pack(side=tk.LEFT, padx=(10, 0))

        # Help text
        if from_master:
            ttk.Label(
                self.content_frame,
                text="These values are managed in the master config sheet.",
                foreground='gray',
                wraplength=480
            ).pack(anchor=tk.W, pady=(20, 0))
        else:
            ttk.Label(
                self.content_frame,
                text="Tip: The folder ID is in the URL when viewing a folder in Google Drive.\n"
                     "Example: https://drive.google.com/drive/folders/0B1FbH7xek1OYxxx",
                foreground='gray',
                wraplength=480
            ).pack(anchor=tk.W, pady=(20, 0))

    def _show_step_hubspot(self):
        """Step 4: HubSpot authentication."""
        self.title_label.config(text="HubSpot")

        ttk.Label(
            self.content_frame,
            text="Enter your HubSpot Private App access token.",
            wraplength=480
        ).pack(anchor=tk.W, pady=(0, 20))

        ttk.Label(self.content_frame, text="Access Token:").pack(anchor=tk.W)

        existing_token = self._hubspot_token or get_config_manager().get_hubspot_token() or ""
        self.hubspot_var = tk.StringVar(value=existing_token)
        token_frame = ttk.Frame(self.content_frame)
        token_frame.pack(fill=tk.X, pady=(5, 10))

        self.hubspot_entry = ttk.Entry(token_frame, textvariable=self.hubspot_var, width=45, show='*')
        self.hubspot_entry.pack(side=tk.LEFT)

        ttk.Button(
            token_frame,
            text="Test",
            command=self._test_hubspot,
            width=8
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.hubspot_status = ttk.Label(token_frame, text="")
        self.hubspot_status.pack(side=tk.LEFT, padx=(10, 0))

        # Show/hide toggle
        self.show_token_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.content_frame,
            text="Show token",
            variable=self.show_token_var,
            command=self._toggle_token_visibility
        ).pack(anchor=tk.W)

        # Instructions
        instructions = ttk.LabelFrame(self.content_frame, text="How to get access token", padding=10)
        instructions.pack(fill=tk.X, pady=(20, 0))

        ttk.Label(
            instructions,
            text="1. Go to HubSpot Settings → Integrations → Private Apps\n"
                 "2. Create a new Private App\n"
                 "3. Grant scopes: Companies (read/write), Deals (read/write)\n"
                 "4. Copy the access token (starts with 'pat-')",
            wraplength=460,
            justify=tk.LEFT
        ).pack(anchor=tk.W)

    def _show_step_places(self):
        """Step 5: Google Places API (optional)."""
        self.title_label.config(text="Google Places API (Optional)")

        ttk.Label(
            self.content_frame,
            text="Optionally configure Google Places API for better company name verification.",
            wraplength=480
        ).pack(anchor=tk.W, pady=(0, 20))

        ttk.Label(self.content_frame, text="API Key:").pack(anchor=tk.W)

        stored_places_key = keyring.get_password(PLACES_KEYRING_SERVICE, PLACES_KEYRING_USERNAME) or ""
        self.places_var = tk.StringVar(value=stored_places_key)
        key_frame = ttk.Frame(self.content_frame)
        key_frame.pack(fill=tk.X, pady=(5, 10))

        self.places_entry = ttk.Entry(key_frame, textvariable=self.places_var, width=45)
        self.places_entry.pack(side=tk.LEFT)

        ttk.Button(
            key_frame,
            text="Test",
            command=self._test_places,
            width=8
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.places_status = ttk.Label(key_frame, text="")
        self.places_status.pack(side=tk.LEFT, padx=(10, 0))

        # Skip option
        ttk.Label(
            self.content_frame,
            text="This is optional. You can skip this step and add it later.",
            foreground='gray'
        ).pack(anchor=tk.W, pady=(20, 0))

    def _show_step_quickbooks(self):
        """Step 6: QuickBooks Online (optional)."""
        self.title_label.config(text="QuickBooks Online (Optional)")

        ttk.Label(
            self.content_frame,
            text="Optionally configure QuickBooks Online for customer creation.\n"
                 "This feature runs in TRIAL MODE by default - no actual changes will be made.",
            wraplength=480
        ).pack(anchor=tk.W, pady=(0, 20))

        # Client ID
        ttk.Label(self.content_frame, text="Client ID:").pack(anchor=tk.W)

        # Pre-populate from keyring
        # Load the right keys based on sandbox/production mode
        if self.config.quickbooks.use_sandbox:
            _id_key = QBO_KEYRING_SANDBOX_CLIENT_ID
            _secret_key = QBO_KEYRING_SANDBOX_CLIENT_SECRET
        else:
            _id_key = QBO_KEYRING_CLIENT_ID
            _secret_key = QBO_KEYRING_CLIENT_SECRET
        stored_client_id = keyring.get_password(QBO_KEYRING_SERVICE, _id_key) or ""
        stored_client_secret = keyring.get_password(QBO_KEYRING_SERVICE, _secret_key) or ""

        self.qbo_client_id_var = tk.StringVar(value=stored_client_id)
        self.qbo_client_id_entry = ttk.Entry(self.content_frame, textvariable=self.qbo_client_id_var, width=50)
        self.qbo_client_id_entry.pack(anchor=tk.W, pady=(5, 15))

        # Client Secret
        ttk.Label(self.content_frame, text="Client Secret:").pack(anchor=tk.W)

        self.qbo_client_secret_var = tk.StringVar(value=stored_client_secret)
        secret_frame = ttk.Frame(self.content_frame)
        secret_frame.pack(fill=tk.X, pady=(5, 10))

        self.qbo_secret_entry = ttk.Entry(secret_frame, textvariable=self.qbo_client_secret_var, width=45, show='*')
        self.qbo_secret_entry.pack(side=tk.LEFT)

        ttk.Button(
            secret_frame,
            text="Test",
            command=self._test_quickbooks,
            width=8
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.qbo_status = ttk.Label(secret_frame, text="")
        self.qbo_status.pack(side=tk.LEFT, padx=(10, 0))

        # Show/hide toggle
        self.show_qbo_secret_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.content_frame,
            text="Show secret",
            variable=self.show_qbo_secret_var,
            command=self._toggle_qbo_secret_visibility
        ).pack(anchor=tk.W)

        # Sandbox option
        self.qbo_sandbox_var = tk.BooleanVar(value=self.config.quickbooks.use_sandbox)
        ttk.Checkbutton(
            self.content_frame,
            text="Use Sandbox environment (recommended for testing)",
            variable=self.qbo_sandbox_var
        ).pack(anchor=tk.W, pady=(10, 0))

        # Instructions
        instructions = ttk.LabelFrame(self.content_frame, text="How to get QuickBooks credentials", padding=10)
        instructions.pack(fill=tk.X, pady=(20, 0))

        ttk.Label(
            instructions,
            text="1. Go to developer.intuit.com\n"
                 "2. Create or select an app\n"
                 "3. Get Client ID and Client Secret from 'Keys & credentials'\n"
                 "4. Add redirect URI: http://localhost:8085/callback\n"
                 "5. Enable 'Accounting' scope",
            wraplength=460,
            justify=tk.LEFT
        ).pack(anchor=tk.W)

        # Skip note
        ttk.Label(
            self.content_frame,
            text="\nThis is optional. Leave blank to skip QuickBooks integration.",
            foreground='gray'
        ).pack(anchor=tk.W)

    def _authenticate_google(self):
        """Authenticate with Google."""
        try:
            success, error = self.drive_service.authenticate()

            if success:
                self.google_authenticated = True
                self.google_status_label.config(text="✓ Authenticated", foreground='green')
                messagebox.showinfo("Success", "Google authentication successful!")
            else:
                messagebox.showerror("Authentication Failed", error or "Unknown error")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _test_folder(self, folder_type: str):
        """Test folder access."""
        if folder_type == 'template':
            folder_id = self.template_var.get().strip()
            status_label = self.template_status
        else:
            folder_id = self.dest_var.get().strip()
            status_label = self.dest_status

        if not folder_id:
            status_label.config(text="Enter ID", foreground='orange')
            return

        accessible, name, error = self.drive_service.test_folder_access(folder_id)

        if accessible:
            status_label.config(text=f"✓ {name}", foreground='green')
        else:
            status_label.config(text=f"✗ {error}", foreground='red')

    def _test_hubspot(self):
        """Test HubSpot connection."""
        token = self.hubspot_var.get().strip()

        if not token:
            self.hubspot_status.config(text="Enter token", foreground='orange')
            return

        service = HubSpotService(token)
        success, name, error = service.test_connection()

        if success:
            self.hubspot_validated = True
            self.hubspot_status.config(text="✓ Connected", foreground='green')
        else:
            self.hubspot_status.config(text=f"✗ {error}", foreground='red')

    def _test_places(self):
        """Test Google Places API."""
        api_key = self.places_var.get().strip()

        if not api_key:
            self.places_status.config(text="Enter key", foreground='orange')
            return

        success, error = test_places_api(api_key)

        if success:
            self.places_status.config(text="✓ Valid", foreground='green')
        else:
            self.places_status.config(text=f"✗ {error}", foreground='red')

    def _toggle_token_visibility(self):
        """Toggle HubSpot token visibility."""
        if self.show_token_var.get():
            self.hubspot_entry.config(show='')
        else:
            self.hubspot_entry.config(show='*')

    def _toggle_qbo_secret_visibility(self):
        """Toggle QuickBooks secret visibility."""
        if self.show_qbo_secret_var.get():
            self.qbo_secret_entry.config(show='')
        else:
            self.qbo_secret_entry.config(show='*')

    def _test_quickbooks(self):
        """Test QuickBooks configuration."""
        client_id = self.qbo_client_id_var.get().strip()
        client_secret = self.qbo_client_secret_var.get().strip()

        if not client_id or not client_secret:
            self.qbo_status.config(text="Enter both values", foreground='orange')
            return

        # Just validate format for now (actual OAuth requires browser flow)
        if len(client_id) < 10:
            self.qbo_status.config(text="Invalid Client ID", foreground='red')
            return

        if len(client_secret) < 10:
            self.qbo_status.config(text="Invalid Secret", foreground='red')
            return

        # Mark as ready (full OAuth test happens during actual use)
        self.quickbooks_validated = True
        self.qbo_status.config(text="✓ Ready (OAuth on first use)", foreground='green')

    def _validate_step(self) -> bool:
        """Validate current step before proceeding."""
        if self.current_step == 0:
            # Configuration name / client selection
            name = self.name_var.get().strip()
            if not name:
                messagebox.showwarning("Validation", "Please select a client configuration.")
                return False
            self.config.configuration_name = name
            # Pre-populate master config values for the selected client
            self._on_client_selected()

        elif self.current_step == 1:
            # Google auth
            if not self.google_authenticated:
                messagebox.showwarning("Validation", "Please authenticate with Google first.")
                return False

        elif self.current_step == 2:
            # Google folders
            template_id = self.template_var.get().strip()
            dest_id = self.dest_var.get().strip()

            if not template_id or not dest_id:
                messagebox.showwarning("Validation", "Please enter both folder IDs.")
                return False

            self.config.google_drive.template_folder_id = template_id
            self.config.google_drive.destination_folder_id = dest_id

        elif self.current_step == 3:
            # HubSpot
            token = self.hubspot_var.get().strip()
            if not token:
                messagebox.showwarning("Validation", "Please enter HubSpot access token.")
                return False
            self._hubspot_token = token

        elif self.current_step == 4:
            # Google Places (optional) - save to OS keyring
            api_key = self.places_var.get().strip()
            if api_key:
                keyring.set_password(PLACES_KEYRING_SERVICE, PLACES_KEYRING_USERNAME, api_key)
            self.config.google_places.api_key = api_key

        elif self.current_step == 5:
            # QuickBooks Online (optional)
            client_id = self.qbo_client_id_var.get().strip()
            client_secret = self.qbo_client_secret_var.get().strip()

            # Both must be provided or both empty
            if bool(client_id) != bool(client_secret):
                messagebox.showwarning("Validation", "Please enter both Client ID and Client Secret, or leave both empty to skip.")
                return False

            # Save credentials to OS keyring (not config.json)
            if client_id and client_secret:
                use_sandbox = self.qbo_sandbox_var.get()
                if use_sandbox:
                    keyring.set_password(QBO_KEYRING_SERVICE, QBO_KEYRING_SANDBOX_CLIENT_ID, client_id)
                    keyring.set_password(QBO_KEYRING_SERVICE, QBO_KEYRING_SANDBOX_CLIENT_SECRET, client_secret)
                else:
                    keyring.set_password(QBO_KEYRING_SERVICE, QBO_KEYRING_CLIENT_ID, client_id)
                    keyring.set_password(QBO_KEYRING_SERVICE, QBO_KEYRING_CLIENT_SECRET, client_secret)
            self.config.quickbooks.client_id = client_id
            self.config.quickbooks.client_secret = client_secret
            self.config.quickbooks.use_sandbox = self.qbo_sandbox_var.get()
            self.config.quickbooks.trial_mode = True  # Always start in trial mode

        return True

    def _on_back(self):
        """Go to previous step."""
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _on_next(self):
        """Go to next step or finish."""
        if not self._validate_step():
            return

        if self.current_step < self.total_steps - 1:
            self._show_step(self.current_step + 1)
        else:
            self._finish()

    def _finish(self):
        """Complete the wizard."""
        from datetime import datetime
        self.config.created_date = datetime.now().isoformat()

        # Save HubSpot token to OS keyring
        if self._hubspot_token:
            get_config_manager().set_hubspot_token(self._hubspot_token)

        log_info(f"Setup wizard completed: {self.config.configuration_name}")
        self.on_complete(self.config)
        self.destroy()

    def _on_cancel(self):
        """Cancel the wizard."""
        if messagebox.askyesno("Cancel Setup", "Are you sure you want to cancel setup?"):
            self.destroy()

    def _on_exit(self):
        """Exit the application entirely."""
        if messagebox.askyesno("Exit Application", "Are you sure you want to exit the application?"):
            self.destroy()
            self.master.destroy()
