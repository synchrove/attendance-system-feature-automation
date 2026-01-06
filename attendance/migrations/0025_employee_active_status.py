# Generated migration for employee active status fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0024_delete_governmentholiday_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='is_active',
            field=models.BooleanField(default=True, help_text='Whether employee is currently active in the company'),
        ),
        migrations.AddField(
            model_name='employee',
            name='date_inactive',
            field=models.DateField(blank=True, help_text='Date when employee was made inactive (left company)', null=True),
        ),
        migrations.AddField(
            model_name='employee',
            name='hire_date',
            field=models.DateField(blank=True, help_text='Date when employee was hired', null=True),
        ),
        migrations.AddField(
            model_name='employee',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='employee',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]