import pandas as pd
import numpy as np

def calculate_kdj(df, k_period=9, k_smooth=3, d_smooth=3):
    """Calculate KDJ indicator with custom parameters"""
    # Calculate RSV (Raw Stochastic Value)
    df['low_min'] = df['low'].rolling(window=k_period).min()
    df['high_max'] = df['high'].rolling(window=k_period).max()
    
    # RSV = (Close - Min(Low, n)) / (Max(High, n) - Min(Low, n)) * 100
    df['rsv'] = ((df['close'] - df['low_min']) / (df['high_max'] - df['low_min'])) * 100
    
    # Handle division by zero - Pandas compatibility fix
    rsv = df['rsv'].copy()
    rsv = rsv.replace([np.inf, -np.inf], np.nan)
    rsv = rsv.fillna(50)  # Use 50 as neutral value for undefined RSV
    df['rsv'] = rsv
    
    # Calculate K, D, J
    df['%K'] = df['rsv'].ewm(span=k_smooth, adjust=False).mean()
    df['%D'] = df['%K'].ewm(span=d_smooth, adjust=False).mean()
    df['%J'] = 3 * df['%K'] - 2 * df['%D']
    
    return df

def calculate_bollinger_bands(df, window=20, num_std=2):
    """Calculate Bollinger Bands"""
    df['SMA'] = df['close'].rolling(window=window).mean()
    df['std'] = df['close'].rolling(window=window).std()
    df['UB'] = df['SMA'] + num_std * df['std']
    df['LB'] = df['SMA'] - num_std * df['std']
    return df

def prepare_dataframe(klines):
    """Convert klines to dataframe and convert types"""
    df = pd.DataFrame(klines, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    
    # Convert string values to float
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    return df

def calculate_indicators(df, kdj_params):
    """Calculate all required indicators with the given parameters"""
    k_period, k_smooth, d_smooth = kdj_params
    
    # Calculate KDJ
    df = calculate_kdj(df, k_period, k_smooth, d_smooth)
    
    # Calculate Bollinger Bands
    df = calculate_bollinger_bands(df)
    
    return df

def analyze_kdj_signals(df):
    """Analyze KDJ indicator to generate signals and state"""
    if len(df) < 2:
        return {
            'signal': 'UNDEFINED',
            'kdj': {'K': None, 'D': None, 'J': None},
            'trend': 'UNDEFINED'
        }
    
    # Get the latest data points
    current = df.iloc[-1]
    previous = df.iloc[-2]
    
    # KDJ Golden Cross: K line crosses above D line
    golden_cross = previous['%K'] <= previous['%D'] and current['%K'] > current['%D']
    
    # KDJ Death Cross: K line crosses below D line
    death_cross = previous['%K'] >= previous['%D'] and current['%K'] < current['%D']
    
    # KDJ Trend: general direction of K and D
    if current['%K'] > 50 and current['%D'] > 50:
        trend = 'BULLISH'
    elif current['%K'] < 50 and current['%D'] < 50:
        trend = 'BEARISH'
    else:
        trend = 'NEUTRAL'
    
    # J-line extreme values
    j_overbought = current['%J'] > 80
    j_oversold = current['%J'] < 20
    
    # Generate signal based on KDJ conditions
    if golden_cross or (current['%K'] > current['%D'] and j_oversold):
        signal = 'BUY'
    elif death_cross or (current['%K'] < current['%D'] and j_overbought):
        signal = 'SELL'
    else:
        signal = 'HOLD'
    
    # Return analysis results
    return {
        'signal': signal,
        'kdj': {
            'K': current['%K'],
            'D': current['%D'],
            'J': current['%J']
        },
        'trend': trend,
        'golden_cross': golden_cross,
        'death_cross': death_cross,
        'j_overbought': j_overbought,
        'j_oversold': j_oversold
    }
