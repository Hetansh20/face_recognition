from flask import Flask, render_template, request, session, jsonify, redirect, url_for, Response
import os
import subprocess
from datetime import datetime
from database import Database
from timetable_manager import timetable_manager
from analytics_service import analytics_service
from csv_export_service import CSVExportService

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
        get_db().add_student(data['student_id'], data['name'], data['email'], data['department'])
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
        sid = get_db().add_semester(data['number'], data['label'])
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
    d = request.json
    try:
        cid = get_db().add_class(d['semester_id'], d['name'], d.get('section'))
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
    class_map = {c[0]: c[2] for c in classes}   # id -> name
    batch_map = {b[0]: b[2] for b in all_batches}  # id -> name

    # Faces in face_database.json not linked to any student
    face_db = {}
    if os.path.exists(FACE_DB):
        with open(FACE_DB) as f:
            face_db = _json.load(f)
    linked_pids = {s[9] for s in students if s[9]}  # face_pid column
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
        students_json=_json.dumps([list(s) for s in students]),
        classes_json=_json.dumps([{"id": c[0], "name": c[2]} for c in classes]),
        batches_json=_json.dumps([{"id": b[0], "name": b[2], "class_id": b[1]} for b in all_batches]),
    )

@app.route("/api/admin/student/add", methods=["POST"])
@admin_required
def api_admin_student_add():
    d = request.json
    try:
        sid = get_db().add_student(
            d['student_id'], d['name'], d['email'], d.get('department', 'Unassigned'),
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
            d.get('class_id'), d.get('batch_id'), d.get('roll_number'), d.get('phone')
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

@app.route("/api/admin/student/link_face", methods=["POST"])
@admin_required
def api_admin_link_face():
    d = request.json
    try:
        get_db().link_student_face(d['student_id'], d['face_pid'])
        return jsonify({"success": True, "message": "Face linked to student!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/api/admin/student/bulk_import_faces", methods=["POST"])
@admin_required
def api_bulk_import_faces():
    """
    Reads face_database.json and auto-creates a student DB record for every
    face entry that does not already have a matching student_id in the DB.
    Also links the face_pid on the created record.
    """
    import json as _json
    if not os.path.exists(FACE_DB):
        return jsonify({"success": False, "message": "face_database.json not found."})

    with open(FACE_DB) as f:
        face_db = _json.load(f)

    db = get_db()
    created = 0
    skipped = 0
    errors  = []

    for pid, info in face_db.items():
        name    = info.get("name", pid)
        emp_id  = (info.get("employee_id") or "").strip()
        student_id = emp_id or pid   # fall back to pid key if no employee_id

        # Skip if already in DB by student_id
        existing = db.get_student_by_student_id(student_id)
        if existing:
            # If not yet linked, link it now
            if not existing[9]:   # face_pid at index 9
                db.link_student_face(existing[0], pid)
            skipped += 1
            continue

        # Create a new student record
        email = f"{student_id.replace(' ','_').lower()}@student.local"
        try:
            new_id = db.add_student(
                student_id, name, email, "Unassigned",
                None, None, None, None, pid   # face_pid = pid
            )
            created += 1
        except Exception as e:
            errors.append(f"{name}: {e}")

    msg = f"✅ Imported {created} student(s). {skipped} already existed."
    if errors:
        msg += f" ⚠️ {len(errors)} error(s): {'; '.join(errors[:3])}"
    return jsonify({"success": True, "message": msg, "created": created, "skipped": skipped})


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
        emp_id = (person.get("employee_id") or "").strip()
        name   = person.get("name", "Unknown")
        try:
            # Look up by roll number (student_id field), not integer PK
            stu = db.get_student_by_student_id(emp_id) if emp_id else None

            if not stu:
                # Auto-register the face-db person into the student table
                print(f"[Group] Auto-registering {name} ({emp_id}) into students table")
                dept  = "Unassigned"
                email = f"{(emp_id or name).replace(' ','_').lower()}@student.local"
                try:
                    db.add_student(emp_id or name, name, email, dept)
                    stu = db.get_student_by_student_id(emp_id) if emp_id else None
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
        emp_id = (person.get("employee_id") or "").strip()
        name   = person.get("name", "Unknown")
        confidence = person.get("confidence", 0)
        try:
            stu = db.get_student_by_student_id(emp_id) if emp_id else None
            if not stu:
                # Auto-register into student table
                email = f"{(emp_id or name).replace(' ','_').lower()}@student.local"
                try:
                    db.add_student(emp_id or name, name, email, "Unassigned")
                    stu = db.get_student_by_student_id(emp_id) if emp_id else None
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
    db = get_db()
    # Pass semesters to populate the capture/add student dropdown
    semesters = db.get_all_semesters()
    return render_template("admin_faces.html", semesters=semesters)

@app.route("/api/admin/list_faces")
@admin_required
def api_list_faces():
    import json
    try:
        people = []
        if os.path.exists(FACE_DB):
            with open(FACE_DB, 'r') as f:
                db_faces = json.load(f)
            
            db = get_db()
            face_map = db.get_face_pid_map()
            class_map = {c[0]: c[2] for c in db.get_classes()}
            batch_map = {b[0]: b[2] for b in db.get_batches()}

            for pid, info in db_faces.items():
                linked = None
                stu = face_map.get(pid)
                if stu:
                    # student_id is index 1, name index 2, class index 5, batch 6, roll 7
                    linked = {
                        'student_id': stu[1],
                        'name': stu[2],
                        'class': class_map.get(stu[5], '?'),
                        'batch': batch_map.get(stu[6], '?'),
                        'roll': stu[7] or 'No Roll'
                    }

                people.append({
                    'person_id': pid,
                    'name': info.get('name', pid),
                    'employee_id': info.get('employee_id', ''),
                    'image_count': len(info.get('image_paths', [])),
                    'registered': info.get('registered', ''),
                    'linked_stu': linked
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
    emp_id = data.get('employee_id', '').strip() or 'NoID'
    email = data.get('email', '').strip()
    dept = data.get('department', '').strip()
    class_id = data.get('class_id')
    batch_id = data.get('batch_id')
    roll = data.get('roll_number')
    phone = data.get('phone')
    frames = data.get('frames', [])  # list of 3 base64 JPEGs
    
    if not name or not email or len(frames) < 3:
        return jsonify({'success': False, 'message': 'Name, Email, and 3 frames required'})
    
    try:
        safe_name = name.replace(' ', '_')
        safe_id = emp_id.replace(' ', '_')
        person_id = f"{safe_name}_{safe_id}"
        os.makedirs(FACES_DIR, exist_ok=True)
        
        db = get_db()
        existing = db.get_student_by_student_id(emp_id)
        if existing:
            db.update_student(existing[0], emp_id, name, email, dept, class_id, batch_id, roll, phone, face_pid=person_id)
        else:
            db.add_student(emp_id, name, email, dept, class_id, batch_id, roll, phone, face_pid=person_id)
        
        suffixes = ['front', 'left', 'right']
        image_paths = []
        for frame_b64, suffix in zip(frames[:3], suffixes):
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
            'employee_id': emp_id,
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
            for img_path in paths:
                # Sanitize paths containing Windows slashes or absolute paths
                filename = os.path.basename(img_path.replace('\\', '/'))
                abs_path = os.path.join(FACES_DIR, filename)
                
                if not os.path.exists(abs_path):
                    print(f"[Train] Missing file: {abs_path}")
                    skipped += 1
                    continue
                total_images += 1
                try:
                    img = cv2.imread(abs_path)
                    if img is None:
                        print(f"[Train] Could not decode image: {abs_path}")
                        errors += 1
                        continue
                    faces = face_app.get(img)
                    if faces:
                        best = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
                        vec = _l2_normalize(best.embedding.astype(np.float32))
                        person_vecs.append(vec)
                        print(f"[Train] ✓ {info.get('name', person_id)} — {abs_path}")
                    else:
                        print(f"[Train] No face detected in: {abs_path}")
                        errors += 1
                except Exception as e:
                    print(f"[Train] Error on {abs_path}: {e}")
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
                f'{len(cache)} persons embedded from {total_images} images. '
                f'Errors/No-face: {errors}. Missing files: {skipped}.'
            )
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
