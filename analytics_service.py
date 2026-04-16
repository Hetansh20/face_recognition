from database import Database
from datetime import datetime, timedelta
from collections import defaultdict

class AnalyticsService:
    """Analytics service for attendance insights and reporting"""
    
    def __init__(self):
        self.db = Database()
    
    def get_system_statistics(self):
        """Get overall system statistics"""
        try:
            self.db.connect()
            
            # Get total sessions
            self.db.cursor.execute('SELECT COUNT(*) FROM attendance_sessions')
            total_sessions = self.db.cursor.fetchone()[0]
            
            # Get total attendance records
            self.db.cursor.execute('SELECT COUNT(*) FROM attendance')
            total_marked = self.db.cursor.fetchone()[0]
            
            # Get average attendance rate
            self.db.cursor.execute('''
                SELECT AVG(CAST(present_count AS FLOAT) / total_students * 100)
                FROM attendance_sessions
                WHERE total_students > 0
            ''')
            avg_attendance = self.db.cursor.fetchone()[0] or 0
            
            # Get highest attendance class
            self.db.cursor.execute('''
                SELECT t.class_name, AVG(CAST(s.present_count AS FLOAT) / s.total_students * 100) as avg_att
                FROM attendance_sessions s
                JOIN timetables t ON s.timetable_id = t.id
                WHERE s.total_students > 0
                GROUP BY t.class_name
                ORDER BY avg_att DESC
                LIMIT 1
            ''')
            highest_result = self.db.cursor.fetchone()
            highest_class = highest_result[0] if highest_result else "N/A"
            
            # Get lowest attendance class
            self.db.cursor.execute('''
                SELECT t.class_name, AVG(CAST(s.present_count AS FLOAT) / s.total_students * 100) as avg_att
                FROM attendance_sessions s
                JOIN timetables t ON s.timetable_id = t.id
                WHERE s.total_students > 0
                GROUP BY t.class_name
                ORDER BY avg_att ASC
                LIMIT 1
            ''')
            lowest_result = self.db.cursor.fetchone()
            lowest_class = lowest_result[0] if lowest_result else "N/A"
            
            # Get top performing students
            self.db.cursor.execute('''
                SELECT s.name, COUNT(a.id) as attendance_count
                FROM students s
                LEFT JOIN attendance a ON s.id = a.student_id
                GROUP BY s.id
                ORDER BY attendance_count DESC
                LIMIT 5
            ''')
            top_students = [(row[0], row[1]) for row in self.db.cursor.fetchall()]
            
            # Get low attendance students
            self.db.cursor.execute('''
                SELECT s.name, 
                       CAST(COUNT(a.id) AS FLOAT) / 
                       (SELECT COUNT(*) FROM attendance_sessions) * 100 as attendance_rate
                FROM students s
                LEFT JOIN attendance a ON s.id = a.student_id
                GROUP BY s.id
                HAVING attendance_rate < 75
                ORDER BY attendance_rate ASC
                LIMIT 5
            ''')
            low_attendance_students = [(row[0], row[1]) for row in self.db.cursor.fetchall()]
            
            self.db.disconnect()
            
            return {
                'total_sessions': total_sessions,
                'total_marked': total_marked,
                'average_attendance': avg_attendance,
                'highest_class': highest_class,
                'lowest_class': lowest_class,
                'top_students': top_students,
                'low_attendance_students': low_attendance_students
            }
        except Exception as e:
            print(f"[v0] Error getting system statistics: {str(e)}")
            return {}
    
    def get_low_attendance_students(self, threshold=75):
        """Get students with attendance below threshold"""
        try:
            self.db.connect()
            
            self.db.cursor.execute('''
                SELECT s.name, s.email, s.gr_number,
                       CAST(COUNT(a.id) AS FLOAT) / 
                       (SELECT COUNT(*) FROM attendance_sessions) * 100 as attendance_rate
                FROM students s
                LEFT JOIN attendance a ON s.id = a.student_id
                GROUP BY s.id
                HAVING attendance_rate < ?
                ORDER BY attendance_rate ASC
            ''', (threshold,))
            
            results = self.db.cursor.fetchall()
            self.db.disconnect()
            
            return results
        except Exception as e:
            print(f"[v0] Error getting low attendance students: {str(e)}")
            return []
    
    def get_student_attendance_history(self, student_id, days=30):
        """Get attendance history for a student"""
        try:
            self.db.connect()
            
            date_threshold = datetime.now() - timedelta(days=days)
            
            self.db.cursor.execute('''
                SELECT a.timestamp, t.class_name, a.status, a.confidence_score
                FROM attendance a
                JOIN timetables t ON a.timetable_id = t.id
                WHERE a.student_id = ? AND a.timestamp > ?
                ORDER BY a.timestamp DESC
            ''', (student_id, date_threshold))
            
            results = self.db.cursor.fetchall()
            self.db.disconnect()
            
            return results
        except Exception as e:
            print(f"[v0] Error getting student attendance history: {str(e)}")
            return []
    
    def get_faculty_performance(self, faculty_id):
        """Get performance metrics for a faculty"""
        try:
            self.db.connect()
            
            # Get total sessions conducted
            self.db.cursor.execute('''
                SELECT COUNT(*) FROM attendance_sessions
                WHERE faculty_id = ?
            ''', (faculty_id,))
            total_sessions = self.db.cursor.fetchone()[0]
            
            # Get average attendance in faculty's classes
            self.db.cursor.execute('''
                SELECT AVG(CAST(present_count AS FLOAT) / total_students * 100)
                FROM attendance_sessions
                WHERE faculty_id = ? AND total_students > 0
            ''', (faculty_id,))
            avg_attendance = self.db.cursor.fetchone()[0] or 0
            
            # Get total students marked
            self.db.cursor.execute('''
                SELECT COUNT(DISTINCT a.student_id)
                FROM attendance a
                JOIN attendance_sessions s ON a.timetable_id = s.timetable_id
                WHERE s.faculty_id = ?
            ''', (faculty_id,))
            total_students_marked = self.db.cursor.fetchone()[0]
            
            self.db.disconnect()
            
            return {
                'total_sessions': total_sessions,
                'average_attendance': avg_attendance,
                'total_students_marked': total_students_marked
            }
        except Exception as e:
            print(f"[v0] Error getting faculty performance: {str(e)}")
            return {}
    
    def get_class_attendance_trends(self, class_name, days=30):
        """Get attendance trends for a specific class"""
        try:
            self.db.connect()
            
            date_threshold = datetime.now() - timedelta(days=days)
            
            self.db.cursor.execute('''
                SELECT DATE(s.session_start) as date,
                       AVG(CAST(s.present_count AS FLOAT) / s.total_students * 100) as attendance_rate
                FROM attendance_sessions s
                JOIN timetables t ON s.timetable_id = t.id
                WHERE t.class_name = ? AND s.session_start > ?
                GROUP BY DATE(s.session_start)
                ORDER BY date DESC
            ''', (class_name, date_threshold))
            
            results = self.db.cursor.fetchall()
            self.db.disconnect()
            
            return results
        except Exception as e:
            print(f"[v0] Error getting class attendance trends: {str(e)}")
            return []
    
    def get_daily_attendance_report(self, date=None):
        """Get attendance report for a specific day"""
        try:
            if date is None:
                date = datetime.now().strftime('%Y-%m-%d')
            
            self.db.connect()
            
            self.db.cursor.execute('''
                SELECT t.class_name, f.name as faculty_name,
                       s.present_count, s.total_students,
                       CAST(s.present_count AS FLOAT) / s.total_students * 100 as attendance_rate
                FROM attendance_sessions s
                JOIN timetables t ON s.timetable_id = t.id
                JOIN faculties f ON s.faculty_id = f.id
                WHERE DATE(s.session_start) = ?
                ORDER BY s.session_start DESC
            ''', (date,))
            
            results = self.db.cursor.fetchall()
            self.db.disconnect()
            
            return results
        except Exception as e:
            print(f"[v0] Error getting daily attendance report: {str(e)}")
            return []
    
    def get_weekly_attendance_report(self, weeks_back=0):
        """Get attendance report for a specific week"""
        try:
            self.db.connect()
            
            # Calculate date range for the week
            today = datetime.now()
            start_of_week = today - timedelta(days=today.weekday() + (weeks_back * 7))
            end_of_week = start_of_week + timedelta(days=6)
            
            self.db.cursor.execute('''
                SELECT t.class_name, f.name as faculty_name,
                       COUNT(*) as sessions,
                       AVG(CAST(s.present_count AS FLOAT) / s.total_students * 100) as avg_attendance
                FROM attendance_sessions s
                JOIN timetables t ON s.timetable_id = t.id
                JOIN faculties f ON s.faculty_id = f.id
                WHERE s.session_start BETWEEN ? AND ?
                GROUP BY t.class_name, f.name
                ORDER BY avg_attendance DESC
            ''', (start_of_week, end_of_week))
            
            results = self.db.cursor.fetchall()
            self.db.disconnect()
            
            return results
        except Exception as e:
            print(f"[v0] Error getting weekly attendance report: {str(e)}")
            return []
    
    def get_monthly_attendance_report(self, month=None, year=None):
        """Get attendance report for a specific month"""
        try:
            if month is None:
                month = datetime.now().month
            if year is None:
                year = datetime.now().year
            
            self.db.connect()
            
            self.db.cursor.execute('''
                SELECT t.class_name, f.name as faculty_name,
                       COUNT(*) as sessions,
                       AVG(CAST(s.present_count AS FLOAT) / s.total_students * 100) as avg_attendance
                FROM attendance_sessions s
                JOIN timetables t ON s.timetable_id = t.id
                JOIN faculties f ON s.faculty_id = f.id
                WHERE MONTH(s.session_start) = ? AND YEAR(s.session_start) = ?
                GROUP BY t.class_name, f.name
                ORDER BY avg_attendance DESC
            ''', (month, year))
            
            results = self.db.cursor.fetchall()
            self.db.disconnect()
            
            return results
        except Exception as e:
            print(f"[v0] Error getting monthly attendance report: {str(e)}")
            return []
    
    def get_student_performance_ranking(self, limit=10):
        """Get top performing students"""
        try:
            self.db.connect()
            
            self.db.cursor.execute('''
                SELECT s.name, s.gr_number, s.email,
                       COUNT(a.id) as attendance_count,
                       AVG(a.confidence_score) as avg_confidence
                FROM students s
                LEFT JOIN attendance a ON s.id = a.student_id
                GROUP BY s.id
                ORDER BY attendance_count DESC, avg_confidence DESC
                LIMIT ?
            ''', (limit,))
            
            results = self.db.cursor.fetchall()
            self.db.disconnect()
            
            return results
        except Exception as e:
            print(f"[v0] Error getting student performance ranking: {str(e)}")
            return []
    
    def export_analytics_report(self, filename=None):
        """Export analytics report to CSV"""
        try:
            import csv
            from datetime import datetime
            
            if filename is None:
                filename = f"analytics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            stats = self.get_system_statistics()
            
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(['Attendance System Analytics Report'])
                writer.writerow(['Generated', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                writer.writerow([])
                
                # Write statistics
                writer.writerow(['System Statistics'])
                writer.writerow(['Total Sessions', stats.get('total_sessions', 0)])
                writer.writerow(['Total Students Marked', stats.get('total_marked', 0)])
                writer.writerow(['Average Attendance Rate', f"{stats.get('average_attendance', 0):.2f}%"])
                writer.writerow(['Highest Attendance Class', stats.get('highest_class', 'N/A')])
                writer.writerow(['Lowest Attendance Class', stats.get('lowest_class', 'N/A')])
                writer.writerow([])
                
                # Write top students
                writer.writerow(['Top Performing Students'])
                writer.writerow(['Rank', 'Student Name', 'Attendance Count'])
                for idx, (name, count) in enumerate(stats.get('top_students', []), 1):
                    writer.writerow([idx, name, count])
                writer.writerow([])
                
                # Write low attendance students
                writer.writerow(['Students with Low Attendance'])
                writer.writerow(['Student Name', 'Attendance Rate'])
                for name, rate in stats.get('low_attendance_students', []):
                    writer.writerow([name, f"{rate:.2f}%"])
            
            return filename
        except Exception as e:
            print(f"[v0] Error exporting analytics report: {str(e)}")
            return None

# Initialize analytics service
analytics_service = AnalyticsService()
