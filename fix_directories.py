import os
import shutil
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_project.settings')
django.setup()

from attendance.models import Employee, AttendanceRecord

def fix_image_directories():
    media_root = 'media'
    checkin_path = os.path.join(media_root, 'checkin_images')
    checkout_path = os.path.join(media_root, 'checkout_images')
    
    # Get all employees and their old/new IDs from attendance records
    records_with_images = AttendanceRecord.objects.filter(
        checkin_image__isnull=False
    ).select_related('employee')
    
    # Track directory renames needed
    renames_needed = {}
    
    for record in records_with_images:
        current_id = record.employee.employee_id
        # Extract old ID from image path
        if record.checkin_image:
            path_parts = record.checkin_image.name.split('/')
            if len(path_parts) >= 2:
                old_id = path_parts[1]  # checkin_images/OLD_ID/date/file.jpg
                if old_id != current_id:
                    renames_needed[old_id] = current_id
    
    print(f"Found {len(renames_needed)} directories that need renaming:")
    for old_id, new_id in renames_needed.items():
        print(f"  {old_id} -> {new_id}")
    
    # Rename directories
    renamed_count = 0
    for old_id, new_id in renames_needed.items():
        # Rename checkin directory
        old_checkin_dir = os.path.join(checkin_path, old_id)
        new_checkin_dir = os.path.join(checkin_path, new_id)
        
        if os.path.exists(old_checkin_dir):
            if os.path.exists(new_checkin_dir):
                # Merge directories
                for item in os.listdir(old_checkin_dir):
                    shutil.move(
                        os.path.join(old_checkin_dir, item),
                        os.path.join(new_checkin_dir, item)
                    )
                os.rmdir(old_checkin_dir)
            else:
                os.rename(old_checkin_dir, new_checkin_dir)
            renamed_count += 1
        
        # Rename checkout directory
        old_checkout_dir = os.path.join(checkout_path, old_id)
        new_checkout_dir = os.path.join(checkout_path, new_id)
        
        if os.path.exists(old_checkout_dir):
            if os.path.exists(new_checkout_dir):
                # Merge directories
                for item in os.listdir(old_checkout_dir):
                    shutil.move(
                        os.path.join(old_checkout_dir, item),
                        os.path.join(new_checkout_dir, item)
                    )
                os.rmdir(old_checkout_dir)
            else:
                os.rename(old_checkout_dir, new_checkout_dir)
    
    print(f"Renamed {renamed_count} directories to match current employee IDs")
    
    # Update database paths
    updated_records = 0
    for record in records_with_images:
        current_id = record.employee.employee_id
        updated = False
        
        if record.checkin_image:
            old_path = record.checkin_image.name
            new_path = old_path.replace(f'checkin_images/{old_path.split("/")[1]}/', f'checkin_images/{current_id}/')
            if old_path != new_path:
                record.checkin_image.name = new_path
                updated = True
        
        if record.checkout_image:
            old_path = record.checkout_image.name
            new_path = old_path.replace(f'checkout_images/{old_path.split("/")[1]}/', f'checkout_images/{current_id}/')
            if old_path != new_path:
                record.checkout_image.name = new_path
                updated = True
        
        if updated:
            record.save()
            updated_records += 1
    
    print(f"Updated {updated_records} attendance record image paths")

if __name__ == '__main__':
    fix_image_directories()