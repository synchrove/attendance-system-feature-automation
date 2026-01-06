
from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path(
        "api/face-attendance/",
        views.face_attendance_api,
        name="face_attendance_api",
    ),
    path(
        "employee/<int:employee_id>/",
        views.employee_detail_view,
        name="employee_detail",
    ),
]
