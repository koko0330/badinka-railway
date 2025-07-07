import praw
import os
import re
import requests
from datetime import datetime, timezone
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBackfill/0.1 by ConfectionInfamous97"
)

KEYWORD_PATTERN = re.compile(r'[@#]?trump(?:\.com)?', re.IGNORECASE)
DASHBOARD_URL = os.getenv("RENDER_UPDATE_URL", "https://badinka-monitor.onrender.com/update")
TIME_FILTER = "day"
seen_ids = set()
new_mentions = []

analyzer = SentimentIntensityAnalyzer()

def analyze_sentiment(text):
    try:
        vs = analyzer.polarity_scores(text)
        c = vs["compound"]
        return "positive" if c >= 0.05 else "negative" if c <= -0.05 else "neutral"
    except Exception as e:
        print(f"Sentiment failed: {e}")
        return "neutral"

def send_to_dashboard(data):
    try:
        response = requests.post(DASHBOARD_URL, json=data)
        print(f"\u2705 Sent {len(data)} mentions" if response.ok else f"\u274c Failed: {response.status_code}")
    except Exception as e:
        print(f"\u274c Error: {e}")

def extract_post(post):
    text = f"{post.title or ''} {post.selftext or ''}"
    match = KEYWORD_PATTERN.search(text)
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
        "matched_keyword": match.group(0) if match else ""
    }

def extract_comment(comment):
    match = KEYWORD_PATTERN.search(comment.body or "")
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
        "matched_keyword": match.group(0) if match else ""
    }

def backfill():
    print("\ud83d\udd01 Backfilling posts...")
    for post in reddit.subreddit("all").search("trump", sort="new", time_filter=TIME_FILTER):
        if post.id not in seen_ids:
            text = f"{post.title or ''} {post.selftext or ''}"
            if KEYWORD_PATTERN.search(text):
                data = extract_post(post)
                new_mentions.append(data)
                seen_ids.add(post.id)

    print("\ud83d\udd01 Backfilling comments...")
    for comment in reddit.subreddit("all").search("trump", sort="new", time_filter=TIME_FILTER):
        if comment.id not in seen_ids and hasattr(comment, "body"):
            if KEYWORD_PATTERN.search(comment.body or ""):
                data = extract_comment(comment)
                new_mentions.append(data)
                seen_ids.add(comment.id)

    send_to_dashboard(new_mentions) if new_mentions else print("\u2139\ufe0f No new mentions.")

if __name__ == "__main__":
    print("Starting backfill...")
    backfill()
