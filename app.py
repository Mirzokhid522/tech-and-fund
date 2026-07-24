from datetime import datetime
import os
import time
from dotenv import load_dotenv
from flask import Flask, render_template
import requests
import yfinance as yf

load_dotenv()

app = Flask(__name__)

PAIRS = [
    "AUDCAD", "AUDUSD", "EURCAD", "EURUSD", "GBPCAD",
    "AUDCHF", "EURGBP", "USDCAD", "GBPUSD", "EURCHF",
    "GBPCHF", "EURAUD", "USDCHF", "GBPAUD", "CADCHF",
    "AUDJPY", "EURJPY", "CHFJPY", "GBPJPY", "USDJPY", "CADJPY"
]

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_KEYS = ["DB_USD", "DB_AUD", "DB_EUR", "DB_GBP", "DB_CAD", "DB_CHF", "DB_JPY"]

cache = {"timestamp": 0, "data": []}
CACHE_DURATION = 300  # Cache data for 5 minutes to prevent rate limits


def get_notion_fundamentals():
    currencies = {}
    if not NOTION_TOKEN:
        return currencies

    HEADERS = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    for db_key in DB_KEYS:
        db_id = os.getenv(db_key)
        if not db_id:
            continue
        
        fallback_code = db_key.replace("DB_", "")
        url = f"https://api.notion.com/v1/databases/{db_id}/query"
        try:
            response = requests.post(url, headers=HEADERS, timeout=5)
            if response.status_code == 200:
                results = response.json().get("results", [])
                for page in results:
                    props = page.get("properties", {})
                    curr_name = fallback_code
                    score = 0.0

                    for prop_name, prop_data in props.items():
                        p_type = prop_data.get("type")
                        if p_type == "title":
                            t_list = prop_data.get("title", [])
                            if t_list and t_list[0].get("plain_text", "").strip():
                                curr_name = t_list[0].get("plain_text").strip().upper()
                        elif prop_name in ["Score", "Final Score"]:
                            if p_type == "rollup":
                                rollup_obj = prop_data.get("rollup", {})
                                if "number" in rollup_obj and rollup_obj["number"] is not None:
                                    score = float(rollup_obj["number"])
                                elif "array" in rollup_obj and rollup_obj["array"]:
                                    first_item = rollup_obj["array"][0]
                                    if "number" in first_item:
                                        score = float(first_item["number"] or 0.0)
                            elif p_type == "number":
                                score = float(prop_data.get("number") or 0.0)
                            elif p_type == "formula":
                                formula_obj = prop_data.get("formula", {})
                                if "number" in formula_obj and formula_obj["number"] is not None:
                                    score = float(formula_obj["number"])
                    
                    currencies[curr_name] = {"score": score}
        except Exception:
            pass
    return currencies


def calculate_technical_scores():
    tech_scores = {symbol: 0.0 for symbol in PAIRS}
    yf_symbols = [f"{symbol}=X" for symbol in PAIRS]
    
    try:
        # Batch download all tickers in a single network request to avoid rate limits
        data = yf.download(yf_symbols, period="1y", interval="1d", group_by="ticker", progress=False, threads=True)
        
        for symbol in PAIRS:
            yf_symbol = f"{symbol}=X"
            try:
                df = data[yf_symbol] if len(PAIRS) > 1 else data
                if df.empty or "Close" not in df.columns:
                    continue
                
                close_prices = df["Close"].dropna()
                if len(close_prices) < 200:
                    continue

                ma20 = close_prices.rolling(window=20).mean().iloc[-1]
                ma50 = close_prices.rolling(window=50).mean().iloc[-1]
                ma100 = close_prices.rolling(window=100).mean().iloc[-1]
                ma200 = close_prices.rolling(window=200).mean().iloc[-1]
                current_price = close_prices.iloc[-1]

                score = 0.0
                if current_price > ma20: score += 1.0
                else: score -= 1.0

                if ma20 > ma50: score += 1.5
                else: score -= 1.5

                if ma50 > ma100: score += 2.0
                else: score -= 2.0

                if ma100 > ma200: score += 2.5
                else: score -= 2.5

                tech_scores[symbol] = float(score)
            except Exception:
                pass
    except Exception as e:
        print(f"[DEBUG] Batch download error: {e}")

    return tech_scores


def generate_combined_market_matrix():
    global cache
    current_time = time.time()

    # Serve from cache if valid to protect against rate limits
    if cache["data"] and (current_time - cache["timestamp"] < CACHE_DURATION):
        return cache["data"]

    external_tech_scores = calculate_technical_scores()
    notion_currencies = get_notion_fundamentals()
    combined_results = []

    for symbol in PAIRS:
        base = symbol[:3]
        quote = symbol[3:]
        tech_val = float(external_tech_scores.get(symbol, 0.0))
        fund_val = 0.0
        if base in notion_currencies and quote in notion_currencies:
            fund_val = (
                notion_currencies[base]["score"] - notion_currencies[quote]["score"]
            )

        composite_score = round((tech_val * 0.6) + (fund_val * 0.4), 4)

        if composite_score >= 2.5:
            bias = "Very Bullish"
        elif composite_score > 0.0:
            bias = "Bullish"
        elif composite_score == 0.0:
            bias = "Neutral"
        elif composite_score > -2.5:
            bias = "Bearish"
        else:
            bias = "Very Bearish"

        combined_results.append({
            "symbol": symbol,
            "tech_score": round(tech_val, 2),
            "fund_score": round(fund_val, 2),
            "bias": bias,
            "score": composite_score,
        })

    combined_results = sorted(
        combined_results, key=lambda x: x["score"], reverse=True
    )

    cache["data"] = combined_results
    cache["timestamp"] = current_time
    return combined_results


@app.route("/")
def dashboard():
    fresh_data = generate_combined_market_matrix()
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return render_template(
        "index.html", derived_pairs=fresh_data, last_updated=update_time
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)