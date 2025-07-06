import praw
import os
import re
import requests
import time
from datetime import datetime, timezone

# === Reddit API ===
reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBackfill/0.1 by ConfectionInfamous97"
)

# === Config ===
KEYWORD = "badinka"
re.compile(r'[@#]?\b(badinka)(\.com)?\b', re.IGNORECASE)
DASHBOARD_URL = os.getenv("RENDER_UPDATE_URL", "https://badinka-monitor.onrender.com/update")

# Track seen results to avoid resending
SEEN_IDS_FILE = "seen_ids.txt"
seen_ids = set()

if os.path.exists(SEEN_IDS_FILE):
    with open(SEEN_IDS_FILE, "r") as f:
        seen_ids = set(line.strip() for line in f)

def save_seen_ids():
    with open(SEEN_IDS_FILE, "w") as f:
        for _id in seen_ids:
            f.write(_id + "\n")

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

def main():
    new_mentions = []

    print("🔍 Polling Reddit search for recent comments with keyword...")

    for comment in reddit.subreddit("all").search(KEYWORD, sort="new", syntax="lucene", time_filter="day"):
        if comment.id not in seen_ids and hasattr(comment, "body"):
            if KEYWORD_PATTERN.search(comment.body):
                data = extract_comment(comment)
                new_mentions.append(data)
                seen_ids.add(comment.id)
                print(f"📥 Found: {data['permalink']}")

    if new_mentions:
        try:
            response = requests.post(DASHBOARD_URL, json=new_mentions)
            if response.ok:
                print(f"✅ Sent {len(new_mentions)} new mentions to dashboard")
            else:
                print(f"❌ Failed to send data: {response.status_code}")
        except Exception as e:
            print(f"❌ Error sending data: {e}")

        save_seen_ids()
    else:
        print("ℹ️ No new mentions found.")

if __name__ == "__main__":
    main()
