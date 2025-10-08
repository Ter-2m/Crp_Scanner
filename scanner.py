import time
import pandas as pd
import os # <-- REQUIRED FOR ENVIRONMENT VARIABLES
from binance.client import Client 

# --- Configuration ---
# IMPORTANT: Load keys from environment variables for security (set these on Render).
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY") 
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET") 

# Define the Futures Base URL (used in older generic client versions)
FUTURES_URL = 'https://fapi.binance.com' 

# Initialize client globally
client = None
if BINANCE_API_KEY and BINANCE_API_SECRET:
    try:
        # Initialize the Client for Binance Futures
        client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, tld='com') 
    except Exception as e:
        print(f"Failed to initialize Binance client: {e}")
        client = None
else:
    # Use a public client for fetching data if keys are not set
    client = Client() 
    print("Using public client (API keys/secret not provided via environment variables).")


# --- Scanner Parameters ---
TIMEFRAME = '1h'
LOOKBACK_PERIOD = 24  # Look back 24 candles (hours) for volume spike comparison
VOLUME_SPIKE_FACTOR = 1.5
EMA_7 = 7
EMA_25 = 25
EMA_99 = 99

def get_futures_exchange_info(client):
    """Fetches futures exchange information (symbols)."""
    if not client:
        return []
        
    try:
        info = client.futures_exchange_info()
        symbols = [d['symbol'] for d in info['symbols'] if d['status'] == 'TRADING']
        return symbols
    except Exception as e:
        print(f"Binance API Error fetching symbols: {e}")
        return []

def get_klines_data(client, symbol, interval, limit):
    """Fetches candlestick data for a symbol."""
    if not client:
        return None
        
    try:
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
            'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
            'taker_buy_quote_asset_volume', 'ignore'
        ])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.iloc[:-1] # Remove the current, unfinished candle
    
    except Exception as e:
        return None

def calculate_emas_and_ratios(df, periods):
    if df is None or len(df) < max(periods) + 1:
        return None
        
    for p in periods:
        df[f'ema_{p}'] = df['close'].ewm(span=p, adjust=False).mean()

    latest = df.iloc[-1]
    avg_volume = df['volume'].iloc[-(LOOKBACK_PERIOD+1):-1].mean()
    spike_factor = latest['volume'] / avg_volume if avg_volume > 0 else 0
    
    ratio_7_25 = latest[f'ema_{EMA_7}'] / latest[f'ema_{EMA_25}']
    ratio_25_99 = latest[f'ema_{EMA_25}'] / latest[f'ema_{EMA_99}']
    
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
    """Runs the Binance futures scanner logic and returns the list of winning symbols."""
    print(f"--- Starting Binance Futures Scanner ({TIMEFRAME}) ---")
    
    global client
    # Re-check client status in case it was created earlier
    if client is None:
        client = Client()

    all_symbols = get_futures_exchange_info(client)
    if not all_symbols:
        return []

    usdt_symbols = [s for s in all_symbols if s.endswith('USDT')]
    print(f"Found {len(usdt_symbols)} USDT pairs to scan...")

    winning_symbols = []
    
    for symbol in usdt_symbols:
        limit = max(EMA_7, EMA_25, EMA_99) + 2 
        df = get_klines_data(client, symbol, TIMEFRAME, limit)
        
        if df is None:
            continue
            
        ema_data = calculate_emas_and_ratios(df, [EMA_7, EMA_25, EMA_99])
        
        if ema_data is None:
            continue
            
        current_price = ema_data['current_price']
        spike_factor = ema_data['spike_factor']

        # 5. Apply Bullish Strategy Logic
        alignment_check = (ema_data['ema_7'] > ema_data['ema_25'] and 
                           ema_data['ema_25'] > ema_data['ema_99'])
                           
        ratio_check = (ema_data['ratio_7_25'] > 1 and ema_data['ratio_7_25'] < 1.005 and 
                       ema_data['ratio_25_99'] > 1 and ema_data['ratio_25_99'] < 1.01)

        volume_check = spike_factor >= VOLUME_SPIKE_FACTOR
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
    return winning_symbols