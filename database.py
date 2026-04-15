import sqlite3
import os
from datetime import datetime
import bcrypt
import json

# Database file path — absolute so it works from any working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "attendance_system.db")


class Database:
    """Database management class for the attendance system"""

    def __init__(self):
        self.conn   = None
        self.cursor = None
        self.init_db()

    # ──────────────────────── Connection ─────────────────────────────

    def connect(self):
        self.conn   = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def disconnect(self):
        if self.conn:
            self.conn.close()
            self.conn   = None
            self.cursor = None

    # ──────────────────────── Schema Init ────────────────────────────

    def init_db(self):
        """Initialize database — creates tables if missing, migrates columns."""
        self.connect()

        # ── Core tables ──────────────────────────────────────────────

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS faculties (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                department    TEXT NOT NULL,
                passcode_hash TEXT NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active     BOOLEAN DEFAULT 1
            )
        ''')

        # Semesters (1–8)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS semesters (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                number     INTEGER UNIQUE NOT NULL,
                label      TEXT,
                level      TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Classes e.g. 6EK1, 6EK2
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS classes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                semester_id INTEGER NOT NULL,
                name        TEXT NOT NULL,
                section     TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (semester_id) REFERENCES semesters(id),
                UNIQUE(semester_id, name)
            )
        ''')

        # Batches A / B / C / Whole within a class
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS batches (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id   INTEGER NOT NULL,
                name       TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (class_id) REFERENCES classes(id),
                UNIQUE(class_id, name)
            )
        ''')

        # Students — extended with class/batch/roll/phone
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                gr_number         TEXT UNIQUE,
                enrollment_number TEXT UNIQUE,
                name              TEXT NOT NULL,
                email             TEXT UNIQUE NOT NULL,
                department        TEXT NOT NULL,
                class_id          INTEGER,
                batch_id          INTEGER,
                roll_number       TEXT,
                phone             TEXT,
                face_pid          TEXT,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active         BOOLEAN DEFAULT 1,
                student_id        TEXT, -- Legacy field, kept for compatibility during migration
                FOREIGN KEY (class_id)  REFERENCES classes(id),
                FOREIGN KEY (batch_id)  REFERENCES batches(id)
            )
        ''')

        # Timetables — extended with class/batch/subject
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS timetables (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id    INTEGER NOT NULL,
                class_name    TEXT NOT NULL,
                class_id      INTEGER,
                batch_id      INTEGER,
                subject_name  TEXT,
                day_of_week   TEXT NOT NULL,
                start_time    TEXT NOT NULL,
                end_time      TEXT NOT NULL,
                room_number   TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (faculty_id) REFERENCES faculties(id),
                FOREIGN KEY (class_id)   REFERENCES classes(id),
                FOREIGN KEY (batch_id)   REFERENCES batches(id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS facial_encodings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id   INTEGER NOT NULL,
                encoding_data TEXT NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id       INTEGER NOT NULL,
                timetable_id     INTEGER NOT NULL,
                timestamp        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status           TEXT DEFAULT 'present',
                confidence_score REAL,
                FOREIGN KEY (student_id)   REFERENCES students(id),
                FOREIGN KEY (timetable_id) REFERENCES timetables(id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id     INTEGER NOT NULL,
                timetable_id   INTEGER NOT NULL,
                session_start  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_end    TIMESTAMP,
                total_students INTEGER,
                present_count  INTEGER DEFAULT 0,
                status         TEXT DEFAULT 'active',
                FOREIGN KEY (faculty_id)   REFERENCES faculties(id),
                FOREIGN KEY (timetable_id) REFERENCES timetables(id)
            )
        ''')

        # ── Safe migrations for old columns ──────────────────────────
        self._add_column_if_missing("students",   "gr_number",   "TEXT")
        self._add_column_if_missing("students",   "enrollment_number", "TEXT")
        self._add_column_if_missing("students",   "class_id",    "INTEGER")
        self._add_column_if_missing("students",   "batch_id",    "INTEGER")
        self._add_column_if_missing("students",   "roll_number", "TEXT")
        self._add_column_if_missing("students",   "phone",       "TEXT")
        self._add_column_if_missing("students",   "face_pid",    "TEXT")
        
        self.cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stu_gr ON students(gr_number)")
        self.cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stu_enroll ON students(enrollment_number)")

        self._add_column_if_missing("timetables", "class_id",    "INTEGER")
        self._add_column_if_missing("timetables", "batch_id",    "INTEGER")
        self._add_column_if_missing("timetables", "subject_name","TEXT")

        # ── Data Migration: Copy student_id to gr_number if empty ─────
        try:
            self.cursor.execute('''
                UPDATE students 
                SET gr_number = student_id 
                WHERE (gr_number IS NULL OR gr_number = '') AND (student_id IS NOT NULL AND student_id != '')
            ''')
        except:
            pass

        # Simplified schema: level directly on semesters
        self._add_column_if_missing("semesters",  "level",   "TEXT")

        self.conn.commit()
        self.disconnect()

    def _add_column_if_missing(self, table, column, col_type):
        """ALTER TABLE … ADD COLUMN safely (SQLite-safe)."""
        self.cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in self.cursor.fetchall()]
        if column not in columns:
            try:
                # Remove UNIQUE for ALTER TABLE as SQLite doesn't support it
                clean_type = col_type.replace('UNIQUE', '').strip()
                self.cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {clean_type}")
                print(f"[DB Migration] Added column {column} to {table}")
            except Exception as e:
                print(f"[DB Migration Error] Failed to add column {column} to {table}: {e}")

    # ──────────────────────── Utilities ──────────────────────────────

    def hash_passcode(self, passcode):
        return bcrypt.hashpw(passcode.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def verify_passcode(self, passcode, passcode_hash):
        return bcrypt.checkpw(passcode.encode('utf-8'), passcode_hash.encode('utf-8'))

    # ──────────────────────── Faculty ────────────────────────────────

    def add_faculty(self, name, email, department, passcode):
        self.connect()
        try:
            passcode_hash = self.hash_passcode(passcode)
            self.cursor.execute(
                'INSERT INTO faculties (name, email, department, passcode_hash) VALUES (?, ?, ?, ?)',
                (name, email, department, passcode_hash)
            )
            self.conn.commit()
            fid = self.cursor.lastrowid
            self.disconnect()
            return fid
        except sqlite3.IntegrityError as e:
            self.disconnect()
            raise Exception(f"Faculty with this email already exists: {e}")

    def get_faculty_by_email(self, email):
        self.connect()
        self.cursor.execute('SELECT * FROM faculties WHERE email = ?', (email,))
        r = self.cursor.fetchone(); self.disconnect(); return r

    def get_faculty_by_id(self, faculty_id):
        self.connect()
        self.cursor.execute('SELECT * FROM faculties WHERE id = ?', (faculty_id,))
        r = self.cursor.fetchone(); self.disconnect(); return r

    def get_all_faculties(self):
        self.connect()
        self.cursor.execute('SELECT * FROM faculties WHERE is_active = 1')
        r = self.cursor.fetchall(); self.disconnect(); return r

    def get_faculty_by_passcode(self, passcode):
        for f in self.get_all_faculties():
            if self.verify_passcode(passcode, f[4]):
                return f
        return None

    def update_faculty(self, faculty_id, name, email, department):
        self.connect()
        self.cursor.execute(
            'UPDATE faculties SET name=?, email=?, department=? WHERE id=?',
            (name, email, department, faculty_id)
        )
        self.conn.commit(); self.disconnect()

    def delete_faculty(self, faculty_id):
        self.connect()
        self.cursor.execute('UPDATE faculties SET is_active=0 WHERE id=?', (faculty_id,))
        self.conn.commit(); self.disconnect()

    # ──────────────────────── Semesters ──────────────────────────────

    def add_semester(self, number, label=None, level=None):
        self.connect()
        try:
            self.cursor.execute(
                'INSERT INTO semesters (number, label, level) VALUES (?, ?, ?)', (number, label, level)
            )
            self.conn.commit()
            sid = self.cursor.lastrowid; self.disconnect(); return sid
        except sqlite3.IntegrityError:
            self.disconnect(); raise Exception("Semester already exists.")

    def get_all_semesters(self):
        self.connect()
        self.cursor.execute('SELECT * FROM semesters ORDER BY number')
        r = self.cursor.fetchall(); self.disconnect(); return r

    def delete_semester(self, semester_id):
        self.connect()
        self.cursor.execute('DELETE FROM semesters WHERE id=?', (semester_id,))
        self.conn.commit(); self.disconnect()

    # ──────────────────────── Classes ────────────────────────────────

    def add_class(self, semester_id, name):
        self.connect()
        try:
            self.cursor.execute(
                'INSERT INTO classes (semester_id, name) VALUES (?, ?)', (semester_id, name)
            )
            self.conn.commit()
            cid = self.cursor.lastrowid; self.disconnect(); return cid
        except sqlite3.IntegrityError:
            self.disconnect(); raise Exception("Class already exists in this semester.")

    def get_classes_by_semester(self, semester_id):
        self.connect()
        self.cursor.execute('SELECT * FROM classes WHERE semester_id=? ORDER BY name', (semester_id,))
        r = self.cursor.fetchall(); self.disconnect(); return r

    def get_all_classes(self):
        self.connect()
        self.cursor.execute('''
            SELECT c.id, c.semester_id, c.name, c.section, s.number, s.label
            FROM classes c JOIN semesters s ON c.semester_id = s.id
            ORDER BY s.number, c.name
        ''')
        r = self.cursor.fetchall(); self.disconnect(); return r

    def delete_class(self, class_id):
        self.connect()
        self.cursor.execute('DELETE FROM classes WHERE id=?', (class_id,))
        self.conn.commit(); self.disconnect()

    # ──────────────────────── Batches ────────────────────────────────

    def add_batch(self, class_id, name):
        self.connect()
        try:
            self.cursor.execute(
                'INSERT INTO batches (class_id, name) VALUES (?, ?)', (class_id, name)
            )
            self.conn.commit()
            bid = self.cursor.lastrowid; self.disconnect(); return bid
        except sqlite3.IntegrityError:
            self.disconnect(); raise Exception("Batch already exists in this class.")

    def get_batches_by_class(self, class_id):
        self.connect()
        self.cursor.execute('SELECT * FROM batches WHERE class_id=? ORDER BY name', (class_id,))
        r = self.cursor.fetchall(); self.disconnect(); return r

    def get_all_batches(self):
        self.connect()
        self.cursor.execute('''
            SELECT b.id, b.class_id, b.name, c.name as class_name, s.number as semester
            FROM batches b
            JOIN classes c ON b.class_id = c.id
            JOIN semesters s ON c.semester_id = s.id
            ORDER BY s.number, c.name, b.name
        ''')
        r = self.cursor.fetchall(); self.disconnect(); return r

    def delete_batch(self, batch_id):
        self.connect()
        self.cursor.execute('DELETE FROM batches WHERE id=?', (batch_id,))
        self.conn.commit(); self.disconnect()

    # ──────────────────────── Students ───────────────────────────────

    def add_student(self, gr_number, enrollment_number, name, email, department,
                    class_id=None, batch_id=None, phone=None, face_pid=None):
        self.connect()
        try:
            self.cursor.execute('''
                INSERT INTO students
                    (gr_number, enrollment_number, name, email, department, class_id, batch_id, phone, face_pid, student_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (gr_number, enrollment_number, name, email, department, class_id, batch_id, phone, face_pid, gr_number))
            self.conn.commit()
            sid = self.cursor.lastrowid; self.disconnect(); return sid
        except sqlite3.IntegrityError as e:
            self.disconnect()
            raise Exception(f"Student with this GR or Enrollment already exists: {e}")

    def update_student(self, student_db_id, name, email, department,
                       gr_number=None, enrollment_number=None,
                       class_id=None, batch_id=None, phone=None, face_pid=None):
        self.connect()
        self.cursor.execute('''
            UPDATE students
            SET name=?, email=?, department=?, gr_number=?, enrollment_number=?,
                class_id=?, batch_id=?, phone=?, face_pid=?
            WHERE id=?
        ''', (name, email, department, gr_number, enrollment_number, 
              class_id, batch_id, phone, face_pid, student_db_id))
        self.conn.commit(); self.disconnect()

    def delete_student(self, student_db_id):
        self.connect()
        self.cursor.execute('UPDATE students SET is_active=0 WHERE id=?', (student_db_id,))
        self.conn.commit(); self.disconnect()

    def clear_all_students(self):
        """DANGER: Permanently deletes ALL students, attendance, and encodings."""
        self.connect()
        try:
            self.cursor.execute('DELETE FROM attendance')
            self.cursor.execute('DELETE FROM facial_encodings')
            self.cursor.execute('DELETE FROM students')
            self.conn.commit()
        finally:
            self.disconnect()

    def get_student_by_id(self, student_db_id):
        self.connect()
        self.cursor.execute('SELECT * FROM students WHERE id=?', (student_db_id,))
        r = self.cursor.fetchone(); self.disconnect(); return r

    def get_student_by_gr_number(self, gr_number):
        self.connect()
        self.cursor.execute('SELECT * FROM students WHERE gr_number=?', (gr_number,))
        r = self.cursor.fetchone(); self.disconnect(); return r

    def get_student_by_enrollment(self, enrollment):
        if not enrollment: return None
        self.connect()
        self.cursor.execute('SELECT * FROM students WHERE enrollment_number=?', (enrollment,))
        r = self.cursor.fetchone(); self.disconnect(); return r

    def get_student_by_email(self, email):
        if not email: return None
        self.connect()
        self.cursor.execute('SELECT * FROM students WHERE email=?', (email,))
        r = self.cursor.fetchone(); self.disconnect(); return r

    def get_all_students(self):
        self.connect()
        self.cursor.execute('SELECT * FROM students WHERE is_active=1 ORDER BY name')
        r = self.cursor.fetchall(); self.disconnect(); return r

    def get_students_by_class(self, class_id):
        """All active students in a class (all batches)."""
        self.connect()
        self.cursor.execute(
            'SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY name',
            (class_id,)
        )
        r = self.cursor.fetchall(); self.disconnect(); return r

    def get_students_by_batch(self, batch_id):
        """All active students in a specific batch."""
        self.connect()
        self.cursor.execute(
            'SELECT * FROM students WHERE batch_id=? AND is_active=1 ORDER BY name',
            (batch_id,)
        )
        r = self.cursor.fetchall(); self.disconnect(); return r

    def search_students(self, query):
        self.connect()
        q = f"%{query}%"
        self.cursor.execute('''
            SELECT * FROM students
            WHERE is_active=1
              AND (name LIKE ? OR gr_number LIKE ? OR enrollment_number LIKE ? OR email LIKE ? OR roll_number LIKE ?)
            ORDER BY name
        ''', (q, q, q, q, q))
        r = self.cursor.fetchall(); self.disconnect(); return r

    def link_student_face(self, student_db_id, face_pid):
        """Link a face_database.json person_id to a student record."""
        self.connect()
        self.cursor.execute('UPDATE students SET face_pid=? WHERE id=?', (face_pid, student_db_id))
        self.conn.commit(); self.disconnect()

    # ──────────────────────── Timetables ─────────────────────────────

    def add_timetable(self, faculty_id, class_name, day_of_week, start_time, end_time,
                      room_number=None, class_id=None, batch_id=None, subject_name=None):
        self.connect()
        self.cursor.execute('''
            INSERT INTO timetables
                (faculty_id, class_name, class_id, batch_id, subject_name,
                 day_of_week, start_time, end_time, room_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (faculty_id, class_name, class_id, batch_id, subject_name,
              day_of_week, start_time, end_time, room_number))
        self.conn.commit()
        tid = self.cursor.lastrowid; self.disconnect(); return tid

    def get_timetable_by_id(self, timetable_id):
        self.connect()
        self.cursor.execute('SELECT * FROM timetables WHERE id=?', (timetable_id,))
        r = self.cursor.fetchone(); self.disconnect(); return r

    def get_faculty_timetables(self, faculty_id):
        self.connect()
        self.cursor.execute('SELECT * FROM timetables WHERE faculty_id=?', (faculty_id,))
        r = self.cursor.fetchall(); self.disconnect(); return r

    def get_all_timetables(self):
        self.connect()
        self.cursor.execute('''
            SELECT t.*, f.name as faculty_name
            FROM timetables t
            JOIN faculties f ON t.faculty_id = f.id
            ORDER BY t.day_of_week, t.start_time
        ''')
        r = self.cursor.fetchall(); self.disconnect(); return r

    def delete_timetable(self, timetable_id):
        self.connect()
        self.cursor.execute('DELETE FROM timetables WHERE id=?', (timetable_id,))
        self.conn.commit(); self.disconnect()

    # ──────────────────────── Face Map Queries ───────────────────────

    def get_students_without_face(self):
        """Students in DB but face_pid is NULL or not set."""
        self.connect()
        self.cursor.execute('''
            SELECT * FROM students
            WHERE is_active=1 AND (face_pid IS NULL OR face_pid = '')
            ORDER BY name
        ''')
        r = self.cursor.fetchall(); self.disconnect(); return r

    def get_face_pid_map(self):
        """Return dict: face_pid → student row for quick lookup."""
        self.connect()
        self.cursor.execute(
            "SELECT * FROM students WHERE is_active=1 AND face_pid IS NOT NULL AND face_pid != ''"
        )
        rows = self.cursor.fetchall(); self.disconnect()
        return {row['face_pid']: row for row in rows}

    # ──────────────────────── Facial Encodings ───────────────────────

    def add_facial_encoding(self, student_id, encoding_data):
        self.connect()
        enc = json.dumps(encoding_data.tolist()) if hasattr(encoding_data, 'tolist') else json.dumps(encoding_data)
        self.cursor.execute(
            'INSERT INTO facial_encodings (student_id, encoding_data) VALUES (?, ?)', (student_id, enc)
        )
        self.conn.commit(); self.disconnect()

    def get_student_encodings(self, student_id):
        self.connect()
        self.cursor.execute('SELECT * FROM facial_encodings WHERE student_id=?', (student_id,))
        r = self.cursor.fetchall(); self.disconnect(); return r

    def get_all_encodings(self):
        self.connect()
        self.cursor.execute('SELECT * FROM facial_encodings')
        r = self.cursor.fetchall(); self.disconnect(); return r

    # ──────────────────────── Attendance ─────────────────────────────

    def mark_attendance(self, student_id, timetable_id, confidence_score=None):
        self.connect()
        self.cursor.execute('''
            INSERT INTO attendance (student_id, timetable_id, status, confidence_score)
            VALUES (?, ?, 'present', ?)
        ''', (student_id, timetable_id, confidence_score))
        self.conn.commit(); self.disconnect()

    def get_attendance_by_session(self, timetable_id):
        self.connect()
        self.cursor.execute('''
            SELECT a.id, a.student_id, a.timetable_id, a.timestamp, a.status, a.confidence_score,
                   s.gr_number as gr_code, s.name, s.email
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.timetable_id = ?
            ORDER BY a.timestamp DESC
        ''', (timetable_id,))
        r = self.cursor.fetchall(); self.disconnect(); return r

    # ──────────────────────── Sessions ───────────────────────────────

    def create_session(self, faculty_id, timetable_id, total_students):
        self.connect()
        self.cursor.execute('''
            INSERT INTO attendance_sessions (faculty_id, timetable_id, total_students)
            VALUES (?, ?, ?)
        ''', (faculty_id, timetable_id, total_students))
        self.conn.commit()
        sid = self.cursor.lastrowid; self.disconnect(); return sid

    def end_session(self, session_id, present_count):
        self.connect()
        self.cursor.execute('''
            UPDATE attendance_sessions
            SET session_end=CURRENT_TIMESTAMP, status='completed', present_count=?
            WHERE id=?
        ''', (present_count, session_id))
        self.conn.commit(); self.disconnect()

    def get_session(self, session_id):
        self.connect()
        self.cursor.execute('SELECT * FROM attendance_sessions WHERE id=?', (session_id,))
        r = self.cursor.fetchone(); self.disconnect(); return r


if __name__ == "__main__":
    db = Database()
    print("Database initialized successfully!")
