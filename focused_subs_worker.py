import praw
import time
import re
import os
import requests
from datetime import datetime, timezone
import markdown
from bs4 import BeautifulSoup
from shared_config import insert_mention
import threading

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
    "badinka": re.compile(r'[@#]?badinka(?:\\.com)?', re.IGNORECASE),
    "iheartraves": re.compile(r'[@#]?iheartraves(?:\\.com)?', re.IGNORECASE),
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
    print("\ud83d\udce1 JSON comment poller started...")
    headers = {"User-Agent": "BrandMentionBackfill/0.1 by ConfectionInfamous97"}
    seen_json_ids = set()
    chunk_size = 5
    delay_between_chunks = 10  # seconds

    while True:
        for i in range(0, len(SUBREDDITS), chunk_size):
            chunk = SUBREDDITS[i:i + chunk_size]
            chunk_str = "+".join(chunk)
            url = f"https://www.reddit.com/r/{chunk_str}/comments.json?limit=100"

            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 429:
                    print(f"\u26a0\ufe0f 429 Too Many Requests on chunk: {chunk_str}")
                    time.sleep(30)
                    continue

                response.raise_for_status()
                data = response.json()
                children = data.get("data", {}).get("children", [])

                for item in children:
                    c = item.get("data", {})
                    cid = c.get("id")
                    if not c or cid in SEEN_IDS or cid in seen_json_ids:
                        continue
                    body = c.get("body", "")
                    for brand in find_brands(body):
                        m = {
                            "type": "comment",
                            "id": cid,
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
                        seen_json_ids.add(cid)
                        SEEN_IDS.add(cid)

            except Exception as e:
                print(f"\u274c JSON polling error for chunk {chunk_str}: {e}")

            time.sleep(delay_between_chunks)


def main():
    comment_stream = subreddit.stream.comments(skip_existing=True)
    last_flush = time.time()

    # Start JSON poller thread
    threading.Thread(target=json_poll_comments, daemon=True).start()

    print("\ud83c\udfaf Focused subreddit worker started...")

    while True:
        now = time.time()

        # Handle comments from stream
        try:
            comment = next(comment_stream)
            if comment.id not in SEEN_IDS:
                for brand in find_brands(comment.body):
                    m = extract_comment(comment, brand)
                    COLLECTED.append(m)
                    SEEN_IDS.add(comment.id)
                    print(f"\ud83d\udcac Comment: {m['permalink']} | Brand: {brand}")
        except Exception:
            pass

        # Flush to DB
        if now - last_flush > FLUSH_INTERVAL and COLLECTED:
            try:
                insert_mention(COLLECTED)
                print(f"\u2705 Stored {len(COLLECTED)} mentions in DB.")
                COLLECTED.clear()
                last_flush = now
            except Exception as e:
                print(f"\u274c Failed to insert to DB: {e}")


if __name__ == "__main__":
    main()
