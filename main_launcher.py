"""
InsightFace Attendance System — Main Launcher
==============================================
Hub entry point for the full attendance system.
Provides Faculty Login, Admin Dashboard, and Setup screens.
"""
import tkinter as tk
from tkinter import messagebox
import threading
import sys
import os
from database import Database

DB_PATH = "attendance_system.db"

class MainLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("InsightFace Attendance System")
        self.root.geometry("580x700")
        self.root.resizable(False, False)
        self.root.configure(bg='#0d1117')

        self._init_db()
        self._setup_ui()

    def _init_db(self):
        try:
            Database()
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to initialize database:\n{e}")
            sys.exit(1)

    def _setup_ui(self):
        # ── Header ──────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg='#161b22')
        header.pack(fill=tk.X)

        tk.Label(header, text="🚀 InsightFace", font=('Segoe UI', 30, 'bold'),
                 bg='#161b22', fg='#58a6ff').pack(pady=(28, 4))
        tk.Label(header, text="Contactless Attendance System",
                 font=('Segoe UI', 13), bg='#161b22', fg='#8b949e').pack(pady=(0, 26))

        # ── Button area ──────────────────────────────────────────────────────
        content = tk.Frame(self.root, bg='#0d1117')
        content.pack(fill=tk.BOTH, expand=True, padx=50, pady=30)

        def big_btn(parent, emoji, title, subtitle, cmd, color):
            outer = tk.Frame(parent, bg=color, bd=0)
            outer.pack(fill=tk.X, pady=10)

            inner = tk.Frame(outer, bg='#161b22', bd=0)
            inner.pack(fill=tk.X, padx=2, pady=2)

            btn = tk.Button(inner, text=f"{emoji}  {title}", command=cmd,
                            font=('Segoe UI', 14, 'bold'), bg='#1c2128', fg='#e6edf3',
                            activebackground='#21262d', activeforeground='#e6edf3',
                            relief=tk.FLAT, bd=0, cursor='hand2', pady=14)
            btn.pack(fill=tk.X)
            btn.bind("<Enter>", lambda e: btn.configure(bg='#21262d'))
            btn.bind("<Leave>", lambda e: btn.configure(bg='#1c2128'))

            tk.Label(inner, text=subtitle, font=('Segoe UI', 9),
                     bg='#1c2128', fg=color).pack(pady=(0, 10))
            return outer

        big_btn(content, "🎓", "Face Recognition (Standalone)",
                "Register faces and take attendance directly with InsightFace",
                self.launch_insightface, '#58a6ff')

        big_btn(content, "👤", "Faculty Login",
                "Start a session for an active timetable class",
                self.launch_faculty_login, '#2ea043')

        big_btn(content, "⚙️", "Admin Dashboard",
                "Manage students, faculty, timetables, and reports",
                self.launch_admin, '#d29922')

        big_btn(content, "🔧", "Setup & Configuration",
                "Register faculties, students, and manage email",
                self.launch_setup, '#8957e5')

        # ── Footer ─────────────────────────────────────────────────────────
        footer = tk.Frame(self.root, bg='#161b22')
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(footer, text="InsightFace (ArcFace + RetinaFace) · buffalo_l model",
                 font=('Segoe UI', 9), bg='#161b22', fg='#484f58').pack(pady=12)

    # ── Launchers ─────────────────────────────────────────────────────────────

    def launch_insightface(self):
        """Launch standalone InsightFace attendance"""
        try:
            from insightface_attendance import InsightFaceAttendanceSystem
            win = tk.Toplevel(self.root)
            InsightFaceAttendanceSystem(win)
            self.root.withdraw()
            win.protocol("WM_DELETE_WINDOW", lambda: (win.destroy(), self.root.deiconify()))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch InsightFace:\n{e}")

    def launch_faculty_login(self):
        """Launch faculty login window"""
        try:
            from faculty_ui import FacultyLoginWindow
            win = tk.Toplevel(self.root)
            FacultyLoginWindow(win, on_close=lambda: (win.destroy(), self.root.deiconify()))
            self.root.withdraw()
            win.protocol("WM_DELETE_WINDOW", lambda: (win.destroy(), self.root.deiconify()))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch Faculty Login:\n{e}")

    def launch_admin(self):
        """Launch admin dashboard"""
        try:
            from admin_ui import AdminDashboard
            win = tk.Toplevel(self.root)
            AdminDashboard(win)
            self.root.withdraw()
            win.protocol("WM_DELETE_WINDOW", lambda: (win.destroy(), self.root.deiconify()))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch Admin Dashboard:\n{e}")

    def launch_setup(self):
        """Launch setup window"""
        try:
            from admin_ui import SetupWindow
            win = tk.Toplevel(self.root)
            SetupWindow(win)
            self.root.withdraw()
            win.protocol("WM_DELETE_WINDOW", lambda: (win.destroy(), self.root.deiconify()))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch Setup:\n{e}")


def main():
    root = tk.Tk()
    MainLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
