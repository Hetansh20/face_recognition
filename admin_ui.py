"""
Admin UI — Dashboard + Setup Window
=====================================
Full admin dashboard: faculty, student, timetable mgmt, analytics,
email/CSV export reports, DB backup, system logs.
Also contains the SetupWindow (quick registration of faculty + students).
"""

import tkinter as tk
from tkinter import ttk, messagebox
import csv, os
from datetime import datetime
from database import Database
from timetable_manager import timetable_manager


DARK   = '#0d1117'
CARD   = '#161b22'
BORDER = '#30363d'
TEXT   = '#c9d1d9'
MUTED  = '#8b949e'
BLUE   = '#58a6ff'
GREEN  = '#2ea043'
RED    = '#da3633'
GOLD   = '#d29922'
PURPLE = '#8957e5'


def _styled_btn(parent, text, cmd, color, **kw):
    b = tk.Button(parent, text=text, command=cmd,
                  font=('Segoe UI', 10, 'bold'),
                  bg=color, fg='white', relief=tk.FLAT,
                  activebackground=color, cursor='hand2', **kw)
    return b


def _label(parent, text, **kw):
    return tk.Label(parent, text=text, bg=kw.pop('bg', DARK),
                    fg=kw.pop('fg', TEXT), **kw)


# ── Admin Dashboard ──────────────────────────────────────────────────────────

class AdminDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Admin Dashboard — InsightFace Attendance")
        self.root.geometry("1050x720")
        self.root.configure(bg=DARK)
        self.db = Database()
        self._setup_ui()

    def _setup_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=CARD)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="⚙️ Admin Dashboard", font=('Segoe UI', 20, 'bold'),
                 bg=CARD, fg=BLUE).pack(side=tk.LEFT, padx=24, pady=16)
        tk.Label(hdr, text=f"Last refresh: {datetime.now().strftime('%H:%M:%S')}",
                 font=('Segoe UI', 9), bg=CARD, fg=MUTED).pack(side=tk.RIGHT, padx=24)

        # Notebook
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background=DARK, borderwidth=0)
        style.configure('TNotebook.Tab', background=CARD, foreground=TEXT,
                        font=('Segoe UI', 10, 'bold'), padding=[14, 6])
        style.map('TNotebook.Tab', background=[('selected', BLUE)],
                  foreground=[('selected', 'white')])
        style.configure('TFrame', background=DARK)

        nb = ttk.Notebook(self.root)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for title, builder in [
            ("📊 Dashboard",   self._tab_dashboard),
            ("👤 Faculty",     self._tab_faculty),
            ("🎓 Students",    self._tab_students),
            ("📅 Timetable",   self._tab_timetable),
            ("📈 Reports",     self._tab_reports),
        ]:
            frame = ttk.Frame(nb)
            nb.add(frame, text=title)
            builder(frame)

    # ── Dashboard tab ────────────────────────────────────────────────────────

    def _tab_dashboard(self, parent):
        frame = tk.Frame(parent, bg=DARK)
        frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        faculties = self.db.get_all_faculties() or []
        students  = self.db.get_all_students()  or []

        # Stat cards row
        cards = tk.Frame(frame, bg=DARK)
        cards.pack(fill=tk.X, pady=(0, 20))

        def stat_card(parent, title, value, color):
            c = tk.Frame(parent, bg=CARD, bd=0)
            c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=4)
            tk.Frame(c, bg=color, height=4).pack(fill=tk.X)
            tk.Label(c, text=str(value), font=('Segoe UI', 28, 'bold'),
                     bg=CARD, fg=color).pack(pady=(14, 2))
            tk.Label(c, text=title, font=('Segoe UI', 10),
                     bg=CARD, fg=MUTED).pack(pady=(0, 14))

        stat_card(cards, "Faculties",  len(faculties), BLUE)
        stat_card(cards, "Students",   len(students),  GREEN)
        stat_card(cards, "DB Status",  "Active",       GOLD)

        # Quick actions
        qa = tk.LabelFrame(frame, text="  Quick Actions  ",
                           font=('Segoe UI', 11, 'bold'),
                           bg=DARK, fg=BLUE, labelanchor='n')
        qa.pack(fill=tk.X)
        row = tk.Frame(qa, bg=DARK)
        row.pack(padx=20, pady=16)

        for txt, cmd, col in [
            ("View All Faculty",   self._show_all_faculty,   BLUE),
            ("View All Students",  self._show_all_students,  GREEN),
            ("Generate Report",    self._generate_report,    GOLD),
            ("Backup Database",    self._backup_db,          PURPLE),
        ]:
            _styled_btn(row, txt, cmd, col).pack(side=tk.LEFT, padx=6, ipady=6, ipadx=10)

    # ── Faculty tab ──────────────────────────────────────────────────────────

    def _tab_faculty(self, parent):
        frame = tk.Frame(parent, bg=DARK)
        frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        cols = ('ID', 'Name', 'Email', 'Department', 'Status')
        tree = self._make_tree(frame, cols)

        faculties = self.db.get_all_faculties() or []
        for f in faculties:
            tree.insert('', tk.END, values=(f[0], f[1], f[2], f[3], "Active" if f[6] else "Inactive"))

        btn_row = tk.Frame(frame, bg=DARK)
        btn_row.pack(fill=tk.X, pady=6)
        _styled_btn(btn_row, "🔄 Refresh", lambda: self._refresh_tab(self._tab_faculty, parent), BLUE).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)

    # ── Students tab ─────────────────────────────────────────────────────────

    def _tab_students(self, parent):
        frame = tk.Frame(parent, bg=DARK)
        frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        cols = ('DB ID', 'Student ID', 'Name', 'Email', 'Department', 'Status')
        tree = self._make_tree(frame, cols)

        students = self.db.get_all_students() or []
        for s in students:
            tree.insert('', tk.END, values=(s[0], s[1], s[2], s[3], s[4], "Active" if s[6] else "Inactive"))

    # ── Timetable tab ────────────────────────────────────────────────────────

    def _tab_timetable(self, parent):
        frame = tk.Frame(parent, bg=DARK)
        frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # ─ Add entry form ─
        add = tk.LabelFrame(frame, text="  Add Timetable Entry  ",
                            font=('Segoe UI', 10, 'bold'),
                            bg=DARK, fg=BLUE, labelanchor='n')
        add.pack(fill=tk.X, pady=(0, 10))

        fg = tk.Frame(add, bg=DARK)
        fg.pack(fill=tk.X, padx=16, pady=12)

        def row(label, var, widget_fn, col):
            tk.Label(fg, text=label, font=('Segoe UI', 9, 'bold'),
                     bg=DARK, fg=MUTED).grid(row=0, column=col*2, sticky=tk.W, padx=(0, 6))
            w = widget_fn(fg, var)
            w.grid(row=1, column=col*2, padx=(0, 20), sticky=tk.EW, pady=2)
            return w

        def entry_w(p, v):
            e = tk.Entry(p, textvariable=v, font=('Segoe UI', 10),
                         bg=CARD, fg=TEXT, insertbackground='white', relief=tk.FLAT)
            return e

        faculties = self.db.get_all_faculties() or []
        fac_opts  = [f"{f[1]} ({f[2]})" for f in faculties]

        self.tt_fac_var   = tk.StringVar()
        self.tt_class_var = tk.StringVar()
        self.tt_day_var   = tk.StringVar()
        self.tt_start_var = tk.StringVar()
        self.tt_end_var   = tk.StringVar()
        self.tt_room_var  = tk.StringVar()

        def combo(p, v, vals=None):
            c = ttk.Combobox(p, textvariable=v, state='readonly', values=vals or [],
                             font=('Segoe UI', 10))
            return c

        days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        row("Faculty",     self.tt_fac_var,   lambda p, v: combo(p, v, fac_opts), 0)
        row("Class Name",  self.tt_class_var, entry_w, 1)
        row("Day",         self.tt_day_var,   lambda p, v: combo(p, v, days),    2)
        row("Start (HH:MM)", self.tt_start_var, entry_w, 3)
        row("End (HH:MM)",   self.tt_end_var,   entry_w, 4)
        row("Room",          self.tt_room_var,  entry_w, 5)

        for i in range(6):
            fg.columnconfigure(i*2, weight=1)

        _styled_btn(add, "✚ Add Entry", self._add_timetable, GREEN).pack(padx=16, pady=(0, 10), anchor=tk.W, ipady=5, ipadx=10)

        # Timetable list
        cols2 = ('ID', 'Faculty', 'Class', 'Day', 'Start', 'End', 'Room')
        self.tt_tree = self._make_tree(frame, cols2, height=8)
        self._refresh_timetable_tree()

    def _add_timetable(self):
        fac_str = self.tt_fac_var.get().strip()
        cls     = self.tt_class_var.get().strip()
        day     = self.tt_day_var.get().strip()
        start   = self.tt_start_var.get().strip()
        end     = self.tt_end_var.get().strip()
        room    = self.tt_room_var.get().strip()

        if not all([fac_str, cls, day, start, end]):
            messagebox.showerror("Missing Fields", "Please fill all required fields (except Room).")
            return

        faculties = self.db.get_all_faculties() or []
        fac_name  = fac_str.split('(')[0].strip()
        fac_id    = next((f[0] for f in faculties if f[1] == fac_name), None)

        if not fac_id:
            messagebox.showerror("Error", "Faculty not found.")
            return

        try:
            tid, msg = timetable_manager.add_timetable_entry(fac_id, cls, day, start, end, room or None)
            if tid:
                messagebox.showinfo("Success", msg)
                self._refresh_timetable_tree()
            else:
                messagebox.showerror("Error", msg)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _refresh_timetable_tree(self):
        if not hasattr(self, 'tt_tree'):
            return
        self.tt_tree.delete(*self.tt_tree.get_children())
        faculties = {f[0]: f[1] for f in (self.db.get_all_faculties() or [])}
        for f in (self.db.get_all_faculties() or []):
            for t in (self.db.get_faculty_timetables(f[0]) or []):
                self.tt_tree.insert('', tk.END,
                    values=(t[0], faculties.get(t[1], '?'), t[2], t[3], t[4], t[5], t[6] or ''))

    # ── Reports tab ──────────────────────────────────────────────────────────

    def _tab_reports(self, parent):
        frame = tk.Frame(parent, bg=DARK)
        frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=16)

        # Email config
        ec = tk.LabelFrame(frame, text="  Email Configuration  ",
                           font=('Segoe UI', 10, 'bold'),
                           bg=DARK, fg=GOLD, labelanchor='n')
        ec.pack(fill=tk.X, pady=(0, 12))

        er = tk.Frame(ec, bg=DARK)
        er.pack(fill=tk.X, padx=16, pady=10)

        self.email_var  = tk.StringVar()
        self.epwd_var   = tk.StringVar()

        for col, (lbl, var, show) in enumerate([
                ("Sender Email", self.email_var, ''),
                ("App Password", self.epwd_var,  '•')]):
            tk.Label(er, text=lbl, font=('Segoe UI', 9, 'bold'),
                     bg=DARK, fg=MUTED).grid(row=0, column=col*2, sticky=tk.W, padx=(0,6))
            tk.Entry(er, textvariable=var, font=('Segoe UI', 10), bg=CARD, fg=TEXT,
                     insertbackground='white', relief=tk.FLAT, show=show
                     ).grid(row=1, column=col*2, sticky=tk.EW, padx=(0, 20), pady=2)
        er.columnconfigure(0, weight=1)
        er.columnconfigure(2, weight=1)

        ebr = tk.Frame(ec, bg=DARK)
        ebr.pack(padx=16, pady=(0, 10), anchor=tk.W)
        _styled_btn(ebr, "💾 Save Config",    self._save_email_cfg,  GREEN).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)
        _styled_btn(ebr, "🔗 Test Connection", self._test_email_conn, BLUE).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)

        # Analytics
        anl = tk.LabelFrame(frame, text="  Analytics  ",
                            font=('Segoe UI', 10, 'bold'),
                            bg=DARK, fg=PURPLE, labelanchor='n')
        anl.pack(fill=tk.X, pady=(0, 12))
        ar = tk.Frame(anl, bg=DARK)
        ar.pack(padx=16, pady=10, anchor=tk.W)
        _styled_btn(ar, "📊 View Analytics",     self._view_analytics,          PURPLE).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)
        _styled_btn(ar, "⚠ Low Attendance Alerts", self._low_attendance_alerts, RED).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)

        # Generate reports
        rp = tk.LabelFrame(frame, text="  Generate & Email Reports  ",
                           font=('Segoe UI', 10, 'bold'),
                           bg=DARK, fg=GREEN, labelanchor='n')
        rp.pack(fill=tk.X, pady=(0, 12))
        rr = tk.Frame(rp, bg=DARK)
        rr.pack(padx=16, pady=10, anchor=tk.W)
        _styled_btn(rr, "📅 Daily Report",   self._daily_report,   BLUE).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)
        _styled_btn(rr, "📆 Weekly Report",  self._weekly_report,  BLUE).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)
        _styled_btn(rr, "🗓 Monthly Report", self._monthly_report, BLUE).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)

        # Export
        ex = tk.LabelFrame(frame, text="  Export CSV  ",
                           font=('Segoe UI', 10, 'bold'),
                           bg=DARK, fg=GOLD, labelanchor='n')
        ex.pack(fill=tk.X)
        er2 = tk.Frame(ex, bg=DARK)
        er2.pack(padx=16, pady=10, anchor=tk.W)
        _styled_btn(er2, "📁 Export All Attendance",   self._export_all,     GREEN).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)
        _styled_btn(er2, "📁 Export by Faculty",       self._export_faculty, GREEN).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)
        _styled_btn(er2, "✉ Email Report to Faculty",  self._email_faculty,  PURPLE).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)

        # System
        sy = tk.LabelFrame(frame, text="  System Management  ",
                           font=('Segoe UI', 10, 'bold'),
                           bg=DARK, fg=RED, labelanchor='n')
        sy.pack(fill=tk.X, pady=(12, 0))
        sr = tk.Frame(sy, bg=DARK)
        sr.pack(padx=16, pady=10, anchor=tk.W)
        _styled_btn(sr, "💾 Backup DB",   self._backup_db,     GOLD).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)
        _styled_btn(sr, "📋 System Logs", self._view_logs,     MUTED).pack(side=tk.LEFT, padx=3, ipady=4, ipadx=8)

    # ── Report helpers ────────────────────────────────────────────────────────

    def _save_email_cfg(self):
        try:
            from email_service import email_service
            email_service.configure_email(self.email_var.get(), self.epwd_var.get())
            messagebox.showinfo("Saved", "Email configuration saved.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _test_email_conn(self):
        try:
            from email_service import email_service
            ok, msg = email_service.test_email_connection()
            (messagebox.showinfo if ok else messagebox.showerror)("Email Test", msg)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _view_analytics(self):
        try:
            from analytics_service import AnalyticsService
            stats = AnalyticsService().get_system_statistics()
            top   = '\n'.join(f"  • {n}: {c}" for n, c in stats.get('top_students', []))
            low   = '\n'.join(f"  • {n}: {r:.1f}%" for n, r in stats.get('low_attendance_students', []))
            msg   = (f"Total Sessions: {stats.get('total_sessions',0)}\n"
                     f"Records Marked: {stats.get('total_marked',0)}\n"
                     f"Avg Attendance: {stats.get('average_attendance',0):.1f}%\n"
                     f"Best Class: {stats.get('highest_class','N/A')}\n"
                     f"Lowest Class: {stats.get('lowest_class','N/A')}\n\n"
                     f"Top Students:\n{top or '  None yet'}\n\n"
                     f"Low Attendance (<75%):\n{low or '  None'}")
            messagebox.showinfo("Analytics", msg)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _low_attendance_alerts(self):
        try:
            from analytics_service import AnalyticsService
            low = AnalyticsService().get_low_attendance_students(75)
            if not low:
                messagebox.showinfo("Low Attendance", "No students below 75% threshold.")
                return
            msg = "STUDENTS BELOW 75% ATTENDANCE\n\n"
            for s in low:
                msg += f"• {s[0]} ({s[2]}) — {s[3]:.1f}%\n"
            messagebox.showinfo("Low Attendance Alerts", msg)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _daily_report(self):
        try:
            from analytics_service import AnalyticsService
            from csv_export_service import CSVExportService
            data = AnalyticsService().get_daily_attendance_report()
            if not data:
                messagebox.showwarning("No Data", "No attendance records for today.")
                return
            svc = CSVExportService()
            os.makedirs(svc.export_dir, exist_ok=True)
            fname = os.path.join(svc.export_dir, f"Daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            with open(fname, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['Class','Faculty','Present','Total','%'])
                for r in data:
                    w.writerow([r[0], r[1], r[2], r[3], f"{r[4]:.1f}%"])
            messagebox.showinfo("Report Generated", f"Daily report saved:\n{fname}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _weekly_report(self):
        try:
            from analytics_service import AnalyticsService
            from csv_export_service import CSVExportService
            data = AnalyticsService().get_weekly_attendance_report()
            if not data:
                messagebox.showwarning("No Data", "No attendance records this week.")
                return
            svc = CSVExportService()
            os.makedirs(svc.export_dir, exist_ok=True)
            fname = os.path.join(svc.export_dir, f"Weekly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            with open(fname, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['Class','Faculty','Sessions','Avg %'])
                for r in data:
                    w.writerow([r[0], r[1], r[2], f"{r[3]:.1f}%"])
            messagebox.showinfo("Report Generated", f"Weekly report saved:\n{fname}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _monthly_report(self):
        try:
            from analytics_service import AnalyticsService
            from csv_export_service import CSVExportService
            data = AnalyticsService().get_monthly_attendance_report()
            if not data:
                messagebox.showwarning("No Data", "No attendance records this month.")
                return
            svc = CSVExportService()
            os.makedirs(svc.export_dir, exist_ok=True)
            fname = os.path.join(svc.export_dir, f"Monthly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            with open(fname, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['Class','Faculty','Sessions','Avg %'])
                for r in data:
                    w.writerow([r[0], r[1], r[2], f"{r[3]:.1f}%"])
            messagebox.showinfo("Report Generated", f"Monthly report saved:\n{fname}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _export_all(self):
        try:
            from csv_export_service import CSVExportService
            fname, msg = CSVExportService().export_all_attendance()
            if fname:
                messagebox.showinfo("Export Done", f"Saved:\n{fname}")
            else:
                messagebox.showwarning("No Data", msg)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _export_faculty(self):
        faculties = self.db.get_all_faculties() or []
        if not faculties:
            messagebox.showwarning("No Faculty", "No faculties registered yet.")
            return
        w = tk.Toplevel(self.root)
        w.title("Select Faculty")
        w.geometry("380x180")
        w.configure(bg=DARK)
        var = tk.StringVar()
        opts = [f"{f[1]} ({f[2]})" for f in faculties]
        tk.Label(w, text="Select Faculty:", font=('Segoe UI', 11, 'bold'),
                 bg=DARK, fg=TEXT).pack(pady=(20, 6))
        ttk.Combobox(w, textvariable=var, values=opts, state='readonly',
                     font=('Segoe UI', 10)).pack(fill=tk.X, padx=30)

        def do_export():
            sel = var.get()
            if not sel:
                return
            fname_str = sel.split('(')[0].strip()
            fac = next((f for f in faculties if f[1] == fname_str), None)
            if not fac:
                return
            from csv_export_service import CSVExportService
            fn, msg = CSVExportService().export_faculty_attendance(fac[0], fac[1])
            if fn:
                messagebox.showinfo("Export Done", f"Saved:\n{fn}")
                w.destroy()
            else:
                messagebox.showwarning("No Data", msg)

        _styled_btn(w, "Export", do_export, GREEN).pack(pady=14, ipady=5, ipadx=14)

    def _email_faculty(self):
        faculties = self.db.get_all_faculties() or []
        if not faculties:
            messagebox.showwarning("No Faculty", "No faculties registered yet.")
            return
        w = tk.Toplevel(self.root)
        w.title("Email Report to Faculty")
        w.geometry("400x200")
        w.configure(bg=DARK)
        var = tk.StringVar()
        opts = [f"{f[1]} ({f[2]})" for f in faculties]
        tk.Label(w, text="Select Faculty:", font=('Segoe UI', 11, 'bold'),
                 bg=DARK, fg=TEXT).pack(pady=(20, 6))
        ttk.Combobox(w, textvariable=var, values=opts, state='readonly',
                     font=('Segoe UI', 10)).pack(fill=tk.X, padx=30)

        def do_email():
            sel = var.get()
            if not sel:
                return
            name_str = sel.split('(')[0].strip()
            email_str = sel.split('(')[1].rstrip(')')
            fac = next((f for f in faculties if f[1] == name_str), None)
            if not fac:
                return
            from csv_export_service import CSVExportService
            from email_service import email_service
            fn, msg = CSVExportService().export_faculty_attendance(fac[0], fac[1])
            if not fn:
                messagebox.showwarning("No Data", msg)
                return
            ok, emsg = email_service.send_csv_report_to_faculty(email_str, name_str, fn, "Attendance")
            (messagebox.showinfo if ok else messagebox.showerror)("Email", emsg)
            w.destroy()

        _styled_btn(w, "Export & Email", do_email, PURPLE).pack(pady=14, ipady=5, ipadx=14)

    def _backup_db(self):
        import shutil
        try:
            fname = f"attendance_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy("attendance_system.db", fname)
            messagebox.showinfo("Backup Done", f"Backed up to:\n{fname}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _view_logs(self):
        path = "system_logs.txt"
        w = tk.Toplevel(self.root)
        w.title("System Logs")
        w.geometry("640x420")
        w.configure(bg=DARK)
        txt = tk.Text(w, font=('Consolas', 9), bg=CARD, fg=TEXT, relief=tk.FLAT)
        sb  = tk.Scrollbar(w, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        if os.path.exists(path):
            txt.insert(tk.END, open(path).read())
        else:
            txt.insert(tk.END, "No log file found yet.")
        txt.config(state=tk.DISABLED)

    def _generate_report(self):
        faculties = self.db.get_all_faculties() or []
        students  = self.db.get_all_students()  or []
        msg = (f"ATTENDANCE SYSTEM REPORT\n"
               f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
               f"Total Faculties: {len(faculties)}\n"
               f"Total Students:  {len(students)}\n\n"
               f"Database: attendance_system.db (Connected)\n"
               f"Recognition: InsightFace buffalo_l (ArcFace + RetinaFace)")
        messagebox.showinfo("System Report", msg)

    def _show_all_faculty(self):
        f = self.db.get_all_faculties() or []
        if not f:
            messagebox.showinfo("Faculty", "No faculties registered.")
            return
        messagebox.showinfo("All Faculties",
                            "\n".join(f"{r[1]} — {r[2]} ({r[3]})" for r in f))

    def _show_all_students(self):
        s = self.db.get_all_students() or []
        if not s:
            messagebox.showinfo("Students", "No students registered.")
            return
        messagebox.showinfo("All Students",
                            "\n".join(f"{r[1]} — {r[2]} ({r[4]})" for r in s))

    def _refresh_tab(self, builder, parent):
        for w in parent.winfo_children():
            w.destroy()
        builder(parent)

    # ── Shared helper ────────────────────────────────────────────────────────

    def _make_tree(self, parent, columns, height=12):
        style = ttk.Style()
        style.configure('Treeview', background=CARD, foreground=TEXT,
                        fieldbackground=CARD, rowheight=26, font=('Segoe UI', 9))
        style.configure('Treeview.Heading', background=BORDER, foreground=BLUE,
                        font=('Segoe UI', 9, 'bold'))
        style.map('Treeview', background=[('selected', '#1f6feb')])

        container = tk.Frame(parent, bg=DARK)
        container.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(container, columns=columns, show='headings', height=height)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=max(80, 140 if col in ('Name', 'Email', 'Class') else 80))

        sb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        return tree


# ── Setup Window ─────────────────────────────────────────────────────────────

class SetupWindow:
    """Quick registration for faculties and students."""

    def __init__(self, root):
        self.root = root
        self.root.title("Setup & Configuration — InsightFace Attendance")
        self.root.geometry("580x620")
        self.root.configure(bg=DARK)
        self.db = Database()
        self._setup_ui()

    def _setup_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=CARD)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🔧 Setup & Configuration",
                 font=('Segoe UI', 20, 'bold'), bg=CARD, fg=PURPLE).pack(pady=(18, 4))
        tk.Label(hdr, text="Register faculties and students",
                 font=('Segoe UI', 10), bg=CARD, fg=MUTED).pack(pady=(0, 16))

        nb = ttk.Notebook(self.root)
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        for title, builder in [
            ("👤 Register Faculty", self._tab_faculty),
            ("🎓 Register Student", self._tab_student),
        ]:
            frame = ttk.Frame(nb)
            nb.add(frame, text=title)
            builder(frame)

    def _form_entry(self, parent, label, var, show='', row=0):
        bg = parent.cget('style') if False else DARK
        tk.Label(parent, text=label, font=('Segoe UI', 10, 'bold'),
                 bg=DARK, fg=MUTED).grid(row=row*2, column=0, sticky=tk.W, padx=20, pady=(10, 2))
        e = tk.Entry(parent, textvariable=var, font=('Segoe UI', 11),
                     bg=CARD, fg=TEXT, insertbackground='white', relief=tk.FLAT, show=show)
        e.grid(row=row*2+1, column=0, sticky=tk.EW, padx=20, pady=(0, 2), ipady=7)
        tk.Frame(parent, bg=BORDER, height=1).grid(row=row*2+2, column=0, sticky=tk.EW, padx=20)
        return e

    def _tab_faculty(self, parent):
        parent.configure(style='TFrame')
        f = tk.Frame(parent, bg=DARK)
        f.pack(fill=tk.BOTH, expand=True)
        f.columnconfigure(0, weight=1)

        self.fn_var  = tk.StringVar()
        self.fe_var  = tk.StringVar()
        self.fd_var  = tk.StringVar()
        self.fp_var  = tk.StringVar()

        self._form_entry(f, "Full Name", self.fn_var, row=0)
        self._form_entry(f, "Email Address", self.fe_var, row=1)
        self._form_entry(f, "Department", self.fd_var, row=2)
        self._form_entry(f, "Passcode", self.fp_var, show='•', row=3)

        self.f_status_var = tk.StringVar()
        tk.Label(f, textvariable=self.f_status_var, font=('Segoe UI', 9),
                 bg=DARK, fg=GREEN).grid(row=9, column=0, pady=6)

        _styled_btn(f, "✚ Register Faculty", self._register_faculty, GREEN
                    ).grid(row=10, column=0, sticky=tk.EW, padx=20, ipady=10, pady=4)

    def _register_faculty(self):
        name = self.fn_var.get().strip()
        email = self.fe_var.get().strip()
        dept = self.fd_var.get().strip()
        pwd  = self.fp_var.get().strip()

        if not all([name, email, dept, pwd]):
            self.f_status_var.set("⚠ Please fill all fields.")
            return
        try:
            self.db.add_faculty(name, email, dept, pwd)
            self.f_status_var.set(f"✓ Faculty '{name}' registered!")
            for v in [self.fn_var, self.fe_var, self.fd_var, self.fp_var]:
                v.set("")
        except Exception as e:
            self.f_status_var.set(f"✗ {e}")

    def _tab_student(self, parent):
        f = tk.Frame(parent, bg=DARK)
        f.pack(fill=tk.BOTH, expand=True)
        f.columnconfigure(0, weight=1)

        self.si_var = tk.StringVar()
        self.sn_var = tk.StringVar()
        self.se_var = tk.StringVar()
        self.sd_var = tk.StringVar()

        self._form_entry(f, "Student ID (e.g. S001)", self.si_var, row=0)
        self._form_entry(f, "Full Name", self.sn_var, row=1)
        self._form_entry(f, "Email Address", self.se_var, row=2)
        self._form_entry(f, "Department", self.sd_var, row=3)

        self.s_status_var = tk.StringVar()
        tk.Label(f, textvariable=self.s_status_var, font=('Segoe UI', 9),
                 bg=DARK, fg=GREEN).grid(row=9, column=0, pady=6)

        _styled_btn(f, "✚ Register Student", self._register_student, GREEN
                    ).grid(row=10, column=0, sticky=tk.EW, padx=20, ipady=10, pady=4)

    def _register_student(self):
        sid  = self.si_var.get().strip()
        name = self.sn_var.get().strip()
        email= self.se_var.get().strip()
        dept = self.sd_var.get().strip()

        if not all([sid, name, email, dept]):
            self.s_status_var.set("⚠ Please fill all fields.")
            return
        try:
            self.db.add_student(sid, name, email, dept)
            self.s_status_var.set(f"✓ Student '{name}' registered!")
            for v in [self.si_var, self.sn_var, self.se_var, self.sd_var]:
                v.set("")
        except Exception as e:
            self.s_status_var.set(f"✗ {e}")
