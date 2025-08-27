
import sqlite3
from collections import defaultdict

DB_PATH = "backend/app.db"

# Overall stats
overall_queries = {
    "Total credential stuffing attempts": "SELECT COUNT(*) FROM events WHERE action = 'stuffing_attempt';",
    "Blocked credential stuffing attempts": "SELECT COUNT(*) FROM events WHERE action = 'stuffing_block';",
}

# Per-user login stats
user_login_queries = {
    "Total login attempts": "SELECT username, COUNT(*) FROM events WHERE action = 'login' GROUP BY username;",
    "Successful logins": "SELECT username, COUNT(*) FROM events WHERE action = 'login' AND success = 1 GROUP BY username;",
    "Failed logins": "SELECT username, COUNT(*) FROM events WHERE action = 'login' AND success = 0 GROUP BY username;",
}

# Per-user stuffing stats
user_stuffing_query = "SELECT username, COUNT(*) FROM events WHERE action = 'stuffing_attempt' GROUP BY username;"


conn = None
try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("--- Overall Credential Stuffing Stats ---")
    for description, query in overall_queries.items():
        cursor.execute(query)
        result = cursor.fetchone()[0]
        print(f"{description}: {result}")

    print("\n--- Credential Stuffing Attempts by User ---")
    cursor.execute(user_stuffing_query)
    rows = cursor.fetchall()
    if not rows:
        print("No stuffing attempt data found for any user.")
    else:
        for row in rows:
            username, count = row
            if username:
                print(f"  {username}: {count} attempts")


    print("\n--- Login Attempt Stats by User ---")
    user_stats = defaultdict(lambda: {"Total login attempts": 0, "Successful logins": 0, "Failed logins": 0})

    for description, query in user_login_queries.items():
        cursor.execute(query)
        rows = cursor.fetchall()
        for row in rows:
            username, count = row
            if username:
                user_stats[username][description] = count

    for username, stats in user_stats.items():
        print(f"\nUser: {username}")
        for desc, count in stats.items():
            print(f"  {desc}: {count}")

except sqlite3.Error as e:
    print(f"Database error: {e}")
    print(f"Please ensure the database file exists at '{DB_PATH}'")
finally:
    if conn:
        conn.close()

