from database import Database
from datetime import datetime, timedelta

class TimetableManager:
    """Manages timetable operations and active class detection"""
    
    def __init__(self):
        self.db = Database()
    
    def add_timetable_entry(self, faculty_id, class_name, day_of_week, start_time, end_time,
                            room_number=None, class_id=None, batch_id=None, subject_name=None):
        """Add a new timetable entry"""
        try:
            timetable_id = self.db.add_timetable(
                faculty_id, class_name, day_of_week, start_time, end_time,
                room_number, class_id, batch_id, subject_name
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
                timetable_day = timetable['day_of_week']
                start_time = timetable['start_time']
                end_time = timetable['end_time']
                
                if timetable_day.lower() == current_day.lower():
                    # Normal class (e.g., 09:00 to 11:00)
                    if start_time < end_time:
                        if start_time <= current_time_str <= end_time:
                            return timetable, "Active class found"
                    # Overnight class (e.g., 19:18 to 07:18)
                    else:
                        if current_time_str >= start_time or current_time_str <= end_time:
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
                timetable_day = timetable['day_of_week']
                start_time = timetable['start_time']
                
                if timetable_day.lower() == current_day.lower():
                    if start_time > current_time_str:
                        return timetable, "Next class found today"
            
            # Look for classes in next 7 days
            for i in range(1, 8):
                future_date = current_time + timedelta(days=i)
                future_day = future_date.strftime("%A")
                
                for timetable in timetables:
                    timetable_day = timetable['day_of_week']
                    
                    if timetable_day.lower() == future_day.lower():
                        return timetable, f"Next class found on {future_day}"
            
            return None, "No upcoming classes found"
        except Exception as e:
            return None, f"Error: {str(e)}"
    
    def get_class_students(self, timetable_id):
        """Get students enrolled in the specific class/batch of the timetable entry"""
        try:
            entry = self.db.get_timetable_by_id(timetable_id)
            if not entry:
                return [], "Timetable entry not found"
            
            class_id = entry['class_id']
            batch_id = entry['batch_id']
            
            if batch_id:
                students = self.db.get_students_by_batch(batch_id)
                msg = f"Retrieved {len(students)} students for specific batch"
            elif class_id:
                students = self.db.get_students_by_class(class_id)
                msg = f"Retrieved {len(students)} students for full class"
            else:
                # Fallback for old/legacy timetable entries
                students = self.db.get_all_students()
                msg = "Fallback: No class/batch ID, showing all students"
                
            return students, msg
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
