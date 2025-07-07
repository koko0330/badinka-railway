import praw
import time
import re
import os
import requests
from datetime import datetime, timezone
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from scipy.special import softmax

# === Reddit API Credentials from Railway Variables ===
reddit = praw.Reddit(
    client_id="z12aa_E8kaHr_vC9LL6xCw",
    client_secret="AfCarYADJDQ2MU3rdIUW1KjMDRvSrw",
    user_agent="BrandMentionBot/0.1 by ConfectionInfamous97"
)

# === Config ===
KEYWORD_PATTERN = re.compile(r'[@#]?trump(?:\.com)?', re.IGNORECASE)
SEEN_IDS = set()
COLLECTED = []
POST_INTERVAL = 60
DASHBOARD_URL = os.getenv("RENDER_UPDATE_URL", "https://badinka-monitor.onrender.com/update")

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
            print(f"✅ Synced {len(data)} mentions to dashboard.")
        else:
            print(f"❌ Sync failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Exception during sync: {e}")

def extract_post(submission):
    text = f"{submission.title} {submission.selftext}"
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
                    print(f"🧵 Post: {data['permalink']} | Sentiment: {data['sentiment']}")
        except Exception:
            pass

        try:
            comment = next(comment_stream)
            if comment.id not in SEEN_IDS:
                if KEYWORD_PATTERN.search(comment.body):
                    data = extract_comment(comment)
                    COLLECTED.append(data)
                    SEEN_IDS.add(comment.id)
                    print(f"💬 Comment: {data['permalink']} | Sentiment: {data['sentiment']}")
        except Exception:
            pass

        if now - last_push > POST_INTERVAL and COLLECTED:
            send_to_dashboard(COLLECTED)
            COLLECTED.clear()
            last_push = now

if __name__ == "__main__":
    main()
