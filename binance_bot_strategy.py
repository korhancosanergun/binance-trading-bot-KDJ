import time
import logging
from binance.client import Client

logger = logging.getLogger(__name__)

class TradingStrategy:
    def __init__(self, bot):
        self.bot = bot
        self.sleep_time = 30  # Default check interval in seconds - faster for 5m signals
        self.custom_kdj_params = {}  # Store custom KDJ parameters
    
    def run(self):
        """Run the trading strategy in a loop"""
        if not self.bot.trading_pair:
            self.bot.select_trading_pair()
        
        logger.info(f"Starting trading bot for {self.bot.trading_pair} in {self.bot.trading_mode} mode")
        logger.info(f"Initial state: In position: {self.bot.in_position}")
        
        # Log KDJ parameters
        kdj_params_log = ", ".join([f"{tf}: {params}" for tf, params in self.bot.kdj_params.items()])
        logger.info(f"KDJ Parameters: {kdj_params_log}")
        
        # Detect market condition on startup
        market_condition = self.bot.detect_market_condition()
        logger.info(f"Current market condition: {market_condition}")
        
        # Initial profit/loss report
        self.bot.print_profit_report(force=True)
        
        try:
            while True:
                self.bot.execute_trading_strategy()
                time.sleep(self.sleep_time)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            self.bot.save_state()
            self.bot.save_trades_history()
            self.bot.print_profit_report(force=True)
        except Exception as e:
            logger.error(f"Bot error: {e}")
            self.bot.save_state()
            self.bot.save_trades_history()
    
    def change_check_interval(self, seconds):
        """Change how often the bot checks for signals"""
        if seconds < 10:
            logger.warning("Check interval too short, setting to minimum of 10 seconds")
            seconds = 10
        
        self.sleep_time = seconds
        logger.info(f"Changed check interval to {seconds} seconds")
    
    def set_custom_kdj_params(self, timeframe, k_period, k_smooth, d_smooth):
        """Set custom KDJ parameters for a specific timeframe"""
        if timeframe not in [
            Client.KLINE_INTERVAL_5MINUTE,
            Client.KLINE_INTERVAL_15MINUTE,
            Client.KLINE_INTERVAL_1HOUR,
            Client.KLINE_INTERVAL_4HOUR
        ]:
            logger.warning(f"Unsupported timeframe: {timeframe}. Parameters not changed.")
            return False
        
        # Validate parameters
        if k_period < 3 or k_period > 50:
            logger.warning(f"Invalid K period: {k_period}. Should be between 3 and 50.")
            return False
            
        if k_smooth < 1 or k_smooth > 10 or d_smooth < 1 or d_smooth > 10:
            logger.warning(f"Invalid smoothing parameters: K={k_smooth}, D={d_smooth}. Should be between 1 and 10.")
            return False
        
        # Update parameters
        self.bot.kdj_params[timeframe] = (k_period, k_smooth, d_smooth)
        logger.info(f"Updated KDJ parameters for {timeframe}: Period={k_period}, K-smooth={k_smooth}, D-smooth={d_smooth}")
        return True
    
    def optimize_parameters_for_market_condition(self, market_condition):
        """Optimize KDJ parameters based on current market condition"""
        if market_condition == "TRENDING":
            # For trending markets, use higher periods to reduce noise
            self.set_custom_kdj_params(Client.KLINE_INTERVAL_4HOUR, 21, 5, 5)
            self.set_custom_kdj_params(Client.KLINE_INTERVAL_1HOUR, 14, 3, 3)
            self.set_custom_kdj_params(Client.KLINE_INTERVAL_15MINUTE, 9, 3, 3)
            self.set_custom_kdj_params(Client.KLINE_INTERVAL_5MINUTE, 7, 3, 3)
            logger.info("Optimized KDJ parameters for TRENDING market")
        elif market_condition == "RANGING":
            # For ranging markets, use lower periods to catch more signals
            self.set_custom_kdj_params(Client.KLINE_INTERVAL_4HOUR, 14, 3, 3)
            self.set_custom_kdj_params(Client.KLINE_INTERVAL_1HOUR, 9, 3, 3)
            self.set_custom_kdj_params(Client.KLINE_INTERVAL_15MINUTE, 7, 2, 2)
            self.set_custom_kdj_params(Client.KLINE_INTERVAL_5MINUTE, 5, 2, 2)
            logger.info("Optimized KDJ parameters for RANGING market")
        else:
            logger.warning(f"Unknown market condition: {market_condition}")
            return False
        
        return True
    
    def backtest_parameters(self, days=30):
        """Backtest different parameter sets on historical data (stub)"""
        logger.info(f"Parameter backtesting requested for {days} days of historical data")
        logger.info("Backtest functionality is not fully implemented in this version")
        
        # This would be a more complex implementation that backtests different parameter sets
        # and selects the best performing ones for the current market condition
        
        return {
            "message": "Backtesting not fully implemented",
            "recommended_params": {
                Client.KLINE_INTERVAL_4HOUR: (21, 5, 5),
                Client.KLINE_INTERVAL_1HOUR: (14, 3, 3),
                Client.KLINE_INTERVAL_15MINUTE: (9, 3, 3),
                Client.KLINE_INTERVAL_5MINUTE: (7, 3, 3)
            }
        }
