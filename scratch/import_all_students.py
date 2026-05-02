"""
import_all_students.py
======================
Imports ALL students from all 3 sheets (Sem-2, Sem-4, Sem-6) into the DB.
Matches each student to their face image in registered_faces/ by GR number.
Updates face_database.json with correct employee_id (GR number).

Run from project root:
    python scratch/import_all_students.py
"""

import sys, os, json, re, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH   = os.path.join(BASE_DIR, "attendance_system.db")
FACE_DB   = os.path.join(BASE_DIR, "face_database.json")
FACES_DIR = os.path.join(BASE_DIR, "registered_faces")
EXCEL     = os.path.join(BASE_DIR, "Student details for AI project.xlsx")

# ── Load face_database.json ──────────────────────────────────────────────────
with open(FACE_DB, "r") as f:
    face_db = json.load(f)

# ── Build GR-number -> face_pid lookup from registered_faces filenames ────────
# Filenames: NAME_GRNO_front.jpg  -> GR is the numeric part before _front
gr_to_face_pid = {}
for fname in os.listdir(FACES_DIR):
    m = re.match(r'^(.+?)_(\d+)_front\.jpg$', fname, re.IGNORECASE)
    if m:
        gr = m.group(2)
        # face_pid key = NAME_GRNO (no _front)
        pid_candidate = f"{m.group(1)}_{gr}"
        if pid_candidate in face_db:
            gr_to_face_pid[gr] = pid_candidate
        else:
            # Try case-insensitive lookup
            for key in face_db:
                if key.endswith(f"_{gr}"):
                    gr_to_face_pid[gr] = key
                    break

print(f"Face lookup built: {len(gr_to_face_pid)} GR numbers mapped to face PIDs")

# ── Connect to DB ────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur  = conn.cursor()

def get_or_create_semester(number, level="Degree"):
    cur.execute("SELECT id FROM semesters WHERE number=?", (number,))
    r = cur.fetchone()
    if r:
        return r[0]
    cur.execute("INSERT INTO semesters (number, label, level) VALUES (?,?,?)",
                (number, f"Semester {number}", level))
    conn.commit()
    print(f"  Created Semester {number}")
    return cur.lastrowid

def get_or_create_class(sem_id, name):
    name = name.strip()
    cur.execute("SELECT id FROM classes WHERE semester_id=? AND name=?", (sem_id, name))
    r = cur.fetchone()
    if r:
        return r[0]
    cur.execute("INSERT INTO classes (semester_id, name, section) VALUES (?,?,?)",
                (sem_id, name, name))
    conn.commit()
    print(f"  Created Class {name}")
    return cur.lastrowid

def get_or_create_batch(class_id, name):
    name = name.strip()
    cur.execute("SELECT id FROM batches WHERE class_id=? AND name=?", (class_id, name))
    r = cur.fetchone()
    if r:
        return r[0]
    cur.execute("INSERT INTO batches (class_id, name) VALUES (?,?)", (class_id, name))
    conn.commit()
    print(f"  Created Batch {name}")
    return cur.lastrowid

# ── Process all sheets ───────────────────────────────────────────────────────
xl = pd.ExcelFile(EXCEL)
total_inserted = 0
total_updated  = 0
total_linked   = 0
total_skipped  = 0

SHEET_META = {
    'Sem-2': {'sem': 2, 'dept': 'ICT', 'roll_prefix': '925001'},
    'Sem-4': {'sem': 4, 'dept': 'ICT', 'roll_prefix': '924001'},
    'Sem-6': {'sem': 6, 'dept': 'ICT', 'roll_prefix': '923017'},
}

for sheet_name in xl.sheet_names:
    df = xl.parse(sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()

    meta = SHEET_META.get(sheet_name, {'sem': 0, 'dept': 'ICT'})
    sem_num = meta['sem']
    dept    = meta['dept']

    print(f"\n{'='*50}")
    print(f"Sheet: {sheet_name}  |  {len(df)} students  |  Sem {sem_num}")
    print(f"{'='*50}")

    sem_id = get_or_create_semester(sem_num)

    inserted = updated = linked = skipped = 0

    for _, row in df.iterrows():
        try:
            gr_number   = str(int(float(str(row["GR NO"]).strip())))
            roll_number = str(row["Roll No"]).strip()
            name        = str(row["Student Name"]).strip()
            class_name  = str(row["Class"]).strip()
            batch_name  = str(row["Lab Batch"]).strip()
        except Exception as e:
            print(f"  SKIP malformed row: {e}")
            skipped += 1
            continue

        if not gr_number or not name or name.lower() == 'nan':
            skipped += 1
            continue

        class_id = get_or_create_class(sem_id, class_name)
        batch_id = get_or_create_batch(class_id, batch_name)

        # Placeholder email based on GR number (unique)
        email = f"{gr_number}@student.edu"

        # Find face_pid by GR number
        face_pid = gr_to_face_pid.get(gr_number)

        # Check existing
        cur.execute("SELECT id FROM students WHERE gr_number=?", (gr_number,))
        existing = cur.fetchone()

        if existing:
            stu_db_id = existing[0]
            cur.execute("""
                UPDATE students
                SET name=?, enrollment_number=?, department=?,
                    class_id=?, batch_id=?, roll_number=?, face_pid=?,
                    student_id=?, is_active=1
                WHERE id=?
            """, (name, roll_number, dept, class_id, batch_id,
                  roll_number, face_pid, gr_number, stu_db_id))
            updated += 1
        else:
            try:
                cur.execute("""
                    INSERT INTO students
                        (gr_number, enrollment_number, name, email, department,
                         class_id, batch_id, roll_number, face_pid, student_id, is_active)
                    VALUES (?,?,?,?,?,?,?,?,?,?,1)
                """, (gr_number, roll_number, name, email, dept,
                      class_id, batch_id, roll_number, face_pid, gr_number))
                stu_db_id = cur.lastrowid
                inserted += 1
            except sqlite3.IntegrityError as e:
                print(f"  SKIP {name} ({gr_number}): {e}")
                skipped += 1
                continue

        # Update face_database.json
        if face_pid and face_pid in face_db:
            face_db[face_pid]["employee_id"] = gr_number
            face_db[face_pid]["gr_number"]   = gr_number
            face_db[face_pid]["class"]        = class_name
            face_db[face_pid]["batch"]        = batch_name
            face_db[face_pid]["semester"]     = sem_num
            linked += 1
            status = f"LINKED -> {face_pid}"
        else:
            status = "no face"

        print(f"  {'NEW' if not existing else 'UPD'} | {name} | GR:{gr_number} | {class_name}/{batch_name} | {status}")

    conn.commit()
    print(f"\n  Sheet summary: inserted={inserted}, updated={updated}, linked={linked}, skipped={skipped}")
    total_inserted += inserted
    total_updated  += updated
    total_linked   += linked
    total_skipped  += skipped

conn.close()

# ── Save updated face_database.json ─────────────────────────────────────────
with open(FACE_DB, "w") as f:
    json.dump(face_db, f, indent=2)
print(f"\nface_database.json updated.")

print(f"""
IMPORT COMPLETE
  Total inserted : {total_inserted}
  Total updated  : {total_updated}
  Total skipped  : {total_skipped}
  Faces linked   : {total_linked} / {total_inserted + total_updated}
  Unmatched faces: {(total_inserted + total_updated) - total_linked} students have no face photo yet
""")
