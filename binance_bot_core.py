import time
import json
import os
import numpy as np
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
import logging
from datetime import datetime
from binance_bot_indicators import prepare_dataframe, calculate_indicators, analyze_kdj_signals
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class BinanceTradingBot:
    def __init__(self, api_key, api_secret, trading_pair=None, trading_mode="SPOT"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = Client(api_key, api_secret)
        self.trading_pair = trading_pair
        self.trading_mode = trading_mode.upper()  # "SPOT" or "FUTURES"
        self.state_file = f"bot_state_{self.trading_mode.lower()}.json"
        self.trades_file = f"trade_history_{self.trading_mode.lower()}.json"
        self.in_position = False
        self.position_price = 0
        self.position_amount = 0
        self.position_side = None  # For futures: "LONG" or "SHORT"
        self.last_action = None
        self.last_action_price = 0
        self.trading_fee_rate = 0.001 if self.trading_mode == "SPOT" else 0.0004  # Lower fees for futures
        self.trades_history = []
        self.last_profit_report_time = 0
        self.leverage = 1  # Default leverage for futures
        
        # Optimized KDJ parameters for different timeframes based on research
        # Format: {timeframe: (k_period, k_smooth, d_smooth)}
        self.kdj_params = {
            Client.KLINE_INTERVAL_4HOUR: (21, 5, 5),    # Higher periods for higher timeframes
            Client.KLINE_INTERVAL_1HOUR: (14, 3, 3),    # Standard for intermediate
            Client.KLINE_INTERVAL_15MINUTE: (9, 3, 3),  # Standard for low timeframe
            Client.KLINE_INTERVAL_5MINUTE: (7, 3, 3)    # Faster for scalping
        }
        
        # Strategy configuration for different market conditions
        self.market_conditions = {
            "TRENDING": {
                "signal_strength_threshold": 4,  # Lower threshold in trending markets
                "take_profit_percentage": 2.5,   # Higher take profit in trending markets
                "stop_loss_percentage": 1.5      # Tighter stop loss in trending markets
            },
            "RANGING": {
                "signal_strength_threshold": 6,  # Higher threshold in ranging markets
                "take_profit_percentage": 1.5,   # Lower take profit in ranging markets
                "stop_loss_percentage": 1.0      # Tighter stop loss in ranging markets
            }
        }
        
        # Current market condition (will be updated by bot)
        self.current_market_condition = "TRENDING"
        
        # Initialize futures-specific settings if needed
        if self.trading_mode == "FUTURES":
            try:
                if self.trading_pair:
                    self.client.futures_change_margin_type(symbol=self.trading_pair, marginType='ISOLATED')
                    logger.info(f"Set margin type to ISOLATED for {self.trading_pair}")
            except Exception as e:
                logger.info(f"Could not set margin type (might be already set): {e}")
        
        # Initialize client with retry mechanism
        self.init_client()
        
        # Load previous state if exists
        self.load_state()
        self.load_trades_history()
    
    def init_client(self):
        """Initialize Binance API client with retry mechanism"""
        # Define retry strategy
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "DELETE", "PUT"]
        )
        
        # Create a session with the retry strategy
        session = self.client.session
        session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
        session.mount("http://", HTTPAdapter(max_retries=retry_strategy))
        
        logger.info("API client initialized with retry mechanism")
        
    def safe_api_call(self, api_func, *args, **kwargs):
        """Execute API calls with retry and error handling"""
        max_retries = 3
        retry_delay = 5  # seconds
        
        for retry in range(max_retries):
            try:
                return api_func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"API call failed: {e}")
                if 'Too many requests' in str(e):
                    logger.warning("Rate limit hit, longer delay needed")
                    retry_delay = 10  # Extend delay for rate limits
                
                if retry < max_retries - 1:
                    logger.info(f"Retrying API call in {retry_delay} seconds... (Attempt {retry+1}/{max_retries})")
                    time.sleep(retry_delay)
                else:
                    logger.error("Maximum retries reached for API call")
                    raise
        
        # Should never reach here due to raise in the loop
        return None
        
    def load_state(self):
        """Load previous bot state from file"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.trading_pair = state.get('trading_pair', self.trading_pair)
                    self.in_position = state.get('in_position', self.in_position)
                    self.position_price = state.get('position_price', self.position_price)
                    self.position_amount = state.get('position_amount', self.position_amount)
                    self.position_side = state.get('position_side', self.position_side)
                    self.last_action = state.get('last_action', self.last_action)
                    self.last_action_price = state.get('last_action_price', self.last_action_price)
                    self.leverage = state.get('leverage', self.leverage)
                    self.current_market_condition = state.get('market_condition', self.current_market_condition)
                    logger.info(f"Loaded previous state: Trading pair: {self.trading_pair}, "
                               f"Mode: {self.trading_mode}, In position: {self.in_position}")
            except Exception as e:
                logger.error(f"Error loading previous state: {e}")
    
    def save_state(self):
        """Save current bot state to file"""
        state = {
            'trading_pair': self.trading_pair,
            'in_position': self.in_position,
            'position_price': self.position_price,
            'position_amount': self.position_amount,
            'position_side': self.position_side,
            'last_action': self.last_action,
            'last_action_price': self.last_action_price,
            'leverage': self.leverage,
            'market_condition': self.current_market_condition,
            'timestamp': datetime.now().isoformat()
        }
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def load_trades_history(self):
        """Load trade history"""
        if os.path.exists(self.trades_file):
            try:
                with open(self.trades_file, 'r') as f:
                    self.trades_history = json.load(f)
                logger.info(f"Loaded trade history: {len(self.trades_history)} trades")
            except Exception as e:
                logger.error(f"Error loading trade history: {e}")
                self.trades_history = []
        else:
            logger.info("Trade history file not found, creating new list.")
            self.trades_history = []
    
    def save_trades_history(self):
        """Save trade history"""
        try:
            with open(self.trades_file, 'w') as f:
                json.dump(self.trades_history, f, indent=4, default=str)
        except Exception as e:
            logger.error(f"Error saving trade history: {e}")
    
    def add_trade(self, trade_type, price, quantity, timestamp=None, profit_loss=None, details=None):
        """Add new trade to history"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        trade = {
            'type': trade_type,  # 'buy', 'sell', 'long', 'short', 'close_long', 'close_short'
            'price': price,
            'quantity': quantity,
            'value_usdt': price * quantity,
            'timestamp': timestamp,
            'trading_pair': self.trading_pair,
            'trading_mode': self.trading_mode,
            'profit_loss': profit_loss,
            'leverage': self.leverage if self.trading_mode == 'FUTURES' else 1,
            'details': details or {},
        }
        
        self.trades_history.append(trade)
        self.save_trades_history()
        logger.info(f"New {trade_type} trade recorded: {price} x {quantity}")
    
    def calculate_total_profit_loss(self):
        """Calculate total profit/loss from all trades"""
        total_profit_loss = 0
        total_buy_volume = 0
        total_sell_volume = 0
        
        for trade in self.trades_history:
            if trade['type'] in ['sell', 'close_long', 'close_short'] and trade.get('profit_loss') is not None:
                total_profit_loss += trade['profit_loss']
            
            if trade['type'] in ['buy', 'long', 'short']:
                total_buy_volume += trade['value_usdt']
            elif trade['type'] in ['sell', 'close_long', 'close_short']:
                total_sell_volume += trade['value_usdt']
        
        return {
            'total_profit_loss': total_profit_loss,
            'total_buy_volume': total_buy_volume,
            'total_sell_volume': total_sell_volume,
            'roi_percentage': (total_profit_loss / total_buy_volume * 100) if total_buy_volume > 0 else 0,
            'total_trades': len(self.trades_history),
            'buy_trades': sum(1 for t in self.trades_history if t['type'] in ['buy', 'long', 'short']),
            'sell_trades': sum(1 for t in self.trades_history if t['type'] in ['sell', 'close_long', 'close_short']),
        }
    
    def print_profit_report(self, force=False):
        """Print profit/loss report"""
        current_time = time.time()
        if not force and (current_time - self.last_profit_report_time) < 3600:  # 1 hour
            return
        
        self.last_profit_report_time = current_time
        profit_stats = self.calculate_total_profit_loss()
        
        # Get USDT balance
        usdt_balance = self.get_wallet_balance('USDT')
        
        # Get base asset balance (BTC, ETH, etc.)
        base_asset = None
        if self.trading_pair:
            base_asset = self.trading_pair[:-4] if self.trading_pair.endswith('USDT') else self.trading_pair[:-3]
        
        base_balance = 0
        if base_asset:
            if self.trading_mode == "SPOT":
                base_balance = self.get_wallet_balance(base_asset)
            else:  # FUTURES
                try:
                    positions = self.safe_api_call(self.client.futures_position_information, symbol=self.trading_pair)
                    for position in positions:
                        if float(position['positionAmt']) != 0:
                            base_balance = abs(float(position['positionAmt']))
                            break
                except Exception as e:
                    logger.error(f"Error getting futures position: {e}")
        
        report = "\n" + "="*50 + "\n"
        report += f"PROFIT/LOSS REPORT: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"TRADING MODE: {self.trading_mode}\n"
        report += f"MARKET CONDITION: {self.current_market_condition}\n"
        report += "-"*50 + "\n"
        report += f"Total Profit/Loss: {profit_stats['total_profit_loss']:.4f} USDT\n"
        report += f"Total Buy Volume: {profit_stats['total_buy_volume']:.4f} USDT\n"
        report += f"Total Sell Volume: {profit_stats['total_sell_volume']:.4f} USDT\n"
        report += f"ROI: {profit_stats['roi_percentage']:.2f}%\n"
        report += f"Total Trades: {profit_stats['total_trades']}\n"
        report += f"Entry Trades: {profit_stats['buy_trades']}\n"
        report += f"Exit Trades: {profit_stats['sell_trades']}\n"
        report += f"Current USDT Balance: {usdt_balance:.4f}\n"
        
        if base_balance > 0:
            try:
                current_price = self.get_current_price()
                base_value = base_balance * current_price
                report += f"Current {base_asset} Balance: {base_balance:.8f} (approx. {base_value:.4f} USDT)\n"
                if self.trading_mode == "FUTURES" and self.leverage > 1:
                    report += f"Current Leverage: {self.leverage}x\n"
            except Exception as e:
                logger.error(f"Error getting current price: {e}")
        
        report += "="*50 + "\n"
        
        try:
            logger.info(report)
        except UnicodeEncodeError:
            # Handle Unicode issues in Windows console
            ascii_report = report.encode('ascii', 'replace').decode('ascii')
            logger.info(ascii_report)
            
        return report
    
    def get_current_price(self):
        """Get current price with error handling"""
        try:
            if self.trading_mode == "SPOT":
                ticker = self.safe_api_call(self.client.get_symbol_ticker, symbol=self.trading_pair)
            else:  # FUTURES
                ticker = self.safe_api_call(self.client.futures_symbol_ticker, symbol=self.trading_pair)
            
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"Failed to get current price: {e}")
            raise
    
    def get_available_trading_pairs(self):
        """Get all available trading pairs from Binance"""
        try:
            if self.trading_mode == "SPOT":
                exchange_info = self.safe_api_call(self.client.get_exchange_info)
                trading_pairs = [s['symbol'] for s in exchange_info['symbols'] if s['status'] == 'TRADING']
            else:  # FUTURES
                exchange_info = self.safe_api_call(self.client.futures_exchange_info)
                trading_pairs = [s['symbol'] for s in exchange_info['symbols'] if s['status'] == 'TRADING']
            
            return trading_pairs
        except Exception as e:
            logger.error(f"Error getting trading pairs: {e}")
            return []
    
    def select_trading_pair(self):
        """Let user select a trading pair"""
        if self.trading_pair:
            confirm = input(f"Current trading pair is {self.trading_pair} in {self.trading_mode} mode. Do you want to change it? (y/n): ")
            if confirm.lower() != 'y':
                return
        
        # Get USDT pairs as they're most common
        trading_pairs = self.get_available_trading_pairs()
        usdt_pairs = [pair for pair in trading_pairs if pair.endswith('USDT')]
        
        print(f"Available USDT trading pairs for {self.trading_mode} mode:")
        for i, pair in enumerate(usdt_pairs[:20]):  # Show only first 20
            print(f"{i+1}. {pair}")
        
        print("Enter the number of the trading pair or type the pair directly (e.g., BTCUSDT):")
        selection = input()
        
        try:
            if selection.isdigit() and 1 <= int(selection) <= len(usdt_pairs):
                self.trading_pair = usdt_pairs[int(selection) - 1]
            else:
                # Check if input pair exists
                if selection in trading_pairs:
                    self.trading_pair = selection
                else:
                    print(f"Trading pair {selection} not found. Please try again.")
                    return self.select_trading_pair()
            
            print(f"Selected trading pair: {self.trading_pair}")
            
            # If futures mode, also set leverage
            if self.trading_mode == "FUTURES":
                self.set_leverage()
            
            self.save_state()
        except Exception as e:
            logger.error(f"Error selecting trading pair: {e}")
            return self.select_trading_pair()
    
    def set_leverage(self, leverage=None):
        """Set leverage for futures trading"""
        if self.trading_mode != "FUTURES":
            logger.info("Leverage setting is only available in FUTURES mode")
            return False
        
        if not self.trading_pair:
            logger.error("Trading pair must be selected before setting leverage")
            return False
        
        try:
            if leverage is None:
                max_leverage = 20  # Default max leverage
                try:
                    # Try to get max leverage for this symbol
                    leverage_info = self.safe_api_call(self.client.futures_leverage_bracket, symbol=self.trading_pair)
                    if leverage_info and len(leverage_info) > 0:
                        max_leverage = int(leverage_info[0]['brackets'][0]['initialLeverage'])
                except Exception as e:
                    logger.warning(f"Could not get max leverage, using default: {e}")
                
                print(f"Current leverage: {self.leverage}x")
                print(f"Enter leverage (1-{max_leverage}):")
                leverage_input = input()
                try:
                    leverage = int(leverage_input)
                    if leverage < 1 or leverage > max_leverage:
                        print(f"Leverage must be between 1 and {max_leverage}")
                        return self.set_leverage()
                except ValueError:
                    print("Please enter a valid number")
                    return self.set_leverage()
            
            # Set leverage on the exchange
            self.safe_api_call(self.client.futures_change_leverage, symbol=self.trading_pair, leverage=leverage)
            self.leverage = leverage
            print(f"Leverage set to {leverage}x for {self.trading_pair}")
            self.save_state()
            return True
        except Exception as e:
            logger.error(f"Error setting leverage: {e}")
            return False
    
    def select_trading_mode(self):
        """Allow user to select between SPOT and FUTURES trading"""
        print(f"Current trading mode: {self.trading_mode}")
        print("Select trading mode:")
        print("1. SPOT")
        print("2. FUTURES")
        choice = input("Enter your choice (1 or 2): ")
        
        if choice == "1":
            if self.trading_mode != "SPOT":
                self.trading_mode = "SPOT"
                self.state_file = "bot_state_spot.json"
                self.trades_file = "trade_history_spot.json"
                self.in_position = False
                self.position_price = 0
                self.position_amount = 0
                self.position_side = None
                print("Switched to SPOT trading mode")
                self.load_state()
                self.load_trades_history()
        elif choice == "2":
            if self.trading_mode != "FUTURES":
                self.trading_mode = "FUTURES"
                self.state_file = "bot_state_futures.json"
                self.trades_file = "trade_history_futures.json"
                self.in_position = False
                self.position_price = 0
                self.position_amount = 0
                self.position_side = None
                print("Switched to FUTURES trading mode")
                self.load_state()
                self.load_trades_history()
        else:
            print("Invalid choice")
            return self.select_trading_mode()
        
        # Reset trading pair after mode change
        self.trading_pair = None
        self.select_trading_pair()
        
        return True
    
    def get_wallet_balance(self, asset):
        """Get available balance for a specific asset with error handling"""
        try:
            if self.trading_mode == "SPOT":
                account = self.safe_api_call(self.client.get_account)
                for balance in account['balances']:
                    if balance['asset'] == asset:
                        return float(balance['free'])
            else:  # FUTURES
                account = self.safe_api_call(self.client.futures_account_balance)
                for balance in account:
                    if balance['asset'] == asset:
                        return float(balance['balance'])
            return 0
        except Exception as e:
            logger.error(f"Error getting wallet balance for {asset}: {e}")
            # Return a very small amount rather than 0 to prevent division by zero errors
            return 0.000001
    
    def get_historical_klines(self, interval=Client.KLINE_INTERVAL_15MINUTE, limit=100):
        """Get historical klines for the trading pair with error handling"""
        try:
            if self.trading_mode == "SPOT":
                klines = self.safe_api_call(
                    self.client.get_klines,
                    symbol=self.trading_pair,
                    interval=interval,
                    limit=limit
                )
            else:  # FUTURES
                klines = self.safe_api_call(
                    self.client.futures_klines,
                    symbol=self.trading_pair,
                    interval=interval,
                    limit=limit
                )
            return klines
        except Exception as e:
            logger.error(f"Error getting historical klines: {e}")
            return []
    
    def detect_market_condition(self):
        """Detect current market condition (TRENDING or RANGING)"""
        try:
            # Use 4h timeframe to determine overall market condition
            klines = self.get_historical_klines(interval=Client.KLINE_INTERVAL_4HOUR, limit=30)
            if not klines or len(klines) < 30:
                logger.warning("Not enough data to determine market condition, using default")
                return "TRENDING"  # Default to trending as it's safer
            
            df = prepare_dataframe(klines)
            
            # Calculate standard deviation of percentage changes
            df['close'] = df['close'].astype(float)
            df['pct_change'] = df['close'].pct_change() * 100
            volatility = df['pct_change'].std()
            
            # Calculate Bollinger Bands to check for contraction/expansion
            df['SMA20'] = df['close'].rolling(window=20).mean()
            df['std20'] = df['close'].rolling(window=20).std()
            df['BB_upper'] = df['SMA20'] + 2 * df['std20']
            df['BB_lower'] = df['SMA20'] - 2 * df['std20']
            
            # Calculate Bollinger Band width
            df['BB_width'] = (df['BB_upper'] - df['BB_lower']) / df['SMA20'] * 100
            
            # Calculate ADX (Average Directional Index) for trend strength
            # For simplicity, we'll use the BB width and volatility as a proxy
            latest_bb_width = df['BB_width'].iloc[-1]
            avg_bb_width = df['BB_width'].rolling(window=10).mean().iloc[-1]
            
            # Determine market condition
            if latest_bb_width > avg_bb_width * 1.2 or volatility > 3.0:
                condition = "TRENDING"
            else:
                condition = "RANGING"
            
            logger.info(f"Market condition detected: {condition} (Volatility: {volatility:.2f}%, BB Width: {latest_bb_width:.2f}%)")
            
            # Only update if condition changed to avoid too frequent switches
            if condition != self.current_market_condition:
                logger.info(f"Market condition changed from {self.current_market_condition} to {condition}")
                self.current_market_condition = condition
                self.save_state()
            
            return condition
            
        except Exception as e:
            logger.error(f"Error detecting market condition: {e}")
            return self.current_market_condition  # Return current if there's an error
    
    def analyze_multi_timeframe(self):
        """Analyze multiple timeframes and generate a combined signal"""
        results = {}
        
        # Define the timeframes to analyze
        timeframes = [
            Client.KLINE_INTERVAL_4HOUR,    # High timeframe - Trend detection
            Client.KLINE_INTERVAL_1HOUR,    # Medium timeframe - Confirmation
            Client.KLINE_INTERVAL_15MINUTE, # Low timeframe - Entry/Exit timing
            Client.KLINE_INTERVAL_5MINUTE   # Ultra-low timeframe - Quick action signals
        ]
        
        # Analyze each timeframe
        for timeframe in timeframes:
            klines = self.get_historical_klines(interval=timeframe, limit=100)
            if not klines:
                logger.error(f"Failed to fetch historical klines for {timeframe}")
                results[timeframe] = {
                    'signal': 'UNDEFINED',
                    'kdj': {'K': None, 'D': None, 'J': None},
                    'trend': 'UNDEFINED'
                }
                continue
                
            df = prepare_dataframe(klines)
            df = calculate_indicators(df, self.kdj_params.get(timeframe, (9, 3, 3)))
            
            # Analyze KDJ signals
            signal_data = analyze_kdj_signals(df)
            results[timeframe] = signal_data
        
        return results
    
    def generate_combined_signal(self, multi_timeframe_results):
        """Generate a combined trading signal based on multi-timeframe analysis"""
        # Extract results from each timeframe
        high_tf = multi_timeframe_results.get(Client.KLINE_INTERVAL_4HOUR, {'signal': 'UNDEFINED', 'trend': 'UNDEFINED'})
        medium_tf = multi_timeframe_results.get(Client.KLINE_INTERVAL_1HOUR, {'signal': 'UNDEFINED', 'trend': 'UNDEFINED'})
        low_tf = multi_timeframe_results.get(Client.KLINE_INTERVAL_15MINUTE, {'signal': 'UNDEFINED', 'trend': 'UNDEFINED'})
        ultra_low_tf = multi_timeframe_results.get(Client.KLINE_INTERVAL_5MINUTE, {'signal': 'UNDEFINED', 'trend': 'UNDEFINED'})
        
        # Check if we have enough data for basic analysis
        if low_tf['signal'] == 'UNDEFINED' or ultra_low_tf['signal'] == 'UNDEFINED':
            logger.warning("Missing data for critical timeframes, holding position")
            return {
                'signal': 'HOLD',
                'strength': 0,
                'explanation': "Insufficient data for basic analysis"
            }
        
        # Get current market condition for signal strength threshold
        market_condition = self.detect_market_condition()
        signal_threshold = self.market_conditions[market_condition]['signal_strength_threshold']
        
        # Determine signal strength (0-10) and explanation
        strength = 0
        reasons = []
        
        # BUY/LONG SIGNAL logic
        if ultra_low_tf['signal'] == 'BUY' or low_tf['signal'] == 'BUY':
            # Weighting based on timeframes
            if ultra_low_tf['signal'] == 'BUY':
                strength += 3  # 5m signal
                reasons.append("5m KDJ buy signal")
            
            if low_tf['signal'] == 'BUY':
                strength += 2  # 15m signal
                reasons.append("15m KDJ buy signal")
            
            # Check for golden cross patterns
            if ultra_low_tf.get('golden_cross', False):
                strength += 2
                reasons.append("5m KDJ golden cross")
            
            if low_tf.get('golden_cross', False):
                strength += 1
                reasons.append("15m KDJ golden cross")
            
            # Higher timeframe confirmations
            if medium_tf['trend'] == 'BULLISH':
                strength += 1
                reasons.append("1h bullish trend confirmation")
            
            if high_tf['trend'] == 'BULLISH':
                strength += 2
                reasons.append("4h bullish trend confirmation")
                
            if medium_tf['signal'] == 'BUY':
                strength += 1
                reasons.append("1h KDJ buy signal")
                
            # Oversold conditions - good entry points
            if ultra_low_tf.get('j_oversold', False):
                strength += 2
                reasons.append("5m oversold (J < 20)")
            elif low_tf.get('j_oversold', False):
                strength += 1
                reasons.append("15m oversold (J < 20)")
                
            # Contradicting signals (reduce strength)
            if high_tf['trend'] == 'BEARISH':
                strength -= 2
                reasons.append("Warning: 4h trend is bearish")
                
        # SELL/SHORT SIGNAL logic
        elif ultra_low_tf['signal'] == 'SELL' or low_tf['signal'] == 'SELL':
            # Weighting based on timeframes
            if ultra_low_tf['signal'] == 'SELL':
                strength -= 3  # 5m signal
                reasons.append("5m KDJ sell signal")
            
            if low_tf['signal'] == 'SELL':
                strength -= 2  # 15m signal
                reasons.append("15m KDJ sell signal")
            
            # Check for death cross patterns
            if ultra_low_tf.get('death_cross', False):
                strength -= 2
                reasons.append("5m KDJ death cross")
            
            if low_tf.get('death_cross', False):
                strength -= 1
                reasons.append("15m KD death cross")
            
            # Higher timeframe confirmations
            if medium_tf['trend'] == 'BEARISH':
                strength -= 1
                reasons.append("1h bearish trend confirmation")
            
            if high_tf['trend'] == 'BEARISH':
                strength -= 2
                reasons.append("4h bearish trend confirmation")
                
            if medium_tf['signal'] == 'SELL':
                strength -= 1
                reasons.append("1h KDJ sell signal")
                
            # Overbought conditions
            if ultra_low_tf.get('j_overbought', False):
                strength -= 2
                reasons.append("5m overbought (J > 80)")
            elif low_tf.get('j_overbought', False):
                strength -= 1
                reasons.append("15m overbought (J > 80)")
                
            # Contradicting signals
            if high_tf['trend'] == 'BULLISH':
                strength += 2
                reasons.append("Warning: 4h trend is bullish")
        
        # Check if the signal meets the threshold for the current market condition
        final_signal = 'HOLD'
        if strength >= signal_threshold:
            final_signal = 'BUY'
        elif strength <= -signal_threshold:
            final_signal = 'SELL'
        
        # In futures mode, we can distinguish between long and short
        if self.trading_mode == "FUTURES":
            if final_signal == 'BUY':
                final_signal = 'LONG'
            elif final_signal == 'SELL':
                final_signal = 'SHORT'
            
        return {
            'signal': final_signal,
            'strength': abs(strength),
            'explanation': ", ".join(reasons),
            'raw_strength': strength,
            'market_condition': market_condition
        }
    
    def calculate_profit_percentage(self, current_price):
        """Calculate profit percentage of current position"""
        if not self.in_position or self.position_price == 0:
            return 0
        
        # For spot or futures long positions
        if self.trading_mode == "SPOT" or self.position_side == "LONG":
            # Calculate raw profit percentage
            raw_profit_percentage = ((current_price - self.position_price) / self.position_price) * 100
            
            # Apply leverage for futures
            if self.trading_mode == "FUTURES":
                raw_profit_percentage *= self.leverage
            
            # Account for trading fees
            fee_impact = self.trading_fee_rate * 2 * 100  # Both buy and sell
            actual_profit = raw_profit_percentage - fee_impact
            
            return actual_profit
        
        # For futures short positions
        elif self.position_side == "SHORT":
            # For shorts, profit is made when price goes down
            raw_profit_percentage = ((self.position_price - current_price) / self.position_price) * 100
            
            # Apply leverage
            raw_profit_percentage *= self.leverage
            
            # Account for trading fees
            fee_impact = self.trading_fee_rate * 2 * 100
            actual_profit = raw_profit_percentage - fee_impact
            
            return actual_profit
        
        return 0
    
    def buy(self, price, quantity):
        """Execute buy order (spot) or long order (futures) with minimum order validation"""
        try:
            base_asset = self.trading_pair[:-4] if self.trading_pair.endswith('USDT') else self.trading_pair[:-3]
            quote_asset = 'USDT' if self.trading_pair.endswith('USDT') else self.trading_pair[-3:]
            
            # Check for minimum order value (11 USDT for safety margin)
            min_order_value = 11.0  # slightly higher than 10 USDT minimum
            order_value = price * quantity
            
            if order_value < min_order_value:
                logger.info(f"Increasing order amount from {order_value:.2f} to minimum {min_order_value} USDT")
                quantity = min_order_value / price
            
            # Check if we have enough balance
            balance = self.get_wallet_balance(quote_asset)
            required_balance = price * quantity
            
            # For futures, adjust required balance based on leverage
            if self.trading_mode == "FUTURES":
                required_balance = (price * quantity) / self.leverage
            
            if balance < required_balance:
                logger.warning(f"Insufficient {quote_asset} balance. Required: {required_balance}, Available: {balance}")
                
                # Adjust quantity to match available balance (with 0.5% safety margin)
                if self.trading_mode == "FUTURES":
                    safe_quantity = (balance * self.leverage * 0.995) / price
                else:
                    safe_quantity = (balance * 0.995) / price
                    
                if safe_quantity * price >= min_order_value:
                    logger.info(f"Adjusting quantity to {safe_quantity:.8f} based on available balance")
                    quantity = safe_quantity
                else:
                    logger.error(f"Cannot place order: Adjusted quantity too small ({safe_quantity * price:.2f} {quote_asset})")
                    return False
            
            # Adjust precision based on exchange requirements
            try:
                if self.trading_mode == "SPOT":
                    symbol_info = self.safe_api_call(self.client.get_symbol_info, self.trading_pair)
                else:  # FUTURES
                    exchange_info = self.safe_api_call(self.client.futures_exchange_info)
                    symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == self.trading_pair), None)
                
                if symbol_info:
                    lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                    if lot_size_filter:
                        step_size = float(lot_size_filter['stepSize'])
                        precision = int(round(-np.log10(step_size), 0))
                        quantity = np.floor(quantity * 10**precision) / 10**precision
                        logger.info(f"Adjusted quantity to match lot size: {quantity} (step size: {step_size})")
            except Exception as e:
                logger.warning(f"Error adjusting precision: {e}")

            # Tekrar minimum emir kontrolü (hassasiyet ayarlamasından sonra)
            if quantity * price < min_order_value:
                logger.warning(f"After precision adjustment, order value {quantity * price:.2f} {quote_asset} is below minimum")
                return False
                
            # Execute order based on trading mode
            if self.trading_mode == "SPOT":
                # Place market buy order for spot
                order = self.safe_api_call(
                    self.client.create_order,
                    symbol=self.trading_pair,
                    side=SIDE_BUY,
                    type=ORDER_TYPE_MARKET,
                    quantity=quantity
                )
            else:  # FUTURES
                # Check if we already have an open position
                if self.in_position and self.position_side == "SHORT":
                    logger.warning("Cannot open LONG position while SHORT position is active")
                    return False
                
                # Place market buy order for futures
                order = self.safe_api_call(
                    self.client.futures_create_order,
                    symbol=self.trading_pair,
                    side=SIDE_BUY,
                    type=ORDER_TYPE_MARKET,
                    quantity=quantity
                )
            
            logger.info(f"{self.trading_mode} {'Buy' if self.trading_mode == 'SPOT' else 'Long'} order executed: {order}")
            
            # Get actual filled quantity from the order details
            try:
                filled_quantity = float(order['executedQty'])
                
                # Calculate fill price differently based on trading mode
                if self.trading_mode == "SPOT":
                    fill_price = float(order['cummulativeQuoteQty']) / filled_quantity if filled_quantity > 0 else price
                else:  # FUTURES
                    # For futures, we might need to get the average price from a separate API call
                    try:
                        fills = order.get('fills', [])
                        if fills:
                            # Calculate weighted average price from fills
                            total_qty = sum(float(fill['qty']) for fill in fills)
                            total_cost = sum(float(fill['qty']) * float(fill['price']) for fill in fills)
                            fill_price = total_cost / total_qty if total_qty > 0 else price
                        else:
                            # If no fills in order response, use current price
                            fill_price = price
                    except Exception as e:
                        logger.warning(f"Could not calculate fill price from futures order: {e}")
                        fill_price = price
                
                logger.info(f"Actual filled quantity: {filled_quantity} {base_asset} at {fill_price} {quote_asset}")
                
                # Update position info with the ACTUAL filled quantity
                self.in_position = True
                self.position_price = fill_price
                self.position_amount = filled_quantity
                
                # Set position side for futures
                if self.trading_mode == "FUTURES":
                    self.position_side = "LONG"
                    self.last_action = 'long'
                else:
                    self.last_action = 'buy'
                
                self.last_action_price = fill_price
                
                # Add to trade history
                trade_type = 'long' if self.trading_mode == "FUTURES" else 'buy'
                self.add_trade(
                    trade_type=trade_type,
                    price=fill_price,
                    quantity=filled_quantity,
                    details={
                        'order_id': order['orderId'],
                        'commission': order.get('commission', self.trading_fee_rate * fill_price * filled_quantity),
                        'leverage': self.leverage if self.trading_mode == "FUTURES" else 1
                    }
                )
                
                self.save_state()
                
                # Double-check by getting the current balance
                if self.trading_mode == "SPOT":
                    actual_balance = self.get_wallet_balance(base_asset)
                    logger.info(f"Current {base_asset} balance after buy: {actual_balance}")
                    if abs(actual_balance - filled_quantity) > filled_quantity * 0.01:  # 1% tolerance
                        logger.warning(f"Balance discrepancy detected. Order filled: {filled_quantity}, Current balance: {actual_balance}")
                        self.position_amount = min(filled_quantity, actual_balance)  # Use the smaller amount to be safe
                        self.save_state()
                
                return True
                
            except (KeyError, ValueError) as e:
                logger.warning(f"Could not extract filled quantity from order: {e}")
                
                # Get the current balance as fallback
                if self.trading_mode == "SPOT":
                    current_balance = self.get_wallet_balance(base_asset)
                    logger.info(f"Using current balance as position amount: {current_balance} {base_asset}")
                    self.position_amount = current_balance
                else:  # FUTURES
                    # For futures, use the requested quantity as fallback
                    logger.info(f"Using requested quantity as position amount: {quantity} {base_asset}")
                    self.position_amount = quantity
                
                self.in_position = True
                self.position_price = price
                if self.trading_mode == "FUTURES":
                    self.position_side = "LONG"
                    self.last_action = 'long'
                else:
                    self.last_action = 'buy'
                self.last_action_price = price
                
                # Add to trade history (with fallback values)
                trade_type = 'long' if self.trading_mode == "FUTURES" else 'buy'
                self.add_trade(
                    trade_type=trade_type,
                    price=price,
                    quantity=self.position_amount,
                    details={
                        'fallback_balance_used': True,
                        'leverage': self.leverage if self.trading_mode == "FUTURES" else 1
                    }
                )
                
                self.save_state()
                return True
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error during buy: {e}")
            return False
        except Exception as e:
            logger.error(f"Error executing buy order: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def sell(self, price):
        """Execute sell order (spot) or close long position (futures)"""
        try:
            if not self.in_position:
                logger.warning("Cannot sell: Not in position")
                return False
            
            # For futures, check if we're in a long position
            if self.trading_mode == "FUTURES" and self.position_side != "LONG":
                logger.warning(f"Cannot execute SELL in {self.position_side} position")
                return False
            
            base_asset = self.trading_pair[:-4] if self.trading_pair.endswith('USDT') else self.trading_pair[:-3]
            
            # Get balance based on trading mode
            if self.trading_mode == "SPOT":
                # Check spot balance
                balance = self.get_wallet_balance(base_asset)
                logger.info(f"Current {base_asset} balance: {balance}")
                
                if balance < 0.0001:
                    logger.warning(f"Insufficient {base_asset} balance for sell. Available: {balance}")
                    self.in_position = False
                    self.save_state()
                    return False
            else:  # FUTURES
                # For futures, use position amount
                balance = self.position_amount
                if balance <= 0:
                    logger.warning(f"No open LONG position to close")
                    self.in_position = False
                    self.position_side = None
                    self.save_state()
                    return False
            
            # Precision adjustment for the order quantity
            try:
                if self.trading_mode == "SPOT":
                    symbol_info = self.safe_api_call(self.client.get_symbol_info, self.trading_pair)
                else:  # FUTURES
                    exchange_info = self.safe_api_call(self.client.futures_exchange_info)
                    symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == self.trading_pair), None)
                
                sell_quantity = balance  # Sell the ACTUAL available balance
                
                # Round to the correct precision based on exchange requirements
                if symbol_info:
                    lot_size_filter = next((f for f in symbol_info.get('filters', []) if f.get('filterType') == 'LOT_SIZE'), None)
                    if lot_size_filter:
                        step_size = float(lot_size_filter['stepSize'])
                        precision = int(round(-np.log10(step_size), 0))
                        sell_quantity = np.floor(sell_quantity * 10**precision) / 10**precision
                        logger.info(f"Adjusted sell quantity to match lot size: {sell_quantity} (step size: {step_size})")
            except Exception as e:
                logger.warning(f"Error adjusting precision for sell: {e}")
                sell_quantity = balance
            
            if sell_quantity <= 0:
                logger.warning(f"Adjusted sell quantity is zero or negative: {sell_quantity}")
                self.in_position = False
                self.save_state()
                return False
            
            # Place order based on trading mode
            if self.trading_mode == "SPOT":
                # Place market sell order for spot
                order = self.safe_api_call(
                    self.client.create_order,
                    symbol=self.trading_pair,
                    side=SIDE_SELL,
                    type=ORDER_TYPE_MARKET,
                    quantity=sell_quantity
                )
            else:  # FUTURES
                # Place market sell order to close long position
                order = self.safe_api_call(
                    self.client.futures_create_order,
                    symbol=self.trading_pair,
                    side=SIDE_SELL,
                    type=ORDER_TYPE_MARKET,
                    quantity=sell_quantity
                )
            
            # Calculate profit/loss
            try:
                filled_quantity = float(order['executedQty'])
                
                # Calculate fill price based on trading mode
                if self.trading_mode == "SPOT":
                    filled_value = float(order['cummulativeQuoteQty'])
                    fill_price = filled_value / filled_quantity if filled_quantity > 0 else price
                else:  # FUTURES
                    try:
                        fills = order.get('fills', [])
                        if fills:
                            total_qty = sum(float(fill['qty']) for fill in fills)
                            total_value = sum(float(fill['qty']) * float(fill['price']) for fill in fills)
                            fill_price = total_value / total_qty if total_qty > 0 else price
                        else:
                            fill_price = price
                    except Exception as e:
                        logger.warning(f"Could not calculate fill price: {e}")
                        fill_price = price
                
                # Calculate profit/loss
                buy_value = self.position_price * self.position_amount
                sell_value = fill_price * filled_quantity
                
                # For futures, adjust for leverage
                if self.trading_mode == "FUTURES":
                    # The profit is already amplified by the leverage in the price difference
                    profit_loss = sell_value - buy_value
                else:  # SPOT
                    profit_loss = sell_value - buy_value
                
                profit_percentage = self.calculate_profit_percentage(fill_price)
                
                logger.info(f"{'Sell' if self.trading_mode == 'SPOT' else 'Close long'} order executed: {order}")
                logger.info(f"Profit/Loss: {profit_loss:.4f} USDT ({profit_percentage:.2f}%)")
                
                # Add to trade history
                trade_type = 'close_long' if self.trading_mode == "FUTURES" else 'sell'
                self.add_trade(
                    trade_type=trade_type,
                    price=fill_price,
                    quantity=filled_quantity,
                    profit_loss=profit_loss,
                    details={
                        'order_id': order['orderId'],
                        'entry_price': self.position_price,
                        'profit_percentage': profit_percentage,
                        'commission': order.get('commission', self.trading_fee_rate * fill_price * filled_quantity),
                        'leverage': self.leverage if self.trading_mode == "FUTURES" else 1
                    }
                )
                
                # Print profit report
                self.print_profit_report(force=True)
                
            except (KeyError, ValueError, ZeroDivisionError) as e:
                logger.warning(f"Could not extract filled data from order: {e}")
                profit_percentage = self.calculate_profit_percentage(price)
                logger.info(f"Approximate profit: {profit_percentage:.2f}%")
                
                # Add to trade history with fallback values
                trade_type = 'close_long' if self.trading_mode == "FUTURES" else 'sell'
                self.add_trade(
                    trade_type=trade_type,
                    price=price,
                    quantity=sell_quantity,
                    profit_loss=None,
                    details={
                        'fallback_values_used': True,
                        'leverage': self.leverage if self.trading_mode == "FUTURES" else 1
                    }
                )
            
            # Update position info
            self.in_position = False
            self.last_action = 'sell' if self.trading_mode == "SPOT" else 'close_long'
            self.last_action_price = price
            self.position_side = None if self.trading_mode == "FUTURES" else self.position_side
            self.save_state()
            
            return True
        except BinanceAPIException as e:
            logger.error(f"Binance API error during sell: {e}")
            # If insufficient balance error, update position state
            if "Account has insufficient balance" in str(e):
                logger.warning("Insufficient balance error detected. Updating position state to closed.")
                self.in_position = False
                self.position_side = None
                self.save_state()
            return False
        except Exception as e:
            logger.error(f"Error executing sell order: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def short(self, price, quantity):
        """Execute short order (futures only)"""
        if self.trading_mode != "FUTURES":
            logger.warning("Short trading is only available in FUTURES mode")
            return False
            
        try:
            base_asset = self.trading_pair[:-4] if self.trading_pair.endswith('USDT') else self.trading_pair[:-3]
            quote_asset = 'USDT' if self.trading_pair.endswith('USDT') else self.trading_pair[-3:]
            
            # Check for minimum order value
            min_order_value = 11.0
            order_value = price * quantity
            
            if order_value < min_order_value:
                logger.info(f"Increasing short order amount from {order_value:.2f} to minimum {min_order_value} USDT")
                quantity = min_order_value / price
            
            # Check if we have enough balance (considering leverage)
            balance = self.get_wallet_balance(quote_asset)
            required_balance = (price * quantity) / self.leverage
            
            if balance < required_balance:
                logger.warning(f"Insufficient {quote_asset} balance for short. Required: {required_balance}, Available: {balance}")
                
                # Adjust quantity based on available balance
                safe_quantity = (balance * self.leverage * 0.995) / price
                
                if safe_quantity * price >= min_order_value:
                    logger.info(f"Adjusting short quantity to {safe_quantity:.8f} based on available balance")
                    quantity = safe_quantity
                else:
                    logger.error(f"Cannot place short order: Adjusted quantity too small ({safe_quantity * price:.2f} {quote_asset})")
                    return False
            
            # Check if we already have an open position
            if self.in_position and self.position_side == "LONG":
                logger.warning("Cannot open SHORT position while LONG position is active")
                return False
            
            # Adjust precision based on exchange requirements
            try:
                exchange_info = self.safe_api_call(self.client.futures_exchange_info)
                symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == self.trading_pair), None)
                
                if symbol_info:
                    lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                    if lot_size_filter:
                        step_size = float(lot_size_filter['stepSize'])
                        precision = int(round(-np.log10(step_size), 0))
                        quantity = np.floor(quantity * 10**precision) / 10**precision
                        logger.info(f"Adjusted short quantity to match lot size: {quantity} (step size: {step_size})")
            except Exception as e:
                logger.warning(f"Error adjusting precision for short: {e}")
            
            # Final check for minimum order size
            if quantity * price < min_order_value:
                logger.warning(f"Final short order value {quantity * price:.2f} {quote_asset} is below minimum")
                return False
            
            # Place market sell order for futures short
            order = self.safe_api_call(
                self.client.futures_create_order,
                symbol=self.trading_pair,
                side=SIDE_SELL,
                type=ORDER_TYPE_MARKET,
                quantity=quantity
            )
            
            logger.info(f"Futures SHORT order executed: {order}")
            
            # Get actual filled quantity from the order details
            try:
                filled_quantity = float(order['executedQty'])
                
                # For futures, calculate average fill price
                try:
                    fills = order.get('fills', [])
                    if fills:
                        # Calculate weighted average price from fills
                        total_qty = sum(float(fill['qty']) for fill in fills)
                        total_cost = sum(float(fill['qty']) * float(fill['price']) for fill in fills)
                        fill_price = total_cost / total_qty if total_qty > 0 else price
                    else:
                        # If no fills in order response, use current price
                        fill_price = price
                except Exception as e:
                    logger.warning(f"Could not calculate fill price from futures order: {e}")
                    fill_price = price
                
                logger.info(f"Actual short quantity: {filled_quantity} {base_asset} at {fill_price} {quote_asset}")
                
                # Update position info
                self.in_position = True
                self.position_price = fill_price
                self.position_amount = filled_quantity
                self.position_side = "SHORT"
                self.last_action = 'short'
                self.last_action_price = fill_price
                
                # Add to trade history
                self.add_trade(
                    trade_type='short',
                    price=fill_price,
                    quantity=filled_quantity,
                    details={
                        'order_id': order['orderId'],
                        'commission': order.get('commission', self.trading_fee_rate * fill_price * filled_quantity),
                        'leverage': self.leverage
                    }
                )
                
                self.save_state()
                
                return True
                
            except (KeyError, ValueError) as e:
                logger.warning(f"Could not extract filled quantity from order: {e}")
                # Fallback approach
                self.in_position = True
                self.position_price = price
                self.position_amount = quantity  # Use requested quantity as fallback
                self.position_side = "SHORT"
                self.last_action = 'short'
                self.last_action_price = price
                
                # Add to trade history with fallback values
                self.add_trade(
                    trade_type='short',
                    price=price,
                    quantity=quantity,
                    details={
                        'order_id': order.get('orderId', 0),
                        'fallback_values_used': True,
                        'leverage': self.leverage
                    }
                )
                
                self.save_state()
                return True
                
        except BinanceAPIException as e:
            logger.error(f"Binance API error during short: {e}")
            return False
        except Exception as e:
            logger.error(f"Error executing short order: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def close_short(self, price):
        """Close short position (futures only)"""
        if self.trading_mode != "FUTURES":
            logger.warning("Short trading is only available in FUTURES mode")
            return False
            
        try:
            if not self.in_position or self.position_side != "SHORT":
                logger.warning("Cannot close short: No short position open")
                return False
            
            base_asset = self.trading_pair[:-4] if self.trading_pair.endswith('USDT') else self.trading_pair[:-3]
            
            # Use position amount for closing
            close_quantity = self.position_amount
            
            # Adjust precision if needed
            try:
                exchange_info = self.safe_api_call(self.client.futures_exchange_info)
                symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == self.trading_pair), None)
                
                if symbol_info:
                    lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                    if lot_size_filter:
                        step_size = float(lot_size_filter['stepSize'])
                        precision = int(round(-np.log10(step_size), 0))
                        close_quantity = np.floor(close_quantity * 10**precision) / 10**precision
                        logger.info(f"Adjusted close short quantity to match lot size: {close_quantity}")
            except Exception as e:
                logger.warning(f"Error adjusting precision for close short: {e}")
            
            if close_quantity <= 0:
                logger.warning(f"Invalid close quantity: {close_quantity}")
                return False
            
            # Place market buy order to close short position
            order = self.safe_api_call(
                self.client.futures_create_order,
                symbol=self.trading_pair,
                side=SIDE_BUY,  # Buy to close short
                type=ORDER_TYPE_MARKET,
                quantity=close_quantity
            )
            
            # Calculate profit/loss
            try:
                filled_quantity = float(order['executedQty'])
                
                # Calculate fill price
                try:
                    fills = order.get('fills', [])
                    if fills:
                        total_qty = sum(float(fill['qty']) for fill in fills)
                        total_cost = sum(float(fill['qty']) * float(fill['price']) for fill in fills)
                        fill_price = total_cost / total_qty if total_qty > 0 else price
                    else:
                        fill_price = price
                except Exception as e:
                    logger.warning(f"Could not calculate fill price: {e}")
                    fill_price = price
                
                # Calculate profit/loss (for shorts: entry price - exit price)
                short_value = self.position_price * self.position_amount
                close_value = fill_price * filled_quantity
                
                # For shorts, profit is made when close value is less than short value
                profit_loss = short_value - close_value
                
                # Calculate profit percentage considering leverage
                profit_percentage = ((self.position_price - fill_price) / self.position_price) * 100 * self.leverage
                
                logger.info(f"Close short order executed: {order}")
                logger.info(f"Profit/Loss: {profit_loss:.4f} USDT ({profit_percentage:.2f}%)")
                
                # Add to trade history
                self.add_trade(
                    trade_type='close_short',
                    price=fill_price,
                    quantity=filled_quantity,
                    profit_loss=profit_loss,
                    details={
                        'order_id': order['orderId'],
                        'entry_price': self.position_price,
                        'profit_percentage': profit_percentage,
                        'commission': order.get('commission', self.trading_fee_rate * fill_price * filled_quantity),
                        'leverage': self.leverage
                    }
                )
                
                # Print profit report
                # Print profit report
                self.print_profit_report(force=True)
                
            except (KeyError, ValueError, ZeroDivisionError) as e:
                logger.warning(f"Could not extract filled data from order: {e}")
                # Calculate approximate profit
                profit_percentage = ((self.position_price - price) / self.position_price) * 100 * self.leverage
                logger.info(f"Approximate profit: {profit_percentage:.2f}%")
                
                # Add to trade history with fallback values
                self.add_trade(
                    trade_type='close_short',
                    price=price,
                    quantity=close_quantity,
                    profit_loss=None,
                    details={
                        'fallback_values_used': True,
                        'leverage': self.leverage
                    }
                )
            
            # Update position info
            self.in_position = False
            self.position_side = None
            self.last_action = 'close_short'
            self.last_action_price = price
            self.save_state()
            
            return True
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error during close_short: {e}")
            return False
        except Exception as e:
            logger.error(f"Error closing short position: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def execute_trading_strategy(self):
        """Execute the multi-timeframe KDJ trading strategy with spot/futures support"""
        max_retries = 3
        retry_delay = 5  # seconds
        
        for retry in range(max_retries):
            try:
                # Get current price
                try:
                    current_price = self.get_current_price()
                except Exception as e:
                    logger.error(f"Error fetching current price: {e}")
                    if retry < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds... (Attempt {retry+1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error("Maximum retries reached, cannot get current price")
                        return
                
                # Detect market condition
                try:
                    market_condition = self.detect_market_condition()
                except Exception as e:
                    logger.warning(f"Error detecting market condition: {e}, using default")
                    market_condition = self.current_market_condition
                
                # Perform multi-timeframe analysis
                try:
                    multi_tf_results = self.analyze_multi_timeframe()
                except Exception as e:
                    logger.error(f"Error in multi-timeframe analysis: {e}")
                    return
                
                # Generate combined signal
                signal_result = self.generate_combined_signal(multi_tf_results)
                final_signal = signal_result['signal']
                signal_strength = signal_result['strength']
                explanation = signal_result.get('explanation', '')  # Use get with default for safety
                
                # Get trading parameters based on market condition
                signal_threshold = self.market_conditions[market_condition]['signal_strength_threshold']
                take_profit_pct = self.market_conditions[market_condition]['take_profit_percentage']
                stop_loss_pct = self.market_conditions[market_condition]['stop_loss_percentage']
                
                # Log the analysis results
                logger.info(f"Current price: {current_price}")
                logger.info(f"Trading mode: {self.trading_mode}, Market condition: {market_condition}")
                logger.info(f"Signal: {final_signal} (Strength: {signal_strength}/10, Threshold: {signal_threshold})")
                logger.info(f"Reason: {explanation}")
                logger.info(f"Take profit: {take_profit_pct}%, Stop loss: {stop_loss_pct}%")
                
                # Log KDJ values for each timeframe if available
                for tf, result in multi_tf_results.items():
                    if result['kdj']['K'] is not None:
                        logger.info(f"{tf} KDJ: K={result['kdj']['K']:.2f}, D={result['kdj']['D']:.2f}, J={result['kdj']['J']:.2f}")
                
                # Hourly profit/loss report check
                self.print_profit_report()
                
                # Check position status
                if self.in_position:
                    # Calculate current profit/loss
                    profit_percentage = self.calculate_profit_percentage(current_price)
                    logger.info(f"Current position profit: {profit_percentage:.2f}%")
                    
                    # Different behavior based on trading mode and position side
                    if self.trading_mode == "SPOT" or self.position_side == "LONG":
                        # Verify actual account balance for spot trading
                        if self.trading_mode == "SPOT":
                            base_asset = self.trading_pair[:-4] if self.trading_pair.endswith('USDT') else self.trading_pair[:-3]
                            real_balance = self.get_wallet_balance(base_asset)
                            
                            # If balance is very low and position shows as open
                            if real_balance < 0.0001 and self.in_position:
                                logger.warning(f"Position shows as open but {base_asset} balance ({real_balance}) is nearly zero. Correcting position state.")
                                self.in_position = False
                                self.position_side = None
                                self.save_state()
                                return
                        
                        # Check for emergency exit at specified loss threshold
                        emergency_threshold = -stop_loss_pct * 2  # Double the normal stop loss
                        if profit_percentage < emergency_threshold:
                            logger.info(f"Emergency sell/close triggered: Position lost more than {abs(emergency_threshold):.1f}%")
                            if self.trading_mode == "SPOT":
                                self.sell(current_price)
                            else:
                                self.sell(current_price)  # For LONG positions in futures
                            return
                        
                        # Check for take profit
                        if profit_percentage >= take_profit_pct:
                            logger.info(f"Take profit triggered at {profit_percentage:.2f}%. Target was {take_profit_pct:.2f}%")
                            if self.trading_mode == "SPOT":
                                self.sell(current_price)
                            else:
                                self.sell(current_price)  # For LONG positions in futures
                            return
                        
                        # Check if we should sell/close based on signal
                        if final_signal in ['SELL', 'SHORT'] and signal_strength >= signal_threshold:
                            logger.info(f"Strong sell signal (strength: {signal_strength}/{signal_threshold}). Executing sell.")
                            if self.trading_mode == "SPOT":
                                self.sell(current_price)
                            else:
                                self.sell(current_price)  # For LONG positions in futures
                            return
                        
                        # Implement trailing stop logic
                        trailing_stop_pct = min(profit_percentage / 2, stop_loss_pct) if profit_percentage > 0 else stop_loss_pct
                        trailing_stop = current_price * (1 - trailing_stop_pct/100)
                        stop_price = max(self.position_price * (1 - stop_loss_pct/100), trailing_stop)
                        
                        if current_price <= stop_price:
                            logger.info(f"Trailing stop triggered at {stop_price:.4f}")
                            if self.trading_mode == "SPOT":
                                self.sell(current_price)
                            else:
                                self.sell(current_price)  # For LONG positions in futures
                    
                    elif self.position_side == "SHORT":  # For futures SHORT positions
                        # Check for emergency exit
                        emergency_threshold = -stop_loss_pct * 2  # Double the normal stop loss
                        if profit_percentage < emergency_threshold:
                            logger.info(f"Emergency close short triggered: Position lost more than {abs(emergency_threshold):.1f}%")
                            self.close_short(current_price)
                            return
                        
                        # Check for take profit
                        if profit_percentage >= take_profit_pct:
                            logger.info(f"Take profit triggered at {profit_percentage:.2f}%. Target was {take_profit_pct:.2f}%")
                            self.close_short(current_price)
                            return
                        
                        # Check if we should close short based on signal
                        if final_signal in ['BUY', 'LONG'] and signal_strength >= signal_threshold:
                            logger.info(f"Strong buy signal (strength: {signal_strength}/{signal_threshold}). Closing short position.")
                            self.close_short(current_price)
                            return
                        
                        # Implement trailing stop for shorts
                        trailing_stop_pct = min(profit_percentage / 2, stop_loss_pct) if profit_percentage > 0 else stop_loss_pct
                        trailing_stop = current_price * (1 + trailing_stop_pct/100)  # For shorts, stop is ABOVE current price
                        stop_price = min(self.position_price * (1 + stop_loss_pct/100), trailing_stop)
                        
                        if current_price >= stop_price:
                            logger.info(f"Trailing stop triggered for short at {stop_price:.4f}")
                            self.close_short(current_price)
                
                else:  # Not in position
                    # Calculate position size based on risk management
                    quote_asset = 'USDT' if self.trading_pair.endswith('USDT') else self.trading_pair[-3:]
                    balance = self.get_wallet_balance(quote_asset)
                    
                    # Risk-based position sizing (5% of account per trade - increased from 2%)
                    risk_percentage = 0.05  # 5% account risk per trade
                    risk_amount = balance * risk_percentage
                    
                    # Calculate quantity based on stop loss and risk
                    position_size = risk_amount / (current_price * (stop_loss_pct / 100))
                    
                    # For futures, apply leverage
                    if self.trading_mode == "FUTURES":
                        position_size = position_size * self.leverage
                    
                    # Use max 20% of available balance regardless of risk calculation
                    max_investment = balance * 0.75  # Use 75% of available balance
                    position_value = position_size * current_price
                    
                    if position_value > max_investment:
                        position_size = max_investment / current_price
                    
                    # Check minimum order amount (and adjust automatically if too small)
                    minimum_order_value = 11  # Minimum 11 USDT value (extra margin above 10)
                    if position_size * current_price < minimum_order_value:
                        logger.info(f"Order amount too small: {position_size * current_price:.2f} {quote_asset}. Adjusting to minimum: {minimum_order_value} {quote_asset}")
                        position_size = minimum_order_value / current_price
                    
                    # Check for buy/long signals
                    if final_signal in ['BUY', 'LONG'] and signal_strength >= signal_threshold:
                        # Verify trend confirmation from higher timeframe
                        high_tf_trend = multi_tf_results.get(Client.KLINE_INTERVAL_4HOUR, {}).get('trend')
                        medium_tf_trend = multi_tf_results.get(Client.KLINE_INTERVAL_1HOUR, {}).get('trend')
                        
                        # In trending markets, look for stronger confirmation
                        if market_condition == "TRENDING" and high_tf_trend == "BEARISH" and medium_tf_trend == "BEARISH":
                            logger.info("Skipping buy despite signal strength: Both 4h and 1h trends are bearish in a trending market")
                            return
                        
                        # In ranging markets, we can be more aggressive
                        if market_condition == "RANGING" and medium_tf_trend == "BEARISH":
                            logger.info("Skipping buy despite signal strength: 1h trend is bearish in a ranging market")
                            return
                        
                        logger.info(f"Strong buy/long signal (strength: {signal_strength}/{signal_threshold}). Executing order.")
                        logger.info(f"Position size: {position_size:.6f} at price {current_price:.4f} ({position_size * current_price:.2f} {quote_asset})")
                        
                        # Execute buy/long based on trading mode
                        if self.trading_mode == "SPOT":
                            self.buy(current_price, position_size)
                        else:  # FUTURES
                            self.buy(current_price, position_size)  # Long position
                    
                    # Check for short signals (futures only)
                    elif final_signal == 'SHORT' and signal_strength >= signal_threshold and self.trading_mode == "FUTURES":
                        # Verify trend confirmation from higher timeframe
                        high_tf_trend = multi_tf_results.get(Client.KLINE_INTERVAL_4HOUR, {}).get('trend')
                        medium_tf_trend = multi_tf_results.get(Client.KLINE_INTERVAL_1HOUR, {}).get('trend')
                        
                        # In trending markets, look for stronger confirmation
                        if market_condition == "TRENDING" and high_tf_trend == "BULLISH" and medium_tf_trend == "BULLISH":
                            logger.info("Skipping short despite signal strength: Both 4h and 1h trends are bullish in a trending market")
                            return
                        
                        # In ranging markets, we can be more aggressive
                        if market_condition == "RANGING" and medium_tf_trend == "BULLISH":
                            logger.info("Skipping short despite signal strength: 1h trend is bullish in a ranging market")
                            return
                        
                        logger.info(f"Strong short signal (strength: {signal_strength}/{signal_threshold}). Executing short order.")
                        logger.info(f"Position size: {position_size:.6f} at price {current_price:.4f} ({position_size * current_price:.2f} {quote_asset})")
                        
                        # Execute short
                        self.short(current_price, position_size)
                    
                    else:
                        logger.info(f"No strong signal (current strength: {signal_strength}/{signal_threshold}). Waiting for better opportunity.")
                
                # Strategy executed successfully, exit the retry loop
                break
                
            except Exception as e:
                logger.error(f"Error in trading strategy execution: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
                if retry < max_retries - 1:
                    logger.info(f"Retrying strategy execution in {retry_delay} seconds... (Attempt {retry+1}/{max_retries})")
                    time.sleep(retry_delay)
                else:
                    logger.error("Maximum retries reached for strategy execution")