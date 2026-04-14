from flask import Flask, render_template, request, session, jsonify, redirect, url_for, Response
import os
import subprocess
from datetime import datetime
from database import Database
from timetable_manager import timetable_manager
from analytics_service import analytics_service
from csv_export_service import CSVExportService
import zipfile
import pandas as pd
import io
import json
import pickle
import numpy as np
import cv2

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Absolute base directory for all file operations
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACES_DIR   = os.path.join(BASE_DIR, "registered_faces")
FACE_DB     = os.path.join(BASE_DIR, "face_database.json")
EMB_CACHE   = os.path.join(BASE_DIR, "face_embeddings_insightface.pkl")
REPORTS_DIR = os.path.join(BASE_DIR, "attendance_reports")

# Face recognition single-threaded video stream
try:
    from face_engine import FaceEngine
except ImportError:
    FaceEngine = None
    
ACTIVE_ENGINE = None

def get_db():
    return Database()

@app.route("/")
def index():
    return render_template("index.html")

# ─────────────────────────────────────────────────────────────
# ADMIN ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        data = request.json
        if data.get("email") == "admin123@gmail.com" and data.get("password") == "admin123":
            session["admin_logged_in"] = True
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Invalid admin credentials"})
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))

def admin_required(f):
    def wrap(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = analytics_service.get_system_statistics()
    return render_template("admin_dashboard.html", stats=stats)

@app.route("/admin/setup")
@admin_required
def admin_setup():
    return render_template("admin_setup.html")

@app.route("/admin/timetables")
@admin_required
def admin_timetables():
    db = get_db()
    faculties  = db.get_all_faculties() or []
    semesters  = db.get_all_semesters()
    all_batches = db.get_all_batches()
    batch_map  = {b[0]: b[2] for b in all_batches}
    f_map      = {f[0]: f[1] for f in faculties}
    timetables = []
    for row in (db.get_all_timetables() or []):
        # row: id, faculty_id, class_name, class_id, batch_id, subject_name, day_of_week, start_time, end_time, room_number, created_at, faculty_name
        timetables.append({
            "id":           row[0],
            "faculty_name": row[-1],
            "class_name":   row[2],
            "subject":      row[5],
            "batch":        batch_map.get(row[4], '') if row[4] else '',
            "day":          row[6],
            "start":        row[7],
            "end":          row[8],
            "room":         row[9],
        })
    return render_template(
        "admin_timetables.html",
        faculties=faculties, timetables=timetables, semesters=semesters
    )

@app.route("/admin/reports")
@admin_required
def admin_reports():
    return render_template("admin_reports.html")

# ADMIN API
@app.route("/api/admin/faculty", methods=["POST"])
@admin_required
def api_add_faculty():
    data = request.json
    try:
        get_db().add_faculty(data['name'], data['email'], data['department'], data['passcode'])
        return jsonify({"success": True, "message": "Faculty added successfully!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/student", methods=["POST"])
@admin_required
def api_add_student():
    data = request.json
    try:
        get_db().add_student(data['gr_number'], data.get('enrollment_number', ''), data['name'], data['email'], data['department'])
        return jsonify({"success": True, "message": "Student added successfully!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/timetable", methods=["POST"])
@admin_required
def api_add_timetable():
    data = request.json
    try:
        tid, msg = timetable_manager.add_timetable_entry(
            int(data['faculty_id']), data['class_name'], data['day'],
            data['start_time'], data['end_time'], data.get('room'),
            data.get('class_id'), data.get('batch_id'), data.get('subject_name')
        )
        if tid:
            return jsonify({"success": True, "message": msg})
        return jsonify({"success": False, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/timetable/delete", methods=["POST"])
@admin_required
def api_delete_timetable():
    try:
        get_db().delete_timetable(request.json['id'])
        return jsonify({"success": True, "message": "Deleted."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/export", methods=["POST"])
@admin_required
def api_admin_export():
    try:
        fname, msg = CSVExportService().export_all_attendance()
        return jsonify({"success": bool(fname), "message": msg, "file": fname})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# ── STRUCTURE: Semesters / Classes / Batches ─────────────────

@app.route("/admin/structure")
@admin_required
def admin_structure():
    db = get_db()
    semesters = db.get_all_semesters()
    return render_template("admin_structure.html", semesters=semesters)

@app.route("/api/admin/semester/add", methods=["POST"])
@admin_required
def api_add_semester():
    data = request.json
    try:
        sid = get_db().add_semester(data['number'], data['label'], data.get('level'))
        return jsonify({"success": True, "message": "Semester added.", "id": sid})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/semester/delete", methods=["POST"])
@admin_required
def api_delete_semester():
    try:
        get_db().delete_semester(request.json['id'])
        return jsonify({"success": True, "message": "Deleted."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/classes", methods=["POST"])
@admin_required
def api_get_classes():
    rows = get_db().get_classes_by_semester(request.json['semester_id'])
    return jsonify({"classes": [{"id": r[0], "name": r[2], "section": r[3]} for r in rows]})

@app.route("/api/admin/class/add", methods=["POST"])
@admin_required
def api_add_class():
    data = request.json
    try:
        cid = get_db().add_class(data['semester_id'], data['name'])
        return jsonify({"success": True, "message": "Class added.", "id": cid})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/class/delete", methods=["POST"])
@admin_required
def api_delete_class():
    try:
        get_db().delete_class(request.json['id'])
        return jsonify({"success": True, "message": "Deleted."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/batches", methods=["POST"])
@admin_required
def api_get_batches():
    rows = get_db().get_batches_by_class(request.json['class_id'])
    return jsonify({"batches": [{"id": r[0], "name": r[2]} for r in rows]})

@app.route("/api/admin/batch/add", methods=["POST"])
@admin_required
def api_add_batch():
    d = request.json
    try:
        bid = get_db().add_batch(d['class_id'], d['name'])
        return jsonify({"success": True, "message": "Batch added.", "id": bid})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/batch/delete", methods=["POST"])
@admin_required
def api_delete_batch():
    try:
        get_db().delete_batch(request.json['id'])
        return jsonify({"success": True, "message": "Deleted."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# ── STUDENT Management ───────────────────────────────────────

@app.route("/admin/students")
@admin_required
def admin_students():
    import json as _json
    db = get_db()
    students  = db.get_all_students()
    classes   = db.get_all_classes()
    semesters = db.get_all_semesters()
    all_batches = db.get_all_batches()
    no_face   = db.get_students_without_face()
    class_map = {c['id']: f"{c['name']} (Sem {c['number']})" for c in classes}   # id -> name
    batch_map = {b['id']: b['name'] for b in all_batches}  # id -> name

    # Faces in face_database.json not linked to any student
    face_db = {}
    if os.path.exists(FACE_DB):
        with open(FACE_DB) as f:
            face_db = _json.load(f)
    linked_pids = {s['face_pid'] for s in students if s['face_pid']}
    unlinked_faces = {pid: info for pid, info in face_db.items() if pid not in linked_pids}

    return render_template(
        "admin_students.html",
        students=students,
        classes=classes,
        semesters=semesters,
        all_batches=all_batches,
        no_face=no_face,
        class_map=class_map,
        batch_map=batch_map,
        unlinked_faces=unlinked_faces,
        students_json=_json.dumps([dict(s) for s in students]),
        classes_json=_json.dumps([{"id": c['id'], "sem_id": c['semester_id'], "name": c['name']} for c in classes]),
        batches_json=_json.dumps([{"id": b['id'], "name": b['name'], "class_id": b['class_id']} for b in all_batches]),
    )

@app.route("/api/admin/student/add", methods=["POST"])
@admin_required
def api_admin_student_add():
    d = request.json
    try:
        sid = get_db().add_student(
            d.get('gr_number'), d.get('enrollment_number'), d['name'], d['email'], d.get('department', 'Unassigned'),
            d.get('class_id'), d.get('batch_id'), d.get('roll_number'), d.get('phone')
        )
        return jsonify({"success": True, "message": "Student added!", "id": sid})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/student/update", methods=["POST"])
@admin_required
def api_admin_student_update():
    d = request.json
    try:
        get_db().update_student(
            d['id'], d['name'], d['email'], d.get('department', 'Unassigned'),
            gr_number=d.get('gr_number'), enrollment_number=d.get('enrollment_number'),
            class_id=d.get('class_id'), batch_id=d.get('batch_id'), 
            roll_number=d.get('roll_number'), phone=d.get('phone')
        )
        return jsonify({"success": True, "message": "Student updated!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/student/delete", methods=["POST"])
@admin_required
def api_admin_student_delete():
    try:
        get_db().delete_student(request.json['id'])
        return jsonify({"success": True, "message": "Student deactivated."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/student/clear_all", methods=["POST"])
@admin_required
def api_admin_student_clear_all():
    try:
        db = get_db()
        db.clear_all_students()
        
        # Clear photos directory
        if os.path.exists(FACES_DIR):
            import shutil
            for filename in os.listdir(FACES_DIR):
                file_path = os.path.join(FACES_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f'Failed to delete {file_path}. Reason: {e}')
        
        # Reset face_database.json
        if os.path.exists(FACE_DB):
            with open(FACE_DB, "w") as f:
                json.dump({}, f)
                
        return jsonify({"success": True, "message": "All student records and photos cleared successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/student/link_face", methods=["POST"])
@admin_required
def api_admin_link_face():
    d = request.json
    try:
        get_db().link_student_face(d['id'], d['face_pid'])
        return jsonify({"success": True, "message": "Face linked to student!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/student/bulk_upload", methods=["POST"])
@admin_required
def api_admin_student_bulk_upload():
    if 'excel' not in request.files or 'zip' not in request.files:
        return jsonify({"success": False, "message": "Excel and ZIP files required."})
    
    excel_file = request.files['excel']
    zip_file = request.files['zip']
    
    try:
        # 1. Parse Data File
        filename = excel_file.filename.lower()
        if filename.endswith('.csv'):
            df = pd.read_csv(excel_file)
        else:
            # Read everything first to allow finding the header row
            df = pd.read_excel(excel_file, header=None)
            
        # Helper to normalize strings for comparison
        def normalize_str(s):
            if not s or pd.isna(s): return ""
            s = str(s).lower().strip().replace('.', '_').replace('-', '_').replace(' ', '_')
            while '__' in s: s = s.replace('__', '_')
            return s.strip('_')

        # Supporting variants of column names (post-normalization)
        col_map = {
            'gr_number': ['gr_number', 'gr_no', 'gr', 'student_id', 'roll_no', 'roll_number', 'sr_no', 'sr_number'],
            'enrollment_number': ['enroll_no', 'enrollment_number', 'enrollment_no', 'enrollment', 'enroll'],
            'name': ['name', 'full_name', 'student_name', 'student'],
            'email': ['email', 'email_id'],
            'department': ['department', 'stream', 'dept', 'specialization'],
            'roll_number': ['roll_number', 'roll_no', 'roll'],
            'class_name': ['class_name', 'class', 'sem_class'],
            'batch_name': ['batch_name', 'batch', 'lab_batch']
        }

        # Try to find which row is the header by looking for 'gr' or 'name' variants
        header_index = 0
        found_any = False
        
        # We'll check the first 10 rows for something that looks like a header
        for i in range(min(10, len(df))):
            row_vals = [normalize_str(v) for v in df.iloc[i]]
            # If this row contains "gr" or "name", assume it's the header
            if any(any(alias in v for v in row_vals) for alias in ['gr_no', 'name', 'email']):
                header_index = i
                found_any = True
                break
        
        if found_any:
            # Set columns to this row and drop everything above it
            df.columns = [normalize_str(c) for c in df.iloc[header_index]]
            df = df.iloc[header_index + 1:].reset_index(drop=True)
        else:
            # Revert to standard header logic if no "smart" header found
            if not filename.endswith('.csv'):
                df = pd.read_excel(excel_file) # Re-read normally
            df.columns = [normalize_str(c) for c in df.columns]

        # Final check and rename
        found_targets = {}
        for target, aliases in col_map.items():
            for alias in aliases:
                if alias in df.columns:
                    df = df.rename(columns={alias: target})
                    found_targets[target] = True
                    break
        
        if not all(found_targets.get(t) for t in ['gr_number', 'name', 'email']):
            missing = [t for t in ['gr_number', 'name', 'email'] if not found_targets.get(t)]
            detected = ", ".join([c for c in df.columns if not c.startswith('unnamed')])
            return jsonify({
                "success": False, 
                "message": f"Missing columns: {', '.join(missing)}. Detected: [{detected}]. Ensure your header is in the first few rows."
            })
        
        # 2. Open ZIP
        with zipfile.ZipFile(zip_file) as zf:
            zip_contents = zf.namelist()
            
            db = get_db()
            face_db = {}
            if os.path.exists(FACE_DB):
                with open(FACE_DB) as f:
                    face_db = json.load(f)
            
            added_count = 0
            photo_count = 0
            errors = []
            
            # Pre-fetch Class and Batch maps for resolution
            all_classes = db.get_all_classes()
            all_batches = db.get_all_batches()
            
            # Map name -> id for classes
            class_map = {str(c[2]).lower().strip(): c[0] for c in all_classes}
            
            def resolve_class(target_name):
                if not target_name: return None
                target = str(target_name).lower().strip()
                # 1. Exact match
                if target in class_map: return class_map[target]
                # 2. Fuzzy match (Excel name 'EK3' matches DB name '6EK3')
                for name_in_db, cid in class_map.items():
                    if target in name_in_db or name_in_db in target:
                        return cid
                return None

            # Batch map
            batch_map = {str(b[2]).lower().strip(): b[0] for b in all_batches}

            # Map basenames in ZIP to full paths to ignore folder structures
            zip_basename_map = {os.path.basename(p): p for p in zip_contents if not p.endswith('/')}
            
            os.makedirs(FACES_DIR, exist_ok=True)
            
            for index, row in df.iterrows():
                try:
                    def clean_id(val):
                        v = str(val).strip()
                        if '.' in v: v = v.split('.')[0]
                        return v if v.lower() != 'nan' else ''

                    gr_num = clean_id(row['gr_number'])
                    enroll = clean_id(row.get('enrollment_number', ''))
                    name   = str(row['name']).strip()
                    email  = str(row['email']).strip()
                    
                    if not gr_num or not name or name.lower() == 'nan': continue
                    
                    dept  = str(row.get('department', 'Unassigned'))
                    # Handle optional class/batch/roll/phone correctly (avoid NaNs)
                    def clean(val): return val if pd.notna(val) and str(val).lower() != 'nan' else None
                    
                    roll  = clean(row.get('roll_number'))
                    phone = clean(row.get('phone'))
                    
                    # Resolve IDs if names are provided
                    cid = clean(row.get('class_id'))
                    bid = clean(row.get('batch_id'))
                    
                    c_name = clean(row.get('class_name'))
                    if c_name and not cid:
                        cid = resolve_class(c_name)
                        
                    b_name = clean(row.get('batch_name'))
                    if b_name:
                        # Batch Renaming: 1A -> A, 1B -> B
                        b_str = str(b_name).strip().upper()
                        if len(b_str) == 2 and b_str[0] == '1' and b_str[1].isalpha():
                            b_str = b_str[1:] # Use just the letter
                        
                        if not bid:
                            bid = batch_map.get(b_str.lower())
                    
                    if cid: cid = int(float(cid))
                    if bid: bid = int(float(bid))
                    
                    # Add/Update in SQLite (Robust Upsert: Check GR, then Enrollment, then Email)
                    existing = db.get_student_by_gr_number(gr_num)
                    if not existing:
                        existing = db.get_student_by_enrollment(enroll)
                    if not existing:
                        existing = db.get_student_by_email(email)
                        
                    if existing:
                        db.update_student(existing[0], name, email, dept, gr_num, enroll, cid, bid, roll, phone)
                        stu_db_id = existing[0]
                    else:
                        stu_db_id = db.add_student(gr_num, enroll, name, email, dept, cid, bid, roll, phone)
                    added_count += 1
                    
                    # 3. Match Photo by GR NUMBER (Search all folders in ZIP)
                    photo_found = None
                    for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.PNG']:
                        search_name = f"{gr_num}{ext}"
                        if search_name in zip_basename_map:
                            photo_found = zip_basename_map[search_name]
                            break
                    
                    if photo_found:
                        safe_name = name.replace(' ', '_')
                        safe_id = gr_num.replace(' ', '_')
                        person_id = f"{safe_name}_{safe_id}"
                        
                        target_filename = f"{person_id}_front.jpg"
                        target_path = os.path.join(FACES_DIR, target_filename)
                        
                        with zf.open(photo_found) as pf:
                            with open(target_path, "wb") as f_out:
                                f_out.write(pf.read())
                        
                        # Update face_database.json
                        face_db[person_id] = {
                            'name': name,
                            'gr_number': gr_num,
                            'image_paths': [target_path],
                            'registered': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        photo_count += 1
                        
                        # Link in SQLite
                        db.link_student_face(stu_db_id, person_id)

                except Exception as row_err:
                    import traceback
                    traceback.print_exc()
                    errors.append(f"Row {index+2} ({row.get('name', '???')}): {str(row_err)}")
            
            with open(FACE_DB, 'w') as f:
                json.dump(face_db, f, indent=4)
                
            # If we uploaded photos, we should probably clear the embedding cache
            if photo_count > 0 and os.path.exists(EMB_CACHE):
                os.remove(EMB_CACHE)
                
            msg = f"Processed {added_count} students. {photo_count} photos mapped."
            if errors:
                msg += f" {len(errors)} errors encountered."
                print(f"[BulkError] {errors}")
                
            return jsonify({"success": True, "message": msg})
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Critical Error: {str(e)}"})


# ─────────────────────────────────────────────────────────────
# FACULTY ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/faculty/login", methods=["GET", "POST"])
def faculty_login():
    if request.method == "POST":
        data = request.json
        from auth import auth_manager
        token, msg = auth_manager.faculty_login(data.get('passcode'))
        if token:
            sess_data, _ = auth_manager.verify_session(token)
            session['faculty_token'] = token
            session['faculty_id'] = sess_data['faculty_id']
            session['faculty_name'] = sess_data['name']
            session['faculty_email'] = sess_data['email']
            
            # ── Auto-start Face Recognition if an active class exists
            active_class, _ = timetable_manager.get_active_class(session['faculty_id'])
            if active_class:
                from attendance_marker import attendance_marker
                session_id_tuple = attendance_marker.start_session(session['faculty_id'], active_class[0])
                sid = session_id_tuple[0] if session_id_tuple else None
                tid = active_class[0]
                
                # Update Flask session to track this class
                session['active_session'] = {
                    "timetable_id": tid,
                    "session_id": sid,
                    "class_name": active_class[2],
                    "time": f"{active_class[4]} - {active_class[5]}"
                }
                
                # Natively turn on the camera via MJPEG FaceEngine
                global ACTIVE_ENGINE
                if FaceEngine is not None and (ACTIVE_ENGINE is None or not ACTIVE_ENGINE.is_running):
                    ACTIVE_ENGINE = FaceEngine(timetable_id=tid, session_id=sid)
                    ACTIVE_ENGINE.start()

            return jsonify({"success": True})
        return jsonify({"success": False, "message": msg})
    return render_template("faculty_login.html")

@app.route("/faculty/logout")
def faculty_logout():
    session.clear()
    return redirect(url_for("faculty_login"))

def faculty_required(f):
    def wrap(*args, **kwargs):
        if not session.get("faculty_token"):
            return redirect(url_for("faculty_login"))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

@app.route("/faculty")
@faculty_required
def faculty_dashboard():
    fid = session['faculty_id']
    active_class, msg = timetable_manager.get_active_class(fid)
    
    session_info = None
    if active_class:
        from attendance_marker import attendance_marker
        session_id_tuple = attendance_marker.start_session(fid, active_class[0])
        session_info = {
            "timetable_id": active_class[0],
            "session_id": session_id_tuple[0] if session_id_tuple else None,
            "class_name": active_class[2],
            "time": f"{active_class[4]} - {active_class[5]}"
        }
        session['active_session'] = session_info
    
    return render_template("faculty_dashboard.html", 
                           faculty_name=session['faculty_name'],
                           active_class=session_info)

# FACULTY API
@app.route("/faculty/active_session")
@faculty_required
def faculty_active_session():
    return render_template("faculty_active_session.html", 
                           faculty_name=session.get('faculty_name'),
                           active_class=session.get('active_session'))

@app.route("/video_feed")
@faculty_required
def video_feed():
    global ACTIVE_ENGINE
    if ACTIVE_ENGINE and ACTIVE_ENGINE.is_running:
        return Response(ACTIVE_ENGINE.generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        # Fallback empty stream
        def empty_feed():
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n\r\n')
        return Response(empty_feed(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/api/faculty/stop_session", methods=["POST"])
@faculty_required
def api_stop_session():
    data = request.json
    pwd = data.get('passcode')
    
    # Verify password explicitly as user requested
    db = get_db()
    faculty = db.get_faculty_by_passcode(pwd)
    
    if not faculty or faculty[0] != session['faculty_id']:
        return jsonify({"success": False, "message": "Invalid password. Cannot stop class."})
        
    global ACTIVE_ENGINE
    if ACTIVE_ENGINE:
        # stop_and_export will terminate the camera safely and generate CSV files securely ordered
        success, msg = ACTIVE_ENGINE.stop_and_export()
        ACTIVE_ENGINE = None
        session.pop('active_session', None)
        return jsonify({"success": success, "message": msg})
        
    session.pop('active_session', None)
    return jsonify({"success": True, "message": "Session forcibly ended."})

@app.route("/api/faculty/group_photo_attend", methods=["POST"])
@faculty_required
def api_group_photo_attend():
    import base64
    session_info = session.get("active_session")
    if not session_info:
        return jsonify({"success": False, "message": "No active class session."})

    data = request.json
    img_b64 = data.get("image", "")
    if not img_b64:
        return jsonify({"success": False, "message": "No image provided."})

    try:
        img_bytes = base64.b64decode(img_b64.split(",")[-1])
    except Exception:
        return jsonify({"success": False, "message": "Invalid image data."})

    try:
        from group_recognizer import process_group_photo
        result = process_group_photo(img_bytes)
    except Exception as e:
        return jsonify({"success": False, "message": f"Recognition error: {e}"})

    if "error" in result:
        return jsonify({"success": False, "message": result["error"]})

    timetable_id = session_info["timetable_id"]
    marked = []
    skipped = []
    db = get_db()
    from attendance_marker import attendance_marker

    for person in result.get("recognized", []):
        gr_num = (person.get("gr_number") or "").strip()
        name   = person.get("name", "Unknown")
        try:
            # Look up by GR number, not integer PK
            stu = db.get_student_by_gr_number(gr_num) if gr_num else None

            if not stu:
                print(f"[Group] Auto-registering {name} ({gr_num}) into students table")
                dept  = "Unassigned"
                email = f"{(gr_num or name).replace(' ','_').lower()}@student.local"
                try:
                    db.add_student(gr_num or name, '', name, email, dept)
                    stu = db.get_student_by_gr_number(gr_num) if gr_num else None
                except Exception as reg_err:
                    print(f"[Group] Auto-register failed: {reg_err}")

            if stu:
                # stu[0] is the integer row-id primary key
                attendance_marker.mark_student_present(stu[0], timetable_id)
                marked.append(name)
            else:
                skipped.append(f"{name} (registration failed)")
        except Exception as e:
            skipped.append(f"{name} (error: {e})")

    return jsonify({
        "success":            True,
        "total_faces":        result.get("total_faces", 0),
        "recognized_count":   len(result.get("recognized", [])),
        "unrecognized_count": result.get("unrecognized_count", 0),
        "marked":             marked,
        "skipped":            skipped,
        "annotated_image":    result.get("annotated_image", ""),
        "yolo_used":          result.get("yolo_used", False),
    })

@app.route("/api/faculty/multi_photo_attend", methods=["POST"])
@faculty_required
def api_multi_photo_attend():
    """
    Accepts up to 3 base64 images. Runs face recognition on each,
    merges results (union), builds present/absent against full student roster.
    Does NOT mark attendance yet — returns data for the review page.
    """
    import base64
    session_info = session.get("active_session")
    if not session_info:
        return jsonify({"success": False, "message": "No active class session."})

    data   = request.json
    images = data.get("images", [])   # list of base64 strings
    if not images:
        return jsonify({"success": False, "message": "No images provided."})

    try:
        from group_recognizer import process_group_photo
    except Exception as e:
        return jsonify({"success": False, "message": f"Recognizer load error: {e}"})

    # Process each photo and merge recognized faces (by person_id)
    merged = {}          # person_id -> best recognition record
    annotated_images = []
    total_face_counts = []

    for img_b64 in images[:3]:
        try:
            img_bytes = base64.b64decode(img_b64.split(",")[-1])
            result    = process_group_photo(img_bytes)
        except Exception as e:
            print(f"[MultiPhoto] Error processing image: {e}")
            continue

        if "error" in result:
            continue

        annotated_images.append(result.get("annotated_image", ""))
        total_face_counts.append(result.get("total_faces", 0))

        for person in result.get("recognized", []):
            pid = person["person_id"]
            # Keep the record with highest confidence across photos
            if pid not in merged or person["confidence"] > merged[pid]["confidence"]:
                merged[pid] = person

    if not annotated_images:
        return jsonify({"success": False, "message": "Could not process any of the uploaded images."})

    # Build present list from merged recognitions
    present_list = list(merged.values())
    present_ids  = {p["person_id"] for p in present_list}

    # Build absent list: all students in face DB not recognized in any photo
    import json
    face_db = {}
    if os.path.exists(FACE_DB):
        with open(FACE_DB) as f:
            face_db = json.load(f)

    absent_list = [
        {
            "person_id":   pid,
            "name":        info.get("name", pid),
            "employee_id": info.get("employee_id", ""),
        }
        for pid, info in face_db.items()
        if pid not in present_ids
    ]

    return jsonify({
        "success":          True,
        "present":          present_list,
        "absent":           absent_list,
        "annotated_images": annotated_images,
        "total_faces":      sum(total_face_counts),
        "photos_processed": len(annotated_images),
    })


@app.route("/api/faculty/confirm_attendance", methods=["POST"])
@faculty_required
def api_confirm_attendance():
    """
    Receives the faculty-reviewed final present list.
    Marks all confirmed students present, exports CSVs.
    """
    session_info = session.get("active_session")
    if not session_info:
        return jsonify({"success": False, "message": "No active class session."})

    data         = request.json
    present_list = data.get("present", [])   # list of {person_id, name, employee_id, confidence}
    timetable_id = session_info["timetable_id"]

    db = get_db()
    from attendance_marker import attendance_marker
    marked  = []
    skipped = []

    for person in present_list:
        gr_num = (person.get("gr_number") or "").strip()
        name   = person.get("name", "Unknown")
        confidence = person.get("confidence", 0)
        try:
            stu = db.get_student_by_gr_number(gr_num) if gr_num else None
            if not stu:
                # Auto-register into student table
                email = f"{(gr_num or name).replace(' ','_').lower()}@student.local"
                try:
                    db.add_student(gr_num or name, '', name, email, "Unassigned")
                    stu = db.get_student_by_gr_number(gr_num) if gr_num else None
                except Exception:
                    pass
            if stu:
                attendance_marker.mark_student_present(stu[0], timetable_id)
                marked.append(name)
            else:
                skipped.append(f"{name} (could not register)")
        except Exception as e:
            skipped.append(f"{name} (error: {e})")

    # Export CSVs
    csv_msg = ""
    try:
        _, csv_msg = CSVExportService().export_faculty_attendance(
            session['faculty_id'], session['faculty_name']
        )
    except Exception as e:
        csv_msg = f"CSV export failed: {e}"

    return jsonify({
        "success":     True,
        "marked":      marked,
        "skipped":     skipped,
        "marked_count": len(marked),
        "csv_message": csv_msg,
    })

@app.route("/api/faculty/export_csv", methods=["POST"])
@faculty_required
def api_faculty_export_csv():
    try:
        fname, msg = CSVExportService().export_faculty_attendance(
            session['faculty_id'], session['faculty_name']
        )
        return jsonify({"success": bool(fname), "message": msg, "file": fname})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/admin/faces")
@admin_required
def admin_faces():
    return render_template("admin_faces.html")

@app.route("/api/admin/list_faces")
@admin_required
def api_list_faces():
    import json
    try:
        people = []
        if os.path.exists(FACE_DB):
            with open(FACE_DB, 'r') as f:
                db = json.load(f)
            for pid, info in db.items():
                people.append({
                    'person_id': pid,
                    'name': info.get('name', pid),
                    'employee_id': info.get('employee_id', ''),
                    'image_count': len(info.get('image_paths', [])),
                    'registered': info.get('registered', ''),
                })
        return jsonify({'success': True, 'people': people})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route("/api/admin/save_face", methods=["POST"])
@admin_required
def api_save_face():
    """Receive base64 image frames and save them to registered_faces/"""
    import base64, json
    import numpy as np
    import cv2
    data = request.json
    name = data.get('name', '').strip()
    gr_number = data.get('gr_number', '').strip() or 'NoGR'
    frames = data.get('frames', [])  # list of base64 JPEGs
    
    if not name or not frames:
        return jsonify({'success': False, 'message': 'Name and at least 1 frame required'})
    
    try:
        safe_name = name.replace(' ', '_')
        safe_id = gr_number.replace(' ', '_')
        person_id = f"{safe_name}_{safe_id}"
        os.makedirs(FACES_DIR, exist_ok=True)
        
        suffixes = ['front', 'left', 'right']
        image_paths = []
        for i, frame_b64 in enumerate(frames):
            suffix = suffixes[i] if i < len(suffixes) else f"extra_{i}"
            img_data = base64.b64decode(frame_b64.split(',')[-1])
            np_arr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            # Store ABSOLUTE path so training always finds the file
            path = os.path.join(FACES_DIR, f"{person_id}_{suffix}.jpg")
            cv2.imwrite(path, img)
            image_paths.append(path)
        
        db = {}
        if os.path.exists(FACE_DB):
            with open(FACE_DB, 'r') as f:
                db = json.load(f)
        
        db[person_id] = {
            'name': name,
            'gr_number': gr_number,
            'image_paths': image_paths,
            'registered': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(FACE_DB, 'w') as f:
            json.dump(db, f, indent=4)
        
        return jsonify({'success': True, 'message': f'{name} registered with 3 face images!', 'person_id': person_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route("/api/admin/delete_face", methods=["POST"])
@admin_required
def api_delete_face():
    import json
    data = request.json
    person_id = data.get('person_id')
    if not person_id:
        return jsonify({'success': False, 'message': 'person_id required'})
    try:
        db = {}
        if os.path.exists(FACE_DB):
            with open(FACE_DB, 'r') as f:
                db = json.load(f)
        info = db.pop(person_id, None)
        if info:
            for p in info.get('image_paths', []):
                try: os.remove(p)
                except: pass
        with open(FACE_DB, 'w') as f:
            json.dump(db, f, indent=4)
        if os.path.exists(EMB_CACHE): os.remove(EMB_CACHE)
        return jsonify({'success': True, 'message': f'{person_id} deleted. Re-train model to apply changes.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def augment_image(img):
    """Generate 4 augmented versions of an image to improve recognition robustess"""
    augments = []
    # 1. Flip
    augments.append(cv2.flip(img, 1))
    # 2. Slight rotation (+5 degrees)
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), 5, 1.0)
    augments.append(cv2.warpAffine(img, M, (w, h)))
    # 3. Slight rotation (-5 degrees)
    M = cv2.getRotationMatrix2D((w//2, h//2), -5, 1.0)
    augments.append(cv2.warpAffine(img, M, (w, h)))
    # 4. Brightness adjustment
    alpha = 1.2 # Contrast control
    beta = 10   # Brightness control
    augments.append(cv2.convertScaleAbs(img, alpha=alpha, beta=beta))
    return augments

@app.route("/api/admin/train_model", methods=["POST"])
@admin_required
def api_train_model():
    """Rebuild InsightFace embedding cache from all registered face images"""
    import json, pickle
    import numpy as np
    import cv2
    
    def _l2_normalize(x):
        return x / (np.linalg.norm(x) + 1e-10)
    
    try:
        if not os.path.exists(FACE_DB):
            return jsonify({'success': False, 'message': 'No faces registered yet.'})
        
        with open(FACE_DB, 'r') as f:
            db = json.load(f)
        
        if not db:
            return jsonify({'success': False, 'message': 'Face database is empty.'})
        
        from insightface.app import FaceAnalysis
        face_app = FaceAnalysis(name='buffalo_l')
        try:
            face_app.prepare(ctx_id=0, det_thresh=0.5)
        except:
            face_app.prepare(ctx_id=-1, det_thresh=0.5)
        
        cache = {}
        total_images = 0
        skipped = 0
        errors = 0
        
        for person_id, info in db.items():
            paths = info.get('image_paths', [])
            if 'image_path' in info:
                paths = [info['image_path']] + paths
            
            person_vecs = []
            valid_images = []
            
            for img_path in paths:
                # Sanitize paths
                filename = os.path.basename(img_path.replace('\\', '/'))
                abs_path = os.path.join(FACES_DIR, filename)
                
                if not os.path.exists(abs_path):
                    skipped += 1
                    continue
                
                img = cv2.imread(abs_path)
                if img is None:
                    errors += 1
                    continue
                
                valid_images.append(img)
                total_images += 1

            # If only one image, use augmentation to improve accuracy
            if len(valid_images) == 1:
                base_img = valid_images[0]
                valid_images.extend(augment_image(base_img))
                print(f"[Train] Augmenting {person_id} (single photo)")

            for img in valid_images:
                try:
                    faces = face_app.get(img)
                    if faces:
                        best = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
                        vec = _l2_normalize(best.embedding.astype(np.float32))
                        person_vecs.append(vec)
                    else:
                        errors += 1
                except Exception:
                    errors += 1
            
            if person_vecs:
                mean_vec = _l2_normalize(np.mean(person_vecs, axis=0))
                cache[person_id] = {'mean': mean_vec, 'all': person_vecs}
        
        with open(EMB_CACHE, 'wb') as f:
            pickle.dump(cache, f)
        
        global ACTIVE_ENGINE
        if ACTIVE_ENGINE:
            ACTIVE_ENGINE.embeddings = cache
        
        return jsonify({
            'success': True,
            'message': (
                f'✅ Training complete! '
                f'{len(cache)} persons embedded. '
                f'Errors: {errors}. Missing: {skipped}.'
            )
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
