import os
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.getenv("postgresql://reddit_mentions_db_user:Lq2m8OwpYXH8DnTIJW6aiLqBJSLt9pGR@dpg-d1lrk9ffte5s73dsqc70-a.oregon-postgres.render.com/reddit_mentions_db")

def insert_mention(data_list):
    if not data_list:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    rows = [
        (
            item["id"],
            item["type"],
            item.get("title"),
            item.get("body"),
            item["permalink"],
            item["created"],
            item["subreddit"],
            item["author"],
            item["score"],
            item["sentiment"]
        )
        for item in data_list
    ]

    query = """
        INSERT INTO mentions (id, type, title, body, permalink, created, subreddit, author, score, sentiment)
        VALUES %s
        ON CONFLICT (id) DO NOTHING;
    """

    execute_values(cur, query, rows)
    conn.commit()
    cur.close()
    conn.close()
