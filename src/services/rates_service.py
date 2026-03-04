"""
Rates service for ClientCreate.

Reads default billing rates and writes client-specific rates
to the Rates tab of the Timesheet Trackings spreadsheet.
"""

from datetime import date
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from logger_setup import get_logger, log_info, log_error, log_warning

# Timesheet Trackings spreadsheet
TIMESHEET_SHEET_ID = "1PjDfAKfK4hC-Q7s6lMkISI9Ngc15ZdvCxRTpdgSZ3_k"
RATES_TAB = "Rates"

# Column mapping (row 3 headers, data starts row 4)
# A: Active Client/Opportunity Name
# B: Peoples Ops Rate
# C: Sr HR Rate
# D: HR Rate
# E: Exec Consulting Rate
# F: CS High Rate
# G: CS Low Rate
# H: ES Rate
# I: TTI-DISC
# J: Break Pt
# K: Start Date (from Client List)
# L: Term
# M: Contract End Date

# Rate field keys mapped to column offsets (from B=0)
RATE_FIELDS = [
    "people_ops_rate",     # B
    "sr_hr_rate",          # C
    "hr_rate",             # D
    "exec_consulting_rate", # E
    "cs_high_rate",        # F
    "cs_low_rate",         # G
    "es_rate",             # H
    "tti_disc",            # I
    "break_pt",            # J
]

# Hardcoded fallback defaults if DEFAULT row not found
FALLBACK_DEFAULTS = {
    "people_ops_rate": "$95.00",
    "sr_hr_rate": "$185.00",
    "hr_rate": "$110.00",
    "exec_consulting_rate": "$225.00",
    "cs_high_rate": "$115.00",
    "cs_low_rate": "$110.00",
    "es_rate": "$225.00",
    "tti_disc": "$80.00",
    "break_pt": "20",
    "term": "Due Upon Receipt",
}


class RatesService:
    """Service for reading/writing client billing rates."""

    def __init__(self, sheets_service):
        """
        Initialize rates service.

        Args:
            sheets_service: Google Sheets API v4 service object
        """
        self.logger = get_logger()
        self.sheets = sheets_service

    def get_defaults(self) -> dict:
        """
        Read default rate values from the DEFAULT row in the Rates tab.

        Returns:
            Dictionary of rate field names to their string values.
        """
        try:
            # Read column A to find the DEFAULT row
            result = self.sheets.spreadsheets().values().get(
                spreadsheetId=TIMESHEET_SHEET_ID,
                range=f"{RATES_TAB}!A4:M",
            ).execute()

            rows = result.get("values", [])

            for row in rows:
                if not row:
                    continue
                cell_a = str(row[0]).strip().upper()
                if cell_a == "DEFAULT":
                    return self._parse_rate_row(row)

            log_warning("DEFAULT row not found in Rates tab, using hardcoded fallbacks")
            return dict(FALLBACK_DEFAULTS)

        except HttpError as e:
            log_error(f"Failed to read default rates: {e}")
            return dict(FALLBACK_DEFAULTS)

    def _parse_rate_row(self, row: list) -> dict:
        """
        Parse a spreadsheet row into a rates dictionary.

        Args:
            row: List of cell values starting from column A.

        Returns:
            Dictionary of rate field names to values.
        """
        defaults = {}

        # Columns B-J are rate fields (index 1-9)
        for i, field_name in enumerate(RATE_FIELDS):
            col_index = i + 1  # B=1, C=2, ...
            if col_index < len(row):
                defaults[field_name] = str(row[col_index]).strip()
            else:
                defaults[field_name] = FALLBACK_DEFAULTS.get(field_name, "")

        # Column L = Term (index 11)
        if len(row) > 11:
            defaults["term"] = str(row[11]).strip()
        else:
            defaults["term"] = FALLBACK_DEFAULTS.get("term", "Due Upon Receipt")

        return defaults

    def find_client_row(self, client_name: str) -> Optional[int]:
        """
        Search column A for an exact client name match.

        Args:
            client_name: Client name to search for.

        Returns:
            1-based row number if found, None otherwise.
        """
        try:
            result = self.sheets.spreadsheets().values().get(
                spreadsheetId=TIMESHEET_SHEET_ID,
                range=f"{RATES_TAB}!A4:A",
            ).execute()

            rows = result.get("values", [])
            for i, row in enumerate(rows):
                if row and str(row[0]).strip().lower() == client_name.strip().lower():
                    return i + 4  # Data starts at row 4 (0-indexed i + 4)

            return None

        except HttpError as e:
            log_error(f"Failed to search for client row: {e}")
            return None

    def write_rates(self, client_name: str, rates: dict) -> bool:
        """
        Write rates for a client to the Rates tab.

        Updates existing row if client found, otherwise appends a new row.
        Sets Start Date (col K) to today's date.

        Args:
            client_name: Company name for column A.
            rates: Dictionary of rate field names to values.

        Returns:
            True on success, False on failure.
        """
        try:
            # Build the row values: A=name, B-J=rates, K=start date, L=term, M=empty
            row_values = [client_name]

            for field_name in RATE_FIELDS:
                row_values.append(rates.get(field_name, ""))

            # K = Start Date
            row_values.append(date.today().strftime("%m/%d/%Y"))

            # L = Term
            row_values.append(rates.get("term", "Due Upon Receipt"))

            # M = Contract End Date (leave empty)
            row_values.append("")

            existing_row = self.find_client_row(client_name)

            if existing_row:
                # Update existing row
                range_str = f"{RATES_TAB}!A{existing_row}:M{existing_row}"
                self.sheets.spreadsheets().values().update(
                    spreadsheetId=TIMESHEET_SHEET_ID,
                    range=range_str,
                    valueInputOption="USER_ENTERED",
                    body={"values": [row_values]},
                ).execute()
                log_info(f"Updated rates for '{client_name}' at row {existing_row}")
            else:
                # Append new row
                self.sheets.spreadsheets().values().append(
                    spreadsheetId=TIMESHEET_SHEET_ID,
                    range=f"{RATES_TAB}!A4",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [row_values]},
                ).execute()
                log_info(f"Added new rates row for '{client_name}'")

            return True

        except HttpError as e:
            log_error(f"Failed to write rates for '{client_name}': {e}")
            return False


# Singleton instance
_rates_service: Optional[RatesService] = None


def get_rates_service(drive_service=None) -> Optional[RatesService]:
    """
    Get or create the rates service singleton.

    Args:
        drive_service: GoogleDriveService instance (needed on first call
                       to build the Sheets API service from existing creds).

    Returns:
        RatesService instance, or None if credentials not available.
    """
    global _rates_service
    if _rates_service is None:
        if drive_service is None or drive_service.creds is None:
            log_warning("Cannot create RatesService: no Google credentials available")
            return None
        sheets = build("sheets", "v4", credentials=drive_service.creds)
        _rates_service = RatesService(sheets)
        log_info("Rates service initialized")
    return _rates_service
