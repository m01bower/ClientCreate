"""
Main application window for ClientCreate.

Provides the primary interface for creating new clients.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import webbrowser
import time
from typing import Optional

from services.google_drive_service import GoogleDriveService, get_drive_service
from services.hubspot_service import HubSpotService, get_hubspot_service, init_hubspot_service
from services.email_service import EmailService, get_email_service
from services.company_lookup import CompanyLookupService, get_company_lookup_service
from services.quickbooks_service import (
    QuickBooksService, get_quickbooks_service, init_quickbooks_service,
    QBOClientInput, QBOResult, QBOStatus
)
from core.config_manager import (
    ConfigManager, get_config_manager, init_config_manager,
    AppConfig, ClientRecord
)
from core.validators import validate_company_name, validate_url, clean_company_name
from core.url_utils import parse_url_parts
from logger_setup import setup_logger, set_status_callback, log_info, log_error, log_warning, log_debug

from gui.setup_wizard import SetupWizard
from gui.dialogs import CompanyNameDialog, CompanyInfoDialog, EmailDialog, ConfirmDialog, UpdateApiKeyDialog
from services.company_lookup import CompanyInfo, CompanyAddress
from gui.history_window import HistoryWindow


class MainWindow(tk.Tk):
    """Main application window."""

    def __init__(self):
        """Initialize main window."""
        super().__init__()

        # Setup logger first
        self.logger = setup_logger()

        # Services (initialized later)
        self.drive_service: Optional[GoogleDriveService] = None
        self.hubspot_service: Optional[HubSpotService] = None
        self.email_service: Optional[EmailService] = None
        self.lookup_service: Optional[CompanyLookupService] = None
        self.quickbooks_service: Optional[QuickBooksService] = None
        self.config_manager: Optional[ConfigManager] = None
        self.app_config: Optional[AppConfig] = None  # Named app_config to avoid shadowing tk.config()

        # State
        self.is_processing = False
        self.cancel_requested = False

        # Window setup
        self.title("ClientCreate")
        self.geometry("600x500")
        self.minsize(500, 400)

        # Build UI
        self._build_menu()
        self._build_ui()

        # Connect logger to status display
        set_status_callback(self._append_status)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 600) // 2
        y = (self.winfo_screenheight() - 500) // 2
        self.geometry(f"+{x}+{y}")

    def _build_menu(self):
        """Build the menu bar."""
        menubar = tk.Menu(self)
        self.config_menu = menubar  # Store reference

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Client", command=self._clear_form, accelerator="Ctrl+N")
        file_menu.add_separator()
        file_menu.add_command(label="View Client History", command=self._show_history, accelerator="Ctrl+H")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close, accelerator="Alt+F4")
        menubar.add_cascade(label="File", menu=file_menu)

        # Settings menu
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Setup New Configuration", command=self._setup_new_config)
        settings_menu.add_command(label="Edit Configuration", command=self._edit_config)
        settings_menu.add_separator()
        settings_menu.add_command(label="Re-authenticate Google", command=self._reauth_google)
        settings_menu.add_command(label="Connect to QuickBooks", command=self._connect_quickbooks)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="How to Use", command=self._show_help)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

        # Keyboard shortcuts
        self.bind('<Control-n>', lambda e: self._clear_form())
        self.bind('<Control-h>', lambda e: self._show_history())

    def _build_ui(self):
        """Build the main UI."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Input section
        input_frame = ttk.LabelFrame(main_frame, text="New Client", padding=15)
        input_frame.pack(fill=tk.X, pady=(0, 15))

        # Company name
        ttk.Label(input_frame, text="Company Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.company_var = tk.StringVar()
        self.company_entry = ttk.Entry(input_frame, textvariable=self.company_var, width=50)
        self.company_entry.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        # Website URL
        ttk.Label(input_frame, text="Website URL:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(input_frame, textvariable=self.url_var, width=50)
        self.url_entry.grid(row=1, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        # Dry run checkbox
        self.dry_run_var = tk.BooleanVar(value=True)  # Default to True for first run
        self.dry_run_check = ttk.Checkbutton(
            input_frame,
            text="Dry Run (test mode - no changes made)",
            variable=self.dry_run_var
        )
        self.dry_run_check.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(15, 0))

        # Status section
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # Status text with scrollbar
        self.status_text = tk.Text(
            status_frame,
            height=12,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=('Consolas', 9)
        )
        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        self.status_text.configure(yscrollcommand=scrollbar.set)

        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Button section
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        # Exit button on the left
        self.exit_btn = ttk.Button(
            btn_frame,
            text="Exit",
            command=self._on_close
        )
        self.exit_btn.pack(side=tk.LEFT)

        # Create and Cancel buttons on the right
        self.create_btn = ttk.Button(
            btn_frame,
            text="Create Client",
            command=self._on_create_client
        )
        self.create_btn.pack(side=tk.RIGHT)

        self.cancel_btn = ttk.Button(
            btn_frame,
            text="Cancel",
            command=self._on_cancel,
            state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.RIGHT, padx=(0, 10))

    def _append_status(self, message: str):
        """Append a message to the status display."""
        self.status_text.config(state=tk.NORMAL)
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.update_idletasks()

    def _clear_status(self):
        """Clear the status display."""
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        self.status_text.config(state=tk.DISABLED)

    def _clear_form(self):
        """Clear the input form."""
        self.company_var.set("")
        self.url_var.set("")
        self.company_entry.focus()

    def initialize(self):
        """Initialize services and check configuration."""
        self._append_status("Initializing...")

        # Initialize config manager first (local storage - no auth needed)
        self.config_manager = init_config_manager()

        # Auto-migrate token from config.json to keyring (one-time, silent)
        self.config_manager.migrate_hubspot_token()

        # Check for existing local configuration (standalone mode)
        if self.config_manager.has_config():
            self._append_status("Loading configuration...")
            self.app_config = self.config_manager.load_config()

            if self.app_config:
                self._append_status(f"Configuration loaded: {self.app_config.configuration_name}")

                # Now initialize Google Drive service
                self._init_drive_service()
                if not self.drive_service:
                    return

                self._init_services_from_config()
                self._append_status("\nReady! Enter company details above.")
                self._append_status("(Dry Run is ON - no changes will be made)")
                return

        # No local config - need to run setup wizard
        self._append_status("No configuration found. Starting setup wizard...")

        # Initialize Google Drive service for setup
        self._init_drive_service()
        if not self.drive_service:
            return

        self._run_setup_wizard()

    def _init_drive_service(self):
        """Initialize Google Drive service with authentication."""
        self.drive_service = get_drive_service()

        if not self.drive_service.has_credentials_file():
            self._append_status("ERROR: credentials.json not found!")
            self._append_status(f"Expected at: {self.drive_service.credentials_path}")
            self._append_status("\nPlease obtain credentials from Google Cloud Console.")
            messagebox.showerror(
                "Missing Credentials",
                f"credentials.json not found.\n\nExpected at:\n{self.drive_service.credentials_path}\n\n"
                "Please obtain this file from Google Cloud Console."
            )
            self.drive_service = None
            return

        # Authenticate with Google (always call authenticate to ensure services are built)
        self._append_status("Authenticating with Google...")

        success, error = self.drive_service.authenticate()
        if not success:
            self._append_status(f"Google authentication failed: {error}")
            messagebox.showerror("Authentication Failed", f"Google authentication failed:\n{error}")
            self.drive_service = None
            return

        self._append_status("Google authentication: OK")

    def _init_services_from_config(self):
        """Initialize services from loaded configuration."""
        if not self.app_config:
            return

        # Initialize HubSpot service (token stored in OS keyring)
        hubspot_token = self.config_manager.get_hubspot_token()
        if hubspot_token:
            self.hubspot_service = init_hubspot_service(hubspot_token)

        # Initialize company lookup service
        self.lookup_service = get_company_lookup_service()
        if self.app_config.google_places.api_key:
            self.lookup_service.set_places_api_key(self.app_config.google_places.api_key)

        # Initialize QuickBooks service
        # trial_mode follows the config setting (default True for safety)
        self.quickbooks_service = init_quickbooks_service(
            client_id=self.app_config.quickbooks.client_id,
            client_secret=self.app_config.quickbooks.client_secret,
            realm_id=self.app_config.quickbooks.realm_id,
            use_sandbox=self.app_config.quickbooks.use_sandbox,
            trial_mode=self.app_config.quickbooks.trial_mode
        )
        if self.app_config.quickbooks.client_id:
            if self.app_config.quickbooks.trial_mode:
                log_info("QuickBooks service configured (TRIAL MODE - no changes will be made)")
            else:
                log_info("QuickBooks service configured (LIVE MODE)")
        else:
            log_info("QuickBooks not configured - skipping QBO integration")

        # Initialize email service
        self.email_service = get_email_service()
        if self.drive_service:
            user_email = self.drive_service.get_user_email()
            if user_email:
                self.email_service.set_gmail_service(
                    self.drive_service.gmail_service,
                    user_email
                )
                log_info(f"Email service configured for: {user_email}")
            else:
                log_warning("Could not get user email - email service not configured")
        else:
            log_warning("Drive service not available - email service not configured")

    def _run_setup_wizard(self):
        """Run the setup wizard."""
        wizard = SetupWizard(self, self.drive_service, self._on_setup_complete)
        self.wait_window(wizard)

    def _on_setup_complete(self, config: AppConfig):
        """Handle setup wizard completion."""
        self.app_config = config

        # Ensure config_manager exists
        if not self.config_manager:
            self.config_manager = init_config_manager()

        # Save configuration locally
        if self.config_manager.save_config(config):
            self._append_status("Configuration saved successfully")
            self._init_services_from_config()
            self._append_status("\nSetup complete! Ready to create clients.")
            self._append_status("(Dry Run is ON - no changes will be made)")
        else:
            self._append_status("Failed to save configuration!")
            messagebox.showerror("Error", "Failed to save configuration.")

    def _setup_new_config(self):
        """Start fresh setup wizard."""
        if messagebox.askyesno(
            "New Configuration",
            "This will replace the current configuration.\nContinue?"
        ):
            self._clear_status()
            self._run_setup_wizard()

    def _edit_config(self):
        """Edit current configuration."""
        if not self.app_config:
            messagebox.showinfo("No Configuration", "No configuration to edit.")
            return

        # For now, just run the wizard with existing values
        # Could be enhanced to show a simpler edit form
        self._run_setup_wizard()

    def _reauth_google(self):
        """Force Google re-authentication."""
        self._append_status("Re-authenticating with Google...")
        success, error = self.drive_service.authenticate(force_new=True)

        if success:
            self._append_status("Google re-authentication successful!")
            # Reinitialize email service
            user_email = self.drive_service.get_user_email()
            if user_email and self.email_service:
                self.email_service.set_gmail_service(
                    self.drive_service.gmail_service,
                    user_email
                )
        else:
            self._append_status(f"Re-authentication failed: {error}")

    def _connect_quickbooks(self):
        """Connect to QuickBooks Online via OAuth."""
        if not self.quickbooks_service:
            messagebox.showerror(
                "Not Configured",
                "QuickBooks is not configured.\n\n"
                "Please go to Settings → Edit Configuration and add your\n"
                "QuickBooks Client ID and Client Secret first."
            )
            return

        if not self.quickbooks_service.is_configured():
            messagebox.showerror(
                "Not Configured",
                "QuickBooks Client ID and Secret are not set.\n\n"
                "Please go to Settings → Edit Configuration and add them."
            )
            return

        self._append_status("\nConnecting to QuickBooks Online...")
        self._append_status("A browser window will open for authorization.")
        self._append_status("Please log in and approve access.\n")

        # Run OAuth flow
        success, error = self.quickbooks_service.start_oauth_flow()

        if success:
            self._append_status("QuickBooks connected successfully!")
            # Test the connection
            test_success, company_name, test_error = self.quickbooks_service.test_connection()
            if test_success:
                self._append_status(f"Connected to QuickBooks company: {company_name}")
                messagebox.showinfo(
                    "Connected",
                    f"Successfully connected to QuickBooks!\n\nCompany: {company_name}"
                )
            else:
                self._append_status(f"Connection test failed: {test_error}")
        else:
            self._append_status(f"QuickBooks connection failed: {error}")
            messagebox.showerror(
                "Connection Failed",
                f"Failed to connect to QuickBooks:\n\n{error}"
            )

    def _show_history(self):
        """Show client history window."""
        if not self.config_manager:
            messagebox.showinfo("Not Ready", "Please complete setup first.")
            return

        history = self.config_manager.get_history()
        HistoryWindow(self, history)

    def _show_help(self):
        """Show help information."""
        help_text = """
ClientCreate - Quick Start Guide

1. Enter the company name and website URL
2. Click "Create Client"
3. The app will:
   - Look up the official company name from website
   - Create a Google Drive folder from template
   - Create a HubSpot company and deal
   - Create a QuickBooks Online customer (TRIAL MODE)

Dry Run Mode:
When enabled, tests all connections without making changes.
Recommended for first-time use.

QuickBooks Online:
Currently runs in TRIAL MODE - simulates customer creation
without making actual changes to your QBO account.

Tips:
- Use the formal company name (e.g., "Acme Corp, Inc.")
- Enter the main website URL (e.g., acmecorp.com)
- Check Dry Run first to test everything works
        """
        messagebox.showinfo("How to Use", help_text.strip())

    def _show_about(self):
        """Show about dialog."""
        about_text = """
ClientCreate

Automates new client onboarding:
• Google Drive folder creation
• HubSpot company & deal creation
• QuickBooks Online customer creation

Version 1.1
        """
        messagebox.showinfo("About", about_text.strip())

    def _on_cancel(self):
        """Handle cancel button."""
        self.cancel_requested = True
        self._append_status("\nCancellation requested...")

    def _on_create_client(self):
        """Handle create client button."""
        if not self.app_config:
            messagebox.showinfo("Not Ready", "Please complete setup first.")
            return

        # Validate inputs
        company_name = self.company_var.get().strip()
        url = self.url_var.get().strip()

        valid, error = validate_company_name(company_name)
        if not valid:
            messagebox.showwarning("Validation", error)
            self.company_entry.focus()
            return

        valid, error = validate_url(url)
        if not valid:
            messagebox.showwarning("Validation", error)
            self.url_entry.focus()
            return

        # Clean company name
        company_name = clean_company_name(company_name)

        # Get dry run setting
        dry_run = self.dry_run_var.get()

        # Start processing in thread
        self.is_processing = True
        self.cancel_requested = False
        self.create_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)

        # Clear previous status
        self._clear_status()

        if dry_run:
            self._append_status("=== DRY RUN MODE - No changes will be made ===\n")

        thread = threading.Thread(
            target=self._process_client,
            args=(company_name, url, dry_run),
            daemon=True
        )
        thread.start()

    def _process_client(self, company_name: str, url: str, dry_run: bool):
        """Process client creation (runs in thread)."""
        try:
            result = self._do_process_client(company_name, url, dry_run)

            # Back to main thread for UI updates
            self.after(0, lambda: self._on_processing_complete(result, dry_run))

        except Exception as e:
            log_error(f"Processing error: {e}")
            self.after(0, lambda: self._on_processing_error(str(e)))

    def _do_process_client(self, company_name: str, url: str, dry_run: bool) -> dict:
        """
        Do the actual client processing.
        Order: HubSpot first (to validate company data), then Google Drive.

        Returns dict with results.
        """
        result = {
            'success': False,
            'company_name': company_name,
            'domain': '',
            'drive_folder_id': '',
            'drive_folder_url': '',
            'hubspot_company_id': '',
            'hubspot_company_url': '',
            'hubspot_deal_id': '',
            'hubspot_deal_url': '',
            'quickbooks_customer_id': '',
            'quickbooks_customer_url': '',
            'quickbooks_status': '',
            'cancelled': False
        }

        # Parse URL
        url_parts = parse_url_parts(url)
        result['domain'] = url_parts['domain']
        log_info(f"Processing: {company_name} ({url_parts['domain']})")

        # Step 1: Verify company name and address from website and other resources
        if self.cancel_requested:
            result['cancelled'] = True
            return result

        log_info("Looking up company name and address from website and other resources...")
        company_address = CompanyAddress()  # Will store verified address

        if self.lookup_service:
            # Use new comprehensive lookup that includes address
            company_info = self.lookup_service.lookup_company_info(
                url_parts['fetch_url'],
                company_name
            )

            # Log what we found
            if company_info.found_names:
                log_info(f"Found {len(company_info.found_names)} potential company name(s)")
                for name in company_info.found_names[:3]:
                    log_info(f"  - {name}")

            if not company_info.address.is_empty():
                log_info(f"Found address from {company_info.source}: {company_info.address.format_single_line()}")
            else:
                log_info("No address found from website")

            # Show dialog for verification on main thread
            dialog_result = [None, None, None]  # name, address, company_info

            def show_info_dialog():
                dialog = CompanyInfoDialog(self, company_name, company_info)
                dialog_result[0], dialog_result[1], dialog_result[2] = dialog.get_result()

            self.after(0, show_info_dialog)

            # Wait for dialog
            while dialog_result[0] is None and dialog_result[1] is None:
                if self.cancel_requested:
                    result['cancelled'] = True
                    return result
                time.sleep(0.1)

            if dialog_result[0]:
                company_name = dialog_result[0]
                result['company_name'] = company_name
                log_info(f"Using company name: {company_name}")

                if dialog_result[1]:
                    company_address = dialog_result[1]
                    if not company_address.is_empty():
                        log_info(f"Using address: {company_address.format_single_line()}")

                # Store phone/email from dialog
                if dialog_result[2]:
                    company_info = dialog_result[2]
            else:
                result['cancelled'] = True
                return result
        else:
            log_info("Company lookup service not configured, using entered name")
            company_info = CompanyInfo(name=company_name)

        # Step 2: HubSpot (run first to validate company data)
        if self.cancel_requested:
            result['cancelled'] = True
            return result

        log_info("\n--- HubSpot ---")
        skip_deal_creation = False  # Track if user declined deal creation

        if not self.hubspot_service:
            log_warning("HubSpot service not configured, skipping...")
        else:
            # Search for existing company
            existing = self.hubspot_service.search_company(
                company_name,
                url_parts['domain_for_hubspot']
            )

            if existing:
                log_warning(f"Company already exists: {existing['name']}")

                # Update type if needed
                if existing.get('type') != 'CLIENT':
                    if not dry_run:
                        self.hubspot_service.update_company_type(existing['id'], 'CLIENT')
                        log_info("Updated company type to 'CLIENT'")
                    else:
                        log_info("[DRY RUN] Would update company type to 'CLIENT'")

                # Store existing company info
                result['hubspot_company_id'] = existing['id']
                result['hubspot_company_url'] = self.hubspot_service.get_company_url(existing['id'])

                # Ask user if they want to create a new deal
                create_deal = [None]

                def ask_deal():
                    dialog = ConfirmDialog(
                        self,
                        "Company Exists",
                        f"Company '{existing['name']}' already exists in HubSpot.",
                        "Create a new deal for this company?"
                    )
                    create_deal[0] = dialog.get_result()

                self.after(0, ask_deal)

                while create_deal[0] is None:
                    if self.cancel_requested:
                        result['cancelled'] = True
                        return result
                    time.sleep(0.1)  # Sleep 100ms to avoid CPU spinning

                if not create_deal[0]:
                    # User declined to create deal - continue without creating deal
                    skip_deal_creation = True
                    log_info("Skipping deal creation, continuing to Google Drive...")

            else:
                # Create company
                if dry_run:
                    log_info(f"[DRY RUN] Would create company: {company_name}")
                    result['hubspot_company_id'] = "DRY_RUN"
                    result['hubspot_company_url'] = "DRY_RUN"
                else:
                    success, company_id, error = self.hubspot_service.create_company(
                        company_name,
                        url_parts['domain_for_hubspot'],
                        company_type='CLIENT',
                        dry_run=False
                    )
                    if not success:
                        raise Exception(f"Failed to create company: {error}")

                    result['hubspot_company_id'] = company_id
                    result['hubspot_company_url'] = self.hubspot_service.get_company_url(company_id)
                    log_info(f"Created company: {company_name}")

            # Update HubSpot company with address if we have one and company doesn't have one
            hubspot_company_id = result['hubspot_company_id']
            if hubspot_company_id and hubspot_company_id != "DRY_RUN":
                # Check if we have an address to add
                if company_address and not company_address.is_empty():
                    # Check if the company already has an address in HubSpot
                    has_address = False
                    if existing:
                        has_address = self.hubspot_service.company_has_address(existing)

                    if not has_address:
                        if not dry_run:
                            # Combine address lines for HubSpot (it has single address field)
                            address_str = company_address.line1
                            if company_address.line2:
                                address_str += f", {company_address.line2}"

                            success, error = self.hubspot_service.update_company_address(
                                hubspot_company_id,
                                address=address_str,
                                city=company_address.city,
                                state=company_address.state,
                                zip_code=company_address.postal_code,
                                country=company_address.country
                            )
                            if success:
                                log_info(f"Updated HubSpot company with address: {company_address.format_single_line()}")
                            else:
                                log_warning(f"Failed to update HubSpot address: {error}")
                        else:
                            log_info(f"[DRY RUN] Would update HubSpot company with address: {company_address.format_single_line()}")
                    else:
                        log_debug("HubSpot company already has address, skipping update")

            # Create deal (unless user declined for existing company)
            if not skip_deal_creation:
                company_id = result['hubspot_company_id']
                if company_id and company_id != "DRY_RUN":
                    if dry_run:
                        log_info(f"[DRY RUN] Would create deal for: {company_name}")
                        result['hubspot_deal_id'] = "DRY_RUN"
                        result['hubspot_deal_url'] = "DRY_RUN"
                    else:
                        success, deal_id, error = self.hubspot_service.create_deal(
                            company_name,
                            company_id,
                            dry_run=False
                        )
                        if not success:
                            raise Exception(f"Failed to create deal: {error}")

                        result['hubspot_deal_id'] = deal_id
                        result['hubspot_deal_url'] = self.hubspot_service.get_deal_url(deal_id)
                        log_info(f"Created deal for: {company_name}")
                elif dry_run:
                    log_info(f"[DRY RUN] Would create deal for: {company_name}")
                    result['hubspot_deal_id'] = "DRY_RUN"
                    result['hubspot_deal_url'] = "DRY_RUN"

        # Step 3: Google Drive
        if self.cancel_requested:
            result['cancelled'] = True
            return result

        log_info("\n--- Google Drive ---")

        # Check template folder access
        accessible, name, error = self.drive_service.test_folder_access(
            self.app_config.google_drive.template_folder_id
        )
        if not accessible:
            log_error(f"Cannot access template folder: {error}")
            raise Exception(f"Cannot access template folder: {error}")
        log_info(f"Template folder: {name}")

        # Check destination folder access
        accessible, name, error = self.drive_service.test_folder_access(
            self.app_config.google_drive.destination_folder_id
        )
        if not accessible:
            log_error(f"Cannot access destination folder: {error}")
            raise Exception(f"Cannot access destination folder: {error}")
        log_info(f"Destination folder: {name}")

        # Check if client folder already exists
        exists, existing_id = self.drive_service.folder_exists(
            company_name,
            self.app_config.google_drive.destination_folder_id
        )

        if exists:
            log_warning(f"WARNING: Folder '{company_name}' already exists in Google Drive!")
            log_warning("Skipping folder creation and continuing to QuickBooks...")
            result['drive_folder_id'] = existing_id
            result['drive_folder_url'] = self.drive_service.get_folder_url(existing_id)

        else:
            # Create folder
            if dry_run:
                log_info(f"[DRY RUN] Would create folder: {company_name}")
                result['drive_folder_id'] = "DRY_RUN"
                result['drive_folder_url'] = "DRY_RUN"
            else:
                success, folder_id, error = self.drive_service.create_folder(
                    company_name,
                    self.app_config.google_drive.destination_folder_id
                )
                if not success:
                    raise Exception(f"Failed to create folder: {error}")

                result['drive_folder_id'] = folder_id
                result['drive_folder_url'] = self.drive_service.get_folder_url(folder_id)
                log_info(f"Created folder: {company_name}")

                # Copy template contents
                log_info("Copying template files...")
                success, copied_files, error = self.drive_service.copy_folder_contents(
                    self.app_config.google_drive.template_folder_id,
                    folder_id,
                    company_name,
                    progress_callback=lambda f, c, t: log_info(f"  [{c}/{t}] {f}"),
                    dry_run=False
                )
                if not success:
                    log_warning(f"Some files may not have copied: {error}")

                log_info(f"Copied {len(copied_files)} items")

        # Step 4: QuickBooks Online
        if self.cancel_requested:
            result['cancelled'] = True
            return result

        log_info("\n--- QuickBooks Online ---")

        if not self.quickbooks_service or not self.quickbooks_service.is_configured():
            log_info("QuickBooks not configured, skipping...")
        else:
            # Sync QuickBooks trial_mode with app's dry_run setting
            self.quickbooks_service.set_trial_mode(dry_run)

            if dry_run:
                log_info("[DRY RUN] QuickBooks in test mode - no actual changes will be made")
            else:
                log_info("QuickBooks LIVE MODE - will create actual customer")

            # Create client input for QuickBooks
            # QuickBooks requires full URL with https:// prefix
            qbo_url = url_parts.get('fetch_url', '') if url_parts else ''
            if qbo_url and not qbo_url.startswith('http'):
                qbo_url = f"https://{qbo_url}"

            # Include address and contact info from verification dialog
            qbo_input = QBOClientInput(
                client_name=company_name,
                client_legal_name=company_name,
                client_url=qbo_url,
                primary_email=company_info.email if company_info else '',
                phone=company_info.phone if company_info else '',
                billing_address_line1=company_address.line1 if company_address else '',
                billing_address_line2=company_address.line2 if company_address else '',
                billing_address_city=company_address.city if company_address else '',
                billing_address_state=company_address.state if company_address else '',
                billing_address_postal_code=company_address.postal_code if company_address else '',
                billing_address_country=company_address.country if company_address else 'USA',
                source_system="ClientCreate",
                notes=f"Created via ClientCreate on {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}"
            )

            # Log the address being used
            if company_address and not company_address.is_empty():
                log_info(f"Using address: {company_address.format_single_line()}")

            # Process QuickBooks customer creation
            qbo_result = self.quickbooks_service.create_customer(qbo_input)

            result['quickbooks_status'] = qbo_result.status
            result['quickbooks_customer_id'] = qbo_result.quickbooks_customer_id or ''

            if qbo_result.quickbooks_customer_id and qbo_result.quickbooks_customer_id != "TRIAL_MODE_ID":
                result['quickbooks_customer_url'] = self.quickbooks_service.get_customer_url(
                    qbo_result.quickbooks_customer_id
                )
            elif qbo_result.quickbooks_customer_id == "TRIAL_MODE_ID":
                result['quickbooks_customer_url'] = "[DRY RUN]"

            # Log result based on status
            if qbo_result.status == QBOStatus.EXISTS.value:
                log_info(f"QuickBooks customer already exists: {qbo_result.quickbooks_customer_id}")
            elif qbo_result.status == QBOStatus.CREATED.value:
                log_info(f"QuickBooks customer created: {qbo_result.quickbooks_customer_id}")
            elif qbo_result.status == QBOStatus.CREATED_WITH_ISSUES.value:
                log_warning(f"QuickBooks customer created with issues: {qbo_result.issues}")
            elif qbo_result.status == QBOStatus.ERROR.value:
                log_error(f"QuickBooks error: {qbo_result.message}")

        result['success'] = True
        return result

    def _on_processing_complete(self, result: dict, dry_run: bool):
        """Handle processing completion."""
        self.is_processing = False
        self.create_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)

        if result['cancelled']:
            log_info("\n=== Operation cancelled ===")
            return

        if dry_run:
            log_info("\n=== DRY RUN COMPLETE ===")
            log_info("No changes were made. Disable 'Dry Run' to create for real.")
        else:
            log_info("\n=== CLIENT CREATED SUCCESSFULLY ===")
            log_info(f"Company: {result['company_name']}")
            log_info(f"Domain: {result['domain']}")

            if result['drive_folder_url']:
                log_info(f"Drive: {result['drive_folder_url']}")
            if result['hubspot_company_url']:
                log_info(f"HubSpot Company: {result['hubspot_company_url']}")
            if result['hubspot_deal_url']:
                log_info(f"HubSpot Deal: {result['hubspot_deal_url']}")
            if result['quickbooks_customer_id']:
                log_info(f"QuickBooks Customer: {result['quickbooks_customer_id']}")
                if result['quickbooks_customer_url'] and result['quickbooks_customer_url'] != "[DRY RUN]":
                    log_info(f"QuickBooks URL: {result['quickbooks_customer_url']}")
                elif result['quickbooks_customer_url'] == "[DRY RUN]":
                    log_info("  (QuickBooks in DRY RUN mode - no actual customer created)")

            # Save to history
            if self.config_manager:
                user_email = self.drive_service.get_user_email() if self.drive_service else ''
                record = ClientRecord(
                    created_date=__import__('datetime').datetime.now().isoformat(),
                    company_name=result['company_name'],
                    domain=result['domain'],
                    google_drive_folder_id=result['drive_folder_id'],
                    google_drive_folder_url=result['drive_folder_url'],
                    hubspot_company_id=result['hubspot_company_id'],
                    hubspot_company_url=result['hubspot_company_url'],
                    hubspot_deal_id=result['hubspot_deal_id'],
                    hubspot_deal_url=result['hubspot_deal_url'],
                    quickbooks_customer_id=result['quickbooks_customer_id'],
                    quickbooks_customer_url=result['quickbooks_customer_url'],
                    created_by=user_email
                )
                self.config_manager.add_client_record(record)

            # Ask about email - always prompt when email service is available
            log_debug(f"Email service exists: {self.email_service is not None}")
            if self.email_service:
                log_debug(f"Email service configured: {self.email_service.is_configured()}")
                if not self.email_service.is_configured():
                    # Try to configure email service if not already done
                    log_debug(f"Drive service exists: {self.drive_service is not None}")
                    if self.drive_service:
                        log_debug(f"Gmail service exists: {self.drive_service.gmail_service is not None}")
                    if self.drive_service and self.drive_service.gmail_service:
                        user_email = self.drive_service.get_user_email()
                        log_debug(f"Got user email for fallback: {user_email}")
                        if user_email:
                            self.email_service.set_gmail_service(
                                self.drive_service.gmail_service,
                                user_email
                            )
                            log_info(f"Email service configured (fallback): {user_email}")

                if self.email_service.is_configured():
                    if messagebox.askyesno("Email Summary", "Would you like to email this summary?"):
                        dialog = EmailDialog(self)
                        emails = dialog.get_result()

                        if emails:
                            success, error = self.email_service.send_summary_email(
                                emails,
                                result['company_name'],
                                result['domain'],
                                result['drive_folder_url'],
                                result['hubspot_company_url'],
                                result['hubspot_deal_url']
                            )
                            if success:
                                log_info(f"Summary emailed to: {', '.join(emails)}")
                            else:
                                log_warning(f"Failed to send email: {error}")

        # Clear form for next client
        self._clear_form()

    def _on_processing_error(self, error: str):
        """Handle processing error."""
        self.is_processing = False
        self.create_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)

        log_error(f"\n=== ERROR ===\n{error}")
        messagebox.showerror("Error", f"Client creation failed:\n{error}")

    def _on_close(self):
        """Handle window close."""
        if self.is_processing:
            if not messagebox.askyesno("Processing", "Client creation in progress. Cancel and exit?"):
                return
            self.cancel_requested = True

        self.destroy()
