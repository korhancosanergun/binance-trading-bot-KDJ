# Detailed Setup Guide

This guide provides detailed instructions for setting up and configuring the Binance Multi-Timeframe KDJ Trading Bot.

## Table of Contents

1. [Binance Account Setup](#binance-account-setup)
2. [API Key Creation](#api-key-creation)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Running the Bot](#running-the-bot)
6. [Customizing Parameters](#customizing-parameters)
7. [Troubleshooting](#troubleshooting)

## Binance Account Setup

1. Sign up for a Binance account at [binance.com](https://www.binance.com/en/register)
2. Complete identity verification (KYC) to enable trading
3. If you plan to use Futures, enable Futures trading in your account:
   - Go to Derivatives > USD-M Futures
   - Complete the futures account setup process

## API Key Creation

1. Log in to your Binance account
2. Navigate to **API Management** (found under your profile)
3. Click **Create API**
4. Set a label for your API (e.g., "KDJ Trading Bot")
5. For security, restrict API access to specific IP addresses if possible
6. Enable the following permissions:
   - For Spot trading: "Enable Reading" and "Enable Spot & Margin Trading"
   - For Futures trading: "Enable Reading" and "Enable Futures"
7. Complete security verification
8. Save your API Key and Secret Key securely

**IMPORTANT**: Never share your API keys with anyone. The bot only needs the keys you created, not your Binance login credentials.

## Installation

### Using Git

```bash
# Clone the repository
git clone https://github.com/yourusername/binance-kdj-trading-bot.git
cd binance-kdj-trading-bot

# Create a virtual environment (recommended)
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Manual Download

If you don't have Git installed:

1. Download the ZIP file from the GitHub repository
2. Extract the files to your preferred location
3. Open a terminal/command prompt in that folder
4. Follow the virtual environment and installation steps above

## Configuration

### API Credentials

Choose one of these methods to set up your API credentials:

#### Method 1: Environment Variables (recommended)

Set these environment variables:

```bash
# On Windows (Command Prompt)
set BINANCE_API_KEY=your_api_key_here
set BINANCE_API_SECRET=your_api_secret_here

# On Windows (PowerShell)
$env:BINANCE_API_KEY="your_api_key_here"
$env:BINANCE_API_SECRET="your_api_secret_here"

# On macOS/Linux
export BINANCE_API_KEY="your_api_key_here"
export BINANCE_API_SECRET="your_api_secret_here"
```

#### Method 2: Enter When Prompted

Simply run the bot, and it will prompt you to enter your API credentials if they're not found in environment variables.

### Initial Bot Setup

1. Run the bot: `python binance_bot_main.py`
2. Select "Configure Trading Mode" (option 2)
3. Choose Spot or Futures trading
4. Select a trading pair
5. If using Futures, set your preferred leverage

## Running the Bot

1. Start the bot: `python binance_bot_main.py`
2. Select "Start Trading Bot" (option 1)
3. The bot will begin analyzing market conditions and executing trades according to the strategy

To stop the bot, press `Ctrl+C`. This will gracefully stop the process and save the current state.

## Running Spot and Futures Simultaneously

To run both Spot and Futures trading at the same time:

1. Open two separate terminal windows
2. In each terminal, navigate to the bot directory
3. Run the bot in each terminal: `python binance_bot_main.py`
4. Configure one for Spot and one for Futures trading

## Customizing Parameters

### KDJ Parameters

To modify the KDJ parameters for different timeframes:

1. From the main menu, select "Configure KDJ Parameters" (option 3)
2. Choose the timeframe you want to modify
3. Enter new values for K Period, K Smoothing, and D Smoothing

### Trading Intervals

To change how frequently the bot checks for signals:

1. From the main menu, select "Change Check Interval" (option 6)
2. Enter a value in seconds (minimum 10 seconds)

## Troubleshooting

### Common Issues

#### "Connection aborted" errors

This is usually due to network issues or Binance API rate limits:

- Check your internet connection
- Reduce the check interval to lower API requests
- Make sure you're not running multiple instances with the same API key

#### "Order amount too small" warnings

Binance has minimum order size requirements:

- Increase your account balance
- Increase the risk percentage in the code (search for `risk_percentage` and change from 0.05 to a higher value)
- Use higher leverage in Futures mode

#### Trading pair not found

If your trading pair isn't found:

- Make sure the pair exists on Binance
- Check for correct formatting (e.g., "BTCUSDT", not "BTC/USDT")
- Verify the pair is available in your selected trading mode

### Getting Help

If you encounter issues not covered here:

1. Check the logs in the `trading_bot.log` file
2. Search for similar issues in the GitHub repository
3. Create a new issue with detailed information about your problem

## Acknowledgments

This bot is for educational purposes only. Always trade responsibly and never risk more than you can afford to lose.
