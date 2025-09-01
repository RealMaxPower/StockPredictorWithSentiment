# Stock Predictor With Sentiment
This Python script uses historical stock trends and the latest news using NEWSAPI for sentiment scores to predict stock price for next 12 months in the future.

## Features
- **Robust Error Handling**: Automatic retry logic with exponential backoff for API failures
- **Smart Date Filtering**: Automatically adjusts date ranges based on NewsAPI plan limits
- **Sentiment Analysis**: Uses VADER sentiment analysis for news impact assessment
- **Forecast Adjustment**: Adjusts stock predictions based on news sentiment scores
- **Comprehensive Output**: Generates both visual forecasts and detailed news data

## Prerequisites
- Python 3.8+ installed
  ```
  python3 --version
  ```
- pip3 available
  ```
  which pip3
  ```
- Install required dependencies (allow 2–3 minutes; increase timeout to avoid network delays):
  ```bash
  export PIP_DEFAULT_TIMEOUT=300
  pip3 install yfinance pandas statsmodels matplotlib newsapi-python vaderSentiment
  # Optional pin:
  # pip3 install yfinance==0.2.58
  ```
- Set your NewsAPI key (required):
  ```bash
  export NEWSAPI_KEY="YOUR_KEY_HERE"
  ```
  > Get your API Key here: https://newsapi.org

## Recent Improvements
- **Fixed API Parameters**: Corrected NewsAPI client parameter names (`from_param`, `to`)
- **Enhanced Error Handling**: Added proper error response handling for NewsAPI
- **Deprecation Fixes**: Updated pandas resampling from deprecated `'M'` to `'ME'`
- **Retry Logic**: Implemented intelligent retry mechanism with date filter fallback
- **Better Logging**: Improved error messages and status reporting

## Instructions
1. Download [stock_forecast_with_sentiment.py](https://github.com/RealMaxPower/StockPredictorWithSentiment/blob/main/stock_forecast_with_sentiment.py) locally to /Documents/Stocks
2. Open Terminal
3. Open directory with the downloaded python script
```
cd "/Users/[user]/Documents/Stocks"
```
> _Help: Replace [user] with the active user main folder name_ 
4. Add your NEWSAPI by running the below script:
```bash
export NEWSAPI_KEY="YOUR_KEY_HERE"
```
> _Help: Replace "YOUR_KEY_HERE" with your own NEWSAPI API Key. Get your API Key [here](https://newsapi.org)._ 
5. Enter your parameters and if successful outputs will appear in your "stock_plots" folder:
```bash
python3 stock_forecast_with_sentiment.py \
  --tickers AAPL,NVDA,AVGO,MSFT,BA,AMZN,GOOGL,META,NFLX,TSLA \
  --start 2010-01-01 \
  --end   2025-08-29 \
  --outdir ./stock_plots \
  --pagesize 5
```
> _Note: The end date (2025-08-29) represents the last Friday from today. To automatically update this date, run: `python3 update_readme_date.py`_
> _Help: If Python is not installed then you came unprepared. You can also check out this [article](https://www.geeksforgeeks.org/download-and-install-python-3-latest-version/)._

## How It Works
1. **Data Collection**: Downloads historical stock data using yfinance
2. **News Fetching**: Retrieves recent news articles for each ticker using NewsAPI
3. **Sentiment Analysis**: Analyzes news sentiment using VADER sentiment analysis
4. **Forecasting**: Uses Holt-Winters exponential smoothing for 12-month predictions
5. **Adjustment**: Adjusts forecasts based on sentiment scores
6. **Output**: Generates plots and saves detailed news data to JSON files

## Error Handling
The script includes robust error handling for:
- Network timeouts and connection issues
- NewsAPI rate limiting and plan restrictions
- Invalid ticker symbols
- Missing or corrupted data
- API parameter validation

## Output Structure
```
stock_plots/
├── YYYY-MM-DD/
│   ├── TICKER_forecasts.png    # Visual forecast plots
│   └── TICKER_news.json       # Detailed news data with sentiment scores
```

## Automatic Date Updates
The README includes an automatic date update feature:
- **Update Script**: `update_readme_date.py` automatically calculates and updates the last Friday date
- **Usage**: Run `python3 update_readme_date.py` to update the example command with the current last Friday
- **Purpose**: Ensures examples always use recent, relevant dates for stock analysis

## Troubleshooting
- **API Key Issues**: Ensure your NewsAPI key is valid and has sufficient quota
- **Date Range Errors**: The script automatically handles NewsAPI plan limitations
- **Network Issues**: Built-in retry logic handles temporary connection problems
- **Memory Issues**: Large ticker lists may require more memory; process in smaller batches
