import sqlite3
import os

PROJECT_ROOT = "/home/ghost/face-recognition/face_recognition"
DB_PATH = os.path.join(PROJECT_ROOT, "attendance_system.db")

def clear_classes():
    if not os.path.exists(DB_PATH):
        print("Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Delete all records from the classes table
        cursor.execute("DELETE FROM classes")
        # Reset the auto-increment counter for the classes table
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='classes'")
        conn.commit()
        print("Successfully removed all data from the 'classes' table.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    clear_classes()
