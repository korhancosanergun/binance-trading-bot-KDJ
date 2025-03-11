import logging
import os
import sys
import time
from binance.client import Client
from binance_bot_core import BinanceTradingBot
from binance_bot_strategy import TradingStrategy

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def display_header():
    """Display welcome banner"""
    print("="*70)
    print(" "*15 + "ENHANCED KDJ MULTI-TIMEFRAME TRADING BOT" + " "*15)
    print("="*70)
    print("This bot uses KDJ indicators across multiple timeframes (5m, 15m, 1h, 4h)")
    print("to filter signals and make trading decisions in both Spot and Futures markets.")
    print("-"*70)

def display_menu():
    """Display main menu options"""
    print("\nMAIN MENU:")
    print("1. Start Trading Bot")
    print("2. Configure Trading Mode (Spot/Futures)")
    print("3. Configure KDJ Parameters")
    print("4. Display Current Balance")
    print("5. Show Profit Report")
    print("6. Change Check Interval")
    print("7. Exit")
    print("\nSelect an option (1-7): ", end="")

def configure_kdj_menu(strategy):
    """Menu for configuring KDJ parameters"""
    print("\nCONFIGURE KDJ PARAMETERS:")
    print("1. Set 4-Hour Parameters")
    print("2. Set 1-Hour Parameters")
    print("3. Set 15-Minute Parameters")
    print("4. Set 5-Minute Parameters")
    print("5. Reset to Default Parameters")
    print("6. Optimize for Current Market Condition")
    print("7. Back to Main Menu")
    
    choice = input("\nSelect an option (1-7): ")
    
    timeframe_map = {
        "1": Client.KLINE_INTERVAL_4HOUR,
        "2": Client.KLINE_INTERVAL_1HOUR,
        "3": Client.KLINE_INTERVAL_15MINUTE,
        "4": Client.KLINE_INTERVAL_5MINUTE
    }
    
    if choice in timeframe_map:
        timeframe = timeframe_map[choice]
        print(f"\nConfigure {timeframe} KDJ Parameters")
        try:
            k_period = int(input("Enter K Period (3-50, recommended: 4H=21, 1H=14, 15M=9, 5M=7): "))
            k_smooth = int(input("Enter K Smoothing (1-10, recommended: 3-5): "))
            d_smooth = int(input("Enter D Smoothing (1-10, recommended: 3-5): "))
            
            if strategy.set_custom_kdj_params(timeframe, k_period, k_smooth, d_smooth):
                print(f"✅ {timeframe} KDJ parameters updated successfully!")
            else:
                print("❌ Invalid parameters. Changes not applied.")
        except ValueError:
            print("❌ Invalid input. Please enter numeric values.")
    
    elif choice == "5":
        # Reset to optimized defaults based on research
        strategy.set_custom_kdj_params(Client.KLINE_INTERVAL_4HOUR, 21, 5, 5)
        strategy.set_custom_kdj_params(Client.KLINE_INTERVAL_1HOUR, 14, 3, 3)
        strategy.set_custom_kdj_params(Client.KLINE_INTERVAL_15MINUTE, 9, 3, 3)
        strategy.set_custom_kdj_params(Client.KLINE_INTERVAL_5MINUTE, 7, 3, 3)
        print("✅ All KDJ parameters reset to optimized values!")
    
    elif choice == "6":
        # Optimize for current market condition
        market_condition = strategy.bot.detect_market_condition()
        print(f"Current market condition: {market_condition}")
        
        if strategy.optimize_parameters_for_market_condition(market_condition):
            print(f"✅ KDJ parameters optimized for {market_condition} market!")
        else:
            print("❌ Failed to optimize parameters.")
    
    elif choice == "7":
        return
    
    else:
        print("❌ Invalid choice")
    
    # Show the menu again
    input("\nPress Enter to continue...")
    configure_kdj_menu(strategy)

def configure_trading_mode(bot):
    """Configure trading mode (Spot or Futures)"""
    print("\nTRADING MODE CONFIGURATION")
    print("1. SPOT Trading")
    print("2. FUTURES Trading")
    print("3. Back to Main Menu")
    
    choice = input("\nSelect trading mode (1-3): ")
    
    if choice == "1":
        if bot.trading_mode != "SPOT":
            bot.select_trading_mode()  # This will set to SPOT
        else:
            print("Already in SPOT trading mode")
    elif choice == "2":
        if bot.trading_mode != "FUTURES":
            bot.select_trading_mode()  # This will set to FUTURES
        else:
            print("Already in FUTURES trading mode")
            
            # Ask about leverage
            change_leverage = input("Do you want to change leverage? (y/n): ")
            if change_leverage.lower() == 'y':
                bot.set_leverage()
    elif choice == "3":
        return
    else:
        print("❌ Invalid choice")
        
    input("\nPress Enter to continue...")

def main():
    """Main function to run the trading bot application"""
    display_header()
    
    # Get API credentials
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    
    if not api_key or not api_secret:
        print("\nAPI Key not found in environment variables.")
        print("Please enter your Binance API credentials:")
        api_key = input("API Key: ").strip()
        api_secret = input("API Secret: ").strip()
        
        # Save to environment for current session
        os.environ["BINANCE_API_KEY"] = api_key
        os.environ["BINANCE_API_SECRET"] = api_secret
    
    try:
        # Initialize the bot
        bot = BinanceTradingBot(api_key, api_secret)
        strategy = TradingStrategy(bot)
        
        # Welcome message with detected mode
        print(f"\nInitialized bot in {bot.trading_mode} mode.")
        if bot.trading_pair:
            print(f"Current trading pair: {bot.trading_pair}")
        
        while True:
            display_menu()
            choice = input().strip()
            
            if choice == "1":
                print(f"\nStarting trading bot in {bot.trading_mode} mode...")
                if not bot.trading_pair:
                    bot.select_trading_pair()
                
                # Detect market condition on startup
                market_condition = bot.detect_market_condition()
                print(f"Detected market condition: {market_condition}")
                
                print("\nBot is running. Press Ctrl+C to stop and return to the menu.")
                try:
                    strategy.run()
                except KeyboardInterrupt:
                    print("\nBot stopped. Returning to main menu...")
            
            elif choice == "2":
                configure_trading_mode(bot)
            
            elif choice == "3":
                configure_kdj_menu(strategy)
            
            elif choice == "4":
                print("\nCHECKING BALANCES...")
                if not bot.trading_pair:
                    bot.select_trading_pair()
                
                # Get base and quote assets
                base_asset = bot.trading_pair[:-4] if bot.trading_pair.endswith('USDT') else bot.trading_pair[:-3]
                quote_asset = 'USDT' if bot.trading_pair.endswith('USDT') else bot.trading_pair[-3:]
                
                if bot.trading_mode == "SPOT":
                    # Get spot balances
                    base_balance = bot.get_wallet_balance(base_asset)
                    quote_balance = bot.get_wallet_balance(quote_asset)
                    
                    # Get current price
                    try:
                        ticker = bot.client.get_symbol_ticker(symbol=bot.trading_pair)
                        current_price = float(ticker['price'])
                        base_value = base_balance * current_price
                        
                        print(f"\nTrading Mode: SPOT")
                        print(f"Current {bot.trading_pair} Price: {current_price}")
                        print(f"{base_asset} Balance: {base_balance} (≈ {base_value:.2f} {quote_asset})")
                        print(f"{quote_asset} Balance: {quote_balance}")
                        print(f"Total Value: {base_value + quote_balance:.2f} {quote_asset}")
                    except Exception as e:
                        print(f"Error getting current price: {e}")
                        print(f"{base_asset} Balance: {base_balance}")
                        print(f"{quote_asset} Balance: {quote_balance}")
                
                else:  # FUTURES
                    # Get futures balances
                    quote_balance = bot.get_wallet_balance(quote_asset)
                    
                    try:
                        # Get position information
                        positions = bot.client.futures_position_information(symbol=bot.trading_pair)
                        active_position = None
                        for position in positions:
                            if float(position['positionAmt']) != 0:
                                active_position = position
                                break
                        
                        # Get current price
                        ticker = bot.client.futures_symbol_ticker(symbol=bot.trading_pair)
                        current_price = float(ticker['price'])
                        
                        print(f"\nTrading Mode: FUTURES (Leverage: {bot.leverage}x)")
                        print(f"Current {bot.trading_pair} Price: {current_price}")
                        print(f"{quote_asset} Wallet Balance: {quote_balance}")
                        
                        if active_position:
                            position_amount = float(active_position['positionAmt'])
                            entry_price = float(active_position['entryPrice'])
                            position_side = "LONG" if position_amount > 0 else "SHORT"
                            position_value = abs(position_amount * current_price)
                            
                            # Calculate unrealized PNL
                            if position_side == "LONG":
                                pnl_pct = ((current_price - entry_price) / entry_price) * 100 * bot.leverage
                            else:  # SHORT
                                pnl_pct = ((entry_price - current_price) / entry_price) * 100 * bot.leverage
                            
                            pnl_usdt = position_value * (pnl_pct / 100 / bot.leverage)
                            
                            print(f"Active {position_side} Position: {abs(position_amount)} {base_asset}")
                            print(f"Position Value: {position_value:.2f} {quote_asset}")
                            print(f"Entry Price: {entry_price}")
                            print(f"Unrealized PNL: {pnl_usdt:.2f} {quote_asset} ({pnl_pct:.2f}%)")
                        else:
                            print("No active position")
                    except Exception as e:
                        print(f"Error getting futures position: {e}")
                        print(f"{quote_asset} Wallet Balance: {quote_balance}")
                
                input("\nPress Enter to continue...")
            
            elif choice == "5":
                print("\nGENERATING PROFIT REPORT...")
                report = bot.print_profit_report(force=True)
                if report:
                    print(report)
                input("\nPress Enter to continue...")
            
            elif choice == "6":
                try:
                    interval = int(input("\nEnter check interval in seconds (min 10): "))
                    strategy.change_check_interval(interval)
                    print(f"✅ Check interval changed to {strategy.sleep_time} seconds")
                except ValueError:
                    print("❌ Invalid input. Please enter a number.")
                
                input("\nPress Enter to continue...")
            
            elif choice == "7":
                print("\nExiting program. Goodbye!")
                sys.exit(0)
            
            else:
                print("❌ Invalid choice. Please try again.")
    
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\nAn error occurred: {e}")
        print("Check the log file for more details.")
        sys.exit(1)

if __name__ == "__main__":
    main()