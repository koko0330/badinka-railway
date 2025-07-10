import praw
import time
import re
import os
import threading
import requests
from datetime import datetime, timezone
import markdown
from bs4 import BeautifulSoup
from shared_config import insert_mention

# === Reddit API ===
reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBackfill/0.1 by ConfectionInfamous97"
)

# === Subreddits to monitor ===
SUBREDDITS = [
    "Rezz", "aves", "ElectricForest", "sewing", "avesfashion",
    "cyber_fashion", "aveoutfits", "RitaFourEssenceSystem", "SoftDramatics",
    "avesNYC", "TorontoRaves", "poledancing", "veld", "BADINKA", "PlusSize",
    "LostLandsMusicFest", "festivals", "avefashion", "avesafe", "EDCOrlando",
    "findfashion", "BassCanyon", "Aerials", "electricdaisycarnival", "bonnaroo",
    "Tomorrowland", "femalefashion", "Soundhaven", "warpedtour", "Shambhala",
    "Lollapalooza", "EDM", "BeyondWonderland", "welcometorockville", "Coachella"
]

subreddit = reddit.subreddit("+".join(SUBREDDITS))

# === Brand matchers ===
BRANDS = {
    "badinka": re.compile(r'[@#]?badinka(?:\.com)?', re.IGNORECASE),
    "iheartraves": re.compile(r'[@#]?iheartraves(?:\.com)?', re.IGNORECASE),
}

SEEN_IDS = set()
COLLECTED = []
FLUSH_INTERVAL = 30

# === Utilities ===
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

# === JSON Comment Poller ===
def poll_json_comments():
    print("📡 JSON comment poller started...")
    LAST_SEEN = set()
    headers = {"User-Agent": "KeywordWatcher/1.0"}
    url = f"https://www.reddit.com/r/{'+'.join(SUBREDDITS)}/comments.json?limit=100"

    while True:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            data = res.json()

            for item in data["data"]["children"]:
                comment = item["data"]
                cid = comment["id"]
                body = comment.get("body", "")
                if cid in SEEN_IDS or cid in LAST_SEEN:
                    continue

                LAST_SEEN.add(cid)
                for brand in find_brands(body):
                    m = {
                        "type": "comment",
                        "id": cid,
                        "body": body,
                        "permalink": f"https://reddit.com{comment['permalink']}",
                        "created": datetime.fromtimestamp(comment["created_utc"], tz=timezone.utc).isoformat(),
                        "subreddit": comment["subreddit"],
                        "author": comment.get("author"),
                        "score": comment.get("score", 0),
                        "link_id": comment.get("link_id", ""),
                        "parent_id": comment.get("parent_id", ""),
                        "sentiment": None,
                        "brand": brand
                    }
                    COLLECTED.append(m)
                    print(f"🌐 JSON Poller: {m['permalink']} | Brand: {brand}")
        except Exception as e:
            print(f"❌ JSON polling error: {e}")
        time.sleep(2)

# === Main Loop ===
def main():
    post_stream = subreddit.stream.submissions(skip_existing=True)
    comment_stream = subreddit.stream.comments(skip_existing=True)
    last_flush = time.time()

    while True:
        now = time.time()

        # Handle posts
        try:
            post = next(post_stream)
            if post.id not in SEEN_IDS:
                text = f"{post.title or ''} {post.selftext or ''}"
                for brand in find_brands(text):
                    m = extract_post(post, brand)
                    COLLECTED.append(m)
                    SEEN_IDS.add(post.id)
                    print(f"🧵 Post: {m['permalink']} | Brand: {brand}")
        except Exception:
            pass

        # Handle comments
        try:
            comment = next(comment_stream)

            print(f"🔗 Link: https://reddit.com{comment.permalink}")
            print(f"📝 Body: {comment.body[:1000]}...\n")

            if comment.id not in SEEN_IDS:
                for brand in find_brands(comment.body):
                    m = extract_comment(comment, brand)
                    COLLECTED.append(m)
                    SEEN_IDS.add(comment.id)
                    print(f"💬 Comment: {m['permalink']} | Brand: {brand}")
        except Exception:
            pass

        # Flush to DB
        if now - last_flush > FLUSH_INTERVAL and COLLECTED:
            try:
                insert_mention(COLLECTED)
                print(f"✅ Stored {len(COLLECTED)} mentions in DB.")
                COLLECTED.clear()
                last_flush = now
            except Exception as e:
                print(f"❌ Failed to insert to DB: {e}")

# === Entry Point ===
if __name__ == "__main__":
    print("🎯 Focused subreddit worker started...")

    # Start JSON polling in background thread
    threading.Thread(target=poll_json_comments, daemon=True).start()

    # Start main PRAW stream
    main()
