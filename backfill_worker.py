import praw
import os
import re
from datetime import datetime, timezone
import requests
import markdown
from bs4 import BeautifulSoup
from shared_config import insert_mention, get_existing_mention_ids
from thread_rescanner import rescan_recent_threads

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


def extract_links(text):
    try:
        html = markdown.markdown(text)
        soup = BeautifulSoup(html, "html.parser")
        return [a.get("href") for a in soup.find_all("a") if a.get("href")]
    except Exception:
        return []

def find_brands(text):
    brands_found = set()

    # Search plain text
    for brand, pattern in BRANDS.items():
        if pattern.search(text):
            brands_found.add(brand)

    # Search URLs inside markdown links
    for link in extract_links(text):
        for brand, pattern in BRANDS.items():
            if pattern.search(link):
                brands_found.add(brand)

    return list(brands_found)

def crawl_post_and_comments(post, brand):
    mentions = []

    if brand in find_brands(f"{post.title or ''} {post.selftext or ''}"):
        mentions.append(extract_post(post, brand))

    try:
        post.comments.replace_more(limit=None)
        for comment in post.comments.list():
            if comment.id not in seen_ids and brand in find_brands(comment.body):
                mentions.append(extract_comment(comment, brand))
    except Exception as e:
        print(f"⚠️ Failed to crawl comments for post {post.id}: {e}")

    return mentions


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

    # 🧠 NEW: Rescan recent threads for new comments
    print("🔄 Scanning previously stored threads for new comments...")
    try:
        rescan_recent_threads()
    except Exception as e:
        print(f"❌ Thread rescanning failed: {e}")


if __name__ == "__main__":
    print("📦 Starting backfill with thread crawl...")
    backfill()
