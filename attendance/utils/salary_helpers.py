# Python standard library imports
from datetime import date, timedelta
from decimal import Decimal

# Django framework imports
from django.db.models import Count, Q

# Local model imports
from ..models import AttendanceRecord, Employee, SalaryAdjustment


def calculate_monthly_salary_adjustments(employee, year, month):
    """
    Core salary calculation engine with updated business rules.
    
    Updated Rules (v2.0):
    - Fine: Only LATE days count (3+ late days = 1 day salary fine per 3 days)
    - Bonus: 100% Present AND No late days = 1000 BDT bonus
    - Excludes: Holidays and Off Days from calculations
    - Daily salary: monthly_salary / 30 days
    
    Algorithm:
    1. Get all attendance records for the month
    2. Count only late days (not absent/half day)
    3. Check if all working days are 'Present' status
    4. Calculate proportional fines and perfect attendance bonus
    
    Returns: Tuple of (bonus_amount, fine_amount, late_days_count)
    """
    # Get attendance records for the month
    records = AttendanceRecord.objects.filter(
        employee=employee,
        date__year=year,
        date__month=month
    )
    
    # Count problematic days (excluding holidays and off days)
    problematic_days = 0
    total_working_days = 0
    
    for record in records:
        # Skip holidays and off days (these don't affect salary)
        if record.status in ['Holiday', 'Off Day']:
            continue
            
        total_working_days += 1
        
        # Updated rule: Only late days trigger fines (not absent/half day)
        if record.is_late_indicator():
            problematic_days += 1
    
    # Calculate fine (every 3 problematic days = 1 day's salary)
    fine_amount = Decimal('0.00')
    if problematic_days >= 3:
        fine_groups = problematic_days // 3
        daily_salary = employee.monthly_salary / Decimal('30')
        fine_amount = daily_salary * fine_groups
    
    # Calculate bonus: Requires BOTH 100% Present AND zero late days
    bonus_amount = Decimal('0.00')
    all_present = all(record.status == 'Present' for record in records if record.status not in ['Holiday', 'Off Day'])
    if problematic_days == 0 and all_present and total_working_days > 0:
        bonus_amount = Decimal('1000.00')  # Fixed bonus amount
    
    return bonus_amount, fine_amount, problematic_days


def process_monthly_salary_adjustments(year, month):
    """
    Bulk processing engine for automatic salary adjustments.
    
    Scope: ALL employees for specified month
    Rules: Only processes automatic adjustments (is_automatic=True)
    
    Process:
    1. Iterate through all employees
    2. Calculate bonus/fine amounts using core algorithm
    3. Create/update automatic SalaryAdjustment records
    4. Delete adjustments that no longer apply
    5. Preserve manual adjustments (is_automatic=False)
    
    Automatic Adjustments:
    - '100% On Time Bonus': 1000 BDT for perfect attendance
    - 'Attendance Issues Fine': Proportional fine for late days
    
    Returns: Number of adjustments processed
    """
    month_date = date(year, month, 1)
    processed_count = 0
    
    for employee in Employee.objects.all():
        bonus_amount, fine_amount, late_days = calculate_monthly_salary_adjustments(
            employee, year, month
        )
        
        # Handle Perfect Attendance Bonus (100% Present + No Late Days = 1000 BDT)
        perfect_bonus_exists = SalaryAdjustment.objects.filter(
            employee=employee,
            month=month_date,
            reason="100% On Time Bonus",
            adjustment_type='bonus',
            is_automatic=True
        ).first()
        
        if bonus_amount > 0:
            if perfect_bonus_exists:
                # Update existing
                perfect_bonus_exists.amount = bonus_amount
                perfect_bonus_exists.comments = f"100% Present + No Late Days"
                perfect_bonus_exists.save()
            else:
                # Create new
                SalaryAdjustment.objects.create(
                    employee=employee,
                    month=month_date,
                    reason="100% On Time Bonus",
                    adjustment_type='bonus',
                    amount=bonus_amount,
                    is_automatic=True,
                    comments=f"100% Present + No Late Days"
                )
            processed_count += 1
        elif perfect_bonus_exists:
            # Remove bonus if no longer eligible
            perfect_bonus_exists.delete()
            processed_count += 1
        
        # Handle Attendance Issues Fine (3+ late days = 1 day's salary per 3 days)
        attendance_fine_exists = SalaryAdjustment.objects.filter(
            employee=employee,
            month=month_date,
            reason="Attendance Issues Fine",
            adjustment_type='fine',
            is_automatic=True
        ).first()
        
        if fine_amount > 0:
            fine_groups = late_days // 3
            daily_salary = employee.monthly_salary / Decimal('30')
            if attendance_fine_exists:
                # Update existing
                attendance_fine_exists.amount = fine_amount
                attendance_fine_exists.comments = f"{late_days} late days - {fine_groups} fine(s) of {daily_salary:.2f} BDT each"
                attendance_fine_exists.save()
            else:
                # Create new
                SalaryAdjustment.objects.create(
                    employee=employee,
                    month=month_date,
                    reason="Attendance Issues Fine",
                    adjustment_type='fine',
                    amount=fine_amount,
                    is_automatic=True,
                    comments=f"{late_days} late days - {fine_groups} fine(s) of {daily_salary:.2f} BDT each"
                )
            processed_count += 1
        elif attendance_fine_exists:
            # Remove fine if no longer applicable
            attendance_fine_exists.delete()
            processed_count += 1
    
    return processed_count


def get_employee_salary_summary(employee, year, month):
    """
    Comprehensive salary report generator for individual employees.
    
    Features:
    - Combines automatic and manual adjustments
    - Calculates net salary impact
    - Provides detailed breakdown by type
    - Includes working days and late days statistics
    
    Data Sources:
    - Employee.monthly_salary (base salary)
    - SalaryAdjustment records (bonuses and fines)
    - AttendanceRecord analysis (working days, late days)
    
    Returns: Dictionary with complete salary breakdown:
    {
        'base_salary': Monthly salary from employee record
        'total_bonus': Sum of all bonus adjustments
        'total_fine': Sum of all fine adjustments
        'net_adjustment': total_bonus - total_fine
        'late_days': Count of late days (for reference)
        'bonuses': QuerySet of bonus records
        'fines': QuerySet of fine records
        'all_adjustments': All adjustment records
        'working_days': Total working days (excludes holidays/off days)
    }
    """
    month_date = date(year, month, 1)
    
    # Get ALL adjustments for the month (manual + automatic)
    # Include adjustments for ANY day of the month, not just 1st
    adjustments = SalaryAdjustment.objects.filter(
        employee=employee,
        month__year=year,
        month__month=month
    )
    bonuses = adjustments.filter(adjustment_type='bonus')
    fines = adjustments.filter(adjustment_type='fine')
    
    total_bonus = sum(b.amount for b in bonuses)
    total_fine = sum(f.amount for f in fines)
    
    # Calculate problematic days
    _, _, problematic_days = calculate_monthly_salary_adjustments(employee, year, month)
    
    # Use monthly salary as base
    working_days = AttendanceRecord.objects.filter(
        employee=employee,
        date__year=year,
        date__month=month
    ).exclude(
        status__in=['Holiday', 'Off Day', 'On Leave']
    ).count()
    
    base_salary = employee.monthly_salary
    net_adjustment = total_bonus - total_fine
    
    return {
        'base_salary': base_salary,
        'total_bonus': total_bonus,
        'total_fine': total_fine,
        'net_adjustment': net_adjustment,
        'late_days': problematic_days,  # Now represents problematic days
        'bonuses': bonuses,
        'fines': fines,
        'all_adjustments': adjustments,
        'working_days': working_days
    }