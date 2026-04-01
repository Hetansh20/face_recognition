"""
InsightFace Attendance System — High Accuracy & High Speed
=============================================================
Uses the InsightFace library (buffalo_l model = ArcFace + RetinaFace)
which runs highly optimized via ONNX Runtime without TensorFlow.

Key facts:
  - 512-dimensional embeddings
  - InsightFace default cosine threshold: ~0.45 
  - Sub-100ms inference time (much faster than deepface)

Run:
  python insightface_attendance.py
"""

import cv2
import tkinter as tk
from tkinter import messagebox, simpledialog
from PIL import Image, ImageTk
import json
import os
import numpy as np
from datetime import datetime
import threading
import time
import pickle

from insightface.app import FaceAnalysis

# ── Constants ────────────────────────────────────────────────────────────────
EMBEDDING_CACHE = "face_embeddings_insightface.pkl"
DISTANCE_METRIC = "cosine"

def _l2_normalize(x):
    return x / (np.linalg.norm(x) + 1e-10)

class InsightFaceAttendanceSystem:
    def __init__(self, root, timetable_id=None, session_id=None, on_attendance_marked=None):
        self.root = root
        self.root.title("InsightFace Attendance System — Lightning Fast")
        self.root.geometry("1200x720")
        self.root.configure(bg='#0d1117')

        # ── Optional SQLite integration (set by faculty_ui.py) ──────────────
        # When timetable_id is provided, recognised faces are also written to
        # the `attendance` table in attendance_system.db in addition to CSV.
        self.timetable_id          = timetable_id
        self.session_id            = session_id
        self.on_attendance_marked  = on_attendance_marked  # callback(name)

        # State
        self.camera           = None
        self.is_running       = False
        self.current_frame    = None
        self.mode             = "idle"
        self.processing       = False
        self.face_app         = None

        # Multi-frame voting buffer
        self.vote_buffer      = []
        self.vote_window      = 7
        self.last_name_shown  = None

        # Paths
        self.faces_dir        = "registered_faces"
        self.database_file    = "face_database.json"
        self.attendance_file  = "attendance_insightface.csv"
        self.embedding_cache  = EMBEDDING_CACHE

        os.makedirs(self.faces_dir, exist_ok=True)

        # Load database + auto-import from disk
        self.load_database()
        self.auto_sync_database()
        self.embeddings = self.load_embeddings()

        # Setup GUI
        self.setup_gui()
        self.update_faces_list()
        self._mark_training_status()

        # Init InsightFace model
        threading.Thread(target=self.init_model, daemon=True).start()

    def init_model(self):
        self.status_label.config(text="Status: Loading InsightFace models...", fg='#f1c40f')
        try:
            # name='buffalo_l' automatically uses ArcFace + RetinaFace
            self.face_app = FaceAnalysis(name="buffalo_l")
            
            # Try GPU first (ctx_id=0), fallback to CPU (ctx_id=-1)
            try:
                self.face_app.prepare(ctx_id=0, det_thresh=0.5)
                print("[Model] InsightFace loaded (GPU Mode / ctx_id=0)")
            except:
                self.face_app.prepare(ctx_id=-1, det_thresh=0.5)
                print("[Model] InsightFace loaded (CPU Mode / ctx_id=-1)")
                
            self.root.after(0, lambda: self.status_label.config(
                text="Status: Models Loaded — System Ready", fg='#2ecc71'))
            
            if not self.embeddings and self.database:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Action Required", "Models loaded! Click 'Train Model' to extract embeddings for the first time."))
        
        except RuntimeError as e:
            if "not found" in str(e).lower():
                self.root.after(0, lambda: messagebox.showerror(
                    "Models Missing", 
                    "InsightFace models not found.\n"
                    "Please run this command in your terminal to download them:\n\n"
                    "python -c \"from insightface.model_zoo import model_zoo; model_zoo.get_model('buffalo_l')\""))
            else:
                err_msg = str(e)
                self.root.after(0, lambda m=err_msg: messagebox.showerror("Init Error", m))
        except Exception as e:
            err_msg = f"Could not load models: {e}"
            self.root.after(0, lambda m=err_msg: messagebox.showerror("Error", m))

    # ── Database ─────────────────────────────────────────────────────────────

    def load_database(self):
        try:
            if os.path.exists(self.database_file):
                with open(self.database_file, 'r') as f:
                    self.database = json.load(f)
            else:
                self.database = {}
                self.save_database()
        except Exception as e:
            print(f"[DB] Load error: {e}")
            self.database = {}

    def auto_sync_database(self):
        added = 0
        person_images: dict = {}
        for fname in os.listdir(self.faces_dir):
            if not fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            for suffix in ('_front', '_left', '_right'):
                if fname.lower().endswith(suffix + os.path.splitext(fname)[1].lower()):
                    person_id = fname[:fname.lower().rfind(suffix)]
                    person_images.setdefault(person_id, []).append(
                        os.path.join(self.faces_dir, fname)
                    )
                    break

        for person_id, paths in person_images.items():
            if person_id in self.database:
                continue

            parts = person_id.split('_')
            id_idx = None
            for i, p in enumerate(parts):
                if p.isdigit() and len(p) >= 5:
                    id_idx = i
                    break
            if id_idx is not None:
                name_parts = parts[:id_idx]
                emp_id     = parts[id_idx]
            else:
                name_parts = parts
                emp_id     = ""

            name = " ".join(name_parts)
            paths_sorted = sorted(paths)

            self.database[person_id] = {
                "name"       : name,
                "employee_id": emp_id,
                "image_paths": paths_sorted,
                "registered" : "imported-from-disk",
            }
            added += 1
            print(f"[Sync] Auto-imported: {name} ({emp_id})")

        if added:
            self.save_database()
            print(f"[Sync] ✅ Imported {added} missing students from registered_faces/")

    def save_database(self):
        try:
            with open(self.database_file, 'w') as f:
                json.dump(self.database, f, indent=4)
        except Exception as e:
            print(f"[DB] Save error: {e}")

    # ── Embedding cache (the "training" step) ─────────────────────────────

    def load_embeddings(self):
        if os.path.exists(self.embedding_cache):
            try:
                with open(self.embedding_cache, 'rb') as f:
                    cache = pickle.load(f)
                print(f"[TRAIN] Loaded {len(cache)} cached InsightFace embeddings.")
                return cache
            except Exception as e:
                print(f"[TRAIN] Cache corrupt, will retrain: {e}")
        return {}

    def save_embeddings(self, cache):
        with open(self.embedding_cache, 'wb') as f:
            pickle.dump(cache, f)

    def train_model(self):
        if not self.face_app:
            messagebox.showwarning("Warning", "InsightFace models not loaded yet. Please wait.")
            return
            
        self.train_btn.config(state=tk.DISABLED, text="Training…")
        self.status_label.config(text="Status: Training InsightFace — please wait…", fg='#f39c12')
        self.root.update_idletasks()

        def _train():
            cache  = {}
            errors = 0
            total  = 0
            n_persons = len(self.database)

            for idx, (person_id, info) in enumerate(self.database.items(), 1):
                name = info.get('name', person_id)

                self.root.after(0, lambda n=name, i=idx:
                    self.status_label.config(
                        text=f"Training {i}/{n_persons}: {n} …", fg='#f39c12'
                    )
                )
                print(f"[TRAIN] {idx}/{n_persons}: {name}")

                paths = info.get('image_paths', [])
                if 'image_path' in info:
                    paths = [info['image_path']] + paths

                person_vecs = []
                for img_path in paths:
                    if not os.path.exists(img_path):
                        continue
                    total += 1
                    try:
                        img_bgr = cv2.imread(img_path)
                        # InsightFace expects BGR image (OpenCV default)
                        faces = self.face_app.get(img_bgr)
                        if faces:
                            # Largest bounding box
                            best_face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
                            vec = _l2_normalize(best_face.embedding.astype(np.float32))
                            person_vecs.append(vec)
                    except Exception as e:
                        errors += 1
                        print(f"[TRAIN]   ✗ Skip: {e}")

                if person_vecs:
                    mean_vec = np.mean(person_vecs, axis=0)
                    mean_vec = _l2_normalize(mean_vec)
                    # Min-of-all caching strategy
                    cache[person_id] = {
                        'mean': mean_vec,
                        'all' : person_vecs,
                    }
                    print(f"[TRAIN]   ✓ {len(person_vecs)}/3 images OK")
                else:
                    print(f"[TRAIN]   ✗ No faces detected in images — skipped")

            self.embeddings = cache
            self.save_embeddings(cache)

            msg = (f"InsightFace Training complete!\n"
                   f"Processed : {total} images\n"
                   f"Persons   : {len(cache)}/{n_persons}\n"
                   f"Skipped   : {errors} images")

            self.root.after(0, lambda: self._on_train_done(msg))

        threading.Thread(target=_train, daemon=True).start()

    def _on_train_done(self, msg):
        self.train_btn.config(state=tk.NORMAL, text="🧠 Train Model (InsightFace)")
        self.status_label.config(text="Status: InsightFace trained — ready to recognize", fg='#2ecc71')
        self._mark_training_status()
        messagebox.showinfo("Training Complete", msg)

    def _mark_training_status(self):
        n_trained = len(self.embeddings)
        n_reg     = len(self.database)
        if n_trained == 0:
            self.train_status_lbl.config(
                text=f"⚠ InsightFace NOT trained ({n_reg} registered)", fg='#e74c3c')
        elif n_trained < n_reg:
            self.train_status_lbl.config(
                text=f"⚠ Partial ({n_trained}/{n_reg} persons)", fg='#f39c12')
        else:
            self.train_status_lbl.config(
                text=f"✅ InsightFace trained ({n_trained} persons)", fg='#2ecc71')

    # ── GUI ──────────────────────────────────────────────────────────────────

    def setup_gui(self):
        title = tk.Label(
            self.root,
            text="🚀 InsightFace Attendance System",
            font=('Segoe UI', 18, 'bold'),
            bg='#161b22', fg='#58a6ff', pady=12
        )
        title.pack(fill=tk.X)

        main = tk.Frame(self.root, bg='#0d1117')
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        # Left — Camera
        left = tk.Frame(main, bg='#161b22', relief=tk.FLAT, bd=0)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        tk.Label(left, text="📷 Camera Feed", font=('Segoe UI', 11, 'bold'),
                 bg='#161b22', fg='#8b949e').pack(pady=(8,2))

        self.video_label = tk.Label(left, bg='#010409', width=72, height=28)
        self.video_label.pack(padx=10, pady=6, fill=tk.BOTH, expand=True)

        self.status_label = tk.Label(
            left, text="Status: Camera Off",
            font=('Segoe UI', 10), bg='#161b22', fg='#8b949e', pady=6
        )
        self.status_label.pack()

        self.conf_label = tk.Label(
            left, text="",
            font=('Segoe UI', 10, 'bold'), bg='#161b22', fg='#d29922', pady=2
        )
        self.conf_label.pack()

        # Right — Controls
        right = tk.Frame(main, bg='#161b22', relief=tk.FLAT, bd=0, width=310)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        right.pack_propagate(False)

        ctrl = tk.Frame(right, bg='#161b22', pady=12)
        ctrl.pack(fill=tk.X, padx=14)

        tk.Label(ctrl, text="Controls", font=('Segoe UI', 13, 'bold'),
                 bg='#161b22', fg='#c9d1d9').pack(pady=(0,10))

        def btn(parent, text, cmd, color, state=tk.NORMAL):
            b = tk.Button(parent, text=text, command=cmd,
                          font=('Segoe UI', 10, 'bold'),
                          bg=color, fg='white', height=2,
                          activebackground=color, relief=tk.FLAT,
                          cursor='hand2', state=state)
            b.pack(fill=tk.X, pady=4)
            return b

        self.cam_btn   = btn(ctrl, "▶ Start Camera",          self.toggle_camera,   '#238636')
        self.train_btn = btn(ctrl, "🧠 Train Model (Insight)", self.train_model,     '#8957e5')
        self.reg_btn   = btn(ctrl, "➕ Register Face",          self.register_mode,   '#1f6feb', tk.DISABLED)
        self.rec_btn   = btn(ctrl, "🔍 Start Recognition",     self.recognize_mode,  '#da3633', tk.DISABLED)
        self.stop_btn  = btn(ctrl, "⏹ Stop",                   self.stop_mode,       '#484f58', tk.DISABLED)
        btn(ctrl, "📋 View Attendance",  self.view_attendance,   '#8957e5')
        btn(ctrl, "🗑 Delete Student",   self.show_delete_dialog,'#da3633')

        # Threshold slider — InsightFace defaults to around ~0.45 for ArcFace
        tk.Label(ctrl, text="Similarity Threshold",
                 font=('Segoe UI', 9), bg='#161b22', fg='#8b949e').pack(pady=(10,0))
        self.threshold_var = tk.DoubleVar(value=0.45)
        self.thresh_slider = tk.Scale(
            ctrl, from_=0.20, to=0.70, resolution=0.01,
            orient=tk.HORIZONTAL, variable=self.threshold_var,
            bg='#161b22', fg='#c9d1d9', troughcolor='#21262d',
            highlightthickness=0, font=('Segoe UI', 9)
        )
        self.thresh_slider.pack(fill=tk.X)
        tk.Label(ctrl, text="← stricter    looser →",
                 font=('Segoe UI', 8), bg='#161b22', fg='#484f58').pack()

        # Training status
        self.train_status_lbl = tk.Label(
            ctrl, text="", font=('Segoe UI', 9, 'bold'),
            bg='#161b22', fg='#e74c3c'
        )
        self.train_status_lbl.pack(pady=(8,0))

        # Registered faces list
        tk.Label(right, text="Registered Faces", font=('Segoe UI', 11, 'bold'),
                 bg='#161b22', fg='#c9d1d9', pady=6).pack()

        list_frame = tk.Frame(right, bg='#161b22')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)

        sb = tk.Scrollbar(list_frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.faces_list = tk.Listbox(
            list_frame, font=('Segoe UI', 9),
            bg='#0d1117', fg='#c9d1d9',
            selectbackground='#1f6feb',
            yscrollcommand=sb.set, relief=tk.FLAT
        )
        self.faces_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self.faces_list.yview)

        tk.Button(right, text="Delete Selected", command=self.delete_face,
                  font=('Segoe UI', 9), bg='#da3633', fg='white',
                  relief=tk.FLAT, cursor='hand2').pack(pady=8)

    def update_faces_list(self):
        self.faces_list.delete(0, tk.END)
        for pid, info in self.database.items():
            self.faces_list.insert(tk.END, f"{info['name']}  ({info.get('employee_id','N/A')})")

    # ── Camera ───────────────────────────────────────────────────────────────

    def toggle_camera(self):
        if not self.is_running:
            try:
                self.camera = cv2.VideoCapture(0)
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                if not self.camera.isOpened():
                    messagebox.showerror("Error", "Cannot open camera!")
                    return
                self.is_running = True
                self.cam_btn.config(text="⏹ Stop Camera", bg='#da3633')
                self.reg_btn.config(state=tk.NORMAL)
                self.rec_btn.config(state=tk.NORMAL)
                self.status_label.config(text="Status: Camera Active")
                self.update_frame()
            except Exception as e:
                messagebox.showerror("Error", f"Camera error: {e}")
        else:
            self.is_running = False
            self.mode = "idle"
            if self.camera:
                self.camera.release()
            self.cam_btn.config(text="▶ Start Camera", bg='#238636')
            self.reg_btn.config(state=tk.DISABLED)
            self.rec_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)
            self.video_label.config(image='')
            self.status_label.config(text="Status: Camera Off")
            self.conf_label.config(text="")

    def update_frame(self):
        if self.is_running and self.camera:
            ret, frame = self.camera.read()
            if ret:
                self.current_frame = frame.copy()
                display = frame.copy()

                if self.mode == "register":
                    display = self.draw_registration_box(display)
                elif self.mode == "recognize" and self.last_name_shown:
                    cv2.putText(display, f">> {self.last_name_shown}", (20, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 100), 2)

                self.display_frame(display)
            self.root.after(30, self.update_frame)

    def display_frame(self, frame):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb).resize((760, 520), Image.Resampling.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
        except Exception as e:
            print(f"[Display] {e}")

    # ── Registration ─────────────────────────────────────────────────────────

    def register_mode(self):
        if not self.face_app:
            messagebox.showwarning("Warning", "InsightFace models not loaded yet. Please wait.")
            return

        self.mode = "register"
        self.registration_step = 0
        self.registration_images = []
        self.status_label.config(text="Status: Registration — Step 1/3  (Look STRAIGHT)")
        self.reg_btn.config(state=tk.DISABLED)
        self.rec_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.root.bind('<space>', self.capture_face)

    def draw_registration_box(self, frame):
        h, w = frame.shape[:2]
        size = 300
        x1, y1 = (w - size)//2, (h - size)//2
        x2, y2 = x1+size, y1+size

        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (88, 166, 255), -1)
        cv2.addWeighted(overlay, 0.10, frame, 0.90, 0, frame)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (88, 166, 255), 3)

        step_texts = ["Step 1/3: Look STRAIGHT", "Step 2/3: Turn SLIGHTLY LEFT", "Step 3/3: Turn SLIGHTLY RIGHT"]
        step = getattr(self, 'registration_step', 0)
        cv2.putText(frame, step_texts[min(step, 2)], (x1, y1-14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (88, 166, 255), 2)
        cv2.putText(frame, "Press SPACE to capture", (x1, y2+32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (88, 166, 255), 2)
        return frame

    def capture_face(self, event=None):
        if self.current_frame is None:
            return

        frame = self.current_frame.copy()

        # Try to extract JUST the face region using insightface
        try:
            faces = self.face_app.get(frame)
            if faces:
                best = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
                x1, y1, x2, y2 = [int(v) for v in best.bbox]
                # Add some padding
                h, w = frame.shape[:2]
                pw = max(0, int((x2-x1)*0.2))
                ph = max(0, int((y2-y1)*0.2))
                cy1 = max(0, y1-ph); cy2 = min(h, y2+ph)
                cx1 = max(0, x1-pw); cx2 = min(w, x2+pw)
                
                frame_to_save = frame[cy1:cy2, cx1:cx2]
                if frame_to_save.size == 0:
                    frame_to_save = frame
            else:
                frame_to_save = frame
        except Exception:
            frame_to_save = frame

        self.registration_images.append(frame_to_save)
        self.registration_step += 1

        if self.registration_step < 3:
            steps = ["", "Step 2/3 (TURN LEFT)", "Step 3/3 (TURN RIGHT)"]
            self.status_label.config(text=f"Status: Registration — {steps[self.registration_step]}")
            return

        self.root.unbind('<space>')

        try:
            name = simpledialog.askstring("Register", "Enter full name:")
            if not name:
                self.stop_mode(); return

            emp_id = simpledialog.askstring("Register", "Employee / Roll ID (optional):")

            safe_name  = name.strip().replace(" ", "_")
            safe_id    = emp_id.strip().replace(" ", "_") if emp_id else "NoID"
            person_id  = f"{safe_name}_{safe_id}"

            suffixes   = ['front', 'left', 'right']
            image_paths = []
            for i, img in enumerate(self.registration_images):
                path = os.path.join(self.faces_dir, f"{person_id}_{suffixes[i]}.jpg")
                cv2.imwrite(path, img)
                image_paths.append(path)

            self.database[person_id] = {
                "name"       : name,
                "employee_id": emp_id if emp_id else "",
                "image_paths": image_paths,
                "registered" : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.save_database()
            self.update_faces_list()

            messagebox.showinfo("Success",
                f"✅ Registered: {name}\n\nIMPORTANT: Click 'Train Model' to update embeddings.")
            self._mark_training_status()
            self.stop_mode()

        except Exception as e:
            messagebox.showerror("Error", f"Registration failed: {e}")
            self.stop_mode()

    # ── Recognition (InsightFace embedding-based) ─────────────────────────────

    def recognize_mode(self):
        if not self.face_app:
            messagebox.showwarning("Warning", "InsightFace models not loaded yet. Please wait.")
            return
        if not self.database:
            messagebox.showwarning("Warning", "No faces registered!")
            return
        if not self.embeddings:
            if not messagebox.askyesno("Train First",
                    "InsightFace model has not been trained yet.\n"
                    "Click 'Train Model' first for accurate results.\n\nContinue anyway?"):
                return

        self.mode = "recognize"
        self.vote_buffer = []
        self.last_name_shown = None
        self.status_label.config(text="Status: InsightFace Recognition Active — scanning…")
        self.reg_btn.config(state=tk.DISABLED)
        self.rec_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        threading.Thread(target=self.recognition_loop, daemon=True).start()

    def recognition_loop(self):
        print("[Recog] InsightFace recognition started")
        while self.mode == "recognize":
            if self.current_frame is not None and not self.processing:
                self.processing = True
                self._process_recognition_frame()
                self.processing = False
            time.sleep(0.3) # Faster checking than deepface (0.6s -> 0.3s)

    def _process_recognition_frame(self):
        try:
            frame = self.current_frame.copy()

            # Step 1: Extract InsightFace embedding from current frame
            faces = self.face_app.get(frame)
            if not faces:
                self.root.after(0, lambda: self.conf_label.config(text="No face detected"))
                return
                
            best_face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
            live_vec = _l2_normalize(best_face.embedding.astype(np.float32))

            # Step 2: Find best match using MIN-OF-ALL strategy
            all_dists = []

            for pid, data in self.embeddings.items():
                if isinstance(data, dict) and 'all' in data:
                    min_dist = float('inf')
                    for stored_vec in data['all']:
                        d = 1.0 - float(np.dot(live_vec, stored_vec))
                        if d < min_dist:
                            min_dist = d
                    all_dists.append((pid, min_dist))
                else:
                    vec = data if isinstance(data, np.ndarray) else data.get('mean', data)
                    d = 1.0 - float(np.dot(live_vec, vec))
                    all_dists.append((pid, d))

            all_dists.sort(key=lambda x: x[1])

            best_pid,  best_dist  = all_dists[0]
            _,         sec_dist   = all_dists[1] if len(all_dists) > 1 else (None, 1.0)

            top3_str = "  ".join(
                f"{self.database.get(p,{}).get('name','?')}={d:.3f}"
                for p, d in all_dists[:3]
            )
            print(f"[Recog] Top3: {top3_str}")

            threshold     = self.threshold_var.get()
            MARGIN_NEEDED = 0.03
            ABS_MAX_DIST  = 0.55   

            decisive = (
                best_dist < threshold
                and best_dist < ABS_MAX_DIST
                and (sec_dist - best_dist) >= MARGIN_NEEDED
            )

            # Step 3: Voting buffer
            if decisive:
                self.vote_buffer.append((best_pid, best_dist))
            else:
                self.vote_buffer.append((None, 1.0))

            if len(self.vote_buffer) > self.vote_window:
                self.vote_buffer.pop(0)

            # Step 4: Decide — require 4 out of 7 frames to agree
            VOTES_NEEDED = self.vote_window // 2 + 1
            valid_votes  = [(p, d) for p, d in self.vote_buffer if p is not None]

            vote_counts = {}
            for p, d in valid_votes:
                vote_counts.setdefault(p, []).append(d)

            winner_pid = None
            winner_avg = 1.0
            for p, dists in vote_counts.items():
                if len(dists) >= VOTES_NEEDED:
                    avg = sum(dists) / len(dists)
                    if avg < winner_avg:
                        winner_avg = avg
                        winner_pid = p

            if winner_pid:
                confidence = 1.0 - winner_avg
                self._on_recognized(winner_pid, confidence)
                self.vote_buffer = []
            else:
                status = f"Scanning… {best_dist:.3f} vs {sec_dist:.3f}" if not decisive else f"Collecting votes…  {best_dist:.3f}"
                self.root.after(0, lambda t=status: self.conf_label.config(text=t))

        except Exception as e:
            if "Face could not be detected" not in str(e):
                print(f"[Recog] Error: {e}")
            self.root.after(0, lambda: self.conf_label.config(text="No face detected"))

    def _on_recognized(self, person_id, confidence):
        info = self.database.get(person_id)
        if not info:
            return

        name = info['name']
        conf_pct = f"{confidence*100:.1f}%"
        self.last_name_shown = name
        self.root.after(0, lambda: self.conf_label.config(
            text=f"✅ {name}  |  Confidence: {conf_pct}"))

        already_logged = self.log_attendance(person_id, info)
        if not already_logged:
            self.root.after(0, lambda: self.show_notification(name, conf_pct))
            print(f"[Recog] Attendance marked: {name}  ({conf_pct})")
        else:
            print(f"[Recog] Already logged today: {name}")

    # ── Attendance logging ────────────────────────────────────────────────

    def log_attendance(self, person_id, info) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check if already logged today in CSV
        if os.path.exists(self.attendance_file):
            try:
                with open(self.attendance_file, 'r') as f:
                    for line in f:
                        if today in line and person_id in line:
                            return True
            except Exception:
                pass

        # ── Write to CSV (always allowed if recognized) ─────────────────────
        try:
            is_new = not os.path.exists(self.attendance_file)
            with open(self.attendance_file, 'a') as f:
                if is_new:
                    f.write("Timestamp,Name,EmployeeID,PersonID\n")
                f.write(f"{timestamp},{info['name']},{info.get('employee_id','')},{person_id}\n")
        except Exception as e:
            print(f"[Log] CSV error: {e}")

        # ── Write to SQLite when in a faculty session ────────────────────────
        if self.timetable_id is not None:
            try:
                from database import Database
                db = Database()

                # Resolve person_id → SQLite student row by matching student_id field
                students = db.get_all_students() or []
                emp_id   = info.get('employee_id', '').strip()
                student_row = None

                # Try matching by employee_id (stored as student_id in DB)
                if emp_id:
                    student_row = db.get_student_by_student_id(emp_id)

                # Fallback: match by name
                if not student_row:
                    name_lower = info['name'].lower()
                    for s in students:
                        if s[2].lower() == name_lower:
                            student_row = s
                            break

                if student_row:
                    db.mark_attendance(
                        student_id=student_row[0],
                        timetable_id=self.timetable_id,
                        confidence_score=None
                    )
                    print(f"[Log] SQLite attendance marked: {info['name']}")
                else:
                    # Auto-register the student directly into the DB so they appear in live counts
                    if not emp_id:
                        import time
                        emp_id = 'AUTO_' + info['name'].replace(' ', '_') + str(int(time.time()))
                    try:
                        new_student_pk = db.add_student(
                            student_id=emp_id,
                            name=info['name'],
                            email=f"{emp_id}@auto.reg",
                            department="InsightFace Auto-Reg"
                        )
                        db.mark_attendance(
                            student_id=new_student_pk,
                            timetable_id=self.timetable_id,
                            confidence_score=None
                        )
                        print(f"[Log] Auto-Registered & Marked in SQLite: {info['name']}")
                    except Exception as reg_err:
                        print(f"[Log] Could not auto-register {info['name']}: {reg_err}")

            except Exception as e:
                print(f"[Log] SQLite error: {e}")

        # ── Fire callback to update FacultySessionWindow counter ─────────────
        if self.on_attendance_marked:
            try:
                self.root.after(0, lambda n=info['name']: self.on_attendance_marked(n))
            except Exception:
                pass

        return False

    # ── Notifications ─────────────────────────────────────────────────────

    def show_notification(self, name, confidence):
        popup = tk.Toplevel(self.root)
        popup.title("✅ Recognized")
        popup.geometry("340x170")
        popup.configure(bg='#238636')
        popup.attributes('-topmost', True)

        tk.Label(popup, text="✅ Attendance Marked!", font=('Segoe UI', 14, 'bold'),
                 bg='#238636', fg='white').pack(pady=(20, 5))
        tk.Label(popup, text=name, font=('Segoe UI', 18, 'bold'),
                 bg='#238636', fg='#f0fff0').pack(pady=2)
        tk.Label(popup, text=f"Confidence: {confidence}  |  {datetime.now().strftime('%H:%M:%S')}",
                 font=('Segoe UI', 10), bg='#238636', fg='#a9dfbf').pack(pady=4)

        popup.after(2500, popup.destroy)

    # ── Stop / Idle ───────────────────────────────────────────────────────

    def stop_mode(self):
        self.mode = "idle"
        self.last_name_shown = None
        self.status_label.config(text="Status: Camera Active", fg='#8b949e')
        self.conf_label.config(text="")
        self.reg_btn.config(state=tk.NORMAL)
        self.rec_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.root.unbind('<space>')

    # ── Delete ────────────────────────────────────────────────────────────

    def delete_face(self):
        selection = self.faces_list.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Select a face to delete!")
            return

        person_id = list(self.database.keys())[selection[0]]
        name = self.database[person_id]['name']

        if messagebox.askyesno("Confirm", f"Delete {name}?"):
            try:
                info = self.database[person_id]
                paths = info.get('image_paths', [])
                if 'image_path' in info:
                    paths.append(info['image_path'])
                for p in paths:
                    if os.path.exists(p):
                        os.remove(p)

                del self.database[person_id]
                self.save_database()
                self.update_faces_list()
                if person_id in self.embeddings:
                    del self.embeddings[person_id]
                    self.save_embeddings(self.embeddings)
                self._mark_training_status()
                messagebox.showinfo("Success", f"Deleted: {name}")
            except Exception as e:
                messagebox.showerror("Error", f"Delete failed: {e}")

    def show_delete_dialog(self):
        if not self.database:
            messagebox.showinfo("Info", "No students registered yet!")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Delete Student")
        dialog.geometry("450x540")
        dialog.configure(bg='#0d1117')
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("+%d+%d" % (self.root.winfo_x()+380, self.root.winfo_y()+100))

        tk.Label(dialog, text="🗑 Delete Student Record",
                 font=('Segoe UI', 14, 'bold'), bg='#0d1117', fg='#da3633').pack(pady=14)

        sf = tk.Frame(dialog, bg='#0d1117'); sf.pack(fill=tk.X, padx=18, pady=4)
        tk.Label(sf, text="🔍", font=('Segoe UI', 11), bg='#0d1117', fg='#c9d1d9').pack(side=tk.LEFT)
        sv = tk.StringVar()
        se = tk.Entry(sf, textvariable=sv, font=('Segoe UI', 10),
                      bg='#161b22', fg='#c9d1d9', insertbackground='#c9d1d9', relief=tk.FLAT)
        se.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8,0))

        lf = tk.Frame(dialog, bg='#0d1117'); lf.pack(fill=tk.BOTH, expand=True, padx=18, pady=8)
        sb2 = tk.Scrollbar(lf); sb2.pack(side=tk.RIGHT, fill=tk.Y)
        dlist = tk.Listbox(lf, font=('Segoe UI', 10), bg='#0d1117', fg='#c9d1d9',
                           selectbackground='#1f6feb', yscrollcommand=sb2.set, relief=tk.FLAT)
        dlist.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb2.config(command=dlist.yview)

        def refresh(*_):
            dlist.delete(0, tk.END)
            q = sv.get().lower()
            for pid, pi in self.database.items():
                txt = f"{pi['name']}  (ID: {pi.get('employee_id','N/A')})"
                if q in txt.lower():
                    dlist.insert(tk.END, txt)

        sv.trace('w', refresh)
        refresh()

        def do_delete():
            sel = dlist.curselection()
            if not sel:
                messagebox.showwarning("Warning", "Select a student!", parent=dialog); return
            sel_txt = dlist.get(sel[0])
            target_pid = None
            for pid, pi in self.database.items():
                if f"{pi['name']}  (ID: {pi.get('employee_id','N/A')})" == sel_txt:
                    target_pid = pid; break
            if not target_pid: return
            n = self.database[target_pid]['name']
            if messagebox.askyesno("Delete", f"Delete {n} permanently?", parent=dialog):
                info = self.database[target_pid]
                for p in info.get('image_paths', []) + ([info.get('image_path')] if 'image_path' in info else []):
                    if p and os.path.exists(p):
                        os.remove(p)
                del self.database[target_pid]
                if target_pid in self.embeddings:
                    del self.embeddings[target_pid]
                    self.save_embeddings(self.embeddings)
                self.save_database()
                self.update_faces_list()
                self._mark_training_status()
                refresh()
                messagebox.showinfo("Deleted", f"Deleted {n}", parent=dialog)

        bf = tk.Frame(dialog, bg='#0d1117'); bf.pack(pady=12, fill=tk.X, padx=18)
        tk.Button(bf, text="Delete Selected", command=do_delete,
                  font=('Segoe UI', 10, 'bold'), bg='#da3633', fg='white',
                  relief=tk.FLAT, cursor='hand2', height=2
                  ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,5))
        tk.Button(bf, text="Close", command=dialog.destroy,
                  font=('Segoe UI', 10), bg='#484f58', fg='white',
                  relief=tk.FLAT, cursor='hand2', height=2
                  ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5,0))

    # ── View Attendance ───────────────────────────────────────────────────

    def view_attendance(self):
        if not os.path.exists(self.attendance_file):
            messagebox.showinfo("Info", "No attendance records yet!")
            return

        win = tk.Toplevel(self.root)
        win.title("Attendance Log — InsightFace")
        win.geometry("700x500")
        win.configure(bg='#0d1117')

        tk.Label(win, text="📋 Attendance Records", font=('Segoe UI', 14, 'bold'),
                 bg='#0d1117', fg='#c9d1d9').pack(pady=10)

        text = tk.Text(win, font=('Courier New', 10), bg='#161b22', fg='#c9d1d9',
                       wrap=tk.WORD, relief=tk.FLAT)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        try:
            with open(self.attendance_file, 'r') as f:
                text.insert(tk.END, f.read())
        except Exception as e:
            text.insert(tk.END, f"Error: {e}")

        text.config(state=tk.DISABLED)

    # ── Cleanup ───────────────────────────────────────────────────────────

    def cleanup(self):
        self.is_running = False
        self.mode = "idle"
        if self.camera:
            self.camera.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
        self.root.destroy()


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  InsightFace Attendance System")
    print("  Model: buffalo_l (ArcFace)  |  Detector: RetinaFace (ONNX)")
    print("=" * 60)
    print()
    print("WORKFLOW:")
    print("  1. Start Camera")
    print("  2. Register all faces (if not already done)")
    print("  3. Click 'Train Model (Insight)' — caches embeddings")
    print("  4. Click 'Start Recognition'")
    print()

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--timetable-id", type=int, default=None, help="The SQLite DB timetable ID to link attendance to.")
    parser.add_argument("--session-id", type=int, default=None, help="The SQLite DB session ID.")
    args = parser.parse_args()

    # Disable annoying warnings
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

    try:
        root = tk.Tk()
        app  = InsightFaceAttendanceSystem(root, timetable_id=args.timetable_id, session_id=args.session_id)
        root.protocol("WM_DELETE_WINDOW", app.cleanup)
        root.mainloop()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback; traceback.print_exc()


if __name__ == "__main__":
    main()
