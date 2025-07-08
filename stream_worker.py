import praw
import time
import re
import os
from datetime import datetime, timezone
import requests
from shared_config import insert_mention

# === Reddit API from Railway ===
reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBot/0.1 by ConfectionInfamous97"
)

# === Config ===
BRANDS = {
    "badinka": re.compile(r'[@#]?badinka(?:\.com)?', re.IGNORECASE),
    "iheartraves": re.compile(r'[@#]?iheartraves(?:\.com)?', re.IGNORECASE),
}

SEEN_IDS = set()
COLLECTED = []
POST_INTERVAL = 60  # seconds
BACKFILL_INTERVAL = 300  # every 5 min
BACKFILL_LOOKBACK_MINUTES = 15
BACKFILL_COMMENT_LIMIT = 50

print("🚀 Reddit monitor started...")

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

def extract_post(submission, brand):
    text = f"{submission.title} {submission.selftext}"
    return {
        "type": "post",
        "id": submission.id,
        "title": submission.title,
        "body": submission.selftext,
        "permalink": f"https://reddit.com{submission.permalink}",
        "created": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
        "subreddit": str(submission.subreddit),
        "author": str(submission.author),
        "score": submission.score,
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
    return [brand for brand, pattern in BRANDS.items() if pattern.search(text)]

def backfill_recent_comments(minutes=15, limit=50):
    cutoff = time.time() - (minutes * 60)
    print(f"🔁 Backfilling comments from last {minutes} minutes...")

    try:
        for comment in reddit.subreddit("all").comments(limit=limit):
            if comment.created_utc < cutoff:
                continue
            if comment.id in SEEN_IDS:
                continue

            for brand in find_brands(comment.body):
                data = extract_comment(comment, brand)
                COLLECTED.append(data)
                SEEN_IDS.add(comment.id)
                print(f"💬 [Backfill] {data['permalink']} | Brand: {brand} | Sentiment: {data['sentiment']}")
    except Exception as e:
        print(f"❌ Backfill failed: {e}")

def main():
    subreddit = reddit.subreddit("all")
    post_stream = subreddit.stream.submissions(skip_existing=True)
    comment_stream = subreddit.stream.comments(skip_existing=True)

    last_push = time.time()
    last_backfill = time.time()

    while True:
        now = time.time()

        try:
            post = next(post_stream)
            if post.id not in SEEN_IDS:
                text = f"{post.title} {post.selftext}"
                for brand in find_brands(text):
                    data = extract_post(post, brand)
                    COLLECTED.append(data)
                    SEEN_IDS.add(post.id)
                    print(f"🧵 Post: {data['permalink']} | Brand: {brand} | Sentiment: {data['sentiment']}")
        except Exception:
            pass

        try:
            comment = next(comment_stream)
            if comment.id not in SEEN_IDS:
                for brand in find_brands(comment.body):
                    data = extract_comment(comment, brand)
                    COLLECTED.append(data)
                    SEEN_IDS.add(comment.id)
                    print(f"💬 Comment: {data['permalink']} | Brand: {brand} | Sentiment: {data['sentiment']}")
        except Exception:
            pass

        # Push collected mentions to DB
        if now - last_push > POST_INTERVAL and COLLECTED:
            try:
                insert_mention(COLLECTED)
                print(f"✅ Stored {len(COLLECTED)} mentions in DB.")
                COLLECTED.clear()
                last_push = now
            except Exception as e:
                print(f"❌ Failed to store in DB: {e}")

        # Periodic backfill
        if now - last_backfill > BACKFILL_INTERVAL:
            backfill_recent_comments(minutes=BACKFILL_LOOKBACK_MINUTES, limit=BACKFILL_COMMENT_LIMIT)
            last_backfill = now

if __name__ == "__main__":
    main()
