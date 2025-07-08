import os
import time
import re
import praw
import pytz
from datetime import datetime, timedelta, timezone
from shared_config import insert_mention, get_existing_mention_ids

# === Reddit API ===
reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="ThreadRescanner/0.1 by ConfectionInfamous97"
)

BRANDS = {
    "badinka": re.compile(r'[@#]?badinka(?:\.com)?', re.IGNORECASE),
    "iheartraves": re.compile(r'[@#]?iheartraves(?:\.com)?', re.IGNORECASE),
}

API_URL = "https://api-inference.huggingface.co/models/tabularisai/multilingual-sentiment-analysis"
API_TOKEN = os.getenv("HF_API_TOKEN")
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

seen_ids = get_existing_mention_ids()
new_mentions = []

# Only scan posts from the past X days
DAYS_BACK = 2

import psycopg2
from psycopg2.extras import RealDictCursor
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def analyze_sentiment(text):
    try:
        if not text or len(text.strip()) == 0:
            return "neutral"
        truncated_text = text[:1000]
        payload = {"inputs": truncated_text}
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        scores = result[0]
        top_label = max(scores, key=lambda x: x['score'])['label'].lower()
        if 'very positive' in top_label:
            return "positive"
        elif 'very negative' in top_label:
            return "negative"
        elif top_label in {"positive", "negative", "neutral"}:
            return top_label
        else:
            return "neutral"
    except Exception as e:
        print(f"Sentiment API call failed: {e}")
        return "neutral"

def find_brands(text):
    return [brand for brand, pattern in BRANDS.items() if pattern.search(text)]

def extract_comment(comment, brand):
    return {
        "type": "comment",
        "id": comment.id,
        "body": comment.body,
        "permalink": f"https://reddit.com{comment.permalink}",
        "created": datetime.fromtimestamp(comment.created_utc, tz=timezone.utc).isoformat(),
        "subreddit": str(comment.subreddit),
        "author": str(comment.author),
        "score": comment.score,
        "link_id": comment.link_id,
        "parent_id": comment.parent_id,
        "sentiment": analyze_sentiment(comment.body),
        "brand": brand
    }

def fetch_recent_threads(days=2):
    cutoff = datetime.utcnow() - timedelta(days=days)
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id FROM mentions WHERE type = 'post' AND created >= %s", (cutoff,))
    post_ids = set(row['id'] for row in cur.fetchall())
    cur.close()
    conn.close()
    return post_ids

def rescan_threads(post_ids):
    for post_id in post_ids:
        try:
            submission = reddit.submission(id=post_id)
            submission.comments.replace_more(limit=None)
            for comment in submission.comments.list():
                if comment.id in seen_ids:
                    continue
                for brand in find_brands(comment.body):
                    new_mentions.append(extract_comment(comment, brand))
                    seen_ids.add(comment.id)
                    print(f"🔁 Rescanned: {comment.permalink} | Brand: {brand}")
        except Exception as e:
            print(f"❌ Failed to rescan post {post_id}: {e}")

if __name__ == "__main__":
    print("🔍 Starting thread rescan...")
    recent_post_ids = fetch_recent_threads(DAYS_BACK)
    rescan_threads(recent_post_ids)
    if new_mentions:
        insert_mention(new_mentions)
        print(f"✅ Inserted {len(new_mentions)} new mentions from rescans.")
    else:
        print("ℹ️ No new mentions found in rescanned threads.")
