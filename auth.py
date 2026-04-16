from database import Database
from datetime import datetime, timedelta
import secrets

class AuthManager:
    """Authentication manager for faculty login"""
    
    def __init__(self):
        self.db = Database()
        self.sessions = {}  # In-memory session storage
    
    def faculty_login(self, passcode):
        """Authenticate faculty with passcode only"""
        faculty = self.db.get_faculty_by_passcode(passcode)
        
        if not faculty:
            return None, "Invalid passcode or Faculty not found"
        
        if not faculty['is_active']:  # Check if active
            return None, "Faculty account is inactive"
        
        # Create session
        session_token = secrets.token_urlsafe(32)
        self.sessions[session_token] = {
            'faculty_id': faculty['id'],
            'email': faculty['email'],
            'name': faculty['name'],
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
            timetable_day = timetable['day_of_week']
            start_time = timetable['start_time']
            end_time = timetable['end_time']
            
            if timetable_day.lower() == current_day.lower():
                if start_time <= current_time_str <= end_time:
                    return timetable, "Active class found"
        
        return None, "No active class at this time"

# Initialize auth manager
auth_manager = AuthManager()
