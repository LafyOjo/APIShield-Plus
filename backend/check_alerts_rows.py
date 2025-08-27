# check_alerts_rows.py

import sqlite3

conn = sqlite3.connect("app.db")
cursor = conn.cursor()

print("Current alerts:")
print("ID | IP Address | Total Fails | Detail | Timestamp")
for row in cursor.execute(
    "SELECT id, ip_address, total_fails, detail, timestamp "
    "FROM alerts ORDER BY timestamp DESC"
):
    print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]}")

conn.close()
