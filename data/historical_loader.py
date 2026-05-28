import requests

def load_history(closes, symbol="LUNCUSDT", limit=100):

    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": "1m",
        "limit": limit
    }

    data = requests.get(url, params=params).json()

    for candle in data:
        closes.append(float(candle[4]))