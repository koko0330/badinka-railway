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


def json_poll_comments():
    print("📡 JSON comment poller started...")
    base_url = f"https://www.reddit.com/r/{'+'.join(SUBREDDITS)}/comments.json?limit=100"
    headers = {"User-Agent": "BrandMentionBackfill/0.1 by ConfectionInfamous97"}

    while True:
        try:
            response = requests.get(base_url, headers=headers, timeout=10)
            if response.status_code == 429:
                print("⚠️ JSON polling error: 429 Too Many Requests — backing off.")
                time.sleep(30)
                continue

            response.raise_for_status()
            data = response.json()
            children = data.get("data", {}).get("children", [])
            for item in children:
                c = item.get("data", {})
                if not c or c["id"] in SEEN_IDS:
                    continue
                body = c.get("body", "")
                for brand in find_brands(body):
                    m = {
                        "type": "comment",
                        "id": c["id"],
                        "body": c["body"],
                        "permalink": f"https://reddit.com{c['permalink']}",
                        "created": datetime.fromtimestamp(c["created_utc"], tz=timezone.utc).isoformat(),
                        "subreddit": c["subreddit"],
                        "author": c["author"],
                        "score": c["score"],
                        "link_id": c["link_id"],
                        "parent_id": c["parent_id"],
                        "sentiment": None,
                        "brand": brand
                    }
                    COLLECTED.append(m)
                    SEEN_IDS.add(c["id"])
        except Exception as e:
            print(f"❌ JSON polling error: {e}")
        time.sleep(15)


def main():
    print("🎯 Focused subreddit worker started...")
    threading.Thread(target=json_poll_comments, daemon=True).start()

    post_stream = subreddit.stream.submissions(skip_existing=True)
    comment_stream = subreddit.stream.comments(skip_existing=True)
    last_flush = time.time()

    while True:
        now = time.time()

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

        try:
            comment = next(comment_stream)
            if comment.id not in SEEN_IDS:
                for brand in find_brands(comment.body):
                    m = extract_comment(comment, brand)
                    COLLECTED.append(m)
                    SEEN_IDS.add(comment.id)
                    print(f"💬 Comment: {m['permalink']} | Brand: {brand}")
        except Exception:
            pass

        if now - last_flush > FLUSH_INTERVAL and COLLECTED:
            try:
                insert_mention(COLLECTED)
                print(f"✅ Stored {len(COLLECTED)} mentions in DB.")
                COLLECTED.clear()
                last_flush = now
            except Exception as e:
                print(f"❌ Failed to insert to DB: {e}")


if __name__ == "__main__":
    main()
