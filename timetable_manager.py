from database import Database
from datetime import datetime, timedelta

class TimetableManager:
    """Manages timetable operations and active class detection"""
    
    def __init__(self):
        self.db = Database()
    
    def add_timetable_entry(self, faculty_id, class_name, day_of_week, start_time, end_time, room_number=None):
        """Add a new timetable entry"""
        try:
            timetable_id = self.db.add_timetable(
                faculty_id, class_name, day_of_week, start_time, end_time, room_number
            )
            return timetable_id, "Timetable entry added successfully"
        except Exception as e:
            return None, f"Error adding timetable: {str(e)}"
    
    def get_faculty_schedule(self, faculty_id):
        """Get complete schedule for a faculty"""
        try:
            timetables = self.db.get_faculty_timetables(faculty_id)
            return timetables, "Schedule retrieved successfully"
        except Exception as e:
            return None, f"Error retrieving schedule: {str(e)}"
    
    def get_active_class(self, faculty_id):
        """Get the currently active class for a faculty"""
        try:
            timetables = self.db.get_faculty_timetables(faculty_id)
            
            if not timetables:
                return None, "No timetables found"
            
            current_time = datetime.now()
            current_day = current_time.strftime("%A")
            current_time_str = current_time.strftime("%H:%M")
            
            for timetable in timetables:
                timetable_day = timetable[3]
                start_time = timetable[4]
                end_time = timetable[5]
                
                if timetable_day.lower() == current_day.lower():
                    if start_time <= current_time_str <= end_time:
                        return timetable, "Active class found"
            
            return None, "No active class at this time"
        except Exception as e:
            return None, f"Error: {str(e)}"
    
    def get_next_class(self, faculty_id):
        """Get the next upcoming class for a faculty"""
        try:
            timetables = self.db.get_faculty_timetables(faculty_id)
            
            if not timetables:
                return None, "No timetables found"
            
            current_time = datetime.now()
            current_day = current_time.strftime("%A")
            current_time_str = current_time.strftime("%H:%M")
            
            # Look for next class today
            for timetable in timetables:
                timetable_day = timetable[3]
                start_time = timetable[4]
                
                if timetable_day.lower() == current_day.lower():
                    if start_time > current_time_str:
                        return timetable, "Next class found today"
            
            # Look for classes in next 7 days
            for i in range(1, 8):
                future_date = current_time + timedelta(days=i)
                future_day = future_date.strftime("%A")
                
                for timetable in timetables:
                    timetable_day = timetable[3]
                    
                    if timetable_day.lower() == future_day.lower():
                        return timetable, f"Next class found on {future_day}"
            
            return None, "No upcoming classes found"
        except Exception as e:
            return None, f"Error: {str(e)}"
    
    def get_class_students(self, timetable_id):
        """Get all students enrolled in a class"""
        try:
            # This would need a student-class enrollment table
            # For now, return all students
            students = self.db.get_all_students()
            return students, "Students retrieved"
        except Exception as e:
            return None, f"Error: {str(e)}"
    
    def validate_time_format(self, time_str):
        """Validate time format (HH:MM)"""
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False
    
    def validate_day_format(self, day_str):
        """Validate day of week"""
        valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return day_str in valid_days

# Initialize timetable manager
timetable_manager = TimetableManager()
