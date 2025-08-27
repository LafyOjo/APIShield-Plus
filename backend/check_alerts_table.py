import sqlite3

conn = sqlite3.connect("app.db")
cursor = conn.cursor()

cursor.execute("SELECT id, ip_address, total_fails, detail, timestamp FROM alerts;")
rows = cursor.fetchall()

print("Current alerts:")
print("ID | IP Address | Total Fails | Detail | Timestamp")
for row in rows:
    print(" | ".join(str(item) for item in row))

conn.close()
