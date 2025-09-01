# Stock Predictor With Sentiment
This Python script uses historical stock trends and the latest news using NEWSAPI for sentiment scores to predict stock price for next 12 months in the future.

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

# Instructions
1. Download [stock_forecast_with_sentiment.py](https://github.com/RealMaxPower/StockPredictorWithSentiment/blob/main/stock_forecast_with_sentiment.py) locally to /Documents/Stocks
2. Open Terminal
3. Open directory with the downloaded python script
```
cd "/Users/[user]/Documents/Stocks"
```
> _Help: Replace [user] with the active user main folder name_ 
4. Add your NEWSAPI by running the below script:
```python
export NEWSAPI_KEY="YOUR_KEY_HERE"
```
> _Help: Replace "YOUR_KEY_HERE" with your own NEWSAPI API Key. Get your API Key [here](https://newsapi.org)._ 
5. Enter your parameters and if successful outputs will appear in your "stock_plots" folder:
```python
python3 stock_forecast_with_sentiment.py \
  --tickers AAPL,NVDA,AVGO,MSFT,BA,AMZN,GOOGL,META,NFLX,TSLA \
  --start 2010-01-01 \
  --end   2025-04-19 \
  --outdir ./stock_plots \
  --pagesize 5
```
> _Help: If Python is not installed then you came unprepared. You can also check out this [article](https://www.geeksforgeeks.org/download-and-install-python-3-latest-version/)._
