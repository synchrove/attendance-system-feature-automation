import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_project.settings')
django.setup()

from attendance.models import Employee, AttendanceRecord

# Get employees who have attendance records
employees_with_records = set(AttendanceRecord.objects.values_list('employee_id', flat=True))

# Get all employees
all_employees = Employee.objects.all()

deleted_count = 0
for emp in all_employees:
    if emp.id not in employees_with_records and emp.employee_image:
        try:
            if os.path.exists(emp.employee_image.path):
                os.remove(emp.employee_image.path)
                deleted_count += 1
            emp.employee_image = None
            emp.save()
        except:
            pass

print(f'Cleared {deleted_count} employee images for employees without attendance records')