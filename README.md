# StockPredictorWithSentiment
This Python script uses historical stock trends and the latest news using NEWSAPI for sentiment scores to predict stock price for next 12 months in the future.

# Instructions
1. Download [StockPredictorWithSentiment.py](StockPredictorWithSentiment.py) locally to /Documents/Stocks
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
python stock_forecast_with_sentiment.py \
  --tickers AAPL,NVDA,AVGO,MSFT,BA,AMZN,GOOGL,META,NFLX,TSLA \
  --start 2010-01-01 \
  --end   2025-04-19 \
  --outdir ./stock_plots \
  --pagesize 5
```
