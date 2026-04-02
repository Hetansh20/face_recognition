import cv2
import numpy as np
import time
import os
import json
import csv
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

from insightface.app import FaceAnalysis

def _l2_normalize(x):
    return x / (np.linalg.norm(x) + 1e-10)

class FaceEngine:
    def __init__(self, timetable_id=None, session_id=None):
        self.camera = None
        self.is_running = False
        
        self.timetable_id = timetable_id
        self.session_id = session_id
        self.session_marked = set()
        
        # Load InsightFace
        self.face_app = FaceAnalysis(name="buffalo_l")
        try:
            self.face_app.prepare(ctx_id=0, det_thresh=0.5)
            print("[FaceEngine] InsightFace loaded (GPU Base)")
        except:
            self.face_app.prepare(ctx_id=-1, det_thresh=0.5)
            print("[FaceEngine] InsightFace loaded (CPU Base)")
            
        # Database setup
        self.faces_dir = "registered_faces"
        self.database_file = "face_database.json"
        
        self.database = {}
        if os.path.exists(self.database_file):
            try:
                with open(self.database_file, 'r') as f:
                    self.database = json.load(f)
            except: pass
            
        self.embeddings = {}
        cache_file = "face_embeddings_insightface.pkl"
        if os.path.exists(cache_file):
            import pickle
            try:
                with open(cache_file, 'rb') as f:
                    self.embeddings = pickle.load(f)
            except: pass
            
        # Recognition buffers
        self.vote_buffer = []
        self.vote_window = 7
        self.last_recognized = None
        self.status_message = "Ready"

    def start(self):
        """Activates camera and internal streaming thread"""
        if not self.is_running:
            self.camera = cv2.VideoCapture(0)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.is_running = True
            self.status_message = "Active — Scanning..."

    def generate_frames(self):
        """Generator that yields JPG frames for Flask MJPEG endpoint."""
        while self.is_running:
            success, frame = self.camera.read()
            if not success:
                break
            else:
                # Process frame for faces
                processed_frame = self.process_frame(frame)
                ret, buffer = cv2.imencode('.jpg', processed_frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.03)

    def process_frame(self, frame):
        """Runs InsightFace + Attendance logic and draws onto frame"""
        try:
            faces = self.face_app.get(frame)
            if not faces:
                self.status_message = "No faces detected"
                return self.draw_hud(frame, [])
                
            # Focus simply on the largest face in frame for fast logic
            best_face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
            live_vec = _l2_normalize(best_face.embedding.astype(np.float32))

            # Find matching embedding
            all_dists = []
            for pid, data in self.embeddings.items():
                if isinstance(data, dict) and 'all' in data:
                    min_dist = float('inf')
                    for stored_vec in data['all']:
                        d = 1.0 - float(np.dot(live_vec, stored_vec))
                        if d < min_dist:
                            min_dist = d
                    all_dists.append((pid, min_dist))

            if not all_dists:
                self.status_message = "No reference embeddings loaded"
                return self.draw_hud(frame, faces)

            all_dists.sort(key=lambda x: x[1])
            best_pid, best_dist = all_dists[0]
            sec_dist = all_dists[1][1] if len(all_dists) > 1 else max(1.0, best_dist+0.2)
            
            threshold = 0.45
            margin = 0.05
            
            # Simple voting logic
            decisive = (best_dist < threshold and (sec_dist - best_dist) >= margin)
            
            if decisive:
                self.vote_buffer.append((best_pid, best_dist))
            else:
                self.vote_buffer.append((None, 1.0))
                
            if len(self.vote_buffer) > self.vote_window:
                self.vote_buffer.pop(0)
                
            valid_votes = [v[0] for v in self.vote_buffer if v[0] is not None]
            winner_pid = None
            if valid_votes:
                counts = {}
                for v in valid_votes: counts[v] = counts.get(v, 0) + 1
                best_cand = max(counts.items(), key=lambda x: x[1])
                if best_cand[1] >= 4:
                    winner_pid = best_cand[0]
                    
            if winner_pid:
                self.trigger_attendance(winner_pid)
                info = self.database.get(winner_pid, {})
                msg = f"✅ {info.get('name', winner_pid)}"
                self.status_message = msg
                self.vote_buffer.clear()
            elif not decisive:
                self.status_message = f"Scanning... distance {best_dist:.2f}"
            else:
                self.status_message = "Collecting votes..."
                
            return self.draw_hud(frame, faces, winner_pid)
            
        except Exception as e:
            print(f"[FaceEngine] Error: {e}")
            return frame

    def draw_hud(self, frame, faces, current_winner=None):
        """Draw bounding boxes cleanly onto the frame"""
        viz = frame.copy()
        
        # Draw status bar
        cv2.rectangle(viz, (0, 0), (viz.shape[1], 40), (0,0,0), -1)
        cv2.putText(viz, "InsightFace Engine — " + self.status_message, (15, 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0) if "✅" in self.status_message else (200,200,200), 2)
                    
        for f in faces:
            box = f.bbox.astype(int)
            color = (0, 255, 0) if current_winner else (255, 150, 0)
            cv2.rectangle(viz, (box[0], box[1]), (box[2], box[3]), color, 2)
            
        return viz

    def trigger_attendance(self, person_id):
        if person_id in self.session_marked:
            return # Already marked!
            
        print(f"[FaceEngine] Marking attendance natively for {person_id}")
        self.session_marked.add(person_id)
        
        if self.timetable_id is not None:
            try:
                from attendance_marker import attendance_marker
                info = self.database.get(person_id)
                if info:
                    emp_id = info.get('employee_id', "").strip()
                    from database import Database
                    db = Database()
                    
                    stu = None
                    if emp_id:
                        stu = db.get_student_by_student_id(emp_id)
                        
                    if not stu:
                        name_lower = info.get('name', '').lower()
                        for s in db.get_all_students() or []:
                            if s[2].lower() == name_lower:
                                stu = s
                                break
                                
                    if stu:
                        attendance_marker.mark_student_present(stu[0], self.timetable_id)
                    else:
                        name = info.get('name', 'Unknown')
                        if not emp_id:
                            emp_id = 'AUTO_' + name.replace(' ', '_') + str(int(time.time()))
                        dept = 'Unassigned'
                        new_email = f"{emp_id}@auto.reg"
                        db.add_student(emp_id, name, new_email, dept)
                        new_stu = db.get_student_by_student_id(emp_id)
                        if new_stu:
                            attendance_marker.mark_student_present(new_stu[0], self.timetable_id)

            except Exception as e:
                print(f"[FaceEngine DB Error] {e}")

    def stop_and_export(self):
        """Stops the camera and queries SQLite for CSV generation"""
        self.is_running = False
        if self.camera:
            self.camera.release()
            
        # Export CSV logic equivalent to insightface_attendance.py stop
        if self.timetable_id is not None:
            try:
                from database import Database
                db = Database()
                
                # Commit final internal session updates if active
                if self.session_id:
                    try:
                        db.end_session(self.session_id, len(self.session_marked))
                    except: pass
                
                export_dir = "attendance_reports"
                os.makedirs(export_dir, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                
                tt = db.get_timetable_by_id(self.timetable_id)
                cn = tt[2].replace(" ", "_") if tt else "Class"
                
                all_s = db.get_all_students() or []
                att_r = db.get_attendance_by_session(self.timetable_id) or []
                present_s = set(r[1] for r in att_r)
                
                p_csv = []
                a_csv = []
                for s in all_s:
                    rec = {'ID': str(s[1]), 'Name': s[2], 'Email': s[3], 'Department': s[4]}
                    if s[0] in present_s:
                        p_csv.append(rec)
                    else:
                        a_csv.append(rec)
                        
                p_csv.sort(key=lambda x: x['ID'])
                a_csv.sort(key=lambda x: x['ID'])
                
                if p_csv:
                    with open(os.path.join(export_dir, f"{cn}_Present_{timestamp}.csv"), 'w', newline='', encoding='utf-8') as f:
                        w = csv.DictWriter(f, fieldnames=['ID','Name','Email','Department'])
                        w.writeheader()
                        w.writerows(p_csv)
                if a_csv:
                    with open(os.path.join(export_dir, f"{cn}_Absent_{timestamp}.csv"), 'w', newline='', encoding='utf-8') as f:
                        w = csv.DictWriter(f, fieldnames=['ID','Name','Email','Department'])
                        w.writeheader()
                        w.writerows(a_csv)
                        
                return True, "Export successful"
            except Exception as e:
                print(f"[FaceEngine CSV Error] {e}")
                return False, str(e)
        
        return True, "Stopped without export"
