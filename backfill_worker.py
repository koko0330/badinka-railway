import praw
import os
import re
import time
from datetime import datetime, timezone
import requests
from shared_config import insert_mention, get_existing_mention_ids

# === Reddit API ===
reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBackfill/0.1 by ConfectionInfamous97"
)

BRANDS = {
    "badinka": re.compile(r'[@#]?badinka(?:\.com)?', re.IGNORECASE),
    "iheartraves": re.compile(r'[@#]?iheartraves(?:\.com)?', re.IGNORECASE),
}

TIME_FILTER = "month"  # Options: all, year, month, week, day, hour
DAYS_AGO = 30  # For Pushshift comment search

seen_ids = get_existing_mention_ids()
print(f"📋 Loaded {len(seen_ids)} mention IDs from DB.")
new_mentions = []

API_URL = "https://api-inference.huggingface.co/models/tabularisai/multilingual-sentiment-analysis"
API_TOKEN = os.getenv("HF_API_TOKEN")
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}


def analyze_sentiment(text):
    try:
        if not text or len(text.strip()) == 0:
            return "neutral"
        max_length = 1000
        truncated_text = text[:max_length]

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


def extract_post(post, brand):
    text = f"{post.title or ''} {post.selftext or ''}"
    return {
        "type": "post",
        "id": post.id,
        "title": post.title,
        "body": post.selftext,
        "permalink": f"https://reddit.com{post.permalink}",
        "created": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
        "subreddit": str(post.subreddit),
        "author": str(post.author),
        "score": post.score,
        "sentiment": analyze_sentiment(text),
        "brand": brand
    }


def fetch_comments_from_pushshift(brand, days_ago=30, size=100):
    end_time = int(time.time())
    start_time = end_time - (days_ago * 86400)
    url = "https://api.pushshift.io/reddit/comment/search"
    params = {
        "q": brand,
        "after": start_time,
        "before": end_time,
        "size": size,
        "sort": "desc"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception as e:
        print(f"❌ Pushshift comment fetch failed: {e}")
        return []


def backfill():
    print("🔁 Backfilling posts...")
    for brand, pattern in BRANDS.items():
        for post in reddit.subreddit("all").search(brand, sort="new", time_filter=TIME_FILTER):
            if post.id not in seen_ids:
                text = f"{post.title or ''} {post.selftext or ''}"
                if pattern.search(text):
                    new_mentions.append(extract_post(post, brand))
                    seen_ids.add(post.id)
                    print(f"🧵 Post: {post.permalink} | Brand: {brand}")

    print("🔁 Backfilling comments from Pushshift...")
    for brand, pattern in BRANDS.items():
        results = fetch_comments_from_pushshift(brand, days_ago=DAYS_AGO, size=100)
        for item in results:
            comment_id = item["id"]
            if comment_id in seen_ids:
                continue
            body = item.get("body", "")
            if pattern.search(body):
                comment_data = {
                    "type": "comment",
                    "id": comment_id,
                    "body": body,
                    "permalink": f"https://reddit.com{item.get('permalink', '')}",
                    "created": datetime.fromtimestamp(item["created_utc"], tz=timezone.utc).isoformat(),
                    "subreddit": item.get("subreddit", "unknown"),
                    "author": item.get("author", "unknown"),
                    "score": item.get("score", 0),
                    "link_id": item.get("link_id"),
                    "parent_id": item.get("parent_id"),
                    "sentiment": analyze_sentiment(body),
                    "brand": brand
                }
                new_mentions.append(comment_data)
                seen_ids.add(comment_id)
                print(f"💬 Comment: {comment_data['permalink']} | Brand: {brand}")

    if new_mentions:
        try:
            insert_mention(new_mentions)
            print(f"✅ Stored {len(new_mentions)} mentions in DB.")
        except Exception as e:
            print(f"❌ Failed to store in DB: {e}")
    else:
        print("ℹ️ No new mentions found.")


if __name__ == "__main__":
    print("📦 Starting backfill...")
    backfill()
