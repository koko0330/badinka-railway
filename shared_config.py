import os
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

def get_existing_mention_ids():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id FROM mentions")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return set(row[0] for row in rows)

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
            item["sentiment"],
            item["brand"]
        )
        for item in data_list
    ]

    query = """
        INSERT INTO mentions (
            id, type, title, body, permalink, created, subreddit, author, score, sentiment, brand
        ) VALUES %s
        ON CONFLICT (id) DO NOTHING;
    """

    execute_values(cur, query, rows)
    conn.commit()
    cur.close()
    conn.close()
