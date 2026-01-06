# Django framework imports
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.template.response import TemplateResponse
from decimal import Decimal

# Local app imports
from .models import Employee, AttendanceRecord, get_active_shift, SalaryAdjustment, BulkHoliday

# Utility modules for organized functionality
from .utils.dashboard_helpers import (
    get_dashboard_params,
    build_month_nav,
    build_days,
    get_employee_queryset,
    build_record_map,
    build_employee_row,
)
from .utils.import_helpers import handle_import, handle_export, HAS_OPENPYXL
from .utils.face_recognition_helpers import (
    debug_request_print,
    load_image_from_request,
    detect_face_and_encoding,
    load_known_encodings,
    find_best_match,
    mark_attendance,
)
from .utils.salary_helpers import (
    get_employee_salary_summary,
    process_monthly_salary_adjustments,
)


@staff_member_required
def attendance_dashboard_view(request):
    """
    Main attendance dashboard with comprehensive features.
    
    Features:
    - Monthly attendance grid view with status icons
    - Department/designation filtering
    - Month-to-month navigation with preserved filters
    - Import/export functionality (CSV, XLSX, ZIP)
    - Real-time attendance totals and late indicators
    - Employee photo integration
    
    Returns: Rendered dashboard template with context data
    """
    (
        selected_year,
        selected_month,
        selected_department,
        selected_designation,
        today,
        days_in_month,
    ) = get_dashboard_params(request)

    prev_qs, next_qs = build_month_nav(
        selected_year,
        selected_month,
        selected_department,
        selected_designation,
    )

    # Export block
    export_response = handle_export(request, selected_year, selected_month)
    if export_response:
        return export_response
    
    # Import block
    import_errors, import_success = handle_import(
        request,
        selected_year,
        selected_month,
    )

    # Dashboard data
    days = build_days(selected_year, selected_month, days_in_month)
    employees_qs = get_employee_queryset(selected_department, selected_designation)
    record_map = build_record_map(selected_year, selected_month)
    active_shift = get_active_shift()

    dashboard_data = []
    for emp in employees_qs:
        statuses, totals, emp_image_url = build_employee_row(
            emp,
            days,
            today,
            record_map,
            active_shift,
        )
        dashboard_data.append(
            {
                "employee_id": emp.employee_id,
                "name": emp.name,
                "designation": emp.designation,
                "statuses": statuses,
                "totals": totals,
                "emp_image_url": emp_image_url,
                "emp_pk": emp.id,
            }
        )

    departments = Employee.objects.values_list("department", flat=True).distinct()
    designations = Employee.objects.values_list("designation", flat=True).distinct()

    months = list(range(1, 13))
    years = [selected_year - 1, selected_year, selected_year + 1]

    context = {
        "month": selected_month,
        "year": selected_year,
        "days": days,
        "employees": dashboard_data,
        "departments": departments,
        "designations": designations,
        "selected_department": selected_department,
        "selected_designation": selected_designation,
        "months": months,
        "years": years,
        "prev_qs": prev_qs,
        "next_qs": next_qs,
        "import_errors": import_errors,
        "import_success": import_success,
        "has_openpyxl": HAS_OPENPYXL,
    }
    return TemplateResponse(request, "admin/attendance-dashboard.html", context)


@csrf_exempt
def face_attendance_api(request):
    """
    Face recognition API endpoint for mobile app integration.
    
    Process Flow:
    1. Receive image and device_id from mobile app
    2. Detect and extract face from image
    3. Generate 128-d face encoding
    4. Match against known employee encodings
    5. Mark attendance (checkin/checkout) with image
    6. Return employee info and attendance status
    
    Expected POST data:
    - image: Face photo file
    - device_id: Terminal/device identifier (optional)
    
    Returns: JSON response with employee info and check status
    """
    debug_request_print(request)

    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    device_id = (request.POST.get("device_id") or "").strip()
    image_file = request.FILES.get("image")

    if not image_file:
        print("DEBUG: NO IMAGE FILE IN REQUEST")
        return JsonResponse(
            {"error": "Image file (field name 'image') is required."}, status=400
        )

    try:
        img = load_image_from_request(image_file)
    except Exception as e:
        print("DEBUG: PIL failed to open image:", e)
        return JsonResponse({"error": "Could not read image."}, status=400)

    img_np, encoding, err = detect_face_and_encoding(img)
    if err:
        return JsonResponse({"error": err}, status=400)

    known_encodings, employees = load_known_encodings()
    employee, err = find_best_match(known_encodings, employees, encoding)
    if err == "No employees with registered face encodings.":
        return JsonResponse({"error": err}, status=500)
    if err == "Face not recognized.":
        return JsonResponse({"status": "unknown", "message": err}, status=404)

    # Check for 1-hour cooldown
    from datetime import datetime, timedelta
    import pytz
    dhaka = pytz.timezone("Asia/Dhaka")
    now = datetime.now(dhaka)
    today = now.date()
    
    # Get today's attendance record
    today_record = AttendanceRecord.objects.filter(
        employee=employee, date=today
    ).first()
    
    if today_record and today_record.checkin_time:
        # Check if less than 1 hour since checkin
        checkin_dhaka = today_record.checkin_time.astimezone(dhaka)
        time_diff = now - checkin_dhaka
        if time_diff < timedelta(hours=1):
            minutes_left = 60 - int(time_diff.total_seconds() / 60)
            return JsonResponse({
                "status": "ok",
                "employee_id": employee.employee_id,
                "employee_name": employee.name,
                "check_type": "cooldown",
                "display_text": f"Please wait {minutes_left} minutes before next recognition",
                "cooldown_remaining": minutes_left
            })

    check_type, display_text = mark_attendance(employee, device_id, image_file)

    return JsonResponse(
        {
            "status": "ok",
            "employee_id": employee.employee_id,
            "employee_name": employee.name,
            "check_type": check_type,
            "display_text": display_text,
        }
    )


@staff_member_required
def salary_management_view(request):
    """
    Comprehensive salary management interface.
    
    Features:
    - Monthly salary calculations with automatic adjustments
    - Manual bonus/fine management
    - Bulk processing of automatic adjustments
    - Employee-wise salary breakdown
    - Real-time calculation based on attendance
    
    Automatic Rules:
    - Fine: 3+ late days = 1 day salary fine per 3 days
    - Bonus: 100% Present + No late days = 1000 BDT bonus
    """
    from datetime import datetime

    selected_month = int(request.GET.get("month", datetime.now().month))
    selected_year = int(request.GET.get("year", datetime.now().year))

    # Process automatic adjustments if requested
    if request.method == "POST" and request.POST.get("process_auto"):
        processed_count = process_monthly_salary_adjustments(
            selected_year, selected_month
        )
        context = {
            "message": f"Processed {processed_count} automatic salary adjustments",
            "message_type": "success",
        }
    else:
        context = {}

    # Get all employees with salary summaries
    employees_data = []
    for emp in Employee.objects.all():
        summary = get_employee_salary_summary(emp, selected_year, selected_month)
        employees_data.append({"employee": emp, "summary": summary})

    context.update(
        {
            "month": selected_month,
            "year": selected_year,
            "employees_data": employees_data,
            "months": list(range(1, 13)),
            "years": [selected_year - 1, selected_year, selected_year + 1],
        }
    )

    return TemplateResponse(request, "admin/salary-management.html", context)


@staff_member_required
def salary_report_view(request):
    """
    Detailed salary report with comprehensive breakdown.
    
    Features:
    - Monthly salary calculations per employee
    - Department-wise filtering
    - Total salary summaries
    - Bonus/fine details with reasons
    - Working days and late days tracking
    - Export-ready format for payroll processing
    """
    from datetime import datetime

    selected_month = int(request.GET.get("month", datetime.now().month))
    selected_year = int(request.GET.get("year", datetime.now().year))
    selected_department = request.GET.get("department") or None
    
    # Process automatic adjustments if requested
    message = None
    if request.method == "POST" and request.POST.get("process_auto"):
        processed_count = process_monthly_salary_adjustments(selected_year, selected_month)
        message = f"Processed {processed_count} automatic salary adjustments for {datetime(selected_year, selected_month, 1).strftime('%B %Y')}"

    # Filter employees by department if selected
    employees_qs = Employee.objects.all()
    if selected_department:
        employees_qs = employees_qs.filter(department=selected_department)

    # Calculate salary data for each employee
    salary_data = []
    total_base_salary = Decimal("0.00")
    total_bonuses = Decimal("0.00")
    total_fines = Decimal("0.00")
    total_final_salary = Decimal("0.00")

    for emp in employees_qs:
        summary = get_employee_salary_summary(emp, selected_year, selected_month)

        final_salary = summary["base_salary"] + summary["net_adjustment"]

        salary_data.append(
            {
                "employee": emp,
                "base_salary": summary["base_salary"],
                "total_bonus": summary["total_bonus"],
                "total_fine": summary["total_fine"],
                "final_salary": final_salary,
                "late_days": summary["late_days"],
                "working_days": summary["working_days"],
                "bonuses": summary["bonuses"],
                "fines": summary["fines"],
            }
        )

        # Add to totals
        total_base_salary += summary["base_salary"]
        total_bonuses += summary["total_bonus"]
        total_fines += summary["total_fine"]
        total_final_salary += final_salary

    departments = Employee.objects.values_list("department", flat=True).distinct()

    context = {
        "month": selected_month,
        "year": selected_year,
        "selected_department": selected_department,
        "salary_data": salary_data,
        "departments": departments,
        "months": list(range(1, 13)),
        "years": [selected_year - 1, selected_year, selected_year + 1],
        "totals": {
            "base_salary": total_base_salary,
            "bonuses": total_bonuses,
            "fines": total_fines,
            "final_salary": total_final_salary,
        },
        "month_name": datetime(selected_year, selected_month, 1).strftime("%B %Y"),
        "message": message,
    }

    return TemplateResponse(request, "admin/salary-report-new.html", context)


@staff_member_required
def employee_detail_view(request, employee_id):
    """
    Employee detail view with attendance summary and recent records.
    
    Features:
    - Employee information and photo
    - Monthly attendance summary
    - Recent attendance records
    - Quick actions (add attendance, edit employee)
    """
    from django.shortcuts import get_object_or_404
    from datetime import datetime, timedelta
    
    employee = get_object_or_404(Employee, id=employee_id)
    
    # Get current month attendance summary
    now = datetime.now()
    current_month_records = AttendanceRecord.objects.filter(
        employee=employee,
        date__year=now.year,
        date__month=now.month
    ).order_by('-date')
    
    # Calculate monthly stats
    monthly_stats = {
        'present': current_month_records.filter(status='Present').count(),
        'absent': current_month_records.filter(status='Absent').count(),
        'late': sum(1 for r in current_month_records if r.is_late_indicator()),
        'on_leave': current_month_records.filter(status='On Leave').count(),
        'holiday': current_month_records.filter(status='Holiday').count(),
    }
    
    # Get recent 10 records
    recent_records = AttendanceRecord.objects.filter(
        employee=employee
    ).order_by('-date')[:10]
    
    context = {
        'employee': employee,
        'monthly_stats': monthly_stats,
        'recent_records': recent_records,
        'current_month': now.strftime('%B %Y'),
    }
    
    return TemplateResponse(request, "admin/employee-detail.html", context)


@staff_member_required
def holiday_management_view(request):
    """
    Advanced holiday management system.
    
    Features:
    - Bulk holiday creation with scope targeting
    - Government holiday auto-generation for Bangladesh
    - Department/designation/custom employee selection
    - Real-time holiday activation/deactivation
    - Smart processing (preserves existing attendance)
    - Holiday calendar management
    
    Supported Operations:
    - Create custom holidays
    - Generate government holidays
    - Update existing holidays
    - Delete holidays with cleanup
    """
    from datetime import datetime, date
    
    message = None
    message_type = None
    
    if request.method == "POST":
        if request.POST.get("create_holiday"):
            try:
                name = request.POST.get("name")
                start_date = datetime.strptime(request.POST.get("start_date"), "%Y-%m-%d").date()
                end_date = datetime.strptime(request.POST.get("end_date"), "%Y-%m-%d").date()
                scope = request.POST.get("scope")
                description = request.POST.get("description", "")
                is_government = request.POST.get("is_government") == "1"
                
                holiday = BulkHoliday.objects.create(
                    name=name,
                    start_date=start_date,
                    end_date=end_date,
                    scope=scope,
                    description=description,
                    created_by=request.user.username if not is_government else "System",
                    is_government=is_government,
                    is_active=True
                )
                
                if scope == "department":
                    holiday.department = request.POST.get("department")
                elif scope == "designation":
                    holiday.designation = request.POST.get("designation")
                elif scope == "custom":
                    employee_ids = request.POST.getlist("selected_employees")
                    holiday.selected_employees.set(employee_ids)
                
                holiday.save()
                message = f"Holiday '{name}' created and activated!"
                message_type = "success"
                
            except Exception as e:
                message = f"Error: {str(e)}"
                message_type = "error"
        
        elif request.POST.get("update_holiday"):
            holiday_id = request.POST.get("holiday_id")
            try:
                holiday = BulkHoliday.objects.get(id=holiday_id)
                holiday.name = request.POST.get("name")
                holiday.start_date = datetime.strptime(request.POST.get("start_date"), "%Y-%m-%d").date()
                holiday.end_date = datetime.strptime(request.POST.get("end_date"), "%Y-%m-%d").date()
                holiday.is_active = request.POST.get("is_active") == "1"
                holiday.save()
                message = f"Holiday '{holiday.name}' updated!"
                message_type = "success"
            except BulkHoliday.DoesNotExist:
                message = "Holiday not found"
                message_type = "error"
            except Exception as e:
                message = f"Error: {str(e)}"
                message_type = "error"
        
        elif request.POST.get("delete_holiday"):
            holiday_id = request.POST.get("holiday_id")
            try:
                holiday = BulkHoliday.objects.get(id=holiday_id)
                name = holiday.name
                holiday.delete()
                message = f"Holiday '{name}' deleted!"
                message_type = "success"
            except BulkHoliday.DoesNotExist:
                message = "Holiday not found"
                message_type = "error"
            except Exception as e:
                message = f"Error: {str(e)}"
                message_type = "error"
        
        elif request.POST.get("auto_generate_holidays"):
            year = int(request.POST.get("generate_year", datetime.now().year))
            try:
                holidays = [
                    {"name": "International Mother Language Day", "month": 2, "day": 21},
                    {"name": "Independence Day", "month": 3, "day": 26},
                    {"name": "Bengali New Year", "month": 4, "day": 14},
                    {"name": "May Day", "month": 5, "day": 1},
                    {"name": "National Mourning Day", "month": 8, "day": 15},
                    {"name": "Victory Day", "month": 12, "day": 16},
                    {"name": "Christmas Day", "month": 12, "day": 25},
                ]
                
                created_count = 0
                for holiday_data in holidays:
                    holiday_date = date(year, holiday_data["month"], holiday_data["day"])
                    holiday_name = f"{holiday_data['name']} {year}"
                    
                    if not BulkHoliday.objects.filter(name=holiday_name, start_date=holiday_date).exists():
                        BulkHoliday.objects.create(
                            name=holiday_name,
                            start_date=holiday_date,
                            end_date=holiday_date,
                            scope='all',
                            description="Bangladesh Government Holiday",
                            created_by="System",
                            is_government=True,
                            is_active=True
                        )
                        created_count += 1
                
                message = f"Generated {created_count} government holidays for {year}!"
                message_type = "success"
                
            except Exception as e:
                message = f"Error: {str(e)}"
                message_type = "error"
    
    all_holidays = BulkHoliday.objects.all().order_by('-created_at')
    government_holidays = all_holidays.filter(is_government=True)
    custom_holidays = all_holidays.filter(is_government=False)
    
    departments = Employee.objects.values_list("department", flat=True).distinct()
    designations = Employee.objects.values_list("designation", flat=True).distinct()
    employees = Employee.objects.all().order_by('name')
    
    context = {
        "holidays": custom_holidays,
        "government_holidays": government_holidays,
        "departments": departments,
        "designations": designations,
        "employees": employees,
        "message": message,
        "message_type": message_type,
        "current_user": request.user.username,
        "current_year": datetime.now().year,
    }
    
    return TemplateResponse(request, "admin/holiday-management.html", context)



