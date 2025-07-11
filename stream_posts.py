import praw
import time
import re
from datetime import datetime, timezone
import markdown
from bs4 import BeautifulSoup
from shared_config import insert_mention
import prawcore  # ✅ Needed to catch 429 TooManyRequests

# === Reddit API ===
reddit = praw.Reddit(
    client_id="ILsQFrHHbPkIyTR_CKu2Dw",
    client_secret="	KfrgQRv9Eb23jBYbFpT1cWzD97jWOQ",
    user_agent="InterestsScanner/0.1 by Relevant-Maybe3472"
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


def extract_post(submission, brand):
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
        "sentiment": None,
        "brand": brand
    }


def main():
    print("🚀 Post stream worker started...")
    subreddit = reddit.subreddit("all")

    # ✅ Retry loop for rate-limited stream setup
    while True:
        try:
            post_stream = subreddit.stream.submissions()
            break  # success
        except prawcore.exceptions.TooManyRequests:
            print("⏳ Rate limited when starting post stream. Waiting 60 seconds...")
            time.sleep(60)

    last_push = time.time()

    for post in post_stream:
        try:
            if post.id not in SEEN_IDS:
                text = f"{post.title or ''} {post.selftext or ''}"
                for brand in find_brands(text):
                    m = extract_post(post, brand)
                    COLLECTED.append(m)
                    SEEN_IDS.add(post.id)
                    print(f"🧵 Post: {m['permalink']} | Brand: {brand}")
        except Exception:
            continue

        now = time.time()
        if now - last_push > POST_INTERVAL and COLLECTED:
            try:
                insert_mention(COLLECTED)
                print(f"✅ Stored {len(COLLECTED)} posts in DB.")
                COLLECTED.clear()
                last_push = now
            except Exception as e:
                print(f"❌ Failed to store posts: {e}")


if __name__ == "__main__":
    main()

