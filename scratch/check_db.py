import sqlite3
import os

db_path = "attendance_system.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(students)")
    cols = cursor.fetchall()
    print("Students Columns:")
    for c in cols:
        print(c)
    
    cursor.execute("SELECT * FROM students WHERE is_active=1 LIMIT 5")
    rows = cursor.fetchall()
    if rows:
        print("\nSample Rows (Indices Check):")
        for row in rows:
            print("-" * 20)
            for i, val in enumerate(row):
                if i < len(cols):
                    print(f"{i}: {val} (Col: {cols[i][1]})")
                else:
                    print(f"{i}: {val} (Col: UNKNOWN)")
    conn.close()
else:
    print(f"DB not found at {os.path.abspath(db_path)}")
