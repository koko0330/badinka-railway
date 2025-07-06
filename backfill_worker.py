import praw
import os
import re
import requests
from datetime import datetime, timezone

# === Reddit API Setup ===
reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBackfill/0.1 by ConfectionInfamous97"
)

# === Config ===
KEYWORD_PATTERN = re.compile(r'[@#]?(badinka)(?:\.com)?', re.IGNORECASE)
DASHBOARD_URL = os.getenv("RENDER_UPDATE_URL", "https://badinka-monitor.onrender.com/update")

seen_ids = set()  # In-memory deduplication only for the current run

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

def extract_post(submission):
    return {
        "type": "post",
        "id": submission.id,
        "title": submission.title,
        "body": submission.selftext,
        "permalink": f"https://reddit.com{submission.permalink}",
        "created": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
        "subreddit": str(submission.subreddit),
        "author": str(submission.author),
        "score": submission.score
    }

def main():
    new_mentions = []

    print("🔍 Searching Reddit for recent posts and comments...")

    # Search both posts and comments using the Reddit search API
    for item in reddit.subreddit("all").search("badinka", sort="new", syntax="lucene", time_filter="day"):
        if item.id not in seen_ids:
            try:
                if hasattr(item, "body"):
                    if KEYWORD_PATTERN.search(item.body):
                        data = extract_comment(item)
                        new_mentions.append(data)
                        print(f"💬 Comment match: {data['permalink']}")
                elif hasattr(item, "title") and hasattr(item, "selftext"):
                    combined = f"{item.title} {item.selftext or ''}"
                    if KEYWORD_PATTERN.search(combined):
                        data = extract_post(item)
                        new_mentions.append(data)
                        print(f"🧵 Post match: {data['permalink']}")
                seen_ids.add(item.id)
            except Exception as e:
                print(f"⚠️ Skipping item due to error: {e}")

    # Send matches to dashboard
    if new_mentions:
        try:
            response = requests.post(DASHBOARD_URL, json=new_mentions)
            if response.ok:
                print(f"✅ Sent {len(new_mentions)} new mentions to dashboard.")
            else:
                print(f"❌ Failed to send data: {response.status_code}")
        except Exception as e:
            print(f"❌ Error during dashboard sync: {e}")
    else:
        print("ℹ️ No new mentions found.")

if __name__ == "__main__":
    main()
