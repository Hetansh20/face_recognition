from database import Database
from datetime import datetime, timedelta
import secrets

class AuthManager:
    """Authentication manager for faculty login"""
    
    def __init__(self):
        self.db = Database()
        self.sessions = {}  # In-memory session storage
    
    def faculty_login(self, email, passcode):
        """Authenticate faculty with email and passcode"""
        faculty = self.db.get_faculty_by_email(email)
        
        if not faculty:
            return None, "Faculty not found"
        
        if not faculty[5]:  # Check if active
            return None, "Faculty account is inactive"
        
        # Verify passcode
        if not self.db.verify_passcode(passcode, faculty[4]):
            return None, "Invalid passcode"
        
        # Create session
        session_token = secrets.token_urlsafe(32)
        self.sessions[session_token] = {
            'faculty_id': faculty[0],
            'email': faculty[2],
            'name': faculty[1],
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(hours=8)
        }
        
        return session_token, "Login successful"
    
    def verify_session(self, session_token):
        """Verify if a session is valid"""
        if session_token not in self.sessions:
            return None, "Invalid session"
        
        session = self.sessions[session_token]
        
        if datetime.now() > session['expires_at']:
            del self.sessions[session_token]
            return None, "Session expired"
        
        return session, "Session valid"
    
    def logout(self, session_token):
        """Logout a faculty member"""
        if session_token in self.sessions:
            del self.sessions[session_token]
            return True, "Logout successful"
        return False, "Session not found"
    
    def get_active_class(self, faculty_id):
        """Get the active class for a faculty based on current time"""
        from datetime import datetime
        
        faculty_timetables = self.db.get_faculty_timetables(faculty_id)
        
        if not faculty_timetables:
            return None, "No timetables found for this faculty"
        
        current_time = datetime.now()
        current_day = current_time.strftime("%A")  # e.g., "Monday"
        current_time_str = current_time.strftime("%H:%M")
        
        for timetable in faculty_timetables:
            timetable_day = timetable[3]  # day_of_week
            start_time = timetable[4]
            end_time = timetable[5]
            
            if timetable_day.lower() == current_day.lower():
                if start_time <= current_time_str <= end_time:
                    return timetable, "Active class found"
        
        return None, "No active class at this time"

# Initialize auth manager
auth_manager = AuthManager()
