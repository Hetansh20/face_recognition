"""
seed_db.py  —  Run once on first boot to populate a fresh DB.
Called automatically from app.py if the DB is empty.
"""

import sqlite3, json, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "attendance_system.db")
FACE_DB  = os.path.join(BASE_DIR, "face_database.json")

# ──────────────────────────────────────────────────────────────────
# SEED DATA  —  generated from local DB snapshot
# ──────────────────────────────────────────────────────────────────

FACULTIES = [
    # (name, email, department, passcode)
    # Add your real faculty records here — passcode is hashed by auth.py
    # These are placeholders; update via Admin → Faculty after first boot
]

SEMESTERS = [
    # (id, number, label, level)
    (1, 6, "Semester 6", "Degree"),
    (2, 4, "Semester 4", "Degree"),
    (3, 2, "Semester 2", "Degree"),
]

# (id, semester_id, name)
CLASSES = [
    (1, 1, "EK1"),
    (2, 1, "EK2"),
    (3, 2, "EK1"),
    (4, 2, "EK2"),
    (5, 2, "EK3"),
    (6, 3, "EK1"),
]

# (id, class_id, name)
BATCHES = [
    (1, 1, "A"),
    (2, 1, "B"),
    (3, 1, "C"),
    (4, 2, "A"),
    (5, 2, "B"),
    (6, 3, "A"),
    (7, 3, "B"),
    (8, 3, "C"),
    (9, 4, "A"),
    (10, 4, "B"),
    (11, 5, "A"),
    (12, 5, "B"),
    (13, 5, "C"),
    (14, 6, "1A"),
    (15, 6, "1B"),
]


def _load_students_from_face_db():
    """
    Build student rows from face_database.json which has been enriched
    with gr_number, class, batch, semester by the import script.
    """
    if not os.path.exists(FACE_DB):
        return []
    with open(FACE_DB) as f:
        face_db = json.load(f)

    # Map (sem, class_name, batch_name) -> class_id / batch_id
    sem_map   = {s[1]: s[0] for s in SEMESTERS}   # number -> id
    class_map = {}   # (sem_id, name) -> class_id
    batch_map = {}   # (class_id, name) -> batch_id
    for cid, sid, cname in CLASSES:
        class_map[(sid, cname)] = cid
    for bid, cid, bname in BATCHES:
        batch_map[(cid, bname)] = bid

    students = []
    for pid, info in face_db.items():
        gr  = info.get("gr_number") or info.get("employee_id", "")
        if not gr:
            continue
        name      = info.get("name", pid.replace("_", " ").title())
        sem_num   = info.get("semester")
        cls_name  = (info.get("class") or "").strip()
        bat_name  = (info.get("batch") or "").strip()

        sem_id   = sem_map.get(sem_num)
        class_id = class_map.get((sem_id, cls_name)) if sem_id else None
        batch_id = batch_map.get((class_id, bat_name)) if class_id else None

        students.append((
            gr,                      # gr_number
            gr,                      # enrollment_number (same until updated)
            name,
            f"{gr}@student.edu",    # placeholder email
            "ICT",                   # department
            class_id,
            batch_id,
            gr,                      # roll_number placeholder
            pid,                     # face_pid
            gr,                      # student_id
        ))
    return students


def seed(conn):
    cur = conn.cursor()

    # ── Semesters ────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM semesters")
    if cur.fetchone()[0] == 0:
        for sid, num, label, level in SEMESTERS:
            cur.execute(
                "INSERT OR IGNORE INTO semesters (id, number, label, level) VALUES (?,?,?,?)",
                (sid, num, label, level)
            )
        print(f"[seed] Inserted {len(SEMESTERS)} semesters")

    # ── Classes ───────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM classes")
    if cur.fetchone()[0] == 0:
        for cid, sid, name in CLASSES:
            cur.execute(
                "INSERT OR IGNORE INTO classes (id, semester_id, name, section) VALUES (?,?,?,?)",
                (cid, sid, name, name)
            )
        print(f"[seed] Inserted {len(CLASSES)} classes")

    # ── Batches ───────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM batches")
    if cur.fetchone()[0] == 0:
        for bid, cid, name in BATCHES:
            cur.execute(
                "INSERT OR IGNORE INTO batches (id, class_id, name) VALUES (?,?,?)",
                (bid, cid, name)
            )
        print(f"[seed] Inserted {len(BATCHES)} batches")

    # ── Students ──────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM students")
    if cur.fetchone()[0] == 0:
        students = _load_students_from_face_db()
        for s in students:
            cur.execute("""
                INSERT OR IGNORE INTO students
                    (gr_number, enrollment_number, name, email, department,
                     class_id, batch_id, roll_number, face_pid, student_id, is_active)
                VALUES (?,?,?,?,?,?,?,?,?,?,1)
            """, s)
        print(f"[seed] Inserted {len(students)} students from face_database.json")

    conn.commit()
    print("[seed] Database seeded successfully.")


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    seed(conn)
    conn.close()
