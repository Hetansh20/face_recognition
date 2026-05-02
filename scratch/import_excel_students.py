"""
import_excel_students.py
========================
Imports students from 'Student details for AI project.xlsx' into the attendance DB.
- Creates Semester 2 / Class EK1 / Batch 1A, 1B if not already present
- Inserts each student (upserts by GR number)
- Links each student to their face_database.json entry (NAME_GRNO key)
- Updates face_database.json with gr_number as employee_id

Run from the project root:
    python scratch/import_excel_students.py
"""

import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "attendance_system.db")
FACE_DB  = os.path.join(BASE_DIR, "face_database.json")
EXCEL    = os.path.join(BASE_DIR, "Student details for AI project.xlsx")

# ── Load Excel ──────────────────────────────────────────────────────────────
df = pd.read_excel(EXCEL)
df.columns = [c.strip() for c in df.columns]
for col in df.columns:
    if df[col].dtype == object:
        df[col] = df[col].astype(str).str.strip()

print(f"Loaded {len(df)} students from Excel")
print(f"Columns: {df.columns.tolist()}")
print(f"Semesters: {df['Semester'].unique()}")
print(f"Classes:   {df['Class'].unique()}")
print(f"Batches:   {df['Lab Batch'].unique()}")

# ── Load Face DB ────────────────────────────────────────────────────────────
with open(FACE_DB, "r") as f:
    face_db = json.load(f)

def find_face_pid(gr_number, name):
    """Find the face_database.json key that matches this student."""
    gr_str = str(gr_number)
    # Direct match: key ends with _GRNO
    for pid, info in face_db.items():
        if pid.endswith(f"_{gr_str}"):
            return pid
    # Fallback: match by name similarity
    clean_name = re.sub(r'\s+', '_', name.strip().upper())
    for pid in face_db:
        if clean_name in pid or pid.startswith(clean_name[:8]):
            return pid
    return None

# ── Connect to DB ───────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur  = conn.cursor()

# ── Ensure Semester 2 exists ────────────────────────────────────────────────
cur.execute("SELECT id FROM semesters WHERE number=2")
row = cur.fetchone()
if row:
    sem_id = row[0]
    print(f"Semester 2 already exists: id={sem_id}")
else:
    cur.execute("INSERT INTO semesters (number, label, level) VALUES (2, 'Semester 2', 'Degree')")
    sem_id = cur.lastrowid
    print(f"Created Semester 2: id={sem_id}")

# ── Ensure Class EK1 exists ─────────────────────────────────────────────────
cur.execute("SELECT id FROM classes WHERE semester_id=? AND name='EK1'", (sem_id,))
row = cur.fetchone()
if row:
    class_id = row[0]
    print(f"Class EK1 already exists: id={class_id}")
else:
    cur.execute("INSERT INTO classes (semester_id, name, section) VALUES (?,?,?)", (sem_id, "EK1", "EK1"))
    class_id = cur.lastrowid
    print(f"Created Class EK1: id={class_id}")

# ── Ensure Batches 1A and 1B exist ──────────────────────────────────────────
batch_ids = {}
for bname in ["1A", "1B"]:
    cur.execute("SELECT id FROM batches WHERE class_id=? AND name=?", (class_id, bname))
    row = cur.fetchone()
    if row:
        batch_ids[bname] = row[0]
        print(f"Batch {bname} already exists: id={row[0]}")
    else:
        cur.execute("INSERT INTO batches (class_id, name) VALUES (?,?)", (class_id, bname))
        batch_ids[bname] = cur.lastrowid
        print(f"Created Batch {bname}: id={batch_ids[bname]}")

conn.commit()

# ── Insert / Update Students ─────────────────────────────────────────────────
inserted = 0
updated  = 0
linked   = 0
skipped  = 0

for _, row in df.iterrows():
    gr_number   = str(int(float(row["GR NO"])))
    roll_number = str(row["Roll No"]).strip()
    name        = str(row["Student Name"]).strip()
    semester_raw= str(row["Semester"]).strip()
    class_name  = str(row["Class"]).strip()
    batch_raw   = str(row["Lab Batch"]).strip()  # "1A" or "1B"

    department  = "ICT"
    email       = f"{gr_number}@ek1.edu"          # placeholder email
    enrollment  = roll_number

    batch_key   = batch_raw.strip()  # "1A" or "1B"
    bid         = batch_ids.get(batch_key)

    # Find face_pid
    face_pid = find_face_pid(gr_number, name)

    # Check if student already exists
    cur.execute("SELECT id FROM students WHERE gr_number=?", (gr_number,))
    existing = cur.fetchone()

    if existing:
        stu_db_id = existing[0]
        cur.execute("""
            UPDATE students
            SET name=?, enrollment_number=?, department=?,
                class_id=?, batch_id=?, roll_number=?, face_pid=?
            WHERE id=?
        """, (name, enrollment, department, class_id, bid, roll_number, face_pid, stu_db_id))
        updated += 1
    else:
        try:
            cur.execute("""
                INSERT INTO students
                    (gr_number, enrollment_number, name, email, department,
                     class_id, batch_id, roll_number, face_pid, student_id, is_active)
                VALUES (?,?,?,?,?,?,?,?,?,?,1)
            """, (gr_number, enrollment, name, email, department,
                  class_id, bid, roll_number, face_pid, gr_number))
            stu_db_id = cur.lastrowid
            inserted += 1
        except sqlite3.IntegrityError as e:
            print(f"  SKIP {name} ({gr_number}): {e}")
            skipped += 1
            continue

    # Update face_database.json entry with gr_number
    if face_pid and face_pid in face_db:
        face_db[face_pid]["employee_id"] = gr_number
        face_db[face_pid]["gr_number"]   = gr_number
        face_db[face_pid]["class"]        = class_name
        face_db[face_pid]["batch"]        = batch_raw
        linked += 1
        print(f"  OK {name} (GR:{gr_number}) -> face: {face_pid}")
    else:
        print(f"  NO FACE {name} (GR:{gr_number}) -> no face match found")

conn.commit()
conn.close()

# ── Save updated face_database.json ─────────────────────────────────────────
with open(FACE_DB, "w") as f:
    json.dump(face_db, f, indent=2)

print(f"""
═══════════════════════════════════════
Import Complete!
  Inserted : {inserted} new students
  Updated  : {updated} existing students
  Skipped  : {skipped}
  Faces linked: {linked} / {len(df)}
═══════════════════════════════════════
""")
