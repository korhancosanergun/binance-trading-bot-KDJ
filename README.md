# Binance Multi-Timeframe KDJ Trading Bot

A sophisticated trading bot for Binance that uses KDJ indicator analysis across multiple timeframes to generate trading signals for both Spot and Futures markets.

## Features

- **Dual Trading Mode**: Supports both Spot and Futures trading
- **Multi-Timeframe Analysis**: Combines signals from 4 different timeframes (5m, 15m, 1h, 4h)
- **Optimized KDJ Parameters**: Uses research-backed parameters for each timeframe
- **Market Condition Detection**: Automatically detects trending vs ranging markets and adjusts strategy
- **Smart Signal Filtering**: Reduces false signals through multiple confirmation mechanisms
- **Advanced Risk Management**: Uses account risk percentage, position sizing, and stop losses
- **Trailing Stop Functionality**: Dynamic trailing stops based on profit levels
- **Detailed Profit Tracking**: Comprehensive profit and loss reporting
- **API Reliability**: Implements retry mechanisms and error handling for robust operation

## Installation

### Prerequisites

- Python 3.8+
- Binance API key and secret with trading permissions

### Setup

1. Clone the repository:
```
git clone https://github.com/yourusername/binance-kdj-trading-bot.git
cd binance-kdj-trading-bot
```

2. Install required packages:
```
pip install python-binance pandas numpy
```

3. Set up your API credentials (choose one method):
   
   - Environment variables:
   ```
   export BINANCE_API_KEY="your_api_key"
   export BINANCE_API_SECRET="your_api_secret"
   ```

   - Or enter them when prompted by the bot

## Usage

1. Run the main script:
```
python binance_bot_main.py
```

2. The bot will display a menu with the following options:
   - Start Trading Bot
   - Configure Trading Mode (Spot/Futures)
   - Configure KDJ Parameters
   - Display Current Balance
   - Show Profit Report
   - Change Check Interval
   - Exit

3. First-time setup:
   - Select "Configure Trading Mode" to choose between Spot and Futures
   - Set up your trading pair
   - If using Futures, configure leverage
   - Start the bot

4. The bot will automatically:
   - Detect market conditions (trending or ranging)
   - Calculate KDJ indicators across multiple timeframes
   - Generate combined signals with confidence levels
   - Execute trades based on your risk settings
   - Manage positions with trailing stops and take-profits

## Trading Strategy

The bot uses a multi-timeframe KDJ strategy optimized through extensive research:

1. **Market Condition Detection**:
   - Analyzes Bollinger Band width and price volatility
   - Identifies trending vs ranging markets

2. **Timeframe Weighting**:
   - 4H: Primary trend direction
   - 1H: Trend confirmation
   - 15M: Entry/exit timing
   - 5M: Quick signals and momentum detection

3. **Signal Generation**:
   - Assigns different weights to timeframes
   - Considers KDJ line crossovers (golden/death cross)
   - Identifies overbought/oversold conditions
   - Checks for trend confirmations across timeframes

4. **Position Management**:
   - Calculates size based on account risk percentage
   - Uses trailing stops that adapt to profit levels
   - Implements take-profit and stop-loss based on market conditions

## KDJ Parameters

The bot uses the following optimized KDJ parameters for different timeframes:

| Timeframe | K Period | K Smooth | D Smooth | Purpose             |
|-----------|----------|----------|----------|---------------------|
| 4 Hour    | 21       | 5        | 5        | Trend detection     |
| 1 Hour    | 14       | 3        | 3        | Trend confirmation  |
| 15 Minute | 9        | 3        | 3        | Entry/exit timing   |
| 5 Minute  | 7        | 3        | 3        | Quick signals       |

## Advanced Configuration

### Market Condition Parameters

The bot dynamically adjusts its strategy based on detected market conditions:

| Condition | Signal Threshold | Take Profit | Stop Loss |
|-----------|------------------|-------------|-----------|
| Trending  | 4                | 2.5%        | 1.5%      |
| Ranging   | 6                | 1.5%        | 1.0%      |

- Lower signal threshold in trending markets for more trades
- Higher signal threshold in ranging markets to filter noise
- Higher take-profit in trending markets to capture larger moves
- Tighter stop-loss in ranging markets to minimize losses

### Trading Multiple Markets

To trade both Spot and Futures markets simultaneously:

1. Open two terminal windows
2. Run the bot in each terminal:
   ```
   python binance_bot_main.py
   ```
3. Configure one for Spot and one for Futures

## Warning

- This bot is for educational and informational purposes only
- Cryptocurrency trading involves substantial risk of loss
- Never trade with money you cannot afford to lose
- Backtest and paper trade before using real funds
- The authors assume no responsibility for any financial losses

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- KDJ indicator strategy based on extensive research on timeframe optimization
- Special thanks to the Python Binance API library creators
