import time
import os
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template
from scanner import get_scanner_results, client # Import the core scanner logic and the client instance
import traceback # <-- REQUIRED for printing full error details to logs

# --- Flask App Initialization ---
# FIX: Explicitly define the template folder path to prevent FileNotFoundError
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=template_dir)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Security Fix: Set the SECRET_KEY from the environment variable (set this on Render!)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'TEMP_SECRET_DO_NOT_USE_IN_PROD') 

# --- Configuration ---
REFRESH_INTERVAL_SECONDS = 60 

@app.route('/')
def index():
    """
    The main route for the dashboard.
    Fetches the latest results from the scanner and renders the index page.
    Includes robust error handling for better debugging in the Render logs.
    """
    start_time = time.time()
    
    try:
        # 1. Run the scanner logic
        results = get_scanner_results()
        
        end_time = time.time()
        scan_duration = end_time - start_time
        
        # 2. Determine if we are using live data
        is_live = client is not None
        
        # 3. Calculate the next refresh time in UTC
        current_utc_time = datetime.now(timezone.utc)
        next_refresh_time = current_utc_time + timedelta(seconds=REFRESH_INTERVAL_SECONDS)
        next_refresh_str = next_refresh_time.strftime("%H:%M:%S")
        
        print(f"--- Scan complete in {scan_duration:.2f} seconds. Found {len(results)} signals. ---")
        
        # 4. Render the HTML template with the results
        return render_template(
            'index.html', 
            coins=results, # Note: Using 'coins' as requested by your index.html template
            is_live=is_live,
            scan_duration=f"{scan_duration:.2f}",
            next_refresh_time=next_refresh_str,
            REFRESH_INTERVAL_SECONDS=REFRESH_INTERVAL_SECONDS 
        )

    except Exception as e:
        # LOG THE FULL TRACEBACK! This is the core fix.
        # This will print the specific Binance API error and stack trace to your Render logs.
        print("!!! CRITICAL UNCATCHED ERROR IN INDEX ROUTE !!!")
        traceback.print_exc()
        
        # TEMPORARY FIX: Do not try to render error.html, just raise the error.
        # Raising the error forces Flask to log the traceback before crashing.
        raise e 

# --- Run the Application ---
if __name__ == '__main__':
    app.run(debug=True)