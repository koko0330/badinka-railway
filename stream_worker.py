import praw
import time
import re
import os
import requests
from datetime import datetime, timezone
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBot/0.1 by ConfectionInfamous97"
)

KEYWORD_PATTERN = re.compile(r'[@#]?trump(?:\.com)?', re.IGNORECASE)
SEEN_IDS = set()
COLLECTED = []
POST_INTERVAL = 60
DASHBOARD_URL = os.getenv("RENDER_UPDATE_URL", "https://badinka-monitor.onrender.com/update")

analyzer = SentimentIntensityAnalyzer()

print("Reddit monitor started...")

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
        print(f"Synced {len(data)} mentions." if response.ok else f"Sync failed: {response.status_code}")
    except Exception as e:
        print(f"Sync error: {e}")

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

def main():
    subreddit = reddit.subreddit("all")
    post_stream = subreddit.stream.submissions(skip_existing=True)
    comment_stream = subreddit.stream.comments(skip_existing=True)

    last_push = time.time()

    while True:
        now = time.time()
        try:
            post = next(post_stream)
            if post.id not in SEEN_IDS:
                text = f"{post.title} {post.selftext}"
                if KEYWORD_PATTERN.search(text):
                    data = extract_post(post)
                    COLLECTED.append(data)
                    SEEN_IDS.add(post.id)
        except Exception:
            pass

        try:
            comment = next(comment_stream)
            if comment.id not in SEEN_IDS:
                if KEYWORD_PATTERN.search(comment.body):
                    data = extract_comment(comment)
                    COLLECTED.append(data)
                    SEEN_IDS.add(comment.id)
        except Exception:
            pass

        if now - last_push > POST_INTERVAL and COLLECTED:
            send_to_dashboard(COLLECTED)
            COLLECTED.clear()
            last_push = now

if __name__ == "__main__":
    main()
