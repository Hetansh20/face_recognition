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
    emp_id = data.get('employee_id', '').strip() or 'NoID'
    frames = data.get('frames', [])  # list of 3 base64 JPEGs
    
    if not name or len(frames) < 3:
        return jsonify({'success': False, 'message': 'Name and 3 frames required'})
    
    try:
        safe_name = name.replace(' ', '_')
        safe_id = emp_id.replace(' ', '_')
        person_id = f"{safe_name}_{safe_id}"
        os.makedirs(FACES_DIR, exist_ok=True)
        
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
                abs_path = img_path if os.path.isabs(img_path) else os.path.join(BASE_DIR, img_path)
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
