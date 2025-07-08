import praw
import os
import re
from datetime import datetime, timezone
import requests
from shared_config import insert_mention

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

TIME_FILTER = "day"  # Options: all, year, month, week, day, hour

seen_ids = set()
new_mentions = []

API_URL = "https://api-inference.huggingface.co/models/tabularisai/multilingual-sentiment-analysis"
API_TOKEN = os.getenv("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")
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

def analyze_sentiment(text):
    try:
        payload = {"inputs": text}
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        label = result[0].get("label", "neutral").lower()
        if label in {"positive", "negative", "neutral"}:
            return label
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

def find_brands(text):
    found_brands = []
    for brand, pattern in BRANDS.items():
        if pattern.search(text):
            found_brands.append(brand)
    return found_brands

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

    print("🔁 Backfilling comments...")
    for brand, pattern in BRANDS.items():
        for comment in reddit.subreddit("all").search(brand, sort="new", time_filter=TIME_FILTER):
            if comment.id not in seen_ids and hasattr(comment, "body"):
                if pattern.search(comment.body or ""):
                    new_mentions.append(extract_comment(comment, brand))
                    seen_ids.add(comment.id)
                    print(f"💬 Comment: {comment.permalink} | Brand: {brand}")

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
