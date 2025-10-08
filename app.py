import time
import os # Import the os module for path handling
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request
from scanner import get_scanner_results, client # Import the core scanner logic

# --- Flask App Initialization ---
# FIX: Explicitly define the template folder path to prevent FileNotFoundError
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=template_dir)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# --- Configuration ---
REFRESH_INTERVAL_SECONDS = 60 # Matches the meta tag in base.html (assuming you have one)

@app.route('/')
def index():
    """
    The main route for the dashboard.
    Fetches the latest results from the scanner and renders the index page.
    """
    start_time = time.time()
    
    # 1. Run the scanner logic (NEW: receives a dictionary)
    scanner_output = get_scanner_results()
    coins = scanner_output['winning_symbols'] # Rename to 'coins' for consistency with index.html
    total_coins_scanned = scanner_output['total_scanned_count'] # NEW: Total scanned coins
    
    end_time = time.time()
    scan_duration = end_time - start_time
    
    # 2. Determine if we are using live data or mock data
    # The 'client' variable in scanner.py is None if API keys are not set.
    is_live = client is not None
    
    # 3. Calculate the next refresh time in UTC
    current_utc_time = datetime.now(timezone.utc)
    
    # We use REFRESH_INTERVAL_SECONDS for the meta tag refresh
    next_refresh_time = current_utc_time + timedelta(seconds=REFRESH_INTERVAL_SECONDS)
    next_refresh_str = next_refresh_time.strftime("%H:%M:%S")
    
    print(f"--- Scan complete in {scan_duration:.2f} seconds. Found {len(coins)} signals out of {total_coins_scanned} scanned. ---")
    
    # 4. Render the HTML template with the results (NEW: pass total_coins_scanned)
    return render_template(
        'index.html', 
        coins=coins, # Passed as 'coins' to match index.html
        total_coins_scanned=total_coins_scanned, # NEW: Passed to template
        is_live=is_live,
        scan_duration=f"{scan_duration:.2f}",
        next_refresh_time=next_refresh_str,
        # Pass the refresh interval to the template for the meta tag
        REFRESH_INTERVAL_SECONDS=REFRESH_INTERVAL_SECONDS 
    )

# --- Run the Application ---
if __name__ == '__main__':
    # When running locally, use a typical development host and port
    print("Starting Flask application...")
    print(f"Live Mode: {client is not None}")
    
    # In a real setup, set host='0.0.0.0' to be accessible externally
    app.run(host='127.0.0.1', port=5000, debug=True)