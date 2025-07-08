import praw
import time
import re
import os
from datetime import datetime, timezone
import requests
from shared_config import insert_mention

# === Reddit API ===
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
POST_INTERVAL = 60
BACKFILL_INTERVAL = 300
BACKFILL_LOOKBACK_MINUTES = 15
BACKFILL_BATCH_SIZE = 100

API_URL = "https://api-inference.huggingface.co/models/tabularisai/multilingual-sentiment-analysis"
API_TOKEN = os.getenv("HF_API_TOKEN")
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}


def analyze_sentiment(text):
    try:
        if not text or len(text.strip()) == 0:
            return "neutral"
        payload = {"inputs": text[:1000]}
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=10)
        response.raise_for_status()
        top_label = max(response.json()[0], key=lambda x: x['score'])['label'].lower()
        if 'very positive' in top_label:
            return "positive"
        elif 'very negative' in top_label:
            return "negative"
        elif top_label in {"positive", "negative", "neutral"}:
            return top_label
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


def crawl_post_and_comments(post, brand):
    mentions = []

    if brand in find_brands(f"{post.title or ''} {post.selftext or ''}"):
        mentions.append(extract_post(post, brand))

    try:
        post.comments.replace_more(limit=None)
        for comment in post.comments.list():
            if comment.id not in SEEN_IDS and brand in find_brands(comment.body):
                mentions.append(extract_comment(comment, brand))
    except Exception as e:
        print(f"⚠️ Failed to crawl comments for post {post.id}: {e}")

    return mentions


def main():
    subreddit = reddit.subreddit("all")
    post_stream = subreddit.stream.submissions(skip_existing=True)
    comment_stream = subreddit.stream.comments(skip_existing=True)

    last_push = time.time()

    while True:
        now = time.time()

        # Posts
        try:
            post = next(post_stream)
            if post.id not in SEEN_IDS:
                post_text = f"{post.title or ''} {post.selftext or ''}"
                for brand in find_brands(post_text):
                    mentions = crawl_post_and_comments(post, brand)
                    for m in mentions:
                        if m["id"] not in SEEN_IDS:
                            COLLECTED.append(m)
                            SEEN_IDS.add(m["id"])
                            print(f"🧵 {m['type'].capitalize()}: {m['permalink']} | Brand: {brand} | Sentiment: {m['sentiment']}")
        except Exception:
            pass

        # Comments
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

        # Push to DB
        if now - last_push > POST_INTERVAL and COLLECTED:
            try:
                insert_mention(COLLECTED)
                print(f"✅ Stored {len(COLLECTED)} mentions in DB.")
                COLLECTED.clear()
                last_push = now
            except Exception as e:
                print(f"❌ Failed to store in DB: {e}")


if __name__ == "__main__":
    print("🚀 Reddit monitor with thread-crawl started...")
    main()
