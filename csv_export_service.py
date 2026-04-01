import csv
import os
from datetime import datetime
from database import Database

class CSVExportService:
    """Service for exporting attendance data to CSV files"""
    
    def __init__(self):
        self.db = Database()
        self.export_dir = "attendance_reports"
        self.create_export_directory()
    
    def create_export_directory(self):
        """Create export directory if it doesn't exist"""
        if not os.path.exists(self.export_dir):
            os.makedirs(self.export_dir)
    
    def export_faculty_attendance(self, faculty_id, faculty_name):
        """Export all attendance records for a specific faculty"""
        try:
            # Get all timetables for the faculty
            timetables = self.db.get_faculty_timetables(faculty_id)
            
            if not timetables:
                return None, "No timetables found for this faculty"
            
            # Prepare filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(
                self.export_dir,
                f"Faculty_{faculty_name.replace(' ', '_')}_{timestamp}.csv"
            )
            
            # Collect all attendance data
            all_attendance = []
            for timetable in timetables:
                timetable_id = timetable[0]
                class_name = timetable[2]
                day = timetable[3]
                time_slot = f"{timetable[4]} - {timetable[5]}"
                
                # Get attendance for this timetable
                attendance_records = self.db.get_attendance_by_session(timetable_id)
                
                for record in attendance_records:
                    all_attendance.append({
                        'class_name': class_name,
                        'day': day,
                        'time_slot': time_slot,
                        'student_id': record[6],  # student_code from students table
                        'student_name': record[7],  # name from students table
                        'email': record[8],  # email from students table
                        'timestamp': record[3],
                        'status': record[4],
                        'confidence': record[5] if record[5] else 'N/A'
                    })
            
            # Write to CSV
            if all_attendance:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['Class Name', 'Day', 'Time Slot', 'Student ID', 'Student Name', 
                                'Email', 'Timestamp', 'Status', 'Confidence Score']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    for record in all_attendance:
                        writer.writerow({
                            'Class Name': record['class_name'],
                            'Day': record['day'],
                            'Time Slot': record['time_slot'],
                            'Student ID': record['student_id'],
                            'Student Name': record['student_name'],
                            'Email': record['email'],
                            'Timestamp': record['timestamp'],
                            'Status': record['status'],
                            'Confidence Score': record['confidence']
                        })
                
                return filename, f"Successfully exported {len(all_attendance)} attendance records"
            else:
                return None, "No attendance records found for this faculty"
        
        except Exception as e:
            return None, f"Error exporting faculty attendance: {str(e)}"
    
    def export_session_attendance(self, timetable_id, class_name):
        """Export attendance records for a specific session/class"""
        try:
            # Get attendance for this session
            attendance_records = self.db.get_attendance_by_session(timetable_id)
            
            if not attendance_records:
                return None, "No attendance records found for this session"
            
            # Prepare filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(
                self.export_dir,
                f"Session_{class_name.replace(' ', '_')}_{timestamp}.csv"
            )
            
            # Write to CSV
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['Student ID', 'Student Name', 'Email', 'Timestamp', 'Status', 'Confidence Score']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for record in attendance_records:
                    writer.writerow({
                        'Student ID': record[6],  # student_code from students table
                        'Student Name': record[7],  # name from students table
                        'Email': record[8],  # email from students table
                        'Timestamp': record[3],
                        'Status': record[4],
                        'Confidence Score': record[5] if record[5] else 'N/A'
                    })
            
            return filename, f"Successfully exported {len(attendance_records)} attendance records"
        
        except Exception as e:
            return None, f"Error exporting session attendance: {str(e)}"
    
    def export_all_attendance(self):
        """Export all attendance records for all faculties"""
        try:
            faculties = self.db.get_all_faculties()
            
            if not faculties:
                return None, "No faculties found"
            
            # Prepare filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(
                self.export_dir,
                f"All_Attendance_{timestamp}.csv"
            )
            
            # Collect all attendance data
            all_attendance = []
            for faculty in faculties:
                faculty_id = faculty[0]
                faculty_name = faculty[1]
                
                timetables = self.db.get_faculty_timetables(faculty_id)
                
                for timetable in timetables:
                    timetable_id = timetable[0]
                    class_name = timetable[2]
                    day = timetable[3]
                    time_slot = f"{timetable[4]} - {timetable[5]}"
                    
                    attendance_records = self.db.get_attendance_by_session(timetable_id)
                    
                    for record in attendance_records:
                        all_attendance.append({
                            'faculty_name': faculty_name,
                            'class_name': class_name,
                            'day': day,
                            'time_slot': time_slot,
                            'student_id': record[6],
                            'student_name': record[7],
                            'email': record[8],
                            'timestamp': record[3],
                            'status': record[4],
                            'confidence': record[5] if record[5] else 'N/A'
                        })
            
            # Write to CSV
            if all_attendance:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['Faculty Name', 'Class Name', 'Day', 'Time Slot', 'Student ID', 
                                'Student Name', 'Email', 'Timestamp', 'Status', 'Confidence Score']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    for record in all_attendance:
                        writer.writerow({
                            'Faculty Name': record['faculty_name'],
                            'Class Name': record['class_name'],
                            'Day': record['day'],
                            'Time Slot': record['time_slot'],
                            'Student ID': record['student_id'],
                            'Student Name': record['student_name'],
                            'Email': record['email'],
                            'Timestamp': record['timestamp'],
                            'Status': record['status'],
                            'Confidence Score': record['confidence']
                        })
                
                return filename, f"Successfully exported {len(all_attendance)} total attendance records"
            else:
                return None, "No attendance records found"
        
        except Exception as e:
            return None, f"Error exporting all attendance: {str(e)}"
    
    def export_faculty_summary(self, faculty_id, faculty_name):
        """Export attendance summary for a faculty (count of present/absent per class)"""
        try:
            timetables = self.db.get_faculty_timetables(faculty_id)
            
            if not timetables:
                return None, "No timetables found for this faculty"
            
            # Prepare filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(
                self.export_dir,
                f"Faculty_Summary_{faculty_name.replace(' ', '_')}_{timestamp}.csv"
            )
            
            # Collect summary data
            summary_data = []
            for timetable in timetables:
                timetable_id = timetable[0]
                class_name = timetable[2]
                day = timetable[3]
                time_slot = f"{timetable[4]} - {timetable[5]}"
                
                attendance_records = self.db.get_attendance_by_session(timetable_id)
                present_count = len(attendance_records)
                
                # Get total students in the class (from database)
                all_students = self.db.get_all_students()
                total_students = len(all_students) if all_students else 0
                absent_count = total_students - present_count
                
                summary_data.append({
                    'class_name': class_name,
                    'day': day,
                    'time_slot': time_slot,
                    'total_students': total_students,
                    'present_count': present_count,
                    'absent_count': absent_count,
                    'attendance_percentage': (present_count / total_students * 100) if total_students > 0 else 0
                })
            
            # Write to CSV
            if summary_data:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['Class Name', 'Day', 'Time Slot', 'Total Students', 'Present', 'Absent', 'Attendance %']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    for record in summary_data:
                        writer.writerow({
                            'Class Name': record['class_name'],
                            'Day': record['day'],
                            'Time Slot': record['time_slot'],
                            'Total Students': record['total_students'],
                            'Present': record['present_count'],
                            'Absent': record['absent_count'],
                            'Attendance %': f"{record['attendance_percentage']:.2f}%"
                        })
                
                return filename, f"Successfully exported summary for {len(summary_data)} classes"
            else:
                return None, "No class data found"
        
        except Exception as e:
            return None, f"Error exporting faculty summary: {str(e)}"
