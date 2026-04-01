import cv2
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import json
import os
import numpy as np
from deepface import DeepFace
import threading
from datetime import datetime
import time

class OptimizedFaceRecognitionSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("DeepFace Attendance System - Optimized")
        self.root.geometry("1400x750")
        self.root.configure(bg='#1a1a2e')
        
        # Initialize variables
        self.camera = None
        self.is_running = False
        self.current_frame = None
        self.mode = "idle"
        self.recognition_active = False
        self.last_recognition = {}
        self.recognition_cooldown = 5  # seconds
        
        # Paths
        self.faces_dir = "registered_faces"
        self.database_file = "face_database.json"
        self.attendance_file = "attendance_log.csv"
        
        # Create directories
        os.makedirs(self.faces_dir, exist_ok=True)
        
        # Load or create database
        self.load_database()
        
        # Initialize attendance log
        self.init_attendance_log()
        
        # Model settings
        self.model_name = 'Facenet512'  # Options: VGG-Face, Facenet, Facenet512, OpenFace, DeepFace, DeepID, ArcFace, Dlib
        self.detector_backend = 'opencv'  # Options: opencv, ssd, dlib, mtcnn, retinaface
        self.distance_metric = 'cosine'  # Options: cosine, euclidean, euclidean_l2
        
        # Setup GUI
        self.setup_gui()
        
    def load_database(self):
        """Load the face database from JSON file"""
        if os.path.exists(self.database_file):
            with open(self.database_file, 'r') as f:
                self.database = json.load(f)
        else:
            self.database = {}
            self.save_database()
    
    def save_database(self):
        """Save the face database to JSON file"""
        with open(self.database_file, 'w') as f:
            json.dump(self.database, f, indent=4)
    
    def init_attendance_log(self):
        """Initialize attendance log CSV file"""
        if not os.path.exists(self.attendance_file):
            with open(self.attendance_file, 'w') as f:
                f.write("Timestamp,Name,Employee_ID,Status\n")
    
    def setup_gui(self):
        """Setup the GUI components"""
        # Top bar
        top_bar = tk.Frame(self.root, bg='#16213e', height=60)
        top_bar.pack(fill=tk.X)
        
        title_label = tk.Label(
            top_bar,
            text="🎯 DeepFace Attendance System",
            font=('Arial', 22, 'bold'),
            bg='#16213e',
            fg='#00d9ff'
        )
        title_label.pack(side=tk.LEFT, padx=20, pady=10)
        
        # Model info label
        self.model_info_label = tk.Label(
            top_bar,
            text=f"Model: {self.model_name} | Detector: {self.detector_backend}",
            font=('Arial', 10),
            bg='#16213e',
            fg='#a8dadc'
        )
        self.model_info_label.pack(side=tk.RIGHT, padx=20)
        
        # Main container
        main_container = tk.Frame(self.root, bg='#1a1a2e')
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Left panel - Camera feed
        left_panel = tk.Frame(main_container, bg='#16213e', relief=tk.RIDGE, borderwidth=3)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Camera header
        cam_header = tk.Frame(left_panel, bg='#0f3460')
        cam_header.pack(fill=tk.X)
        
        tk.Label(
            cam_header,
            text="📹 Live Camera Feed",
            font=('Arial', 14, 'bold'),
            bg='#0f3460',
            fg='white',
            pady=8
        ).pack()
        
        # Video display
        self.video_label = tk.Label(left_panel, bg='black')
        self.video_label.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        # Status bar
        status_bar = tk.Frame(left_panel, bg='#0f3460')
        status_bar.pack(fill=tk.X)
        
        self.status_label = tk.Label(
            status_bar,
            text="⚪ Status: Camera Off",
            font=('Arial', 11, 'bold'),
            bg='#0f3460',
            fg='#ecf0f1',
            pady=8
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.fps_label = tk.Label(
            status_bar,
            text="FPS: 0",
            font=('Arial', 10),
            bg='#0f3460',
            fg='#95a5a6',
            pady=8
        )
        self.fps_label.pack(side=tk.RIGHT, padx=10)
        
        # Right panel
        right_panel = tk.Frame(main_container, bg='#16213e', relief=tk.RIDGE, borderwidth=3, width=400)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH)
        right_panel.pack_propagate(False)
        
        # Control section
        controls_frame = tk.Frame(right_panel, bg='#16213e')
        controls_frame.pack(fill=tk.X, padx=15, pady=15)
        
        tk.Label(
            controls_frame,
            text="⚙️ Controls",
            font=('Arial', 16, 'bold'),
            bg='#16213e',
            fg='#00d9ff'
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # Camera control
        self.camera_btn = self.create_button(
            controls_frame,
            "🎥 Start Camera",
            self.toggle_camera,
            '#27ae60'
        )
        self.camera_btn.pack(fill=tk.X, pady=3)
        
        # Register button
        self.register_btn = self.create_button(
            controls_frame,
            "➕ Register New Face",
            self.start_registration,
            '#3498db',
            state=tk.DISABLED
        )
        self.register_btn.pack(fill=tk.X, pady=3)
        
        # Recognition button
        self.recognize_btn = self.create_button(
            controls_frame,
            "🔍 Start Recognition",
            self.start_recognition,
            '#e67e22',
            state=tk.DISABLED
        )
        self.recognize_btn.pack(fill=tk.X, pady=3)
        
        # Stop button
        self.stop_mode_btn = self.create_button(
            controls_frame,
            "⏹️ Stop Current Mode",
            self.stop_mode,
            '#7f8c8d',
            state=tk.DISABLED
        )
        self.stop_mode_btn.pack(fill=tk.X, pady=3)
        
        # View attendance button
        view_attendance_btn = self.create_button(
            controls_frame,
            "📋 View Attendance",
            self.view_attendance,
            '#9b59b6'
        )
        view_attendance_btn.pack(fill=tk.X, pady=3)
        
        # Delete Student button
        self.delete_student_btn = self.create_button(
            controls_frame,
            "🗑️ Delete Student",
            self.show_delete_dialog,
            '#c0392b'
        )
        self.delete_student_btn.pack(fill=tk.X, pady=3)
        
        # Settings button
        settings_btn = self.create_button(
            controls_frame,
            "⚙️ Model Settings",
            self.show_settings,
            '#34495e'
        )
        settings_btn.pack(fill=tk.X, pady=3)
        
        # Separator
        ttk.Separator(right_panel, orient='horizontal').pack(fill=tk.X, padx=15, pady=10)
        
        # Registered faces section
        faces_frame = tk.Frame(right_panel, bg='#16213e')
        faces_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        faces_header = tk.Frame(faces_frame, bg='#16213e')
        faces_header.pack(fill=tk.X)
        
        tk.Label(
            faces_header,
            text="👥 Registered Faces",
            font=('Arial', 14, 'bold'),
            bg='#16213e',
            fg='#00d9ff'
        ).pack(side=tk.LEFT)
        
        self.face_count_label = tk.Label(
            faces_header,
            text=f"({len(self.database)})",
            font=('Arial', 12),
            bg='#16213e',
            fg='#95a5a6'
        )
        self.face_count_label.pack(side=tk.LEFT, padx=5)
        
        # Search box
        search_frame = tk.Frame(faces_frame, bg='#16213e')
        search_frame.pack(fill=tk.X, pady=(10, 5))
        
        tk.Label(
            search_frame,
            text="🔍",
            font=('Arial', 12),
            bg='#16213e',
            fg='white'
        ).pack(side=tk.LEFT)
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.filter_faces())
        
        search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            font=('Arial', 10),
            bg='#0f3460',
            fg='white',
            insertbackground='white',
            relief=tk.FLAT
        )
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Listbox with scrollbar
        list_frame = tk.Frame(faces_frame, bg='#16213e')
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.faces_listbox = tk.Listbox(
            list_frame,
            font=('Arial', 10),
            bg='#0f3460',
            fg='#ecf0f1',
            selectbackground='#3498db',
            selectforeground='white',
            yscrollcommand=scrollbar.set,
            relief=tk.FLAT
        )
        self.faces_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.faces_listbox.yview)
        
        # Action buttons
        action_frame = tk.Frame(faces_frame, bg='#16213e')
        action_frame.pack(fill=tk.X, pady=(5, 0))
        
        view_btn = tk.Button(
            action_frame,
            text="👁️ View",
            command=self.view_selected,
            font=('Arial', 9),
            bg='#3498db',
            fg='white',
            cursor='hand2',
            relief=tk.FLAT,
            padx=10
        )
        view_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        
        delete_btn = tk.Button(
            action_frame,
            text="🗑️ Delete",
            command=self.delete_selected,
            font=('Arial', 9),
            bg='#e74c3c',
            fg='white',
            cursor='hand2',
            relief=tk.FLAT,
            padx=10
        )
        delete_btn.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(2, 0))
        
        # Update faces list
        self.update_faces_list()
        
        # FPS counter variables
        self.frame_count = 0
        self.fps_start_time = time.time()
    
    def create_button(self, parent, text, command, bg_color, state=tk.NORMAL):
        """Create a styled button"""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=('Arial', 11, 'bold'),
            bg=bg_color,
            fg='white',
            cursor='hand2',
            relief=tk.FLAT,
            height=2,
            state=state
        )
        return btn
    
    def update_faces_list(self, filter_text=""):
        """Update the registered faces listbox"""
        self.faces_listbox.delete(0, tk.END)
        
        for person_id, info in self.database.items():
            display_text = f"👤 {info['name']}"
            if info.get('employee_id'):
                display_text += f" (ID: {info['employee_id']})"
            
            # Filter if needed
            if filter_text.lower() in display_text.lower():
                self.faces_listbox.insert(tk.END, display_text)
        
        self.face_count_label.config(text=f"({len(self.database)})")
    
    def filter_faces(self):
        """Filter faces based on search text"""
        self.update_faces_list(self.search_var.get())
    
    def toggle_camera(self):
        """Start or stop the camera"""
        if not self.is_running:
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                messagebox.showerror("Error", "Could not open camera!")
                return
            
            # Set camera properties for better performance
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.camera.set(cv2.CAP_PROP_FPS, 30)
            
            self.is_running = True
            self.camera_btn.config(text="🛑 Stop Camera", bg='#c0392b')
            self.register_btn.config(state=tk.NORMAL)
            self.recognize_btn.config(state=tk.NORMAL)
            self.status_label.config(text="🟢 Status: Camera Active")
            self.update_frame()
        else:
            self.is_running = False
            self.mode = "idle"
            self.recognition_active = False
            if self.camera:
                self.camera.release()
            self.camera_btn.config(text="🎥 Start Camera", bg='#27ae60')
            self.register_btn.config(state=tk.DISABLED)
            self.recognize_btn.config(state=tk.DISABLED)
            self.stop_mode_btn.config(state=tk.DISABLED)
            self.video_label.config(image='')
            self.status_label.config(text="⚪ Status: Camera Off")
            self.fps_label.config(text="FPS: 0")
    
    def update_frame(self):
        """Update the video frame"""
        if self.is_running and self.camera:
            ret, frame = self.camera.read()
            if ret:
                self.current_frame = frame.copy()
                
                # Calculate FPS
                self.frame_count += 1
                if self.frame_count >= 30:
                    elapsed = time.time() - self.fps_start_time
                    fps = self.frame_count / elapsed
                    self.fps_label.config(text=f"FPS: {fps:.1f}")
                    self.frame_count = 0
                    self.fps_start_time = time.time()
                
                # Process frame based on mode
                if self.mode == "recognize" and self.recognition_active:
                    # Run recognition in thread to avoid blocking
                    threading.Thread(target=self.recognize_faces_thread, args=(frame.copy(),), daemon=True).start()
                    frame = self.draw_recognition_ui(frame)
                elif self.mode == "register":
                    frame = self.draw_registration_box(frame)
                
                # Display frame
                self.display_frame(frame)
            
            self.root.after(10, self.update_frame)
    
    def display_frame(self, frame):
        """Display frame on GUI"""
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        
        # Resize to fit display
        display_width = 900
        display_height = 650
        img = img.resize((display_width, display_height), Image.Resampling.LANCZOS)
        
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.imgtk = imgtk
        self.video_label.configure(image=imgtk)
    
    def draw_registration_box(self, frame):
        """Draw a box for face registration"""
        h, w = frame.shape[:2]
        box_size = 350
        x1 = (w - box_size) // 2
        y1 = (h - box_size) // 2
        x2 = x1 + box_size
        y2 = y1 + box_size
        
        # Draw main box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
        
        # Draw corners
        corner_length = 30
        # Top-left
        cv2.line(frame, (x1, y1), (x1 + corner_length, y1), (0, 255, 0), 5)
        cv2.line(frame, (x1, y1), (x1, y1 + corner_length), (0, 255, 0), 5)
        # Top-right
        cv2.line(frame, (x2, y1), (x2 - corner_length, y1), (0, 255, 0), 5)
        cv2.line(frame, (x2, y1), (x2, y1 + corner_length), (0, 255, 0), 5)
        # Bottom-left
        cv2.line(frame, (x1, y2), (x1 + corner_length, y2), (0, 255, 0), 5)
        cv2.line(frame, (x1, y2), (x1, y2 - corner_length), (0, 255, 0), 5)
        # Bottom-right
        cv2.line(frame, (x2, y2), (x2 - corner_length, y2), (0, 255, 0), 5)
        cv2.line(frame, (x2, y2), (x2, y2 - corner_length), (0, 255, 0), 5)
        
        # Instructions
        instruction_text = ""
        if hasattr(self, 'registration_step'):
            if self.registration_step == 0:
                instruction_text = "Step 1: Look STRAIGHT into camera"
            elif self.registration_step == 1:
                instruction_text = "Step 2: Turn your head SLIGHTLY LEFT"
            elif self.registration_step == 2:
                instruction_text = "Step 3: Turn your head SLIGHTLY RIGHT"
        else:
             instruction_text = "Position your face in the frame"
             
        cv2.putText(frame, instruction_text, (x1-50, y1-20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame, "Press SPACE to capture", (x1+20, y2+40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        
        return frame
    
    def draw_recognition_ui(self, frame):
        """Draw UI elements for recognition mode"""
        cv2.putText(frame, "Recognition Active", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"Registered: {len(self.database)} faces", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return frame
    
    def start_registration(self):
        """Start the registration mode"""
        self.mode = "register"
        self.registration_step = 0
        self.registration_images = []
        self.status_label.config(text="🔵 Status: Registration Mode - Step 1/3 (Front)")
        self.register_btn.config(state=tk.DISABLED)
        self.recognize_btn.config(state=tk.DISABLED)
        self.stop_mode_btn.config(state=tk.NORMAL)
        
        # Bind spacebar for capture
        self.root.bind('<space>', self.capture_face)
    
    def capture_face(self, event=None):
        """Capture and register a face sequentially (Front, Left, Right)"""
        if self.current_frame is None:
            return
            
        frame_to_save = self.current_frame.copy()
        self.registration_images.append(frame_to_save)
        self.registration_step += 1
        
        if self.registration_step == 1:
            self.status_label.config(text="🔵 Status: Registration Mode - Step 2/3 (Left)")
            return
        elif self.registration_step == 2:
            self.status_label.config(text="🔵 Status: Registration Mode - Step 3/3 (Right)")
            return
            
        # Unbind spacebar temporarily while dialog is open
        self.root.unbind('<space>')
        
        
        # Create registration dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Register New Face")
        dialog.geometry("400x300")
        dialog.configure(bg='#2c3e50')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.geometry("+%d+%d" % (self.root.winfo_x() + 400, self.root.winfo_y() + 200))
        
        tk.Label(dialog, text="Enter Person Details", font=('Arial', 16, 'bold'),
                bg='#2c3e50', fg='white').pack(pady=20)
        
        # Form fields
        fields_frame = tk.Frame(dialog, bg='#2c3e50')
        fields_frame.pack(padx=30, pady=10, fill=tk.BOTH, expand=True)
        
        # Name
        tk.Label(fields_frame, text="Name *", font=('Arial', 10),
                bg='#2c3e50', fg='white').grid(row=0, column=0, sticky=tk.W, pady=5)
        name_entry = tk.Entry(fields_frame, font=('Arial', 10), width=25)
        name_entry.grid(row=0, column=1, pady=5, padx=(10, 0))
        name_entry.focus()
        
        # Employee ID
        tk.Label(fields_frame, text="Employee ID", font=('Arial', 10),
                bg='#2c3e50', fg='white').grid(row=1, column=0, sticky=tk.W, pady=5)
        emp_id_entry = tk.Entry(fields_frame, font=('Arial', 10), width=25)
        emp_id_entry.grid(row=1, column=1, pady=5, padx=(10, 0))
        
        # Email
        tk.Label(fields_frame, text="Email", font=('Arial', 10),
                bg='#2c3e50', fg='white').grid(row=2, column=0, sticky=tk.W, pady=5)
        email_entry = tk.Entry(fields_frame, font=('Arial', 10), width=25)
        email_entry.grid(row=2, column=1, pady=5, padx=(10, 0))
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg='#2c3e50')
        btn_frame.pack(pady=20)
        
        def save_registration():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Name is required!")
                return
            
            # Generate ID based on Name and Employee ID
            emp_id = emp_id_entry.get().strip()
            safe_name = name.replace(" ", "_")
            safe_id = emp_id.replace(" ", "_") if emp_id else "NoID"
            person_id = f"{safe_name}_{safe_id}"
            
            # Save face images
            image_paths = []
            suffixes = ['front', 'left', 'right']
            
            for i, img in enumerate(self.registration_images):
                face_path = os.path.join(self.faces_dir, f"{person_id}_{suffixes[i]}.jpg")
                cv2.imwrite(face_path, img)
                image_paths.append(face_path)
            
            # Save to database
            self.database[person_id] = {
                "name": name,
                "email": email_entry.get().strip(),
                "employee_id": emp_id_entry.get().strip(),
                "image_paths": image_paths, # Store all 3 paths
                "registered_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.save_database()
            
            self.update_faces_list()
            messagebox.showinfo("Success", f"Face registered successfully for {name}!")
            dialog.destroy()
            self.stop_mode()
        
        tk.Button(btn_frame, text="✓ Save", command=save_registration,
                 font=('Arial', 11, 'bold'), bg='#27ae60', fg='white',
                 cursor='hand2', width=10).pack(side=tk.LEFT, padx=5)
        
        def cancel_registration():
            dialog.destroy()
            self.stop_mode()
            
        tk.Button(btn_frame, text="✗ Cancel", command=cancel_registration,
                 font=('Arial', 11, 'bold'), bg='#e74c3c', fg='white',
                 cursor='hand2', width=10).pack(side=tk.LEFT, padx=5)
    
    def start_recognition(self):
        """Start the recognition mode"""
        if len(self.database) == 0:
            messagebox.showwarning("Warning", "No faces registered yet!\nPlease register at least one face first.")
            return
        
        self.mode = "recognize"
        self.recognition_active = True
        self.last_recognition = {}
        self.status_label.config(text="🟠 Status: Recognition Active")
        self.register_btn.config(state=tk.DISABLED)
        self.recognize_btn.config(state=tk.DISABLED)
        self.stop_mode_btn.config(state=tk.NORMAL)
    
    def recognize_faces_thread(self, frame):
        """Process frame for face recognition in separate thread"""
        try:
            # Detect faces
            face_objs = DeepFace.extract_faces(
                img_path=frame,
                detector_backend=self.detector_backend,
                enforce_detection=False,
                align=True
            )
            
            for face_obj in face_objs:
                facial_area = face_obj['facial_area']
                x, y, w, h = facial_area['x'], facial_area['y'], facial_area['w'], facial_area['h']
                
                # Extract face region
                face_img = frame[y:y+h, x:x+w]
                
                # Recognize face
                recognized = False
                best_match = None
                min_distance = float('inf')
                
                for person_id, info in self.database.items():
                    try:
                        # Check cooldown
                        current_time = time.time()
                        if person_id in self.last_recognition:
                            if current_time - self.last_recognition[person_id] < self.recognition_cooldown:
                                continue
                        
                        # Support both new array format and legacy single image format
                        target_images = info.get('image_paths', [])
                        if not target_images and 'image_path' in info:
                            target_images = [info['image_path']]
                            
                        person_min_dist = float('inf')
                        verified = False
                        
                        for target_img in target_images:
                            try:
                                result = DeepFace.verify(
                                    img1_path=face_img,
                                    img2_path=target_img,
                                    model_name=self.model_name,
                                    detector_backend=self.detector_backend,
                                    distance_metric=self.distance_metric,
                                    enforce_detection=False
                                )
                                
                                if result['verified'] and result['distance'] < person_min_dist:
                                    person_min_dist = result['distance']
                                    verified = True
                            except Exception as e:
                                continue
                                
                        if verified and person_min_dist < min_distance:
                            min_distance = person_min_dist
                            best_match = (person_id, info)
                            recognized = True
                    
                    except Exception as e:
                        continue
                
                if recognized and best_match:
                    person_id, info = best_match
                    self.last_recognition[person_id] = time.time()
                    
                    # Log attendance
                    self.log_attendance(person_id, info)
                    
                    # Draw on frame (in main thread)
                    self.root.after(0, lambda: self.show_recognition_popup(info['name']))
        
        except Exception as e:
            pass
    
    def show_recognition_popup(self, name):
        """Show recognition notification"""
        popup = tk.Toplevel(self.root)
        popup.title("Face Recognized")
        popup.geometry("300x150")
        popup.configure(bg='#27ae60')
        popup.transient(self.root)
        
        # Position at top right
        popup.geometry("+%d+%d" % (self.root.winfo_x() + self.root.winfo_width() - 350,
                                   self.root.winfo_y() + 50))
        
        tk.Label(popup, text="✓ Face Recognized", font=('Arial', 14, 'bold'),
                bg='#27ae60', fg='white').pack(pady=10)
        
        tk.Label(popup, text=name, font=('Arial', 18, 'bold'),
                bg='#27ae60', fg='white').pack(pady=10)
        
        tk.Label(popup, text=datetime.now().strftime("%H:%M:%S"), font=('Arial', 10),
                bg='#27ae60', fg='white').pack(pady=5)
        
        # Auto close after 2 seconds
        popup.after(2000, popup.destroy)
    
    def log_attendance(self, person_id, info):
        """Log attendance for recognized person"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(self.attendance_file, 'a') as f:
            f.write(f"{timestamp},{info['name']},{info.get('employee_id', 'N/A')},Present\n")
    
    def stop_mode(self):
        """Stop current mode"""
        self.mode = "idle"
        self.recognition_active = False
        self.status_label.config(text="🟢 Status: Camera Active")
        self.register_btn.config(state=tk.NORMAL)
        self.recognize_btn.config(state=tk.NORMAL)
        self.stop_mode_btn.config(state=tk.DISABLED)
        self.root.unbind('<space>')
    
    def view_selected(self):
        """View details of selected face"""
        selection = self.faces_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a face to view!")
            return
        
        # Get actual person_id accounting for filter
        filtered_ids = []
        filter_text = self.search_var.get()
        for person_id, info in self.database.items():
            display_text = f"👤 {info['name']}"
            if info.get('employee_id'):
                display_text += f" (ID: {info['employee_id']})"
            if filter_text.lower() in display_text.lower():
                filtered_ids.append(person_id)
        
        if not filtered_ids or selection[0] >= len(filtered_ids):
            return
            
        person_id = filtered_ids[selection[0]]
        info = self.database[person_id]
        
        # Create view dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Details - {info['name']}")
        dialog.geometry("500x600")
        dialog.configure(bg='#2c3e50')
        dialog.transient(self.root)
        
        # Show image
        target_images = info.get('image_paths', [])
        if not target_images and 'image_path' in info:
            target_images = [info['image_path']]
            
        if target_images and os.path.exists(target_images[0]):
            img = Image.open(target_images[0])
            img = img.resize((200, 200), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            img_label = tk.Label(dialog, image=photo, bg='#2c3e50')
            img_label.image = photo
            img_label.pack(pady=20)
        
        # Show details
        details_frame = tk.Frame(dialog, bg='#34495e', relief=tk.RAISED, borderwidth=2)
        details_frame.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)
        
        details = [
            ("Name:", info['name']),
            ("Employee ID:", info.get('employee_id', 'N/A')),
            ("Email:", info.get('email', 'N/A')),
            ("Registered:", info.get('registered_date', 'N/A'))
        ]
        
        for i, (label, value) in enumerate(details):
            tk.Label(details_frame, text=label, font=('Arial', 11, 'bold'),
                    bg='#34495e', fg='#ecf0f1', anchor=tk.W).grid(
                    row=i, column=0, sticky=tk.W, padx=20, pady=10)
            tk.Label(details_frame, text=value, font=('Arial', 11),
                    bg='#34495e', fg='white', anchor=tk.W).grid(
                    row=i, column=1, sticky=tk.W, padx=20, pady=10)
        
        tk.Button(dialog, text="Close", command=dialog.destroy,
                 font=('Arial', 11), bg='#7f8c8d', fg='white',
                 cursor='hand2', width=15).pack(pady=20)
    
    def delete_selected(self):
        """Delete selected face from database"""
        selection = self.faces_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a face to delete!")
            return
        
        # Get actual person_id accounting for filter
        filtered_ids = []
        filter_text = self.search_var.get()
        for person_id, info in self.database.items():
            display_text = f"👤 {info['name']}"
            if info.get('employee_id'):
                display_text += f" (ID: {info['employee_id']})"
            if filter_text.lower() in display_text.lower():
                filtered_ids.append(person_id)
        
        if not filtered_ids or selection[0] >= len(filtered_ids):
            return
            
        person_id = filtered_ids[selection[0]]
        name = self.database[person_id]['name']
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete\n{name} from the database?"):
            # Delete image files
            info = self.database[person_id]
            target_images = info.get('image_paths', [])
            if 'image_path' in info:
                target_images.append(info['image_path'])
                
            for image_path in target_images:
                if os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except Exception as e:
                        print(f"Failed to delete {image_path}: {e}")
            
            # Delete from database
            del self.database[person_id]
            self.save_database()
            
            self.update_faces_list(self.search_var.get())
            messagebox.showinfo("Success", f"{name} deleted successfully!")

    def show_delete_dialog(self):
        """Show a dedicated dialog to select and delete a student"""
        if not self.database:
            messagebox.showinfo("Info", "No students registered yet!")
            return
            
        dialog = tk.Toplevel(self.root)
        dialog.title("Delete Student")
        dialog.geometry("450x550")
        dialog.configure(bg='#1a1a2e')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.geometry("+%d+%d" % (self.root.winfo_x() + 400, self.root.winfo_y() + 100))
        
        tk.Label(
            dialog,
            text="🗑️ Delete Student Record",
            font=('Arial', 16, 'bold'),
            bg='#1a1a2e',
            fg='#e74c3c'
        ).pack(pady=15)
        
        # Search Box
        search_frame = tk.Frame(dialog, bg='#1a1a2e')
        search_frame.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(search_frame, text="🔍 Search:", font=('Arial', 11), bg='#1a1a2e', fg='white').pack(side=tk.LEFT)
        search_var = tk.StringVar()
        
        def filter_dialog_list(*args):
            dialog_list.delete(0, tk.END)
            filter_text = search_var.get().lower()
            for pid, pinfo in self.database.items():
                display_text = f"{pinfo['name']} (ID: {pinfo.get('employee_id', 'N/A')})"
                if filter_text in display_text.lower():
                    dialog_list.insert(tk.END, display_text)
                    
        search_var.trace('w', filter_dialog_list)
        search_entry = tk.Entry(search_frame, textvariable=search_var, font=('Arial', 11), bg='#0f3460', fg='white', insertbackground='white')
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        # ListBox
        list_frame = tk.Frame(dialog, bg='#1a1a2e')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        dialog_list = tk.Listbox(
            list_frame,
            font=('Arial', 11),
            bg='#0f3460',
            fg='#ecf0f1',
            selectbackground='#e74c3c',
            yscrollcommand=scrollbar.set
        )
        dialog_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=dialog_list.yview)
        
        filter_dialog_list() # Populate initially
        
        def confirm_delete():
            selection = dialog_list.curselection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a student to delete!", parent=dialog)
                return
                
            # Figure out who was selected by matching the text back
            selected_text = dialog_list.get(selection[0])
            target_pid = None
            for pid, pinfo in self.database.items():
                if f"{pinfo['name']} (ID: {pinfo.get('employee_id', 'N/A')})" == selected_text:
                    target_pid = pid
                    break
                    
            if not target_pid:
                return
                
            name = self.database[target_pid]['name']
            if messagebox.askyesno("Confirm Delete", f"Permanently delete {name} and all associated images?", parent=dialog):
                # Delete files
                info = self.database[target_pid]
                target_images = info.get('image_paths', [])
                if 'image_path' in info:
                    target_images.append(info['image_path'])
                    
                for image_path in target_images:
                    if os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                        except Exception as e:
                            print(f"Failed to delete {image_path}: {e}")
                
                # Delete from database
                del self.database[target_pid]
                self.save_database()
                
                # Update UI
                self.update_faces_list(self.search_var.get())
                filter_dialog_list() # Refresh dialog list
                
                messagebox.showinfo("Success", f"Deleted {name} successfully!", parent=dialog)
                
        btn_frame = tk.Frame(dialog, bg='#1a1a2e')
        btn_frame.pack(pady=15, fill=tk.X, padx=20)
        
        tk.Button(btn_frame, text="Delete Selected", command=confirm_delete,
                 font=('Arial', 11, 'bold'), bg='#c0392b', fg='white',
                 cursor='hand2', height=2).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
                 
        tk.Button(btn_frame, text="Close", command=dialog.destroy,
                 font=('Arial', 11), bg='#7f8c8d', fg='white',
                 cursor='hand2', height=2).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))
    
    def view_attendance(self):
        """View attendance log"""
        if not os.path.exists(self.attendance_file):
            messagebox.showinfo("Info", "No attendance records found!")
            return
        
        # Create attendance viewer
        dialog = tk.Toplevel(self.root)
        dialog.title("Attendance Log")
        dialog.geometry("800x500")
        dialog.configure(bg='#2c3e50')
        
        tk.Label(dialog, text="📋 Attendance Records", font=('Arial', 16, 'bold'),
                bg='#2c3e50', fg='white').pack(pady=10)
        
        # Text widget with scrollbar
        text_frame = tk.Frame(dialog)
        text_frame.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(text_frame, font=('Courier', 10),
                             yscrollcommand=scrollbar.set, wrap=tk.WORD)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # Load and display attendance
        with open(self.attendance_file, 'r') as f:
            text_widget.insert(tk.END, f.read())
        
        text_widget.config(state=tk.DISABLED)
        
        tk.Button(dialog, text="Close", command=dialog.destroy,
                 font=('Arial', 11), bg='#7f8c8d', fg='white',
                 cursor='hand2', width=15).pack(pady=10)
    
    def show_settings(self):
        """Show model settings dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Model Settings")
        dialog.geometry("500x400")
        dialog.configure(bg='#2c3e50')
        dialog.transient(self.root)
        
        tk.Label(dialog, text="⚙️ DeepFace Model Settings", font=('Arial', 16, 'bold'),
                bg='#2c3e50', fg='white').pack(pady=20)
        
        settings_frame = tk.Frame(dialog, bg='#34495e', relief=tk.RAISED, borderwidth=2)
        settings_frame.pack(padx=30, pady=10, fill=tk.BOTH, expand=True)
        
        # Model selection
        tk.Label(settings_frame, text="Recognition Model:", font=('Arial', 11, 'bold'),
                bg='#34495e', fg='white').grid(row=0, column=0, sticky=tk.W, padx=20, pady=10)
        
        models = ['VGG-Face', 'Facenet', 'Facenet512', 'OpenFace', 'DeepFace', 'DeepID', 'ArcFace', 'Dlib']
        model_var = tk.StringVar(value=self.model_name)
        model_combo = ttk.Combobox(settings_frame, textvariable=model_var, values=models, state='readonly')
        model_combo.grid(row=0, column=1, padx=20, pady=10)
        
        # Detector selection
        tk.Label(settings_frame, text="Face Detector:", font=('Arial', 11, 'bold'),
                bg='#34495e', fg='white').grid(row=1, column=0, sticky=tk.W, padx=20, pady=10)
        
        detectors = ['opencv', 'ssd', 'dlib', 'mtcnn', 'retinaface']
        detector_var = tk.StringVar(value=self.detector_backend)
        detector_combo = ttk.Combobox(settings_frame, textvariable=detector_var, values=detectors, state='readonly')
        detector_combo.grid(row=1, column=1, padx=20, pady=10)
        
        # Distance metric
        tk.Label(settings_frame, text="Distance Metric:", font=('Arial', 11, 'bold'),
                bg='#34495e', fg='white').grid(row=2, column=0, sticky=tk.W, padx=20, pady=10)
        
        metrics = ['cosine', 'euclidean', 'euclidean_l2']
        metric_var = tk.StringVar(value=self.distance_metric)
        metric_combo = ttk.Combobox(settings_frame, textvariable=metric_var, values=metrics, state='readonly')
        metric_combo.grid(row=2, column=1, padx=20, pady=10)
        
        # Cooldown
        tk.Label(settings_frame, text="Recognition Cooldown (s):", font=('Arial', 11, 'bold'),
                bg='#34495e', fg='white').grid(row=3, column=0, sticky=tk.W, padx=20, pady=10)
        
        cooldown_var = tk.IntVar(value=self.recognition_cooldown)
        cooldown_spin = tk.Spinbox(settings_frame, from_=1, to=60, textvariable=cooldown_var, width=18)
        cooldown_spin.grid(row=3, column=1, padx=20, pady=10)
        
        def save_settings():
            self.model_name = model_var.get()
            self.detector_backend = detector_var.get()
            self.distance_metric = metric_var.get()
            self.recognition_cooldown = cooldown_var.get()
            
            self.model_info_label.config(text=f"Model: {self.model_name} | Detector: {self.detector_backend}")
            messagebox.showinfo("Success", "Settings updated successfully!")
            dialog.destroy()
        
        btn_frame = tk.Frame(dialog, bg='#2c3e50')
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="✓ Save", command=save_settings,
                 font=('Arial', 11, 'bold'), bg='#27ae60', fg='white',
                 cursor='hand2', width=10).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="✗ Cancel", command=dialog.destroy,
                 font=('Arial', 11, 'bold'), bg='#e74c3c', fg='white',
                 cursor='hand2', width=10).pack(side=tk.LEFT, padx=5)
    
    def on_closing(self):
        """Handle window closing"""
        if self.is_running:
            self.camera.release()
        cv2.destroyAllWindows()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = OptimizedFaceRecognitionSystem(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
