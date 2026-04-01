"""
Faculty UI — Login + Attendance Session
=========================================
Faculty logs in with email + passcode, sees active class from timetable,
then launches the InsightFace window linked to the current DB session.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from datetime import datetime
from database import Database
from auth import auth_manager
from timetable_manager import timetable_manager
from attendance_marker import attendance_marker


class FacultyLoginWindow:
    def __init__(self, root, on_close=None):
        self.root = root
        self.on_close = on_close
        self.root.title("Faculty Login — InsightFace Attendance")
        self.root.geometry("480x520")
        self.root.resizable(False, False)
        self.root.configure(bg='#0d1117')

        self.session_token = None
        self.faculty_data = None

        self._setup_ui()

    def _setup_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg='#161b22')
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="👤 Faculty Login", font=('Segoe UI', 22, 'bold'),
                 bg='#161b22', fg='#58a6ff').pack(pady=(22, 4))
        tk.Label(hdr, text="Enter your credentials to start an attendance session",
                 font=('Segoe UI', 10), bg='#161b22', fg='#8b949e').pack(pady=(0, 20))

        # Form
        form = tk.Frame(self.root, bg='#0d1117')
        form.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

        def lbl(text):
            tk.Label(form, text=text, font=('Segoe UI', 10, 'bold'),
                     bg='#0d1117', fg='#c9d1d9').pack(anchor=tk.W, pady=(10, 2))

        def entry(var, show=''):
            e = tk.Entry(form, textvariable=var, font=('Segoe UI', 11),
                         bg='#161b22', fg='#e6edf3', insertbackground='white',
                         relief=tk.FLAT, bd=0, show=show)
            e.pack(fill=tk.X, ipady=8, pady=(0, 4))
            tk.Frame(form, bg='#30363d', height=1).pack(fill=tk.X)
            return e

        lbl("Email Address")
        self.email_var = tk.StringVar()
        entry(self.email_var)

        lbl("Passcode")
        self.pass_var = tk.StringVar()
        e = entry(self.pass_var, show='•')
        e.bind('<Return>', lambda _: self._do_login())

        # Status
        self.status_var = tk.StringVar()
        tk.Label(form, textvariable=self.status_var, font=('Segoe UI', 9),
                 bg='#0d1117', fg='#f85149').pack(pady=(14, 0))

        # Login button
        self.login_btn = tk.Button(form, text='LOGIN', command=self._do_login,
                                   font=('Segoe UI', 12, 'bold'),
                                   bg='#1f6feb', fg='white', relief=tk.FLAT,
                                   activebackground='#388bfd', cursor='hand2')
        self.login_btn.pack(fill=tk.X, ipady=10, pady=(20, 0))

        # Back link
        tk.Button(form, text='← Back to Launcher',
                  command=lambda: self.on_close() if self.on_close else self.root.destroy(),
                  font=('Segoe UI', 9), bg='#0d1117', fg='#58a6ff',
                  relief=tk.FLAT, cursor='hand2').pack(pady=(16, 0))

    def _do_login(self):
        email = self.email_var.get().strip()
        passcode = self.pass_var.get().strip()
        if not email or not passcode:
            self.status_var.set("Please enter both email and passcode.")
            return
        self.login_btn.config(state=tk.DISABLED, text='Logging in…')
        self.status_var.set("")
        threading.Thread(target=self._perform_login, args=(email, passcode), daemon=True).start()

    def _perform_login(self, email, passcode):
        try:
            token, msg = auth_manager.faculty_login(email, passcode)
            if token:
                self.session_token = token
                session_data, _ = auth_manager.verify_session(token)
                self.faculty_data = session_data
                self.email_var.set("")
                self.pass_var.set("")
                self.root.after(0, self._open_session_window)
            else:
                self.root.after(0, lambda: (
                    self.status_var.set(msg),
                    self.login_btn.config(state=tk.NORMAL, text='LOGIN')
                ))
        except Exception as e:
            self.root.after(0, lambda: (
                self.status_var.set(f"Error: {e}"),
                self.login_btn.config(state=tk.NORMAL, text='LOGIN')
            ))

    def _open_session_window(self):
        self.root.withdraw()
        win = tk.Toplevel(self.root)
        FacultySessionWindow(win, self.faculty_data, self.session_token,
                             on_logout=self._on_logout)

    def _on_logout(self):
        if self.session_token:
            auth_manager.logout(self.session_token)
        self.session_token = None
        self.faculty_data = None
        self.login_btn.config(state=tk.NORMAL, text='LOGIN')
        self.status_var.set("Logged out successfully.")
        self.root.deiconify()


class FacultySessionWindow:
    """Shows active class, lets faculty start InsightFace recognition, end session."""

    def __init__(self, root, faculty_data, session_token, on_logout=None):
        self.root = root
        self.faculty_data = faculty_data
        self.session_token = session_token
        self.on_logout = on_logout

        self.root.title(f"Session — {faculty_data.get('name', '')}")
        self.root.geometry("720x620")
        self.root.configure(bg='#0d1117')

        self.db = Database()
        self.active_class = None
        self.session_id = None
        self.recognized_students = set()

        self._setup_ui()
        self._load_active_class()

    def _setup_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg='#161b22')
        hdr.pack(fill=tk.X)
        name = self.faculty_data.get('name', 'Faculty')
        dept = self.faculty_data.get('department', '')
        tk.Label(hdr, text=f"Welcome, {name}",
                 font=('Segoe UI', 18, 'bold'), bg='#161b22', fg='#e6edf3').pack(pady=(16, 2))
        tk.Label(hdr, text=dept, font=('Segoe UI', 10),
                 bg='#161b22', fg='#8b949e').pack(pady=(0, 14))

        content = tk.Frame(self.root, bg='#0d1117')
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # Active class card
        class_frame = tk.LabelFrame(content, text="  Active Class  ",
                                    font=('Segoe UI', 11, 'bold'),
                                    bg='#161b22', fg='#58a6ff',
                                    labelanchor='n', bd=1, relief=tk.GROOVE)
        class_frame.pack(fill=tk.X, pady=(0, 14))

        self.class_info_var = tk.StringVar(value="Detecting active class…")
        tk.Label(class_frame, textvariable=self.class_info_var,
                 font=('Segoe UI', 10), bg='#161b22', fg='#c9d1d9',
                 justify=tk.LEFT).pack(padx=20, pady=14, anchor=tk.W)

        # Session status log
        log_frame = tk.LabelFrame(content, text="  Session Log  ",
                                  font=('Segoe UI', 11, 'bold'),
                                  bg='#161b22', fg='#2ea043',
                                  labelanchor='n', bd=1, relief=tk.GROOVE)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        self.log = tk.Text(log_frame, height=10, font=('Consolas', 9),
                           bg='#0d1117', fg='#7ee787', relief=tk.FLAT, state=tk.DISABLED)
        sb = tk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Buttons
        btn_row = tk.Frame(content, bg='#0d1117')
        btn_row.pack(fill=tk.X)

        def btn(text, cmd, color):
            b = tk.Button(btn_row, text=text, command=cmd,
                          font=('Segoe UI', 10, 'bold'),
                          bg=color, fg='white', relief=tk.FLAT,
                          cursor='hand2', activebackground=color)
            b.pack(side=tk.LEFT, padx=4, ipady=8, ipadx=12)
            return b

        self.start_btn = btn("▶ Start Recognition", self._start_recognition, '#1f6feb')
        self.end_btn   = btn("⏹ End Session",       self._end_session,       '#da3633')
        self.csv_btn   = btn("📁 Export CSV",        self._export_csv,        '#d29922')
        self.email_btn = btn("✉ Email Report",       self._email_report,      '#8957e5')
        btn("🚪 Logout",                             self._logout,            '#484f58')

        # Registered students count
        self.recog_var = tk.StringVar(value="Recognized this session: 0")
        tk.Label(content, textvariable=self.recog_var,
                 font=('Segoe UI', 9), bg='#0d1117', fg='#8b949e').pack(pady=(8, 0))

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, f"[{ts}] {msg}\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _load_active_class(self):
        try:
            faculty_id = self.faculty_data['faculty_id']
            active, msg = auth_manager.get_active_class(faculty_id)
            if active:
                self.active_class = active
                info = (f"Class: {active[2]}\n"
                        f"Day: {active[3]}     Time: {active[4]} – {active[5]}\n"
                        f"Room: {active[6] or 'N/A'}")
                self.class_info_var.set(info)
                self._log(f"✓ Active class: {active[2]}")
                # Start a session in DB
                faculty_id = self.faculty_data['faculty_id']
                total = len(self.db.get_all_students())
                self.session_id = self.db.create_session(faculty_id, active[0], total)
                self._log(f"Session #{self.session_id} started ({total} students enrolled)")
            else:
                self.class_info_var.set("No active class right now.\n"
                                        "Check your timetable or ask the admin to add one.")
                self._log("⚠ No active class detected for current time.")
        except Exception as e:
            self._log(f"✗ Error loading class: {e}")

    def _start_recognition(self):
        if not self.active_class:
            messagebox.showwarning("No Active Class",
                                   "There is no active class scheduled right now.\n"
                                   "You can still use the standalone mode from the launcher.")
            return

        timetable_id = self.active_class[0]
        session_id   = self.session_id

        self._log("Launching InsightFace recognition…")

        try:
            from insightface_attendance import InsightFaceAttendanceSystem

            win = tk.Toplevel(self.root)
            app = InsightFaceAttendanceSystem(win,
                                              timetable_id=timetable_id,
                                              session_id=session_id,
                                              on_attendance_marked=self._on_attendance_update)

            self._log("✓ InsightFace window opened — waiting for recognitions")
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch InsightFace:\n{e}")
            self._log(f"✗ Launch error: {e}")

    def _on_attendance_update(self, name):
        """Callback fired by InsightFace when someone is marked present."""
        self.recognized_students.add(name)
        count = len(self.recognized_students)
        self.recog_var.set(f"Recognized this session: {count}")
        self._log(f"✓ Marked present: {name}")

        # Update DB session count
        if self.session_id:
            try:
                self.db.end_session(self.session_id, count)
            except Exception:
                pass

    def _end_session(self):
        if not self.session_id:
            messagebox.showwarning("No Session", "No active session to end.")
            return
        n = len(self.recognized_students)
        if not messagebox.askyesno("End Session",
                                   f"End session?\n{n} student(s) recognized."):
            return
        try:
            self.db.end_session(self.session_id, n)
            self._log(f"✓ Session ended. {n} present.")
            messagebox.showinfo("Session Ended", f"Attendance recorded.\n{n} students marked present.")
            self.session_id = None
        except Exception as e:
            messagebox.showerror("Error", f"Could not end session: {e}")

    def _export_csv(self):
        if not self.active_class:
            messagebox.showwarning("No Session", "No active class to export.")
            return
        try:
            from csv_export_service import CSVExportService
            svc = CSVExportService()
            fname, msg = svc.export_session_attendance(self.active_class[0], self.active_class[2])
            if fname:
                messagebox.showinfo("Export Done", f"CSV saved:\n{fname}")
                self._log(f"✓ Exported: {fname}")
            else:
                messagebox.showwarning("Export Failed", msg)
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")

    def _email_report(self):
        if not self.active_class:
            messagebox.showwarning("No Session", "No active class to email.")
            return
        try:
            from email_service import email_service
            from csv_export_service import CSVExportService

            svc = CSVExportService()
            fname, msg = svc.export_session_attendance(self.active_class[0], self.active_class[2])
            if not fname:
                messagebox.showwarning("Export Failed", msg)
                return

            db = Database()
            faculty = db.get_faculty_by_id(self.faculty_data['faculty_id'])
            if not faculty:
                messagebox.showerror("Error", "Faculty record not found in DB.")
                return

            ok, emsg = email_service.send_csv_report_to_faculty(
                faculty[2], faculty[1], fname, "Session Attendance"
            )
            if ok:
                messagebox.showinfo("Email Sent", f"Report emailed to {faculty[2]}")
                self._log(f"✓ Email sent to {faculty[2]}")
            else:
                messagebox.showerror("Email Failed", emsg)
        except Exception as e:
            messagebox.showerror("Error", f"Email error: {e}")

    def _logout(self):
        if not messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            return
        if self.session_id:
            try:
                self.db.end_session(self.session_id, len(self.recognized_students))
            except Exception:
                pass
        if self.on_logout:
            self.on_logout()
        self.root.destroy()
