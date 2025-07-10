import os
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

API_URL = "https://api-inference.huggingface.co/models/tabularisai/multilingual-sentiment-analysis"
API_TOKEN = os.getenv("HF_API_TOKEN")
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

def analyze_sentiment(text):
    try:
        if not text or len(text.strip()) == 0:
            return "neutral"
        payload = {"inputs": text[:1000]}
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=10)
        response.raise_for_status()
        label = max(response.json()[0], key=lambda x: x['score'])['label'].lower()
        return "positive" if "positive" in label else "negative" if "negative" in label else "neutral"
    except Exception as e:
        print(f"❌ Sentiment failed: {e}")
        return "neutral"

def process_batch(limit=100):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id, title, body FROM mentions WHERE sentiment IS NULL LIMIT %s", (limit,))
    rows = cur.fetchall()

    for row in rows:
        text = f"{row.get('title') or ''} {row.get('body') or ''}"
        sentiment = analyze_sentiment(text)
        cur.execute("UPDATE mentions SET sentiment = %s WHERE id = %s", (sentiment, row['id']))

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Updated {len(rows)} rows with sentiment")

if __name__ == "__main__":
    process_batch()
