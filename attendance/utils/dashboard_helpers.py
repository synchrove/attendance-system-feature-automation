# Python standard library imports
import calendar
from datetime import date
from urllib.parse import urlencode

# Django framework imports
from django.urls import reverse

# Local model imports
from ..models import AttendanceRecord, Employee


def get_dashboard_params(request):
    """
    Extract dashboard parameters from request with intelligent defaults.
    
    Parameters extracted:
    - month/year: Current month/year if not specified
    - department/designation: Optional filters
    - today: Current date for comparison
    - days_in_month: Calendar calculation for grid layout
    
    Returns: Tuple of (year, month, department, designation, today, days_in_month)
    """
    selected_month = int(request.GET.get("month", date.today().month))
    selected_year = int(request.GET.get("year", date.today().year))
    selected_department = request.GET.get("department") or None
    selected_designation = request.GET.get("designation") or None
    today = date.today()
    days_in_month = calendar.monthrange(selected_year, selected_month)[1]
    return (
        selected_year,
        selected_month,
        selected_department,
        selected_designation,
        today,
        days_in_month,
    )


def build_month_nav(
    selected_year, selected_month, selected_department, selected_designation
):
    """
    Generate navigation URLs for previous/next month with filter preservation.
    
    Features:
    - Handles year transitions (Dec -> Jan, Jan -> Dec)
    - Preserves department/designation filters
    - Returns URL-encoded query strings
    
    Returns: Tuple of (prev_month_qs, next_month_qs)
    """

    def prev_month(y, m):
        return (y - 1, 12) if m == 1 else (y, m - 1)

    def next_month(y, m):
        return (y + 1, 1) if m == 12 else (y, m + 1)

    py, pm = prev_month(selected_year, selected_month)
    ny, nm = next_month(selected_year, selected_month)

    base_prev = {"month": pm, "year": py}
    base_next = {"month": nm, "year": ny}

    if selected_department:
        base_prev["department"] = selected_department
        base_next["department"] = selected_department
    if selected_designation:
        base_prev["designation"] = selected_designation
        base_next["designation"] = selected_designation

    prev_qs = urlencode(base_prev)
    next_qs = urlencode(base_next)
    return prev_qs, next_qs


def build_days(selected_year, selected_month, days_in_month):
    """
    Generate day metadata for calendar grid display.
    
    Creates structured data for each day including:
    - Day number and weekday names
    - ISO date format for processing
    - Short and full weekday names for display
    
    Returns: List of day dictionaries with metadata
    """
    days = []
    for d in range(1, days_in_month + 1):
        current = date(selected_year, selected_month, d)
        days.append(
            {
                "num": d,
                "short": current.strftime("%a"),
                "full": current.strftime("%A"),
                "iso": current.isoformat(),
            }
        )
    return days


def get_employee_queryset(selected_department, selected_designation):
    """
    Build filtered employee queryset based on dashboard filters.
    
    Supports:
    - Department filtering
    - Designation filtering
    - Combined filters
    - No filters (all employees)
    - Orders by active status (active employees first)
    
    Returns: Filtered Employee queryset
    """
    employee_filter = {}
    if selected_department:
        employee_filter["department"] = selected_department
    if selected_designation:
        employee_filter["designation"] = selected_designation

    if employee_filter:
        return Employee.objects.filter(**employee_filter).order_by('-is_active', 'employee_id')
    return Employee.objects.all().order_by('-is_active', 'employee_id')


def build_record_map(selected_year, selected_month):
    """
    Create efficient lookup map for attendance records.
    
    Optimization:
    - Single database query for entire month
    - Dictionary lookup by (employee_id, day) key
    - Includes related employee data via select_related
    
    Returns: Dictionary mapping (employee_id, day) -> AttendanceRecord
    """
    records = AttendanceRecord.objects.filter(
        date__year=selected_year, date__month=selected_month
    ).select_related("employee")
    return {(r.employee.id, r.date.day): r for r in records}


# Status icon mapping for visual dashboard display
ICON_MAP = {
    "Present": "icons/present.png",
    "Absent": "icons/absent.png",
    "Early Leave": "icons/early_leave.png",
    "Half Day": "icons/half_day.png",
    "On Leave": "icons/on_leave.png",
    "Holiday": "icons/holidays.png",
    "Pending": "icons/pendings.png",
    "Off Day": "icons/off_day.png",
    "Late": "icons/late.png",
}


def build_employee_row(emp, days, today, record_map, active_shift):
    """
    Generate comprehensive employee row data for dashboard grid.
    
    Process:
    1. Iterate through each day of the month
    2. Determine attendance status (Present/Absent/etc.)
    3. Calculate late indicators separately from status
    4. Handle special cases (weekends, future dates, missing records)
    5. Generate admin edit URLs for existing records
    6. Count totals for summary statistics
    
    Features:
    - Friday = Off Day (Bangladesh weekend)
    - Future dates = blank (no status)
    - Missing past records = blank (not assumed absent)
    - Late indicators separate from attendance status
    - Employee photo URL extraction
    
    Returns: Tuple of (statuses_list, totals_dict, employee_image_url)
    """
    statuses = []
    totals = {
        "Present": 0,
        "Late": 0,
        "On_Leave": 0,
        "Holiday": 0,
        "Absent": 0,
        "Half_Day": 0,
        "Early_Leave": 0,
    }

    # employee image url
    emp_image_url = None
    try:
        img_field = getattr(emp, "employee_image", None)
        if img_field and hasattr(img_field, "url"):
            emp_image_url = img_field.url
    except Exception:
        emp_image_url = None

    for day_info in days:
        day_num = day_info["num"]
        current_date = date(
            int(day_info["iso"].split("-")[0]),
            int(day_info["iso"].split("-")[1]),
            day_num,
        )
        record = record_map.get((emp.id, day_num), None)

        # Check if employee was inactive on this date
        if not emp.is_active and emp.date_inactive and current_date >= emp.date_inactive:
            # Employee was inactive - show as dash
            display_status = None
            icon = None
            is_late = False
            late_display = None
            change_url = None
            list_url = None
        # Check if employee hadn't joined yet
        elif emp.hire_date and current_date < emp.hire_date:
            # Employee hadn't joined yet - show special indicator
            display_status = "Not Joined"
            icon = None  # No icon, will show text
            is_late = False
            late_display = None
            change_url = None
            list_url = None
        # Friday = Off Day (weekly off)
        elif current_date.weekday() == 4:
            display_status = "Off Day"
            icon = ICON_MAP.get(display_status, "icons/pendings.png")
            is_late = False
            late_display = None
            change_url = None
            list_url = None
        else:
            if record is None:
                # Future -> blank
                if current_date > today:
                    display_status = None
                    icon = None
                    is_late = False
                    late_display = None
                    change_url = None
                    list_url = None
                else:
                    # Past/today without record -> show as Absent
                    display_status = "Absent"
                    icon = ICON_MAP.get("Absent", "icons/absent.png")
                    is_late = False
                    late_display = None
                    try:
                        change_url = f"{reverse('admin:attendance_attendancerecord_add')}?employee={emp.id}&date={current_date.isoformat()}"
                    except Exception:
                        change_url = None
                    list_url = None
            else:
                # Compute status & late
                manual_statuses = ["On Leave", "Holiday", "Off Day"]
                stored_status = getattr(record, "status", None)

                try:
                    computed_late = record._compute_late_duration(active_shift)
                except Exception:
                    computed_late = None

                try:
                    computed_status = record.compute_status()
                except Exception:
                    computed_status = stored_status or "Pending"

                if stored_status in manual_statuses and stored_status:
                    display_status = stored_status
                else:
                    display_status = computed_status or stored_status or "Pending"

                icon = ICON_MAP.get(display_status, "icons/pendings.png")

                try:
                    change_url = reverse(
                        "admin:attendance_attendancerecord_change",
                        args=(record.pk,),
                    )
                except Exception:
                    change_url = None
                list_url = None

                try:
                    is_late = record.is_late_indicator()
                except Exception:
                    is_late = False

                late_display = None
                if computed_late:
                    try:
                        total = int(computed_late.total_seconds())
                        hours, rem = divmod(total, 3600)
                        minutes, seconds = divmod(rem, 60)
                        late_display = (
                            f"{hours:d}:{minutes:02d}:{seconds:02d}"
                            if hours
                            else f"{minutes:d}:{seconds:02d}"
                        )
                    except Exception:
                        late_display = None

        # update totals - count late indicators separately
        if display_status == "Present":
            totals["Present"] += 1
        elif display_status == "On Leave":
            totals["On_Leave"] += 1
        elif display_status == "Holiday":
            totals["Holiday"] += 1
        elif display_status == "Absent":
            totals["Absent"] += 1
        elif display_status == "Half Day":
            totals["Half_Day"] += 1
        elif display_status == "Early Leave":
            totals["Early_Leave"] += 1
        
        # Count late indicators (separate from status)
        if is_late:
            totals["Late"] += 1

        statuses.append(
            {
                "day": day_num,
                "status": display_status,
                "icon": icon,
                "change_url": change_url,
                "list_url": list_url,
                "is_late": is_late,
                "late_display": late_display,
            }
        )

    return statuses, totals, emp_image_url