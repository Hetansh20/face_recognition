from database import Database
from datetime import datetime

class AttendanceMarker:
    """Handles attendance marking and session management"""
    
    def __init__(self):
        self.db = Database()
        self.current_session = None
    
    def start_session(self, faculty_id, timetable_id):
        """Start a new attendance session"""
        try:
            # Get class students
            students = self.db.get_all_students()
            total_students = len(students)
            
            # Create session
            session_id = self.db.create_session(faculty_id, timetable_id, total_students)
            self.current_session = {
                'session_id': session_id,
                'faculty_id': faculty_id,
                'timetable_id': timetable_id,
                'start_time': datetime.now(),
                'total_students': total_students,  # Store total_students in session
                'recognized_students': set()
            }
            
            return session_id, f"Session started. Total students: {total_students}"
        except Exception as e:
            return None, f"Error starting session: {str(e)}"
    
    def mark_student_present(self, student_id, timetable_id, confidence_score=None):
        """Mark a student as present"""
        try:
            self.db.mark_attendance(student_id, timetable_id, confidence_score)
            
            if self.current_session:
                self.current_session['recognized_students'].add(student_id)
            
            return True, "Attendance marked"
        except Exception as e:
            return False, f"Error marking attendance: {str(e)}"
    
    def end_session(self):
        """End the current attendance session"""
        try:
            if not self.current_session:
                return None, "No active session"
            
            session_id = self.current_session['session_id']
            present_count = len(self.current_session['recognized_students'])
            total_students = self.current_session.get('total_students', 0)
            
            absent_count = total_students - present_count
            
            self.db.end_session(session_id, present_count)
            
            session_info = {
                'session_id': session_id,
                'present_count': present_count,
                'absent_count': absent_count,
                'total_students': total_students,
                'duration': datetime.now() - self.current_session['start_time']
            }
            
            self.current_session = None
            
            return session_info, "Session ended successfully"
        except Exception as e:
            return None, f"Error ending session: {str(e)}"
    
    def get_session_report(self, session_id):
        """Get attendance report for a session"""
        try:
            session = self.db.get_session(session_id)
            
            if not session:
                return None, "Session not found"
            
            # Get attendance records
            timetable_id = session[2]
            attendance_records = self.db.get_attendance_by_session(timetable_id)
            
            report = {
                'session_id': session_id,
                'total_students': session[4],
                'present_count': session[5],
                'absent_count': session[4] - session[5],
                'attendance_percentage': (session[5] / session[4] * 100) if session[4] > 0 else 0,
                'records': attendance_records
            }
            
            return report, "Report generated"
        except Exception as e:
            return None, f"Error generating report: {str(e)}"

# Initialize attendance marker
attendance_marker = AttendanceMarker()
