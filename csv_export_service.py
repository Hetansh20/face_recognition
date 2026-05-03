"""
csv_export_service.py
Generates attendance CSVs purely in-memory (io.StringIO).
No files are written to disk — the bytes are sent directly via email.
"""

import csv
import io
from datetime import datetime
from database import Database


class CSVExportService:
    """Generates attendance CSV content in memory (no disk I/O)."""

    def __init__(self):
        self.db = Database()

    # ── Internal helper ────────────────────────────────────────────────────
    def _make_csv_bytes(self, fieldnames: list, rows: list[dict]) -> bytes:
        """Write rows to an in-memory CSV and return UTF-8 bytes."""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue().encode("utf-8")

    # ── Session attendance (used right after confirm) ───────────────────────
    def build_session_csv(self, timetable_id: int, class_name: str,
                          present_names: list[str]) -> tuple[bytes, str]:
        """
        Build a CSV for a single lecture session.
        Returns (csv_bytes, suggested_filename).
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Attendance_{class_name.replace(' ', '_')}_{ts}.csv"

        attendance_records = self.db.get_attendance_by_session(timetable_id) or []

        rows = []
        for record in attendance_records:
            # record indices from get_attendance_by_session query
            rows.append({
                "GR Number":        record[6] if len(record) > 6 else "",
                "Enrollment Number": record[9] if len(record) > 9 else "",
                "Student Name":     record[7] if len(record) > 7 else "",
                "Email":            record[8] if len(record) > 8 else "",
                "Timestamp":        record[3] if len(record) > 3 else "",
                "Status":           record[4] if len(record) > 4 else "Present",
                "Confidence Score": record[5] if len(record) > 5 else "N/A",
            })

        if not rows:
            # Fallback: build from the present_names list passed in
            for name in present_names:
                rows.append({
                    "GR Number": "",
                    "Enrollment Number": "",
                    "Student Name": name,
                    "Email": "",
                    "Timestamp": datetime.now().isoformat(),
                    "Status": "Present",
                    "Confidence Score": "N/A",
                })

        # Sort rows by Enrollment Number ascending
        rows.sort(key=lambda x: str(x.get("Enrollment Number", "")))

        fieldnames = ["GR Number", "Enrollment Number", "Student Name", "Email",
                      "Timestamp", "Status", "Confidence Score"]
        return self._make_csv_bytes(fieldnames, rows), filename

    # ── Full faculty attendance export ─────────────────────────────────────
    def build_faculty_csv(self, faculty_id: int, faculty_name: str) -> tuple[bytes, str]:
        """
        Build a CSV of ALL attendance for a faculty member.
        Returns (csv_bytes, suggested_filename).
        """
        timetables = self.db.get_faculty_timetables(faculty_id)
        if not timetables:
            return b"", "No timetable data."

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Faculty_{faculty_name.replace(' ', '_')}_{ts}.csv"

        rows = []
        for tt in timetables:
            timetable_id = tt[0]
            class_name   = tt[2]
            day          = tt[3]
            time_slot    = f"{tt[4]} - {tt[5]}"

            for record in (self.db.get_attendance_by_session(timetable_id) or []):
                rows.append({
                    "Class Name":      class_name,
                    "Day":             day,
                    "Time Slot":       time_slot,
                    "Student ID":      record[6] if len(record) > 6 else "",
                    "Student Name":    record[7] if len(record) > 7 else "",
                    "Email":           record[8] if len(record) > 8 else "",
                    "Timestamp":       record[3] if len(record) > 3 else "",
                    "Status":          record[4] if len(record) > 4 else "",
                    "Confidence Score": record[5] if len(record) > 5 else "N/A",
                })

        fieldnames = ["Class Name", "Day", "Time Slot", "Student ID",
                      "Student Name", "Email", "Timestamp", "Status", "Confidence Score"]
        return self._make_csv_bytes(fieldnames, rows), filename

    # ── Absent list CSV ────────────────────────────────────────────────────
    def build_absent_csv(self, absent_list: list[dict], class_name: str) -> tuple[bytes, str]:
        """Build an absent-students CSV from the review page absent list."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Absent_{class_name.replace(' ', '_')}_{ts}.csv"
        rows = [
            {"GR Number": s.get("employee_id", ""),
             "Enrollment Number": s.get("enrollment_number", ""),
             "Student Name": s.get("name", ""),
             "Status": "Absent",
             "Date": datetime.now().strftime("%Y-%m-%d"),
             "Class": class_name}
            for s in absent_list
        ]
        
        # Sort rows by Enrollment Number ascending
        rows.sort(key=lambda x: str(x.get("Enrollment Number", "")))
        
        fieldnames = ["GR Number", "Enrollment Number", "Student Name", "Status", "Date", "Class"]
        return self._make_csv_bytes(fieldnames, rows), filename
