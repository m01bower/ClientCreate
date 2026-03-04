"""
ClientCreate - Main Entry Point

Automates new client onboarding by creating:
- Google Drive folder structure from template
- HubSpot company and deal
- (Future) QuickBooks customer

Usage:
    python main.py
"""

import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import MainWindow


def main():
    """Main entry point."""
    # Create and run main window
    app = MainWindow()

    # Initialize after window is created
    app.after(100, app.initialize)

    # Handle window close
    app.protocol("WM_DELETE_WINDOW", app._on_close)

    # Start main loop
    app.mainloop()


if __name__ == "__main__":
    main()
