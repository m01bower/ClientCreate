"""
Dialog windows for ClientCreate.

Includes:
- Company name and address verification dialog
- Email summary dialog
- API key update dialogs
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Callable, Tuple

from services.company_lookup import CompanyAddress, CompanyInfo, Executive, SocialMedia, CorpRegistration


class CompanyNameDialog(tk.Toplevel):
    """Dialog for verifying/selecting company name."""

    def __init__(
        self,
        parent,
        entered_name: str,
        found_names: List[str],
        best_match: Optional[str]
    ):
        """
        Initialize company name dialog.

        Args:
            parent: Parent window
            entered_name: Name entered by user
            found_names: List of names found from various sources
            best_match: Suggested best match
        """
        super().__init__(parent)

        self.entered_name = entered_name
        self.found_names = found_names
        self.best_match = best_match
        self.result: Optional[str] = None

        self.title("Verify Company Name")
        self.geometry("520x550")
        self.minsize(480, 500)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 520) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 550) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        """Build the dialog UI."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header - adjust based on whether we found a different name
        if self.best_match and self.best_match != self.entered_name:
            header_text = "We found a potential official company name from web resources."
        else:
            header_text = "Please confirm the company name to use."

        ttk.Label(
            main_frame,
            text=header_text,
            font=('Segoe UI', 10)
        ).pack(anchor=tk.W, pady=(0, 15))

        # Show what was found - always show the info frame
        info_frame = ttk.LabelFrame(main_frame, text="Names Found from Web Resources", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(
            info_frame,
            text=f"You entered: {self.entered_name}",
            foreground='gray'
        ).pack(anchor=tk.W)

        if self.best_match:
            if self.best_match != self.entered_name:
                ttk.Label(
                    info_frame,
                    text=f"Official name found: {self.best_match}",
                    font=('Segoe UI', 10, 'bold')
                ).pack(anchor=tk.W, pady=(5, 0))
            else:
                ttk.Label(
                    info_frame,
                    text=f"Confirmed: {self.best_match}",
                    font=('Segoe UI', 10, 'bold'),
                    foreground='green'
                ).pack(anchor=tk.W, pady=(5, 0))

        # Selection options
        ttk.Label(
            main_frame,
            text="Which name would you like to use?"
        ).pack(anchor=tk.W, pady=(0, 10))

        # Determine default selection
        if self.best_match and self.best_match != self.entered_name:
            default_selection = 'formal'
        else:
            default_selection = 'original'

        self.selection_var = tk.StringVar(value=default_selection)

        # Option: Use official/formal name (if different from entered)
        if self.best_match and self.best_match != self.entered_name:
            ttk.Radiobutton(
                main_frame,
                text=f'Use official name: "{self.best_match}"',
                variable=self.selection_var,
                value='formal'
            ).pack(anchor=tk.W, pady=2)

        # Option: Keep original/entered name
        ttk.Radiobutton(
            main_frame,
            text=f'Use entered name: "{self.entered_name}"',
            variable=self.selection_var,
            value='original'
        ).pack(anchor=tk.W, pady=2)

        # Option: Edit manually
        ttk.Radiobutton(
            main_frame,
            text='Edit manually:',
            variable=self.selection_var,
            value='edit'
        ).pack(anchor=tk.W, pady=2)

        self.edit_var = tk.StringVar(value=self.best_match or self.entered_name)
        self.edit_entry = ttk.Entry(main_frame, textvariable=self.edit_var, width=45)
        self.edit_entry.pack(anchor=tk.W, padx=(25, 0), pady=(0, 10))

        # All found names (if multiple)
        if len(self.found_names) > 1:
            ttk.Label(
                main_frame,
                text="All names found from web:",
                foreground='gray'
            ).pack(anchor=tk.W, pady=(10, 5))

            names_text = "\n".join(f"  • {name}" for name in self.found_names[:5])
            if len(self.found_names) > 5:
                names_text += f"\n  ... and {len(self.found_names) - 5} more"

            ttk.Label(
                main_frame,
                text=names_text,
                foreground='gray',
                font=('Segoe UI', 9)
            ).pack(anchor=tk.W)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        ttk.Button(btn_frame, text="Exit", command=self._on_exit).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(btn_frame, text="Confirm", command=self._on_continue).pack(side=tk.RIGHT)

    def _on_continue(self):
        """Handle continue button."""
        selection = self.selection_var.get()

        if selection == 'formal':
            self.result = self.best_match
        elif selection == 'original':
            self.result = self.entered_name
        else:  # edit
            self.result = self.edit_var.get().strip()
            if not self.result:
                messagebox.showwarning("Validation", "Please enter a company name.")
                return

        self.destroy()

    def _on_cancel(self):
        """Handle cancel button."""
        self.result = None
        self.destroy()

    def _on_exit(self):
        """Handle exit button - exit entire application."""
        if messagebox.askyesno("Exit Application", "Are you sure you want to exit the application?"):
            self.result = None
            self.destroy()
            self.master.destroy()

    def get_result(self) -> Optional[str]:
        """Get the selected company name."""
        self.wait_window()
        return self.result


class CompanyInfoDialog(tk.Toplevel):
    """Dialog for verifying company name AND address, with optional rates tab and HubSpot tab."""

    def __init__(
        self,
        parent,
        entered_name: str,
        company_info: CompanyInfo,
        default_rates: Optional[dict] = None,
        hubspot_existing: Optional[dict] = None,
        hubspot_configured: bool = False
    ):
        """
        Initialize company info dialog.

        Args:
            parent: Parent window
            entered_name: Name entered by user
            company_info: CompanyInfo with found names and address
            default_rates: Default rate values from spreadsheet (enables Rates tab)
            hubspot_existing: Existing HubSpot company data (None = new company)
            hubspot_configured: Whether HubSpot service is available
        """
        super().__init__(parent)

        self.entered_name = entered_name
        self.company_info = company_info
        self.result_name: Optional[str] = None
        self.result_address: Optional[CompanyAddress] = None
        self.exec_vars: List[dict] = []
        self.social_vars: dict = {}
        self.rates_data: Optional[dict] = None
        self.send_agreement: bool = False
        self._default_rates = default_rates
        self._hubspot_existing = hubspot_existing
        self._hubspot_configured = hubspot_configured
        self.create_deal: Optional[bool] = None

        # Rate StringVars (initialized in _build_rates_tab)
        self.cs_high_var: Optional[tk.StringVar] = None
        self.cs_low_var: Optional[tk.StringVar] = None
        self.es_rate_var: Optional[tk.StringVar] = None
        self.exec_rate_var: Optional[tk.StringVar] = None
        self.sr_hr_var: Optional[tk.StringVar] = None
        self.hr_rate_var: Optional[tk.StringVar] = None
        self.people_ops_var: Optional[tk.StringVar] = None
        self.tti_disc_var: Optional[tk.StringVar] = None
        self.break_pt_var: Optional[tk.StringVar] = None
        self.term_var: Optional[tk.StringVar] = None
        self.template_var: Optional[tk.StringVar] = None
        self.send_agreement_var: Optional[tk.BooleanVar] = None

        self.title("Verify Company Information")
        self.geometry("600x900")
        self.minsize(580, 700)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 600) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 900) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        """Build the dialog UI with notebook tabs and wizard-style navigation."""
        # Pack buttons FIRST at bottom so notebook doesn't steal all space
        btn_frame = ttk.Frame(self, padding=(15, 10))
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="Exit", command=self._on_exit).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.LEFT, padx=(10, 0))

        self._continue_btn = ttk.Button(btn_frame, text="Continue", command=self._on_continue)
        self._continue_btn.pack(side=tk.RIGHT)

        self._back_btn = ttk.Button(btn_frame, text="Back", command=self._on_back)
        self._back_btn.pack(side=tk.RIGHT, padx=(0, 10))

        # Notebook fills remaining space
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))

        # Tab 1: Company Info
        self._build_company_info_tab()

        # Tab 2: Rates & Agreement (only if defaults were provided)
        if self._default_rates is not None:
            self._build_rates_tab()

        # Tab 3: HubSpot (only if HubSpot is configured)
        if self._hubspot_configured:
            self._build_hubspot_tab()

        # Bind tab change to update button state
        self.notebook.bind('<<NotebookTabChanged>>', lambda e: self._update_nav_buttons())

        # Initial button state
        self._update_nav_buttons()

    def _make_scrollable_tab(self, tab_title: str) -> ttk.Frame:
        """Create a scrollable tab in the notebook and return its inner frame."""
        tab_outer = ttk.Frame(self.notebook)
        self.notebook.add(tab_outer, text=tab_title)

        canvas = tk.Canvas(tab_outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab_outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner_frame = ttk.Frame(canvas, padding=15)
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor='nw')

        def _on_configure(event):
            canvas.configure(scrollregion=canvas.bbox('all'))

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        inner_frame.bind('<Configure>', _on_configure)
        canvas.bind('<Configure>', _on_canvas_configure)

        # Mouse wheel scrolling - guard against destroyed canvas
        def _on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
            except tk.TclError:
                pass

        def _on_linux_scroll_up(event):
            try:
                canvas.yview_scroll(-1, 'units')
            except tk.TclError:
                pass

        def _on_linux_scroll_down(event):
            try:
                canvas.yview_scroll(1, 'units')
            except tk.TclError:
                pass

        canvas.bind_all('<MouseWheel>', _on_mousewheel)
        canvas.bind_all('<Button-4>', _on_linux_scroll_up)
        canvas.bind_all('<Button-5>', _on_linux_scroll_down)

        return inner_frame

    def _build_company_info_tab(self):
        """Build the Company Info tab (existing content)."""
        main_frame = self._make_scrollable_tab("Company Info")

        # === Company Name Section ===
        name_frame = ttk.LabelFrame(main_frame, text="Company Name", padding=10)
        name_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(name_frame, text="You entered:", foreground='gray').pack(anchor=tk.W)
        ttk.Label(name_frame, text=self.entered_name, font=('Segoe UI', 10)).pack(anchor=tk.W)

        if self.company_info.found_names:
            ttk.Label(name_frame, text="\nNames found from web:", foreground='gray').pack(anchor=tk.W)
            for name in self.company_info.found_names[:3]:
                ttk.Label(name_frame, text=f"  - {name}", font=('Segoe UI', 9)).pack(anchor=tk.W)

        ttk.Label(name_frame, text="\nCompany name to use:").pack(anchor=tk.W, pady=(10, 5))

        self.name_var = tk.StringVar(value=self.company_info.name or self.entered_name)
        self.name_entry = ttk.Entry(name_frame, textvariable=self.name_var, width=50)
        self.name_entry.pack(fill=tk.X)

        # === Address Section ===
        addr_frame = ttk.LabelFrame(main_frame, text="Company Address", padding=10)
        addr_frame.pack(fill=tk.X, pady=(0, 10))

        if self.company_info.source:
            ttk.Label(
                addr_frame,
                text=f"Address found from: {self.company_info.source}",
                foreground='green'
            ).pack(anchor=tk.W, pady=(0, 10))
        elif self.company_info.address.is_empty():
            ttk.Label(
                addr_frame,
                text="No address found - please enter manually",
                foreground='orange'
            ).pack(anchor=tk.W, pady=(0, 10))

        fields_frame = ttk.Frame(addr_frame)
        fields_frame.pack(fill=tk.X)

        ttk.Label(fields_frame, text="Street Address:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.addr_line1_var = tk.StringVar(value=self.company_info.address.line1)
        ttk.Entry(fields_frame, textvariable=self.addr_line1_var, width=45).grid(row=0, column=1, sticky=tk.W, pady=2)

        ttk.Label(fields_frame, text="Suite/Floor:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.addr_line2_var = tk.StringVar(value=self.company_info.address.line2)
        ttk.Entry(fields_frame, textvariable=self.addr_line2_var, width=45).grid(row=1, column=1, sticky=tk.W, pady=2)

        ttk.Label(fields_frame, text="City:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.city_var = tk.StringVar(value=self.company_info.address.city)
        ttk.Entry(fields_frame, textvariable=self.city_var, width=30).grid(row=2, column=1, sticky=tk.W, pady=2)

        state_zip_frame = ttk.Frame(fields_frame)
        state_zip_frame.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)

        ttk.Label(state_zip_frame, text="State:").pack(side=tk.LEFT)
        self.state_var = tk.StringVar(value=self.company_info.address.state)
        ttk.Entry(state_zip_frame, textvariable=self.state_var, width=5).pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(state_zip_frame, text="ZIP:").pack(side=tk.LEFT)
        self.zip_var = tk.StringVar(value=self.company_info.address.postal_code)
        ttk.Entry(state_zip_frame, textvariable=self.zip_var, width=12).pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(fields_frame, text="Country:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.country_var = tk.StringVar(value=self.company_info.address.country or "USA")
        ttk.Entry(fields_frame, textvariable=self.country_var, width=20).grid(row=4, column=1, sticky=tk.W, pady=2)

        # === Corporate Registration Section (conditional) ===
        if self.company_info.corp_registration:
            reg = self.company_info.corp_registration
            corp_frame = ttk.LabelFrame(main_frame, text="Corporate Registration", padding=10)
            corp_frame.pack(fill=tk.X, pady=(0, 10))

            corp_fields = ttk.Frame(corp_frame)
            corp_fields.pack(fill=tk.X)

            row = 0
            for label_text, value in [
                ("State:", reg.state),
                ("Entity Name:", reg.entity_name),
                ("Entity Number:", reg.entity_number),
                ("Status:", reg.status),
                ("Formation Date:", reg.formation_date),
            ]:
                if value:
                    ttk.Label(corp_fields, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=1)
                    ttk.Label(corp_fields, text=value).grid(row=row, column=1, sticky=tk.W, pady=1, padx=(10, 0))
                    row += 1

            if reg.opencorporates_url:
                ttk.Label(corp_fields, text="Source:").grid(row=row, column=0, sticky=tk.W, pady=1)
                link_label = ttk.Label(
                    corp_fields, text="View on OpenCorporates",
                    foreground='blue', cursor='hand2'
                )
                link_label.grid(row=row, column=1, sticky=tk.W, pady=1, padx=(10, 0))
                link_label.bind('<Button-1>', lambda e, url=reg.opencorporates_url: self._open_url(url))

        # === Contact Info Section ===
        contact_frame = ttk.LabelFrame(main_frame, text="Contact Info (Optional)", padding=10)
        contact_frame.pack(fill=tk.X, pady=(0, 10))

        contact_fields = ttk.Frame(contact_frame)
        contact_fields.pack(fill=tk.X)

        ttk.Label(contact_fields, text="Phone:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.phone_var = tk.StringVar(value=self.company_info.phone)
        ttk.Entry(contact_fields, textvariable=self.phone_var, width=20).grid(row=0, column=1, sticky=tk.W, pady=2)

        ttk.Label(contact_fields, text="Email:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.email_var = tk.StringVar(value=self.company_info.email)
        ttk.Entry(contact_fields, textvariable=self.email_var, width=35, name="email").grid(row=1, column=1, sticky=tk.W, pady=2)

        # === Executives Section (conditional) ===
        if self.company_info.executives:
            exec_frame = ttk.LabelFrame(main_frame, text="Executives Found", padding=10)
            exec_frame.pack(fill=tk.X, pady=(0, 10))

            for i, executive in enumerate(self.company_info.executives):
                if i > 0:
                    ttk.Separator(exec_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

                ef = ttk.Frame(exec_frame)
                ef.pack(fill=tk.X)

                exec_entry_vars = {}

                row = 0
                ttk.Label(ef, text="Name:").grid(row=row, column=0, sticky=tk.W, pady=1)
                var = tk.StringVar(value=executive.name)
                ttk.Entry(ef, textvariable=var, width=35).grid(row=row, column=1, sticky=tk.W, pady=1, padx=(5, 0))
                exec_entry_vars['name'] = var

                row += 1
                ttk.Label(ef, text="Title:").grid(row=row, column=0, sticky=tk.W, pady=1)
                var = tk.StringVar(value=executive.title)
                ttk.Entry(ef, textvariable=var, width=35).grid(row=row, column=1, sticky=tk.W, pady=1, padx=(5, 0))
                exec_entry_vars['title'] = var

                if executive.email:
                    row += 1
                    ttk.Label(ef, text="Email:").grid(row=row, column=0, sticky=tk.W, pady=1)
                    var = tk.StringVar(value=executive.email)
                    ttk.Entry(ef, textvariable=var, width=35).grid(row=row, column=1, sticky=tk.W, pady=1, padx=(5, 0))
                    exec_entry_vars['email'] = var

                if executive.phone:
                    row += 1
                    ttk.Label(ef, text="Phone:").grid(row=row, column=0, sticky=tk.W, pady=1)
                    var = tk.StringVar(value=executive.phone)
                    ttk.Entry(ef, textvariable=var, width=20).grid(row=row, column=1, sticky=tk.W, pady=1, padx=(5, 0))
                    exec_entry_vars['phone'] = var

                if executive.linkedin_url:
                    row += 1
                    ttk.Label(ef, text="LinkedIn:").grid(row=row, column=0, sticky=tk.W, pady=1)
                    var = tk.StringVar(value=executive.linkedin_url)
                    ttk.Entry(ef, textvariable=var, width=45).grid(row=row, column=1, sticky=tk.W, pady=1, padx=(5, 0))
                    exec_entry_vars['linkedin_url'] = var

                self.exec_vars.append(exec_entry_vars)

        # === Social Media Section (conditional) ===
        social = self.company_info.social_media
        if social and any(vars(social).values()):
            social_frame = ttk.LabelFrame(main_frame, text="Social Media", padding=10)
            social_frame.pack(fill=tk.X, pady=(0, 10))

            sf = ttk.Frame(social_frame)
            sf.pack(fill=tk.X)

            row = 0
            for label_text, field_name in [
                ("LinkedIn:", 'linkedin_url'),
                ("Twitter/X:", 'twitter_url'),
                ("Facebook:", 'facebook_url'),
                ("Instagram:", 'instagram_url'),
                ("YouTube:", 'youtube_url'),
            ]:
                value = getattr(social, field_name, '')
                if value:
                    ttk.Label(sf, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=1)
                    var = tk.StringVar(value=value)
                    ttk.Entry(sf, textvariable=var, width=50).grid(row=row, column=1, sticky=tk.W, pady=1, padx=(5, 0))
                    self.social_vars[field_name] = var
                    row += 1

    def _build_rates_tab(self):
        """Build the Rates & Agreement tab."""
        main_frame = self._make_scrollable_tab("Rates & Agreement")
        defaults = self._default_rates or {}

        # === Agreement Template ===
        template_frame = ttk.LabelFrame(main_frame, text="Agreement Template", padding=10)
        template_frame.pack(fill=tk.X, pady=(0, 10))

        self.template_var = tk.StringVar(value="Standard Consulting Agreement")
        template_combo = ttk.Combobox(
            template_frame,
            textvariable=self.template_var,
            values=["Standard Consulting Agreement"],
            state="readonly",
            width=35
        )
        template_combo.pack(anchor=tk.W)

        # === Rate Fields ===
        rates_frame = ttk.LabelFrame(main_frame, text="Billing Rates", padding=10)
        rates_frame.pack(fill=tk.X, pady=(0, 10))

        rf = ttk.Frame(rates_frame)
        rf.pack(fill=tk.X)

        # Define rate fields with labels and their default-dict keys
        rate_fields = [
            ("CS High Rate:", "cs_high_rate"),
            ("CS Low Rate:", "cs_low_rate"),
            ("ES Rate:", "es_rate"),
            ("Exec Consulting Rate:", "exec_consulting_rate"),
            ("Sr HR Rate:", "sr_hr_rate"),
            ("HR Rate:", "hr_rate"),
            ("People Ops Rate:", "people_ops_rate"),
            ("TTI-DISC:", "tti_disc"),
            ("Break Pt:", "break_pt"),
        ]

        self.cs_high_var = tk.StringVar(value=defaults.get("cs_high_rate", ""))
        self.cs_low_var = tk.StringVar(value=defaults.get("cs_low_rate", ""))
        self.es_rate_var = tk.StringVar(value=defaults.get("es_rate", ""))
        self.exec_rate_var = tk.StringVar(value=defaults.get("exec_consulting_rate", ""))
        self.sr_hr_var = tk.StringVar(value=defaults.get("sr_hr_rate", ""))
        self.hr_rate_var = tk.StringVar(value=defaults.get("hr_rate", ""))
        self.people_ops_var = tk.StringVar(value=defaults.get("people_ops_rate", ""))
        self.tti_disc_var = tk.StringVar(value=defaults.get("tti_disc", ""))
        self.break_pt_var = tk.StringVar(value=defaults.get("break_pt", ""))

        # Map field keys to their StringVars for the grid
        var_map = {
            "cs_high_rate": self.cs_high_var,
            "cs_low_rate": self.cs_low_var,
            "es_rate": self.es_rate_var,
            "exec_consulting_rate": self.exec_rate_var,
            "sr_hr_rate": self.sr_hr_var,
            "hr_rate": self.hr_rate_var,
            "people_ops_rate": self.people_ops_var,
            "tti_disc": self.tti_disc_var,
            "break_pt": self.break_pt_var,
        }

        for row, (label_text, field_key) in enumerate(rate_fields):
            ttk.Label(rf, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=3)
            ttk.Entry(rf, textvariable=var_map[field_key], width=15).grid(
                row=row, column=1, sticky=tk.W, pady=3, padx=(10, 0)
            )

        # === Term ===
        term_frame = ttk.LabelFrame(main_frame, text="Payment Terms", padding=10)
        term_frame.pack(fill=tk.X, pady=(0, 10))

        self.term_var = tk.StringVar(value=defaults.get("term", "Due Upon Receipt"))
        term_combo = ttk.Combobox(
            term_frame,
            textvariable=self.term_var,
            values=["Due Upon Receipt", "Net 15", "Net 30", "Net 45", "Net 60"],
            width=20
        )
        term_combo.pack(anchor=tk.W)

        # === Send Agreement Checkbox ===
        self.send_agreement_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            main_frame,
            text="Send Agreement for Signature",
            variable=self.send_agreement_var,
        ).pack(anchor=tk.W, pady=(5, 0))

    def _build_hubspot_tab(self):
        """Build the HubSpot tab (Tab 3)."""
        main_frame = self._make_scrollable_tab("HubSpot")

        hubspot_frame = ttk.LabelFrame(main_frame, text="HubSpot Integration", padding=15)
        hubspot_frame.pack(fill=tk.X, pady=(0, 10))

        if self._hubspot_existing:
            # Company already exists in HubSpot
            ttk.Label(
                hubspot_frame,
                text=f"Company '{self._hubspot_existing['name']}' already exists in HubSpot.",
                font=('Segoe UI', 10, 'bold'),
                wraplength=500
            ).pack(anchor=tk.W, pady=(0, 15))

            ttk.Label(
                hubspot_frame,
                text="Create a new deal for this company?",
                font=('Segoe UI', 10)
            ).pack(anchor=tk.W, pady=(0, 10))

            self._deal_var = tk.BooleanVar(value=True)

            ttk.Radiobutton(
                hubspot_frame,
                text="Yes, create a new deal",
                variable=self._deal_var,
                value=True
            ).pack(anchor=tk.W, pady=2)

            ttk.Radiobutton(
                hubspot_frame,
                text="No, skip deal creation",
                variable=self._deal_var,
                value=False
            ).pack(anchor=tk.W, pady=2)
        else:
            # New company - informational
            ttk.Label(
                hubspot_frame,
                text="Company will be created in HubSpot as a new client.",
                font=('Segoe UI', 10),
                foreground='green'
            ).pack(anchor=tk.W, pady=(0, 5))

            ttk.Label(
                hubspot_frame,
                text="A new company record and deal will be created automatically.",
                foreground='gray'
            ).pack(anchor=tk.W)

            self._deal_var = None  # No choice needed for new companies

    def _get_tab_count(self) -> int:
        """Get the total number of tabs."""
        return self.notebook.index('end')

    def _get_current_tab(self) -> int:
        """Get the current tab index."""
        return self.notebook.index(self.notebook.select())

    def _update_nav_buttons(self):
        """Update Back/Continue button visibility and text based on current tab."""
        current = self._get_current_tab()
        last = self._get_tab_count() - 1

        # Show/hide Back button
        if current == 0:
            self._back_btn.pack_forget()
        else:
            # Re-pack in correct position (before Continue)
            self._back_btn.pack(side=tk.RIGHT, padx=(0, 10))
            # Ensure Continue is still rightmost
            self._continue_btn.pack_forget()
            self._continue_btn.pack(side=tk.RIGHT)

        # Change button text
        if current == last:
            self._continue_btn.config(text="Confirm")
        else:
            self._continue_btn.config(text="Continue")

    def _on_continue(self):
        """Handle Continue/Confirm button."""
        current = self._get_current_tab()
        last = self._get_tab_count() - 1

        if current < last:
            # Advance to next tab
            self.notebook.select(current + 1)
        else:
            # On last tab - confirm
            self._on_confirm()

    def _on_back(self):
        """Handle Back button."""
        current = self._get_current_tab()
        if current > 0:
            self.notebook.select(current - 1)

    def _open_url(self, url: str):
        """Open a URL in the default browser."""
        import webbrowser
        webbrowser.open(url)

    def _on_confirm(self):
        """Handle confirm button."""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation", "Please enter a company name.")
            return

        self.result_name = name
        self.result_address = CompanyAddress(
            line1=self.addr_line1_var.get().strip(),
            line2=self.addr_line2_var.get().strip(),
            city=self.city_var.get().strip(),
            state=self.state_var.get().strip().upper(),
            postal_code=self.zip_var.get().strip(),
            country=self.country_var.get().strip() or "USA"
        )

        # Store phone/email in company_info for later use
        self.company_info.phone = self.phone_var.get().strip()
        self.company_info.email = self.email_var.get().strip()

        # Update executives from editable fields
        for i, exec_entry_vars in enumerate(self.exec_vars):
            if i < len(self.company_info.executives):
                exec_obj = self.company_info.executives[i]
                exec_obj.name = exec_entry_vars.get('name', tk.StringVar()).get().strip()
                exec_obj.title = exec_entry_vars.get('title', tk.StringVar()).get().strip()
                if 'email' in exec_entry_vars:
                    exec_obj.email = exec_entry_vars['email'].get().strip()
                if 'phone' in exec_entry_vars:
                    exec_obj.phone = exec_entry_vars['phone'].get().strip()
                if 'linkedin_url' in exec_entry_vars:
                    exec_obj.linkedin_url = exec_entry_vars['linkedin_url'].get().strip()

        # Update social media from editable fields
        for field_name, var in self.social_vars.items():
            setattr(self.company_info.social_media, field_name, var.get().strip())

        # Collect rates data if the rates tab was built
        if self._default_rates is not None and self.cs_high_var is not None:
            self.rates_data = {
                "people_ops_rate": self.people_ops_var.get().strip(),
                "sr_hr_rate": self.sr_hr_var.get().strip(),
                "hr_rate": self.hr_rate_var.get().strip(),
                "exec_consulting_rate": self.exec_rate_var.get().strip(),
                "cs_high_rate": self.cs_high_var.get().strip(),
                "cs_low_rate": self.cs_low_var.get().strip(),
                "es_rate": self.es_rate_var.get().strip(),
                "tti_disc": self.tti_disc_var.get().strip(),
                "break_pt": self.break_pt_var.get().strip(),
                "term": self.term_var.get().strip(),
                "send_agreement": self.send_agreement_var.get(),
                "template": self.template_var.get().strip(),
            }

        # Collect HubSpot deal choice if the HubSpot tab was built
        if self._hubspot_configured:
            if self._deal_var is not None:
                # Existing company - user chose yes/no
                self.create_deal = self._deal_var.get()
            else:
                # New company - always create deal
                self.create_deal = True

        self.destroy()

    def _on_cancel(self):
        """Handle cancel button."""
        self.result_name = None
        self.result_address = None
        self.destroy()

    def _on_exit(self):
        """Handle exit button - exit entire application."""
        if messagebox.askyesno("Exit Application", "Are you sure you want to exit the application?"):
            self.result_name = None
            self.result_address = None
            self.destroy()
            self.master.destroy()

    def get_result(self) -> Tuple[Optional[str], Optional[CompanyAddress], Optional[CompanyInfo], Optional[dict], Optional[bool]]:
        """Get the verified company name, address, info, optional rates data, and HubSpot deal choice."""
        self.wait_window()
        return self.result_name, self.result_address, self.company_info, self.rates_data, self.create_deal


class EmailDialog(tk.Toplevel):
    """Dialog for entering email recipients."""

    def __init__(self, parent):
        """
        Initialize email dialog.

        Args:
            parent: Parent window
        """
        super().__init__(parent)

        self.result: Optional[List[str]] = None

        self.title("Email Summary")
        self.geometry("400x200")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 400) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 200) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        """Build the dialog UI."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Label explicitly says "Email" to help password managers
        ttk.Label(
            main_frame,
            text="Email addresses (comma-separated):",
            font=('Segoe UI', 10)
        ).pack(anchor=tk.W, pady=(0, 10))

        self.email_var = tk.StringVar()
        # Use name="email" so password managers recognize this as an email field
        self.email_entry = ttk.Entry(main_frame, textvariable=self.email_var, width=45, name="email")
        self.email_entry.pack(fill=tk.X, pady=(0, 10))
        self.email_entry.focus()

        ttk.Label(
            main_frame,
            text="Example: boss@example.com, team@example.com",
            foreground='gray'
        ).pack(anchor=tk.W)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(30, 0))

        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Send", command=self._on_send).pack(side=tk.RIGHT)

    def _on_send(self):
        """Handle send button."""
        from core.validators import validate_emails

        emails_str = self.email_var.get().strip()
        valid, error, emails = validate_emails(emails_str)

        if not valid:
            messagebox.showwarning("Validation", error)
            return

        self.result = emails
        self.destroy()

    def _on_cancel(self):
        """Handle cancel button."""
        self.result = None
        self.destroy()

    def get_result(self) -> Optional[List[str]]:
        """Get the list of email addresses."""
        self.wait_window()
        return self.result


class UpdateApiKeyDialog(tk.Toplevel):
    """Dialog for updating an API key."""

    def __init__(self, parent, key_type: str, current_value: str = ""):
        """
        Initialize API key update dialog.

        Args:
            parent: Parent window
            key_type: Type of key ("HubSpot" or "Google Places")
            current_value: Current key value
        """
        super().__init__(parent)

        self.key_type = key_type
        self.result: Optional[str] = None

        self.title(f"Update {key_type} API Key")
        self.geometry("450x180")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 450) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 180) // 2
        self.geometry(f"+{x}+{y}")

        self.current_value = current_value
        self._build_ui()

    def _build_ui(self):
        """Build the dialog UI."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame,
            text=f"The {self.key_type} API key appears to be invalid.\nPlease enter a new key:",
            wraplength=400
        ).pack(anchor=tk.W, pady=(0, 15))

        ttk.Label(main_frame, text="New API Key:").pack(anchor=tk.W)

        self.key_var = tk.StringVar(value=self.current_value)
        self.key_entry = ttk.Entry(main_frame, textvariable=self.key_var, width=50)
        self.key_entry.pack(fill=tk.X, pady=(5, 0))
        self.key_entry.focus()
        self.key_entry.select_range(0, tk.END)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(25, 0))

        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Save", command=self._on_save).pack(side=tk.RIGHT)

    def _on_save(self):
        """Handle save button."""
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning("Validation", "Please enter an API key.")
            return

        self.result = key
        self.destroy()

    def _on_cancel(self):
        """Handle cancel button."""
        self.result = None
        self.destroy()

    def get_result(self) -> Optional[str]:
        """Get the new API key."""
        self.wait_window()
        return self.result


class ConfirmDialog(tk.Toplevel):
    """Simple confirmation dialog with custom message."""

    def __init__(self, parent, title: str, message: str, detail: str = ""):
        """
        Initialize confirmation dialog.

        Args:
            parent: Parent window
            title: Dialog title
            message: Main message
            detail: Additional detail text
        """
        super().__init__(parent)

        self.result = False

        self.title(title)
        self.geometry("400x180")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 400) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 180) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui(message, detail)

    def _build_ui(self, message: str, detail: str):
        """Build the dialog UI."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame,
            text=message,
            font=('Segoe UI', 10),
            wraplength=360
        ).pack(anchor=tk.W, pady=(0, 10))

        if detail:
            ttk.Label(
                main_frame,
                text=detail,
                foreground='gray',
                wraplength=360
            ).pack(anchor=tk.W)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(30, 0))

        ttk.Button(btn_frame, text="No", command=self._on_no).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Yes", command=self._on_yes).pack(side=tk.RIGHT)

    def _on_yes(self):
        """Handle yes button."""
        self.result = True
        self.destroy()

    def _on_no(self):
        """Handle no button."""
        self.result = False
        self.destroy()

    def get_result(self) -> bool:
        """Get the dialog result."""
        self.wait_window()
        return self.result
