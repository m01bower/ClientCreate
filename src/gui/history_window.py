"""
Client history window for ClientCreate.

Displays list of previously created clients with links.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import webbrowser
from typing import List

from core.config_manager import ClientRecord


class HistoryWindow(tk.Toplevel):
    """Window for viewing client creation history."""

    def __init__(self, parent, history: List[ClientRecord]):
        """
        Initialize history window.

        Args:
            parent: Parent window
            history: List of client records
        """
        super().__init__(parent)

        self.history = history

        self.title("Client History")
        self.geometry("750x450")
        self.minsize(600, 300)
        self.transient(parent)

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 750) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 450) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        """Build the window UI."""
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Toolbar
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(toolbar, text=f"Total clients: {len(self.history)}").pack(side=tk.LEFT)

        ttk.Button(
            toolbar,
            text="Export CSV",
            command=self._export_csv
        ).pack(side=tk.RIGHT)

        # Treeview for history
        columns = ('date', 'company', 'domain', 'links')

        self.tree = ttk.Treeview(main_frame, columns=columns, show='headings', selectmode='browse')

        # Column headings
        self.tree.heading('date', text='Date')
        self.tree.heading('company', text='Company')
        self.tree.heading('domain', text='Domain')
        self.tree.heading('links', text='Links')

        # Column widths
        self.tree.column('date', width=100, minwidth=80)
        self.tree.column('company', width=200, minwidth=150)
        self.tree.column('domain', width=150, minwidth=100)
        self.tree.column('links', width=250, minwidth=200)

        # Scrollbar
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind double-click
        self.tree.bind('<Double-1>', self._on_double_click)

        # Link buttons frame
        link_frame = ttk.LabelFrame(main_frame, text="Open Links", padding=10)
        link_frame.pack(fill=tk.X, pady=(10, 0), side=tk.BOTTOM)

        ttk.Label(link_frame, text="Select a row and click:").pack(side=tk.LEFT)

        ttk.Button(
            link_frame,
            text="Drive Folder",
            command=lambda: self._open_link('drive')
        ).pack(side=tk.LEFT, padx=(10, 5))

        ttk.Button(
            link_frame,
            text="HubSpot Company",
            command=lambda: self._open_link('company')
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            link_frame,
            text="HubSpot Deal",
            command=lambda: self._open_link('deal')
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            link_frame,
            text="QuickBooks",
            command=lambda: self._open_link('quickbooks')
        ).pack(side=tk.LEFT, padx=5)

    def _populate_list(self):
        """Populate the treeview with history data."""
        for record in self.history:
            # Format date (just date portion)
            date_str = record.created_date[:10] if record.created_date else ''

            # Build links text
            links = []
            if record.google_drive_folder_url:
                links.append("Drive")
            if record.hubspot_company_url:
                links.append("HS Company")
            if record.hubspot_deal_url:
                links.append("HS Deal")
            if record.quickbooks_customer_url and record.quickbooks_customer_url not in ["[DRY RUN]", "DRY_RUN"]:
                links.append("QBO")
            links_text = " | ".join(links) if links else ""

            self.tree.insert('', tk.END, values=(
                date_str,
                record.company_name,
                record.domain,
                links_text
            ), tags=(record.company_name,))

    def _get_selected_record(self) -> ClientRecord:
        """Get the currently selected client record."""
        selection = self.tree.selection()
        if not selection:
            return None

        item = self.tree.item(selection[0])
        company_name = item['values'][1]

        # Find matching record
        for record in self.history:
            if record.company_name == company_name:
                return record

        return None

    def _open_link(self, link_type: str):
        """Open a link for the selected record."""
        record = self._get_selected_record()
        if not record:
            messagebox.showinfo("No Selection", "Please select a client first.")
            return

        url = None
        if link_type == 'drive':
            url = record.google_drive_folder_url
        elif link_type == 'company':
            url = record.hubspot_company_url
        elif link_type == 'deal':
            url = record.hubspot_deal_url
        elif link_type == 'quickbooks':
            url = record.quickbooks_customer_url
            if url in ["[DRY RUN]", "DRY_RUN"]:
                messagebox.showinfo("Dry Run", "QuickBooks was run in dry run mode - no actual customer was created.")
                return

        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("No Link", f"No {link_type} link available for this client.")

    def _on_double_click(self, event):
        """Handle double-click on a row."""
        # Try to open Drive folder on double-click
        self._open_link('drive')

    def _export_csv(self):
        """Export history to CSV file."""
        if not self.history:
            messagebox.showinfo("No Data", "No history to export.")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
            initialfilename='client_history.csv'
        )

        if not filename:
            return

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow([
                    'Date', 'Company', 'Domain',
                    'Drive Folder URL', 'HubSpot Company URL', 'HubSpot Deal URL',
                    'QuickBooks Customer ID', 'QuickBooks Customer URL',
                    'Created By'
                ])

                # Data
                for record in self.history:
                    writer.writerow([
                        record.created_date,
                        record.company_name,
                        record.domain,
                        record.google_drive_folder_url,
                        record.hubspot_company_url,
                        record.hubspot_deal_url,
                        record.quickbooks_customer_id,
                        record.quickbooks_customer_url,
                        record.created_by
                    ])

            messagebox.showinfo("Export Complete", f"History exported to:\n{filename}")

        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {e}")
