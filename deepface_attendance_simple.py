"""
DeepFace Attendance System - High-Accuracy Version
Key improvements for large class sizes (50+ students):
  1. TRAIN MODEL: Pre-extracts & caches face embeddings so recognition is fast
  2. Uses DeepFace.find() for 1-vs-all cosine search (much faster than looping)
  3. RetinaFace detector backend for far better face detection accuracy
  4. Crops and saves ONLY the face region during registration (not full frame)
  5. Multi-frame voting for stable recognition decisions
  6. Per-day duplicate attendance guard (person logged only once per day)
  7. Live confidence display on camera feed
  8. Adjustable similarity threshold slider
"""

import cv2
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from PIL import Image, ImageTk
import json
import os
import numpy as np
from deepface import DeepFace
from datetime import datetime
import threading
import time
import pickle
import shutil

# ── Constants ────────────────────────────────────────────────────────────────
MODEL_NAME      = "Facenet512"          # best accuracy / speed tradeoff
# IMPORTANT: DETECTOR must be the SAME for training AND recognition.
# Using different detectors produces different face crops → incompatible
# embeddings → wrong matches even for the correct person.
# mtcnn is thread-safe (fine in background thread) and more accurate than opencv.
DETECTOR        = "mtcnn"
DISTANCE_METRIC = "cosine"
EMBEDDING_CACHE = "face_embeddings.pkl" # trained embeddings cache


class SimpleAttendanceSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("DeepFace Attendance System — High Accuracy")
        self.root.geometry("1200x720")
        self.root.configure(bg='#1a1a2e')

        # State
        self.camera           = None
        self.is_running       = False
        self.current_frame    = None
        self.mode             = "idle"
        self.processing       = False

        # Multi-frame voting buffer
        self.vote_buffer      = []        # list of (person_id, distance) tuples
        self.vote_window      = 7         # frames to collect before deciding (5/7 required)
        self.last_name_shown  = None

        # Paths
        self.faces_dir        = "registered_faces"
        self.database_file    = "face_database.json"
        self.attendance_file  = "attendance_log.csv"
        self.embedding_cache  = EMBEDDING_CACHE

        os.makedirs(self.faces_dir, exist_ok=True)

        # Load database + auto-import any images not yet in DB
        self.load_database()
        self.auto_sync_database()
        self.embeddings = self.load_embeddings()

        # Setup GUI
        self.setup_gui()
        self.update_faces_list()

        # Status flag: is the embedding cache fresh?
        self._mark_training_status()

        print("✅ System initialized. Click 'Train Model' before starting recognition.")

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
        """
        Scans registered_faces/ and imports any person whose images exist on disk
        but are missing from face_database.json.

        Image naming convention (set during registration):
            {FirstName}_{LastName}_{EmployeeID}_front.jpg
            {FirstName}_{LastName}_{EmployeeID}_left.jpg
            {FirstName}_{LastName}_{EmployeeID}_right.jpg
        """
        added = 0
        # Collect all image files grouped by person_id
        person_images: dict = {}
        for fname in os.listdir(self.faces_dir):
            if not fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            # Strip suffix (_front / _left / _right)
            for suffix in ('_front', '_left', '_right'):
                if fname.lower().endswith(suffix + os.path.splitext(fname)[1].lower()):
                    person_id = fname[:fname.lower().rfind(suffix)]
                    person_images.setdefault(person_id, []).append(
                        os.path.join(self.faces_dir, fname)
                    )
                    break

        for person_id, paths in person_images.items():
            if person_id in self.database:
                continue  # already registered

            # Parse name and employee ID from person_id string
            # Expected pattern: Word_Word_..._NumericID
            parts = person_id.split('_')
            # Find where the numeric employee-ID part starts
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
            # Sort paths so front/left/right order is consistent
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
        else:
            print(f"[Sync] Database already in sync ({len(self.database)} persons).")

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
                print(f"[TRAIN] Loaded {len(cache)} cached embeddings.")
                return cache
            except Exception as e:
                print(f"[TRAIN] Cache corrupt, will retrain: {e}")
        return {}

    def save_embeddings(self, cache):
        with open(self.embedding_cache, 'wb') as f:
            pickle.dump(cache, f)

    def train_model(self):
        """
        Pre-compute and cache a face embedding for every registered image.
        This means recognition never has to re-compute embeddings from disk.
        """
        self.train_btn.config(state=tk.DISABLED, text="Training…")
        self.status_label.config(text="Status: Training — please wait…", fg='#f39c12')
        self.root.update_idletasks()

        def _train():
            cache  = {}
            errors = 0
            total  = 0
            n_persons = len(self.database)

            for idx, (person_id, info) in enumerate(self.database.items(), 1):
                name = info.get('name', person_id)

                # Live progress update in the status bar
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
                        # ── Pre-load image via cv2 as numpy array.
                        # Passing a string path to DeepFace triggers TF's
                        # internal HDF5 reader which crashes on JPEG files
                        # with 'file signature not found'.
                        img_bgr = cv2.imread(img_path)
                        if img_bgr is None:
                            from PIL import Image as _PILImage
                            img_bgr = cv2.cvtColor(
                                np.array(_PILImage.open(img_path).convert('RGB')),
                                cv2.COLOR_RGB2BGR
                            )

                        # Use the SAME detector constant as recognition so that
                        # training and live embeddings are comparable.
                        # mtcnn is used: thread-safe and more accurate than opencv.
                        result = DeepFace.represent(
                            img_path         = img_bgr,
                            model_name       = MODEL_NAME,
                            detector_backend = DETECTOR,
                            enforce_detection= False,
                            align            = True,
                        )

                        if result:
                            vec = np.array(result[0]['embedding'], dtype=np.float32)
                            vec /= (np.linalg.norm(vec) + 1e-10)
                            person_vecs.append(vec)
                    except Exception as e:
                        errors += 1
                        print(f"[TRAIN]   ✗ Skip: {e}")

                if person_vecs:
                    mean_vec = np.mean(person_vecs, axis=0)
                    mean_vec /= (np.linalg.norm(mean_vec) + 1e-10)
                    cache[person_id] = mean_vec
                    print(f"[TRAIN]   ✓ {len(person_vecs)}/3 images OK")
                else:
                    print(f"[TRAIN]   ✗ No embeddings extracted — skipped")

            self.embeddings = cache
            self.save_embeddings(cache)

            msg = (f"Training complete!\n"
                   f"Processed : {total} images\n"
                   f"Persons   : {len(cache)}/{n_persons}\n"
                   f"Skipped   : {errors} images")

            self.root.after(0, lambda: self._on_train_done(msg))

        threading.Thread(target=_train, daemon=True).start()

    def _on_train_done(self, msg):
        self.train_btn.config(state=tk.NORMAL, text="🧠 Train Model")
        self.status_label.config(text="Status: Training complete — ready to recognize", fg='#2ecc71')
        self._mark_training_status()
        messagebox.showinfo("Training Complete", msg)

    def _mark_training_status(self):
        n_trained = len(self.embeddings)
        n_reg     = len(self.database)
        if n_trained == 0:
            self.train_status_lbl.config(
                text=f"⚠ Model NOT trained ({n_reg} registered)", fg='#e74c3c')
        elif n_trained < n_reg:
            self.train_status_lbl.config(
                text=f"⚠ Partial train ({n_trained}/{n_reg} persons)", fg='#f39c12')
        else:
            self.train_status_lbl.config(
                text=f"✅ Model trained ({n_trained} persons)", fg='#2ecc71')

    # ── GUI ──────────────────────────────────────────────────────────────────

    def setup_gui(self):
        # ── Title bar
        title = tk.Label(
            self.root,
            text="🎓 DeepFace Attendance System — High Accuracy",
            font=('Segoe UI', 18, 'bold'),
            bg='#16213e', fg='#e94560', pady=12
        )
        title.pack(fill=tk.X)

        # ── Main area
        main = tk.Frame(self.root, bg='#1a1a2e')
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        # Left — Camera
        left = tk.Frame(main, bg='#16213e', relief=tk.FLAT, bd=0)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        tk.Label(left, text="📷 Camera Feed", font=('Segoe UI', 11, 'bold'),
                 bg='#16213e', fg='#a8dadc').pack(pady=(8,2))

        self.video_label = tk.Label(left, bg='#0f0f1a', width=72, height=28)
        self.video_label.pack(padx=10, pady=6, fill=tk.BOTH, expand=True)

        self.status_label = tk.Label(
            left, text="Status: Camera Off",
            font=('Segoe UI', 10), bg='#16213e', fg='#a8dadc', pady=6
        )
        self.status_label.pack()

        self.conf_label = tk.Label(
            left, text="",
            font=('Segoe UI', 10, 'bold'), bg='#16213e', fg='#f1c40f', pady=2
        )
        self.conf_label.pack()

        # Right — Controls
        right = tk.Frame(main, bg='#16213e', relief=tk.FLAT, bd=0, width=310)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        right.pack_propagate(False)

        ctrl = tk.Frame(right, bg='#16213e', pady=12)
        ctrl.pack(fill=tk.X, padx=14)

        tk.Label(ctrl, text="Controls", font=('Segoe UI', 13, 'bold'),
                 bg='#16213e', fg='white').pack(pady=(0,10))

        def btn(parent, text, cmd, color, state=tk.NORMAL):
            b = tk.Button(parent, text=text, command=cmd,
                          font=('Segoe UI', 10, 'bold'),
                          bg=color, fg='white', height=2,
                          activebackground=color, relief=tk.FLAT,
                          cursor='hand2', state=state)
            b.pack(fill=tk.X, pady=4)
            return b

        self.cam_btn   = btn(ctrl, "▶ Start Camera",    self.toggle_camera,  '#27ae60')
        self.train_btn = btn(ctrl, "🧠 Train Model",     self.train_model,    '#8e44ad')
        self.reg_btn   = btn(ctrl, "➕ Register Face",   self.register_mode,  '#2980b9', tk.DISABLED)
        self.rec_btn   = btn(ctrl, "🔍 Start Recognition", self.recognize_mode,'#e67e22', tk.DISABLED)
        self.stop_btn  = btn(ctrl, "⏹ Stop",             self.stop_mode,      '#7f8c8d', tk.DISABLED)
        btn(ctrl, "📋 View Attendance",  self.view_attendance,   '#9b59b6')
        btn(ctrl, "🗑 Delete Student",   self.show_delete_dialog,'#c0392b')

        # Threshold slider
        tk.Label(ctrl, text="Similarity Threshold",
                 font=('Segoe UI', 9), bg='#16213e', fg='#a8dadc').pack(pady=(10,0))
        self.threshold_var = tk.DoubleVar(value=0.35)
        self.thresh_slider = tk.Scale(
            ctrl, from_=0.20, to=0.65, resolution=0.01,
            orient=tk.HORIZONTAL, variable=self.threshold_var,
            bg='#16213e', fg='white', troughcolor='#2c3e50',
            highlightthickness=0, font=('Segoe UI', 9)
        )
        self.thresh_slider.pack(fill=tk.X)
        tk.Label(ctrl, text="← stricter    looser →",
                 font=('Segoe UI', 8), bg='#16213e', fg='#7f8c8d').pack()

        # Training status
        self.train_status_lbl = tk.Label(
            ctrl, text="", font=('Segoe UI', 9, 'bold'),
            bg='#16213e', fg='#e74c3c'
        )
        self.train_status_lbl.pack(pady=(8,0))

        # Registered faces list
        tk.Label(right, text="Registered Faces", font=('Segoe UI', 11, 'bold'),
                 bg='#16213e', fg='white', pady=6).pack()

        list_frame = tk.Frame(right, bg='#16213e')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)

        sb = tk.Scrollbar(list_frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.faces_list = tk.Listbox(
            list_frame, font=('Segoe UI', 9),
            bg='#0f3460', fg='#e2e2e2',
            selectbackground='#e94560',
            yscrollcommand=sb.set, relief=tk.FLAT
        )
        self.faces_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self.faces_list.yview)

        tk.Button(right, text="Delete Selected", command=self.delete_face,
                  font=('Segoe UI', 9), bg='#c0392b', fg='white',
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
                # Increase resolution for better detection
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                if not self.camera.isOpened():
                    messagebox.showerror("Error", "Cannot open camera!")
                    return
                self.is_running = True
                self.cam_btn.config(text="⏹ Stop Camera", bg='#c0392b')
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
            self.cam_btn.config(text="▶ Start Camera", bg='#27ae60')
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
                    cv2.putText(display, f"✓ {self.last_name_shown}", (20, 50),
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
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 100), -1)
        cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 100), 3)

        step_texts = ["Step 1/3: Look STRAIGHT", "Step 2/3: Turn SLIGHTLY LEFT", "Step 3/3: Turn SLIGHTLY RIGHT"]
        step = getattr(self, 'registration_step', 0)
        cv2.putText(frame, step_texts[min(step, 2)], (x1, y1-14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 100), 2)
        cv2.putText(frame, "Press SPACE to capture", (x1, y2+32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 100), 2)
        return frame

    def capture_face(self, event=None):
        if self.current_frame is None:
            return

        frame = self.current_frame.copy()

        # ── Try to extract JUST the face region using retinaface ──
        try:
            faces = DeepFace.extract_faces(
                img_path         = frame,
                detector_backend = DETECTOR,
                enforce_detection= True,
                align            = True,
            )
            if faces:
                # Use the face with highest confidence
                best = max(faces, key=lambda f: f.get('confidence', 0))
                face_arr = (best['face'] * 255).astype(np.uint8)
                face_bgr = cv2.cvtColor(face_arr, cv2.COLOR_RGB2BGR)
                frame_to_save = face_bgr
            else:
                frame_to_save = frame
        except Exception:
            # Fallback: save full frame (face detection failed for this angle)
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
                f"✅ Registered: {name}\n\nIMPORTANT: Click 'Train Model' to update the recognition model.")
            self._mark_training_status()
            self.stop_mode()

        except Exception as e:
            messagebox.showerror("Error", f"Registration failed: {e}")
            self.stop_mode()

    # ── Recognition (fast embedding-based) ──────────────────────────────────

    def recognize_mode(self):
        if not self.database:
            messagebox.showwarning("Warning", "No faces registered!")
            return
        if not self.embeddings:
            if not messagebox.askyesno("Train First",
                    "The model has not been trained yet.\n"
                    "Recognition accuracy will be poor.\n\nContinue anyway?"):
                return

        self.mode = "recognize"
        self.vote_buffer = []
        self.last_name_shown = None
        self.status_label.config(text="Status: Recognition Active — scanning…")
        self.reg_btn.config(state=tk.DISABLED)
        self.rec_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        threading.Thread(target=self.recognition_loop, daemon=True).start()

    def recognition_loop(self):
        print("[Recog] Started recognition loop")
        while self.mode == "recognize":
            if self.current_frame is not None and not self.processing:
                self.processing = True
                self._process_recognition_frame()
                self.processing = False
            time.sleep(0.6)  # 0.6 s between frames

    def _process_recognition_frame(self):
        try:
            frame = self.current_frame.copy()

            # Step 1: Extract face embedding from current frame
            # Try preferred detector first, fall back to opencv for robustness
            result = None
            last_err = None
            for detector in (DETECTOR, 'mtcnn', 'opencv'):
                try:
                    result = DeepFace.represent(
                        img_path         = frame,
                        model_name       = MODEL_NAME,
                        detector_backend = detector,
                        enforce_detection= True,
                        align            = True,
                    )
                    if result:  # got at least one face
                        break
                except Exception as e:
                    last_err = e
                    continue

            if not result:
                self.root.after(0, lambda: self.conf_label.config(text="No face detected"))
                return

            live_vec = np.array(result[0]['embedding'], dtype=np.float32)
            live_vec /= (np.linalg.norm(live_vec) + 1e-10)

            # Step 2: Cosine similarity against ALL cached embeddings
            all_dists = sorted(
                [(pid, 1.0 - float(np.dot(live_vec, sv)))
                 for pid, sv in self.embeddings.items()],
                key=lambda x: x[1]
            )

            best_pid,  best_dist  = all_dists[0]
            _,         sec_dist   = all_dists[1] if len(all_dists) > 1 else (None, 1.0)

            # Print top-3 for debugging
            top3_str = "  ".join(
                f"{self.database.get(p,{}).get('name','?')}={d:.3f}"
                for p, d in all_dists[:3]
            )
            print(f"[Recog] Top3: {top3_str}")

            threshold     = self.threshold_var.get()
            # Margin check: gap between #1 and #2 must be meaningful.
            # 0.03 is chosen empirically — filters coin-flip frames (gap<0.01)
            # without blocking genuine recognitions which often have gaps of 0.02+
            MARGIN_NEEDED = 0.03
            ABS_MAX_DIST  = 0.36   # absolute ceiling; above this is rejected regardless

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

            # Step 4: Decide — require 4 out of 7 frames to agree on same person.
            # (5/7 was too strict when camera noise scatters valid frames.)
            VOTES_NEEDED = self.vote_window // 2 + 1  # = 4 for window of 7
            valid_votes  = [(p, d) for p, d in self.vote_buffer if p is not None]

            # Count votes per person
            vote_counts = {}
            for p, d in valid_votes:
                vote_counts.setdefault(p, []).append(d)

            # Find a person who has enough votes
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
                self.vote_buffer = []  # reset after recognition
            else:
                status = f"Scanning… {best_dist:.3f} vs {sec_dist:.3f}" if not decisive else f"Collecting votes…  {best_dist:.3f}"
                self.root.after(0, lambda t=status: self.conf_label.config(text=t))


        except Exception as e:
            if "Face could not be detected" not in str(e):
                print(f"[Recog] {e}")
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
        """
        Returns True if this person was already logged TODAY (skip duplicate).
        """
        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check for duplicate in today's records only
        if os.path.exists(self.attendance_file):
            try:
                with open(self.attendance_file, 'r') as f:
                    for line in f:
                        if today in line and person_id in line:
                            return True   # already logged today
            except Exception:
                pass

        try:
            is_new = not os.path.exists(self.attendance_file)
            with open(self.attendance_file, 'a') as f:
                if is_new:
                    f.write("Timestamp,Name,EmployeeID,PersonID\n")
                f.write(f"{timestamp},{info['name']},{info.get('employee_id','')},{person_id}\n")
        except Exception as e:
            print(f"[Log] Error: {e}")

        return False

    # ── Notifications ─────────────────────────────────────────────────────

    def show_notification(self, name, confidence):
        popup = tk.Toplevel(self.root)
        popup.title("✅ Recognized")
        popup.geometry("340x170")
        popup.configure(bg='#1e8449')
        popup.attributes('-topmost', True)

        tk.Label(popup, text="✅ Attendance Marked!", font=('Segoe UI', 14, 'bold'),
                 bg='#1e8449', fg='white').pack(pady=(20, 5))
        tk.Label(popup, text=name, font=('Segoe UI', 18, 'bold'),
                 bg='#1e8449', fg='#f0fff0').pack(pady=2)
        tk.Label(popup, text=f"Confidence: {confidence}  |  {datetime.now().strftime('%H:%M:%S')}",
                 font=('Segoe UI', 10), bg='#1e8449', fg='#a9dfbf').pack(pady=4)

        popup.after(2500, popup.destroy)

    # ── Stop / Idle ───────────────────────────────────────────────────────

    def stop_mode(self):
        self.mode = "idle"
        self.last_name_shown = None
        self.status_label.config(text="Status: Camera Active", fg='#a8dadc')
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
                # Invalidate cached embedding for this person
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
        dialog.configure(bg='#1a1a2e')
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("+%d+%d" % (self.root.winfo_x()+380, self.root.winfo_y()+100))

        tk.Label(dialog, text="🗑 Delete Student Record",
                 font=('Segoe UI', 14, 'bold'), bg='#1a1a2e', fg='#e74c3c').pack(pady=14)

        sf = tk.Frame(dialog, bg='#1a1a2e'); sf.pack(fill=tk.X, padx=18, pady=4)
        tk.Label(sf, text="🔍", font=('Segoe UI', 11), bg='#1a1a2e', fg='white').pack(side=tk.LEFT)
        sv = tk.StringVar()
        se = tk.Entry(sf, textvariable=sv, font=('Segoe UI', 10),
                      bg='#16213e', fg='white', insertbackground='white', relief=tk.FLAT)
        se.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8,0))

        lf = tk.Frame(dialog, bg='#1a1a2e'); lf.pack(fill=tk.BOTH, expand=True, padx=18, pady=8)
        sb2 = tk.Scrollbar(lf); sb2.pack(side=tk.RIGHT, fill=tk.Y)
        dlist = tk.Listbox(lf, font=('Segoe UI', 10), bg='#0f3460', fg='#e2e2e2',
                           selectbackground='#e74c3c', yscrollcommand=sb2.set, relief=tk.FLAT)
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

        bf = tk.Frame(dialog, bg='#1a1a2e'); bf.pack(pady=12, fill=tk.X, padx=18)
        tk.Button(bf, text="Delete Selected", command=do_delete,
                  font=('Segoe UI', 10, 'bold'), bg='#c0392b', fg='white',
                  relief=tk.FLAT, cursor='hand2', height=2
                  ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,5))
        tk.Button(bf, text="Close", command=dialog.destroy,
                  font=('Segoe UI', 10), bg='#7f8c8d', fg='white',
                  relief=tk.FLAT, cursor='hand2', height=2
                  ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5,0))

    # ── View Attendance ───────────────────────────────────────────────────

    def view_attendance(self):
        if not os.path.exists(self.attendance_file):
            messagebox.showinfo("Info", "No attendance records yet!")
            return

        win = tk.Toplevel(self.root)
        win.title("Attendance Log")
        win.geometry("700x500")
        win.configure(bg='#1a1a2e')

        tk.Label(win, text="📋 Attendance Records", font=('Segoe UI', 14, 'bold'),
                 bg='#1a1a2e', fg='white').pack(pady=10)

        text = tk.Text(win, font=('Courier New', 10), bg='#0f3460', fg='#e2e2e2',
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
        cv2.destroyAllWindows()
        self.root.destroy()


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  DeepFace Attendance System — High Accuracy Edition")
    print("=" * 60)
    print()
    print("WORKFLOW:")
    print("  1. Start Camera")
    print("  2. Register all faces (if not already done)")
    print("  3. Click 'Train Model' — this caches embeddings for speed")
    print("  4. Click 'Start Recognition'")
    print()
    print("Required packages:")
    print("  pip install deepface opencv-python Pillow tensorflow numpy")
    print()

    try:
        root = tk.Tk()
        app  = SimpleAttendanceSystem(root)
        root.protocol("WM_DELETE_WINDOW", app.cleanup)
        root.mainloop()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback; traceback.print_exc()


if __name__ == "__main__":
    main()
