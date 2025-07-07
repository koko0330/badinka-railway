import praw
import os
import re
import requests
from datetime import datetime, timezone
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from scipy.special import softmax

# === Reddit API ===
reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBackfill/0.1 by ConfectionInfamous97"
)

# === Config ===
KEYWORD = "trump"
KEYWORD_PATTERN = re.compile(r'[@#]?\b(trump)(?:\.com)?\b', re.IGNORECASE)
DASHBOARD_URL = os.getenv("RENDER_UPDATE_URL", "https://badinka-monitor.onrender.com/update")
TIME_FILTER = "day"

# === Transformers Sentiment Model ===
tokenizer = AutoTokenizer.from_pretrained("cardiffnlp/twitter-roberta-base-sentiment")
model = AutoModelForSequenceClassification.from_pretrained("cardiffnlp/twitter-roberta-base-sentiment")

def analyze_sentiment(text):
    try:
        encoded_input = tokenizer(text, return_tensors='pt', truncation=True)
        output = model(**encoded_input)
        scores = softmax(output.logits.detach().numpy()[0])
        labels = ['negative', 'neutral', 'positive']
        return labels[scores.argmax()]
    except Exception as e:
        print(f"Sentiment analysis failed: {e}")
        return "neutral"

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
    text = f"{post.title or ''} {post.selftext or ''}"
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
        "sentiment": analyze_sentiment(text)
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
        "parent_id": comment.parent_id,
        "sentiment": analyze_sentiment(comment.body)
    }

def backfill():
    seen_ids = set()
    new_mentions = []

    print("🔁 Backfilling posts...")
    for post in reddit.subreddit("all").search("badinka", sort="new", time_filter=TIME_FILTER):
        if post.id not in seen_ids:
            text = f"{post.title or ''} {post.selftext or ''}"
            if KEYWORD_PATTERN.search(text):
                data = extract_post(post)
                new_mentions.append(data)
                seen_ids.add(post.id)
                print(f"🧵 Post: {data['permalink']} | Sentiment: {data['sentiment']}")

    print("🔁 Backfilling comments...")
    for comment in reddit.subreddit("all").search("badinka", sort="new", time_filter=TIME_FILTER)
