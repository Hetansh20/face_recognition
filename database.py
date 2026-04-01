import sqlite3
import os
from datetime import datetime
import bcrypt
import json

# Database file path
DB_PATH = "attendance_system.db"

class Database:
    """Database management class for the attendance system"""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.init_db()
    
    def connect(self):
        """Connect to the database"""
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()
    
    def disconnect(self):
        """Disconnect from the database"""
        if self.conn:
            self.conn.close()
    
    def init_db(self):
        """Initialize database with all required tables"""
        self.connect()
        
        # Create Faculties table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS faculties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                department TEXT NOT NULL,
                passcode_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Create Students table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                department TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Create Timetables table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS timetables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                day_of_week TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                room_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (faculty_id) REFERENCES faculties(id)
            )
        ''')
        
        # Create Facial Encodings table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS facial_encodings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                encoding_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        ''')
        
        # Create Attendance table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                timetable_id INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'present',
                confidence_score REAL,
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (timetable_id) REFERENCES timetables(id)
            )
        ''')
        
        # Create Attendance Sessions table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id INTEGER NOT NULL,
                timetable_id INTEGER NOT NULL,
                session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_end TIMESTAMP,
                total_students INTEGER,
                present_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (faculty_id) REFERENCES faculties(id),
                FOREIGN KEY (timetable_id) REFERENCES timetables(id)
            )
        ''')
        
        self.conn.commit()
        self.disconnect()
    
    def hash_passcode(self, passcode):
        """Hash a passcode using bcrypt"""
        return bcrypt.hashpw(passcode.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def verify_passcode(self, passcode, passcode_hash):
        """Verify a passcode against its hash"""
        return bcrypt.checkpw(passcode.encode('utf-8'), passcode_hash.encode('utf-8'))
    
    # Faculty operations
    def add_faculty(self, name, email, department, passcode):
        """Add a new faculty member"""
        self.connect()
        try:
            passcode_hash = self.hash_passcode(passcode)
            self.cursor.execute('''
                INSERT INTO faculties (name, email, department, passcode_hash)
                VALUES (?, ?, ?, ?)
            ''', (name, email, department, passcode_hash))
            self.conn.commit()
            faculty_id = self.cursor.lastrowid
            self.disconnect()
            return faculty_id
        except sqlite3.IntegrityError as e:
            self.disconnect()
            raise Exception(f"Faculty with this email already exists: {e}")
    
    def get_faculty_by_email(self, email):
        """Get faculty by email"""
        self.connect()
        self.cursor.execute('SELECT * FROM faculties WHERE email = ?', (email,))
        result = self.cursor.fetchone()
        self.disconnect()
        return result
    
    def get_faculty_by_id(self, faculty_id):
        """Get faculty by ID"""
        self.connect()
        self.cursor.execute('SELECT * FROM faculties WHERE id = ?', (faculty_id,))
        result = self.cursor.fetchone()
        self.disconnect()
        return result
    
    def get_all_faculties(self):
        """Get all active faculties"""
        self.connect()
        self.cursor.execute('SELECT * FROM faculties WHERE is_active = 1')
        results = self.cursor.fetchall()
        self.disconnect()
        return results
    
    # Student operations
    def add_student(self, student_id, name, email, department):
        """Add a new student"""
        self.connect()
        try:
            self.cursor.execute('''
                INSERT INTO students (student_id, name, email, department)
                VALUES (?, ?, ?, ?)
            ''', (student_id, name, email, department))
            self.conn.commit()
            sid = self.cursor.lastrowid
            self.disconnect()
            return sid
        except sqlite3.IntegrityError as e:
            self.disconnect()
            raise Exception(f"Student with this ID or email already exists: {e}")
    
    def get_student_by_id(self, student_id):
        """Get student by database ID"""
        self.connect()
        self.cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
        result = self.cursor.fetchone()
        self.disconnect()
        return result
    
    def get_student_by_student_id(self, student_id):
        """Get student by student ID"""
        self.connect()
        self.cursor.execute('SELECT * FROM students WHERE student_id = ?', (student_id,))
        result = self.cursor.fetchone()
        self.disconnect()
        return result
    
    def get_all_students(self):
        """Get all active students"""
        self.connect()
        self.cursor.execute('SELECT * FROM students WHERE is_active = 1')
        results = self.cursor.fetchall()
        self.disconnect()
        return results
    
    # Timetable operations
    def add_timetable(self, faculty_id, class_name, day_of_week, start_time, end_time, room_number=None):
        """Add a new timetable entry"""
        self.connect()
        self.cursor.execute('''
            INSERT INTO timetables (faculty_id, class_name, day_of_week, start_time, end_time, room_number)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (faculty_id, class_name, day_of_week, start_time, end_time, room_number))
        self.conn.commit()
        timetable_id = self.cursor.lastrowid
        self.disconnect()
        return timetable_id
    
    def get_timetable_by_id(self, timetable_id):
        """Get timetable by ID"""
        self.connect()
        self.cursor.execute('SELECT * FROM timetables WHERE id = ?', (timetable_id,))
        result = self.cursor.fetchone()
        self.disconnect()
        return result
    
    def get_faculty_timetables(self, faculty_id):
        """Get all timetables for a faculty"""
        self.connect()
        self.cursor.execute('SELECT * FROM timetables WHERE faculty_id = ?', (faculty_id,))
        results = self.cursor.fetchall()
        self.disconnect()
        return results
    
    # Facial encoding operations
    def add_facial_encoding(self, student_id, encoding_data):
        """Add facial encoding for a student"""
        self.connect()
        encoding_json = json.dumps(encoding_data.tolist()) if hasattr(encoding_data, 'tolist') else json.dumps(encoding_data)
        self.cursor.execute('''
            INSERT INTO facial_encodings (student_id, encoding_data)
            VALUES (?, ?)
        ''', (student_id, encoding_json))
        self.conn.commit()
        self.disconnect()
    
    def get_student_encodings(self, student_id):
        """Get all facial encodings for a student"""
        self.connect()
        self.cursor.execute('SELECT * FROM facial_encodings WHERE student_id = ?', (student_id,))
        results = self.cursor.fetchall()
        self.disconnect()
        return results
    
    def get_all_encodings(self):
        """Get all facial encodings"""
        self.connect()
        self.cursor.execute('SELECT * FROM facial_encodings')
        results = self.cursor.fetchall()
        self.disconnect()
        return results
    
    # Attendance operations
    def mark_attendance(self, student_id, timetable_id, confidence_score=None):
        """Mark attendance for a student"""
        self.connect()
        self.cursor.execute('''
            INSERT INTO attendance (student_id, timetable_id, status, confidence_score)
            VALUES (?, ?, 'present', ?)
        ''', (student_id, timetable_id, confidence_score))
        self.conn.commit()
        self.disconnect()
    
    def get_attendance_by_session(self, timetable_id):
        """Get all attendance records for a timetable"""
        self.connect()
        self.cursor.execute('''
            SELECT a.id, a.student_id, a.timetable_id, a.timestamp, a.status, a.confidence_score, 
                   s.student_id as student_code, s.name, s.email FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.timetable_id = ?
            ORDER BY a.timestamp DESC
        ''', (timetable_id,))
        results = self.cursor.fetchall()
        self.disconnect()
        return results
    
    # Attendance session operations
    def create_session(self, faculty_id, timetable_id, total_students):
        """Create a new attendance session"""
        self.connect()
        self.cursor.execute('''
            INSERT INTO attendance_sessions (faculty_id, timetable_id, total_students)
            VALUES (?, ?, ?)
        ''', (faculty_id, timetable_id, total_students))
        self.conn.commit()
        session_id = self.cursor.lastrowid
        self.disconnect()
        return session_id
    
    def end_session(self, session_id, present_count):
        """End an attendance session"""
        self.connect()
        self.cursor.execute('''
            UPDATE attendance_sessions
            SET session_end = CURRENT_TIMESTAMP, status = 'completed', present_count = ?
            WHERE id = ?
        ''', (present_count, session_id))
        self.conn.commit()
        self.disconnect()
    
    def get_session(self, session_id):
        """Get session details"""
        self.connect()
        self.cursor.execute('SELECT * FROM attendance_sessions WHERE id = ?', (session_id,))
        result = self.cursor.fetchone()
        self.disconnect()
        return result

# Initialize database on import
if __name__ == "__main__":
    db = Database()
    print("Database initialized successfully!")
