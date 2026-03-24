import sqlite3
import os

db_file = r"c:\Uma\UmapyoiBot\bot_data.db"

if not os.path.exists(db_file):
    print(f"Error: {db_file} not found.")
    exit(1)

conn = sqlite3.connect(db_file)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

def check_table(table_name):
    try:
        cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        row = cursor.fetchone()
        print(f"Table '{table_name}' has {row['count']} rows.")
    except Exception as e:
        print(f"Error checking table '{table_name}': {e}")

print("\nRecent User Feedback (last 5):")
try:
    cursor.execute("SELECT user_id, type, subject, timestamp FROM user_feedback ORDER BY timestamp DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(dict(row))
except Exception as e:
    print(f"Error: {e}")

print("\nRecent Level Updates:")
try:
    cursor.execute("SELECT user_id, level, xp FROM levels ORDER BY xp DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(dict(row))
except Exception as e:
    print(f"Error: {e}")

conn.close()
