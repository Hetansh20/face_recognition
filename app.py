from flask import Flask, render_template, request, session, jsonify, redirect, url_for
import os
import subprocess
from datetime import datetime
from database import Database
from timetable_manager import timetable_manager
from analytics_service import analytics_service
from csv_export_service import CSVExportService

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Native process tracking to prevent multiple windows
ACTIVE_PROCESSES = {}

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
    faculties = db.get_all_faculties() or []
    timetables = []
    f_map = {f[0]: f[1] for f in faculties}
    for f in faculties:
        for t in (db.get_faculty_timetables(f[0]) or []):
            timetables.append({
                "id": t[0],
                "faculty_name": f_map.get(t[1], "Unknown"),
                "class_name": t[2],
                "day": t[3],
                "start": t[4],
                "end": t[5],
                "room": t[6]
            })
    return render_template("admin_timetables.html", faculties=faculties, timetables=timetables)

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
            data['start_time'], data['end_time'], data.get('room')
        )
        if tid:
            return jsonify({"success": True, "message": msg})
        return jsonify({"success": False, "message": msg})
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


# ─────────────────────────────────────────────────────────────
# FACULTY ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/faculty/login", methods=["GET", "POST"])
def faculty_login():
    if request.method == "POST":
        data = request.json
        from auth import auth_manager
        token, msg = auth_manager.faculty_login(data.get('email'), data.get('passcode'))
        if token:
            sess_data, _ = auth_manager.verify_session(token)
            session['faculty_token'] = token
            session['faculty_id'] = sess_data['faculty_id']
            session['faculty_name'] = sess_data['name']
            session['faculty_email'] = sess_data['email']
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
@app.route("/api/faculty/start_recognition", methods=["POST"])
@faculty_required
def api_start_recognition():
    session_info = session.get('active_session')
    if not session_info:
        return jsonify({"success": False, "message": "No active class session found."})
    
    tid = session_info['timetable_id']
    sid = session_info['session_id']
    
    # Check if a process is already running for this session
    if sid in ACTIVE_PROCESSES and ACTIVE_PROCESSES[sid].poll() is None:
        return jsonify({"success": False, "message": "Recognition window is already open!"})
        
    try:
        # Launch the native OpenCV script decoupled from Web Server thread
        cmd = ["python", "insightface_attendance.py", "--timetable-id", str(tid), "--session-id", str(sid)]
        proc = subprocess.Popen(cmd)
        ACTIVE_PROCESSES[sid] = proc
        return jsonify({"success": True, "message": "Face recognition window opened natively on host!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/faculty/session_status", methods=["GET"])
@faculty_required
def api_session_status():
    session_info = session.get('active_session')
    if not session_info:
        return jsonify({"present_count": 0})
    
    try:
        db = get_db()
        # Get live count directly from the attendance logs for this timetable
        records = db.get_attendance_by_session(session_info['timetable_id'])
        present = len(records) if records else 0
        return jsonify({"present_count": present})
    except Exception:
        return jsonify({"present_count": 0})

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

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
