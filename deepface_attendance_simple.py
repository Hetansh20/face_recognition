"""
DeepFace Attendance System - Simple & Stable Version
Easier to use with better error handling
"""

import cv2
import tkinter as tk
from tkinter import messagebox, simpledialog
from PIL import Image, ImageTk
import json
import os
from deepface import DeepFace
from datetime import datetime
import threading

class SimpleAttendanceSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("DeepFace Attendance System")
        self.root.geometry("1100x650")
        self.root.configure(bg='#2c3e50')
        
        # Variables
        self.camera = None
        self.is_running = False
        self.current_frame = None
        self.mode = "idle"  # idle, register, recognize
        self.processing = False
        
        # Paths
        self.faces_dir = "registered_faces"
        self.database_file = "face_database.json"
        self.attendance_file = "attendance_log.txt"
        
        # Create directories
        os.makedirs(self.faces_dir, exist_ok=True)
        
        # Load database
        self.load_database()
        
        # Setup GUI
        self.setup_gui()
        
        print("System initialized successfully!")
        print("Click 'Start Camera' to begin")
        
    def load_database(self):
        """Load face database"""
        try:
            if os.path.exists(self.database_file):
                with open(self.database_file, 'r') as f:
                    self.database = json.load(f)
            else:
                self.database = {}
                self.save_database()
        except Exception as e:
            print(f"Error loading database: {e}")
            self.database = {}
            self.save_database()
    
    def save_database(self):
        """Save face database"""
        try:
            with open(self.database_file, 'w') as f:
                json.dump(self.database, f, indent=4)
        except Exception as e:
            print(f"Error saving database: {e}")
    
    def setup_gui(self):
        """Setup GUI"""
        # Title
        title = tk.Label(
            self.root,
            text="DeepFace Attendance System",
            font=('Arial', 20, 'bold'),
            bg='#34495e',
            fg='white',
            pady=15
        )
        title.pack(fill=tk.X)
        
        # Main container
        main = tk.Frame(self.root, bg='#2c3e50')
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left - Camera
        left = tk.Frame(main, bg='#34495e', relief=tk.RAISED, bd=2)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        tk.Label(left, text="Camera Feed", font=('Arial', 12, 'bold'),
                bg='#34495e', fg='white', pady=5).pack()
        
        self.video_label = tk.Label(left, bg='black')
        self.video_label.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        self.status_label = tk.Label(
            left,
            text="Status: Camera Off",
            font=('Arial', 11),
            bg='#34495e',
            fg='#ecf0f1',
            pady=10
        )
        self.status_label.pack()
        
        # Right - Controls
        right = tk.Frame(main, bg='#34495e', relief=tk.RAISED, bd=2, width=300)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        right.pack_propagate(False)
        
        # Buttons
        controls = tk.Frame(right, bg='#34495e', pady=20)
        controls.pack(fill=tk.X, padx=15)
        
        tk.Label(controls, text="Controls", font=('Arial', 14, 'bold'),
                bg='#34495e', fg='white').pack(pady=(0, 15))
        
        # Camera button
        self.cam_btn = tk.Button(
            controls,
            text="Start Camera",
            command=self.toggle_camera,
            font=('Arial', 11, 'bold'),
            bg='#27ae60',
            fg='white',
            height=2,
            cursor='hand2'
        )
        self.cam_btn.pack(fill=tk.X, pady=5)
        
        # Register button
        self.reg_btn = tk.Button(
            controls,
            text="Register Face",
            command=self.register_mode,
            font=('Arial', 11, 'bold'),
            bg='#3498db',
            fg='white',
            height=2,
            cursor='hand2',
            state=tk.DISABLED
        )
        self.reg_btn.pack(fill=tk.X, pady=5)
        
        # Recognize button
        self.rec_btn = tk.Button(
            controls,
            text="Start Recognition",
            command=self.recognize_mode,
            font=('Arial', 11, 'bold'),
            bg='#e67e22',
            fg='white',
            height=2,
            cursor='hand2',
            state=tk.DISABLED
        )
        self.rec_btn.pack(fill=tk.X, pady=5)
        
        # Stop button
        self.stop_btn = tk.Button(
            controls,
            text="Stop",
            command=self.stop_mode,
            font=('Arial', 11, 'bold'),
            bg='#95a5a6',
            fg='white',
            height=2,
            cursor='hand2',
            state=tk.DISABLED
        )
        self.stop_btn.pack(fill=tk.X, pady=5)
        
        view_btn = tk.Button(
            controls,
            text="View Attendance",
            command=self.view_attendance,
            font=('Arial', 11, 'bold'),
            bg='#9b59b6',
            fg='white',
            height=2,
            cursor='hand2'
        )
        view_btn.pack(fill=tk.X, pady=5)
        
        # Delete Student button
        del_btn_main = tk.Button(
            controls,
            text="Delete Student",
            command=self.show_delete_dialog,
            font=('Arial', 11, 'bold'),
            bg='#c0392b',
            fg='white',
            height=2,
            cursor='hand2'
        )
        del_btn_main.pack(fill=tk.X, pady=5)
        
        # Registered faces
        tk.Label(right, text="Registered Faces", font=('Arial', 12, 'bold'),
                bg='#34495e', fg='white', pady=10).pack()
        
        list_frame = tk.Frame(right, bg='#34495e')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.faces_list = tk.Listbox(
            list_frame,
            font=('Arial', 10),
            bg='#ecf0f1',
            yscrollcommand=scrollbar.set
        )
        self.faces_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.faces_list.yview)
        
        # Delete button
        del_btn = tk.Button(
            right,
            text="Delete Selected",
            command=self.delete_face,
            font=('Arial', 10),
            bg='#e74c3c',
            fg='white',
            cursor='hand2'
        )
        del_btn.pack(pady=10)
        
        self.update_faces_list()
    
    def update_faces_list(self):
        """Update faces listbox"""
        self.faces_list.delete(0, tk.END)
        for person_id, info in self.database.items():
            self.faces_list.insert(tk.END, f"{info['name']} ({info.get('employee_id', 'N/A')})")
    
    def toggle_camera(self):
        """Start/stop camera"""
        if not self.is_running:
            try:
                self.camera = cv2.VideoCapture(0)
                if not self.camera.isOpened():
                    messagebox.showerror("Error", "Cannot open camera!")
                    return
                
                self.is_running = True
                self.cam_btn.config(text="Stop Camera", bg='#c0392b')
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
            self.cam_btn.config(text="Start Camera", bg='#27ae60')
            self.reg_btn.config(state=tk.DISABLED)
            self.rec_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)
            self.video_label.config(image='')
            self.status_label.config(text="Status: Camera Off")
    
    def update_frame(self):
        """Update video frame"""
        if self.is_running and self.camera:
            ret, frame = self.camera.read()
            if ret:
                self.current_frame = frame.copy()
                
                # Add overlays based on mode
                if self.mode == "register":
                    frame = self.draw_registration_box(frame)
                elif self.mode == "recognize" and not self.processing:
                    cv2.putText(frame, "Recognition Active", (10, 30),
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # Display
                self.display_frame(frame)
            
            self.root.after(30, self.update_frame)
    
    def display_frame(self, frame):
        """Display frame in GUI"""
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            img = img.resize((700, 500), Image.Resampling.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
        except Exception as e:
            print(f"Display error: {e}")
    
    def draw_registration_box(self, frame):
        """Draw registration guide"""
        h, w = frame.shape[:2]
        size = 300
        x1, y1 = (w - size) // 2, (h - size) // 2
        x2, y2 = x1 + size, y1 + size
        
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
        
        instruction_text = ""
        if hasattr(self, 'registration_step'):
            if self.registration_step == 0:
                instruction_text = "Step 1: Look STRAIGHT"
            elif self.registration_step == 1:
                instruction_text = "Step 2: Turn SLIGHTLY LEFT"
            elif self.registration_step == 2:
                instruction_text = "Step 3: Turn SLIGHTLY RIGHT"
        else:
             instruction_text = "Position face in box"
             
        cv2.putText(frame, instruction_text, (x1, y1-10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, "Press SPACE to capture", (x1, y2+30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        return frame
    
    def register_mode(self):
        """Enter registration mode"""
        self.mode = "register"
        self.registration_step = 0
        self.registration_images = []
        self.status_label.config(text="Status: Registration Mode - Step 1/3 (Front)")
        self.reg_btn.config(state=tk.DISABLED)
        self.rec_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.root.bind('<space>', self.capture_face)
    
    def capture_face(self, event=None):
        """Capture and save face"""
        if self.current_frame is None:
            return
            
        frame_to_save = self.current_frame.copy()
        self.registration_images.append(frame_to_save)
        self.registration_step += 1
        
        if self.registration_step == 1:
            self.status_label.config(text="Status: Registration Mode - Step 2/3 (Left)")
            return
        elif self.registration_step == 2:
            self.status_label.config(text="Status: Registration Mode - Step 3/3 (Right)")
            return
            
        # Unbind space temporarily
        self.root.unbind('<space>')
        
        try:
            # Get info
            name = simpledialog.askstring("Register", "Enter name:")
            if not name:
                self.stop_mode()
                return
            
            emp_id = simpledialog.askstring("Register", "Employee ID (optional):")
            
            # Generate ID based on Name and Employee ID
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
                "employee_id": emp_id if emp_id else "",
                "image_paths": image_paths,
                "registered": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.save_database()
            self.update_faces_list()
            
            messagebox.showinfo("Success", f"Registered: {name}")
            self.stop_mode()
            
        except Exception as e:
            messagebox.showerror("Error", f"Registration failed: {e}")
            self.stop_mode()
    
    def recognize_mode(self):
        """Enter recognition mode"""
        if not self.database:
            messagebox.showwarning("Warning", "No faces registered!")
            return
        
        self.mode = "recognize"
        self.status_label.config(text="Status: Recognition Active")
        self.reg_btn.config(state=tk.DISABLED)
        self.rec_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        # Start recognition thread
        threading.Thread(target=self.recognition_loop, daemon=True).start()
    
    def recognition_loop(self):
        """Continuous recognition loop"""
        print("Recognition started...")
        
        while self.mode == "recognize":
            if self.current_frame is not None and not self.processing:
                self.processing = True
                self.recognize_current_frame()
                self.processing = False
            
            # Wait before next recognition
            import time
            time.sleep(2)
    
    def recognize_current_frame(self):
        """Recognize face in current frame"""
        try:
            frame = self.current_frame.copy()
            
            # Try to find faces
            for person_id, info in self.database.items():
                try:
                    target_images = info.get('image_paths', [])
                    if not target_images and 'image_path' in info:
                        target_images = [info['image_path']]
                        
                    verified = False
                    
                    for target_img in target_images:
                        try:
                            result = DeepFace.verify(
                                img1_path=frame,
                                img2_path=target_img,
                                model_name='Facenet512',
                                detector_backend='opencv',
                                enforce_detection=False
                            )
                            
                            if result['verified']:
                                verified = True
                                break
                        except Exception as e:
                            continue
                            
                    if verified:
                        name = info['name']
                        print(f"Recognized: {name}")
                        
                        # Log attendance
                        self.log_attendance(person_id, info)
                        
                        # Show notification
                        self.root.after(0, lambda: self.show_notification(name))
                        break
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"Recognition error: {e}")
    
    def show_notification(self, name):
        """Show recognition notification"""
        popup = tk.Toplevel(self.root)
        popup.title("Recognized")
        popup.geometry("300x150")
        popup.configure(bg='#27ae60')
        
        tk.Label(popup, text="Face Recognized!", font=('Arial', 14, 'bold'),
                bg='#27ae60', fg='white').pack(pady=20)
        tk.Label(popup, text=name, font=('Arial', 16, 'bold'),
                bg='#27ae60', fg='white').pack(pady=10)
        tk.Label(popup, text=datetime.now().strftime("%H:%M:%S"),
                font=('Arial', 10), bg='#27ae60', fg='white').pack(pady=5)
        
        popup.after(2000, popup.destroy)
    
    def log_attendance(self, person_id, info):
        """Log attendance"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.attendance_file, 'a') as f:
                f.write(f"{timestamp} - {info['name']} (ID: {info.get('employee_id', 'N/A')})\n")
        except Exception as e:
            print(f"Logging error: {e}")
    
    def stop_mode(self):
        """Stop current mode"""
        self.mode = "idle"
        self.status_label.config(text="Status: Camera Active")
        self.reg_btn.config(state=tk.NORMAL)
        self.rec_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.root.unbind('<space>')
    
    def delete_face(self):
        """Delete selected face"""
        selection = self.faces_list.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Select a face to delete!")
            return
        
        person_id = list(self.database.keys())[selection[0]]
        name = self.database[person_id]['name']
        
        if messagebox.askyesno("Confirm", f"Delete {name}?"):
            try:
                # Delete image
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
                self.update_faces_list()
                
                messagebox.showinfo("Success", f"Deleted: {name}")
            except Exception as e:
                messagebox.showerror("Error", f"Delete failed: {e}")

    def show_delete_dialog(self):
        """Show a dedicated dialog to select and delete a student"""
        if not self.database:
            messagebox.showinfo("Info", "No students registered yet!")
            return
            
        dialog = tk.Toplevel(self.root)
        dialog.title("Delete Student")
        dialog.geometry("450x550")
        dialog.configure(bg='#2c3e50')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.geometry("+%d+%d" % (self.root.winfo_x() + 400, self.root.winfo_y() + 100))
        
        tk.Label(
            dialog,
            text="🗑️ Delete Student Record",
            font=('Arial', 16, 'bold'),
            bg='#2c3e50',
            fg='#e74c3c'
        ).pack(pady=15)
        
        # Search Box
        search_frame = tk.Frame(dialog, bg='#2c3e50')
        search_frame.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(search_frame, text="🔍 Search:", font=('Arial', 11), bg='#2c3e50', fg='white').pack(side=tk.LEFT)
        search_var = tk.StringVar()
        
        def filter_dialog_list(*args):
            dialog_list.delete(0, tk.END)
            filter_text = search_var.get().lower()
            for pid, pinfo in self.database.items():
                display_text = f"{pinfo['name']} (ID: {pinfo.get('employee_id', 'N/A')})"
                if filter_text in display_text.lower():
                    dialog_list.insert(tk.END, display_text)
                    
        search_var.trace('w', filter_dialog_list)
        search_entry = tk.Entry(search_frame, textvariable=search_var, font=('Arial', 11), bg='#34495e', fg='white', insertbackground='white')
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        # ListBox
        list_frame = tk.Frame(dialog, bg='#2c3e50')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        dialog_list = tk.Listbox(
            list_frame,
            font=('Arial', 11),
            bg='#ecf0f1',
            fg='black',
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
                self.update_faces_list()
                filter_dialog_list() # Refresh dialog list
                
                messagebox.showinfo("Success", f"Deleted {name} successfully!", parent=dialog)
                
        btn_frame = tk.Frame(dialog, bg='#2c3e50')
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
            messagebox.showinfo("Info", "No attendance records!")
            return
        
        window = tk.Toplevel(self.root)
        window.title("Attendance Log")
        window.geometry("600x400")
        
        tk.Label(window, text="Attendance Records", font=('Arial', 14, 'bold')).pack(pady=10)
        
        text = tk.Text(window, font=('Courier', 10), wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        try:
            with open(self.attendance_file, 'r') as f:
                text.insert(tk.END, f.read())
        except Exception as e:
            text.insert(tk.END, f"Error reading log: {e}")
        
        text.config(state=tk.DISABLED)
    
    def cleanup(self):
        """Cleanup on exit"""
        self.is_running = False
        if self.camera:
            self.camera.release()
        cv2.destroyAllWindows()
        self.root.destroy()

def main():
    print("=" * 50)
    print("DeepFace Attendance System")
    print("=" * 50)
    print("\nStarting application...")
    
    try:
        root = tk.Tk()
        app = SimpleAttendanceSystem(root)
        root.protocol("WM_DELETE_WINDOW", app.cleanup)
        root.mainloop()
    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure you have installed all requirements:")
        print("pip install deepface opencv-python Pillow tensorflow")

if __name__ == "__main__":
    main()
