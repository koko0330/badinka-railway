import praw
import time
import re
from datetime import datetime, timezone
import markdown
from bs4 import BeautifulSoup
from shared_config import insert_mention
import prawcore
from bs4 import XMLParsedAsHTMLWarning
import warnings
import random

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# === Reddit API ===
reddit = praw.Reddit(
    client_id="3VI1QspELmEQ96bKo6C3BQ",
    client_secret="yeoMoHX2b9pNAemTLxtpgBBuFY7uaQ",
    user_agent="BrandMention/0.1 by Disastrous-Sun2226"
)

# === Brand patterns ===
BRANDS = {
    "badinka": re.compile(r'[@#]?badinka(?:\.com)?', re.IGNORECASE),
    "iheartraves": re.compile(r'[@#]?iheartraves(?:\.com)?', re.IGNORECASE),
}

SEEN_IDS = set()
COLLECTED = []
POST_INTERVAL = 30  # seconds


def extract_links(text):
    try:
        html = markdown.markdown(text)
        soup = BeautifulSoup(html, "html.parser")
        return [a.get("href") for a in soup.find_all("a") if a.get("href")]
    except Exception:
        return []


def find_brands(text):
    brands_found = set()
    for brand, pattern in BRANDS.items():
        if pattern.search(text):
            brands_found.add(brand)
    for link in extract_links(text):
        for brand, pattern in BRANDS.items():
            if pattern.search(link):
                brands_found.add(brand)
    return list(brands_found)


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
        "sentiment": None,
        "brand": brand
    }


def stream_worker():
    subreddit = reddit.subreddit("all")
    comment_stream = subreddit.stream.comments(pause_after=5)

    last_push = time.time()

    for comment in comment_stream:
        if comment is None:
            time.sleep(3)  # light pause to avoid rapid cycling
            continue

        try:
            if comment.id not in SEEN_IDS:
                for brand in find_brands(comment.body):
                    m = extract_comment(comment, brand)
                    COLLECTED.append(m)
                    SEEN_IDS.add(comment.id)
                    print(f"💬 Comment: {m['permalink']} | Brand: {brand}")
        except Exception as e:
            print(f"⚠️ Failed to process comment: {e}")
            continue

        now = time.time()
        if now - last_push > POST_INTERVAL and COLLECTED:
            try:
                insert_mention(COLLECTED)
                print(f"✅ Stored {len(COLLECTED)} comments in DB.")
                COLLECTED.clear()
                last_push = now
            except Exception as e:
                print(f"❌ Failed to store comments: {e}")


def main():
    print("🚀 Comment stream worker started...")

    while True:
        try:
            stream_worker()
        except prawcore.exceptions.TooManyRequests:
            print("⏳ Rate limited during streaming. Waiting 60 seconds...")
            time.sleep(60)
        except prawcore.exceptions.ServerError as e:
            backoff = random.randint(60, 120)
            print(f"⚠️ Reddit server error (500): {e}. Cooling down for {backoff} seconds...")
            time.sleep(backoff)
        except Exception as e:
            backoff = random.randint(20, 45)
            print(f"⚠️ Unexpected error in stream loop: {e}. Waiting {backoff} seconds before retrying.")
            time.sleep(backoff)


if __name__ == "__main__":
    main()
