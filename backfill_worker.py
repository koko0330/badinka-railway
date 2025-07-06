import praw
import os
import re
import requests
from datetime import datetime, timezone

# === Reddit API ===
reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBackfill/0.1 by ConfectionInfamous97"
)

# === Config ===
KEYWORD_PATTERN = re.compile(r'[@#]?\b?badinka(?:\.com)?\b?', re.IGNORECASE)
DASHBOARD_URL = os.getenv("RENDER_UPDATE_URL", "https://badinka-monitor.onrender.com/update")
TIME_FILTER = "day"  # Options: all, year, month, week, day, hour

# === In-memory seen cache ===
seen_ids = set()
new_mentions = []

def send_to_dashboard(data):
    try:
        response = requests.post(DASHBOARD_URL, json=data)
        if response.ok:
            print(f"✅ Sent {len(data)} new mentions to dashboard")
        else:
            print(f"❌ Failed to send data: {response.status_code}")
    except Exception as e:
        print(f"❌ Error sending data: {e}")

def extract_post(post):
    return {
        "type": "post",
        "id": post.id,
        "title": post.title,
        "body": post.selftext,
        "permalink": f"https://reddit.com{post.permalink}",
        "created": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
        "subreddit": str(post.subreddit),
        "author": str(post.author),
        "score": post.score
    }

def extract_comment(comment):
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
        "parent_id": comment.parent_id
    }

def backfill():
    print("🔁 Backfilling posts...")
    for post in reddit.subreddit("all").search("badinka", sort="new", time_filter=TIME_FILTER):
        if post.id not in seen_ids:
            text = f"{post.title or ''} {post.selftext or ''}"
            if KEYWORD_PATTERN.search(text):
                new_mentions.append(extract_post(post))
                seen_ids.add(post.id)
                print(f"🧵 Post: {post.permalink}")

    print("🔁 Backfilling comments...")
    for comment in reddit.subreddit("all").search("badinka", sort="new", time_filter=TIME_FILTER):
        if comment.id not in seen_ids and hasattr(comment, "body"):
            if KEYWORD_PATTERN.search(comment.body or ""):
                new_mentions.append(extract_comment(comment))
                seen_ids.add(comment.id)
                print(f"💬 Comment: {comment.permalink}")

    if new_mentions:
        send_to_dashboard(new_mentions)
    else:
        print("ℹ️ No new mentions found.")

if __name__ == "__main__":
    print("📦 Starting backfill...")
    backfill()
