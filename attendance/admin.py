# Django admin framework imports
from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.forms.widgets import SplitDateTimeWidget
import pytz

# Local model imports
from .models import (
    Employee, AttendanceRecord, DashboardStub, Shift, 
    SalaryAdjustment, SalaryReportStub, BulkHoliday, HolidayManagementStub
)

# Timezone configuration
dhaka = pytz.timezone("Asia/Dhaka")

# Admin site branding
admin.site.site_header = "BaraBDOnline.XYZ"
admin.site.site_title = "barabdonline.xyz"
admin.site.index_title = "Welcome to barabdonline.xyz attendance Dashboard"


class AttendanceRecordForm(forms.ModelForm):
    """Custom form for attendance records with enhanced datetime widgets"""
    class Meta:
        model = AttendanceRecord
        fields = "__all__"
        widgets = {
            # Split datetime widgets for better UX
            "checkin_time": SplitDateTimeWidget(
                date_attrs={"type": "date"}, time_attrs={"type": "time"}
            ),
            "checkout_time": SplitDateTimeWidget(
                date_attrs={"type": "date"}, time_attrs={"type": "time"}
            ),
        }


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    """Enhanced admin interface for attendance records with image previews"""
    form = AttendanceRecordForm
    list_display = (
        "employee",
        "date",
        "formatted_checkin_time",
        "formatted_checkout_time",
        "status",
        "formatted_late_duration",
        "device_id",  # NEW
        "checkin_image_preview",
        "checkout_image_preview",
    )
    list_filter = ("date", "status", "employee__department")
    search_fields = ("employee__employee_id", "employee__name", "device_id")
    readonly_fields = ("late_duration",)
    actions = ['remove_checkout']
    
    def remove_checkout(self, request, queryset):
        """Remove checkout time and image for selected records"""
        import os
        updated = 0
        for record in queryset:
            if record.checkout_time or record.checkout_image:
                # Remove checkout image file
                if record.checkout_image:
                    try:
                        if os.path.exists(record.checkout_image.path):
                            os.remove(record.checkout_image.path)
                    except:
                        pass
                    record.checkout_image = None
                
                # Remove checkout time
                record.checkout_time = None
                record.save()
                updated += 1
        
        self.message_user(request, f"Removed checkout for {updated} records.")
    
    remove_checkout.short_description = "Remove checkout time and image"

    def formatted_checkin_time(self, obj):
        """Display checkin time in dd/mm/yyyy format with Dhaka timezone"""
        if obj.checkin_time:
            return obj.checkin_time.astimezone(dhaka).strftime("%d/%m/%Y %I:%M %p")
        return "—"

    formatted_checkin_time.short_description = "Check-In Time"

    def formatted_checkout_time(self, obj):
        """Display checkout time in dd/mm/yyyy format with Dhaka timezone"""
        if obj.checkout_time:
            return obj.checkout_time.astimezone(dhaka).strftime("%d/%m/%Y %I:%M %p")
        return "—"

    formatted_checkout_time.short_description = "Check-Out Time"

    def formatted_late_duration(self, obj):
        """Display late duration in human-readable format (H:M:S or M:S)"""
        if obj.late_duration:
            total = int(obj.late_duration.total_seconds())
            hours, rem = divmod(total, 3600)
            minutes, seconds = divmod(rem, 60)
            if hours:
                return f"{hours:d}:{minutes:02d}:{seconds:02d}"
            return f"{minutes:d}:{seconds:02d}"
        return "—"

    formatted_late_duration.short_description = "Late (m:s)"

    def checkin_image_preview(self, obj):
        """Display thumbnail preview of checkin image"""
        if obj.checkin_image:
            return format_html(
                '<img src="{}" width="60" height="60" style="object-fit:cover;border-radius:5px;" />',
                obj.checkin_image.url,
            )
        return "—"

    checkin_image_preview.short_description = "Check-In Image"

    def checkout_image_preview(self, obj):
        """Display thumbnail preview of checkout image"""
        if obj.checkout_image:
            return format_html(
                '<img src="{}" width="60" height="60" style="object-fit:cover;border-radius:5px;" />',
                obj.checkout_image.url,
            )
        return "—"

    checkout_image_preview.short_description = "Check-Out Image"


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    """Employee admin with photo preview, face recognition support, and import/export"""
    list_display = (
        "employee_image_tag",
        "employee_id",
        "name",
        "department",
        "designation",
        "monthly_salary",
        "is_active",
        "face_encoding_status",
    )
    search_fields = ("employee_id", "name", "department", "email")
    list_filter = ("is_active", "department", "designation")
    list_display_links = ("employee_id",)
    list_editable = ("is_active",)
    
    def changelist_view(self, request, extra_context=None):
        """Enhanced changelist with import/export functionality"""
        # Handle export
        if request.GET.get('export'):
            from .utils.import_helpers import export_employees
            return export_employees(request)
        
        # Handle import
        if request.method == 'POST' and request.FILES.get('import_file'):
            from .utils.import_helpers import import_employees
            import_errors, import_success = import_employees(request)
            
            if import_errors:
                from django.contrib import messages
                for error in import_errors:
                    messages.error(request, error)
            
            if import_success:
                from django.contrib import messages
                messages.success(request, f"Import successful! Created: {import_success['created']}, Updated: {import_success['updated']}")
        
        # Add import/export context
        if extra_context is None:
            extra_context = {}
        from .utils.import_helpers import HAS_OPENPYXL
        extra_context.update({
            'has_openpyxl': HAS_OPENPYXL,
            'show_import_export': True,
        })
        
        return super().changelist_view(request, extra_context)

    def employee_image_tag(self, obj):
        """Display circular employee photo thumbnail with fallback"""
        if obj.employee_image and hasattr(obj.employee_image, "url"):
            url = obj.employee_image.url
        else:
            url = "/static/icons/default-avatar.png"
        return format_html(
            '<img src="{}" style="width:40px;height:40px;object-fit:cover;border-radius:50%;border:1px solid #ddd;" alt="{}" />',
            url,
            obj.name,
        )

    employee_image_tag.short_description = ""
    
    def face_encoding_status(self, obj):
        """Display face encoding registration status"""
        if obj.face_encoding:
            return format_html('<span style="color:green;">✓ Registered</span>')
        return format_html('<span style="color:red;">✗ Not Registered</span>')
    
    face_encoding_status.short_description = "Face Recognition"


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    """Shift configuration admin with inline editing"""
    list_display = (
        "name",
        "shift_start",
        "shift_end",
        "present_hours",
        "half_day_hours",
        "allowed_late_minutes",
        "enable_late_status",
        "is_active",
    )
    list_editable = ("is_active",)
    search_fields = ("name",)


@admin.register(SalaryAdjustment)
class SalaryAdjustmentAdmin(admin.ModelAdmin):
    """Salary adjustment admin with automatic/manual distinction"""
    list_display = (
        "employee",
        "adjustment_type",
        "amount",
        "reason",
        "month",
        "date_created",
        "is_automatic",
    )
    list_filter = ("adjustment_type", "is_automatic", "date_created", "month", "employee__department")
    search_fields = ("employee__name", "employee__employee_id", "reason")
    readonly_fields = ("date_created",)
    fields = ("employee", "adjustment_type", "amount", "reason", "month", "comments", "is_automatic")
    
    def get_form(self, request, obj=None, **kwargs):
        """Customize form with intelligent defaults"""
        form = super().get_form(request, obj, **kwargs)
        # Set default month to current month for new records
        if not obj:
            from datetime import date
            form.base_fields['month'].initial = date.today().replace(day=1)
            form.base_fields['is_automatic'].initial = False
        return form


@admin.register(DashboardStub)
class DashboardStubAdmin(admin.ModelAdmin):
    """Redirect admin to custom dashboard view"""
    def changelist_view(self, request, extra_context=None):
        """Override changelist to show custom dashboard"""
        from attendance.views import attendance_dashboard_view
        return attendance_dashboard_view(request)


@admin.register(SalaryReportStub)
class SalaryReportStubAdmin(admin.ModelAdmin):
    """Redirect admin to custom salary report view"""
    def changelist_view(self, request, extra_context=None):
        """Override changelist to show custom salary report"""
        from attendance.views import salary_report_view
        return salary_report_view(request)


@admin.register(BulkHoliday)
class BulkHolidayAdmin(admin.ModelAdmin):
    """Holiday management admin with bulk operations"""
    list_display = (
        "name",
        "start_date",
        "end_date",
        "scope",
        "is_active",
        "is_government",
        "created_at",
    )
    list_filter = ("scope", "is_active", "is_government", "created_at")
    search_fields = ("name", "department", "designation")
    filter_horizontal = ("selected_employees",)
    readonly_fields = ("created_at", "created_by")
    list_editable = ("is_active",)
    
    def delete_model(self, request, obj):
        """Custom delete to trigger attendance record cleanup"""
        obj.delete()
    
    def delete_queryset(self, request, queryset):
        """Custom bulk delete to trigger attendance record cleanup"""
        for obj in queryset:
            obj.delete()


@admin.register(HolidayManagementStub)
class HolidayManagementStubAdmin(admin.ModelAdmin):
    """Redirect admin to custom holiday management view"""
    def changelist_view(self, request, extra_context=None):
        """Override changelist to show custom holiday management"""
        from attendance.views import holiday_management_view
        return holiday_management_view(request)






