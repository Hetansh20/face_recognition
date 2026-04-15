from datetime import datetime
import sys
import os

# Mock the logic
def check_active(current_time_str, start_time, end_time):
    if start_time < end_time:
        return start_time <= current_time_str <= end_time
    else:
        return current_time_str >= start_time or current_time_str <= end_time

# Test Cases
tests = [
    # Normal hours
    ("10:00", "09:00", "11:00", True),
    ("08:00", "09:00", "11:00", False),
    ("12:00", "09:00", "11:00", False),
    
    # Overnight
    ("19:21", "19:18", "07:18", True),  # User's case
    ("23:59", "19:18", "07:18", True),
    ("01:00", "19:18", "07:18", True),
    ("07:17", "19:18", "07:18", True),
    ("08:00", "19:18", "07:18", False),
    ("18:00", "19:18", "07:18", False),
]

for cur, start, end, expected in tests:
    result = check_active(cur, start, end)
    print(f"Current: {cur}, Range: {start}-{end} -> Result: {result} (Expected: {expected})")
    if result != expected:
        print("!!! FAILURE !!!")
        sys.exit(1)

print("\nAll tests passed!")
