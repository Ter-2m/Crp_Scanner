import time
import pandas as pd
# --- FIXED IMPORTS for generic/older python-binance compatibility ---
# REMOVED: import binance-futures (invalid)
# REMOVED: from binance.error import ClientError (module not found)
# REPLACED: Use the standard way to import the main Client if binance.futures fails.
# The core Binance Client class is often imported from binance.client or the top-level package.
# Assuming the user meant to use the main Client class which handles futures.
# NOTE: If this fails, the user likely needs to update their python-binance library.
from binance.client import Client 

# --- Configuration ---
# IMPORTANT: REPLACE these with your actual keys to enable live scanning.
BINANCE_API_KEY = "Tix2AA490U1IJBBEqL7gzV4z396nWVIOMuEbTyJAGPie57sWOnFqgFVo4RHCytLI" # REPLACE with your actual API key
BINANCE_API_SECRET = "9cZ1RoB04SIIMS3UjZi3yTEA7hZ8f1vwv4fCiFaVEFEuiM9RkezfE7CCDGLBAsqq" # REPLACE with your actual API secret

# Define the Futures Base URL to ensure the client connects to the Futures environment
# This is a common requirement for older versions of the generic Client.
# If this client doesn't support futures, it will fail on the klines call.
FUTURES_URL = 'https://fapi.binance.com' 

# Use a public client if keys are not set for mocking data
client = None
if BINANCE_API_KEY != "YOUR_API_KEY_HERE":
    try:
        # Initialize the Client for Binance Futures
        # FIX: Replaced custom 'Futures' with the imported 'Client' class. 
        # We specify the tld='com' and use testnet=False as a workaround for futures connection.
        client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, tld='com') 
    except Exception as e:
        print(f"Failed to initialize Binance client: {e}")
        client = None
else:
    # Use a public client for fetching data if keys are not set
    # FIX: Replaced custom 'futures()' with the imported 'Client()' class.
    client = Client() 
    print("Using public client (no keys/secret provided).")


# --- Scanner Parameters ---
TIMEFRAME = '1h'
LOOKBACK_PERIOD = 24  # Look back 24 candles (hours) for volume spike comparison
VOLUME_SPIKE_FACTOR = 1.5 # Current volume must be 1.5x the average
EMA_7 = 7
EMA_25 = 25
EMA_99 = 99

def get_futures_exchange_info(client):
    """
    Fetches futures exchange information (symbols).
    Handles potential API errors gracefully.
    """
    if not client:
        print("Client not initialized. Cannot fetch symbols.")
        return []
        
    try:
        # Get all symbols that are TRADING
        # FIX: Changed to the generic futures_exchange_info method
        info = client.futures_exchange_info()
        symbols = [d['symbol'] for d in info['symbols'] if d['status'] == 'TRADING']
        return symbols
    # FIX: Replaced ClientError with a generic Exception catch
    except Exception as e:
        print(f"Binance API Error fetching symbols: {e}")
        return []

def get_klines_data(client, symbol, interval, limit):
    """
    Fetches candlestick data for a symbol.
    """
    if not client:
        return None
        
    try:
        # klines format: [timestamp, open, high, low, close, volume, ...]
        # FIX: Changed to the generic futures_klines method
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        
        # Convert klines to a pandas DataFrame for easier processing
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
            'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
            'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # Convert necessary columns to numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df.iloc[:-1] # Remove the current, unfinished candle
    
    # FIX: Replaced ClientError with a generic Exception catch
    except Exception as e:
        # print(f"General error fetching klines for {symbol}: {e}")
        return None

def calculate_emas_and_ratios(df, periods):
    """
    Calculates Exponential Moving Averages and related metrics.
    """
    if df is None or len(df) < max(periods) + 1:
        return None
        
    # Calculate EMAs
    for p in periods:
        df[f'ema_{p}'] = df['close'].ewm(span=p, adjust=False).mean()

    # Get the latest data point
    latest = df.iloc[-1]
    
    # Check for Volume Spike: Current volume vs. average volume of the previous LOOKBACK_PERIOD candles
    avg_volume = df['volume'].iloc[-(LOOKBACK_PERIOD+1):-1].mean()
    spike_factor = latest['volume'] / avg_volume if avg_volume > 0 else 0
    
    # Calculate EMA Ratios
    ratio_7_25 = latest[f'ema_{EMA_7}'] / latest[f'ema_{EMA_25}']
    ratio_25_99 = latest[f'ema_{EMA_25}'] / latest[f'ema_{EMA_99}']
    
    # Calculate the percentage change from the close of the previous candle
    previous_close = df.iloc[-2]['close']
    close_change = (latest['close'] - previous_close) / previous_close
    
    return {
        'current_price': latest['close'],
        'ema_7': latest[f'ema_{EMA_7}'],
        'ema_25': latest[f'ema_{EMA_25}'],
        'ema_99': latest[f'ema_{EMA_99}'],
        'ratio_7_25': ratio_7_25,
        'ratio_25_99': ratio_25_99,
        'spike_factor': spike_factor,
        'close_change': close_change
    }

def get_scanner_results():
    """
    Runs the Binance futures scanner logic and returns the list of winning symbols
    and the total number of symbols scanned.
    """
    print(f"--- Starting Binance Futures Scanner ({TIMEFRAME}) ---")
    
    # 1. Get the client
    global client
    if client is None:
        # If the client wasn't initialized with keys, create a public client for fetching data
        # FIX: Replaced custom 'futures()' with the imported 'Client()' class
        client = Client()
        print("Using public client (no keys/secret provided).")

    # 2. Get all trading symbols
    all_symbols = get_futures_exchange_info(client)
    if not all_symbols:
        print("Could not retrieve trading symbols.")
        # NEW: Return a dictionary structure even on failure
        return {'winning_symbols': [], 'total_scanned_count': 0}

    # Filter out non-USD pairs (e.g., BTCBUSD, ETHBUSD) to focus on common ones (e.g., USDT)
    usdt_symbols = [s for s in all_symbols if s.endswith('USDT')]
    
    # NEW: Store the total count of coins we will scan
    total_coins_to_scan = len(usdt_symbols)
    print(f"Found {total_coins_to_scan} USDT pairs to scan...")

    winning_symbols = []
    
    for symbol in usdt_symbols:
        # 3. Fetch K-lines data
        # Fetch one more candle than needed for accurate EMA calculation
        limit = max(EMA_7, EMA_25, EMA_99) + 2 
        df = get_klines_data(client, symbol, TIMEFRAME, limit)
        
        if df is None:
            continue
            
        # 4. Calculate Indicators and Ratios
        ema_data = calculate_emas_and_ratios(df, [EMA_7, EMA_25, EMA_99])
        
        if ema_data is None:
            continue
            
        current_price = ema_data['current_price']
        spike_factor = ema_data['spike_factor']

        # 5. Apply Bullish Strategy Logic
        
        # Condition 1: EMA Alignment (7 > 25 > 99)
        alignment_check = (ema_data['ema_7'] > ema_data['ema_25'] and 
                           ema_data['ema_25'] > ema_data['ema_99'])
                           
        # Condition 2: EMA Ratios are close (no sudden, sharp moves)
        ratio_check = (ema_data['ratio_7_25'] > 1 and ema_data['ratio_7_25'] < 1.005 and 
                       ema_data['ratio_25_99'] > 1 and ema_data['ratio_25_99'] < 1.01)

        # Condition 3: Volume Spike (current volume is VOLUME_SPIKE_FACTOR * average)
        volume_check = spike_factor >= VOLUME_SPIKE_FACTOR
        
        # Condition 4: Current candle is closing bullish (close > previous close, indicating momentum)
        change_check = ema_data['close_change'] > 0
        
        if alignment_check and ratio_check and volume_check and change_check:
            
            # --- Calculate TP/SL ---
            risk_percent = 0.005 # 0.5% risk
            SL_PRICE = current_price * (1 - risk_percent)
            
            RISK_DISTANCE = current_price - SL_PRICE 
            
            TP1_PRICE = current_price + (RISK_DISTANCE * 3.0) 
            
            TP2_PRICE = current_price + (RISK_DISTANCE * 5.0) 
            
            winning_symbols.append({
                'symbol': symbol,
                'price': current_price,
                'spike_factor': spike_factor,
                'sl_price': SL_PRICE,
                'tp1_price': TP1_PRICE,
                'tp2_price': TP2_PRICE,
                'scan_time': time.strftime("%H:%M:%S", time.gmtime()),
                'ratios': {
                    '7/25': ema_data['ratio_7_25'],
                    '25/99': ema_data['ratio_25_99'],
                }
            })

    # 6. Return Results (instead of printing)
    # NEW: Return a dictionary with both results and the total count
    return {
        'winning_symbols': winning_symbols,
        'total_scanned_count': total_coins_to_scan
    }