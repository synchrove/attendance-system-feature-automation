# <your_app>/templatetags/list_utils.py
from django import template

register = template.Library()


@register.filter
def get_index(value, arg):
    """
    Return the item at index 'arg' from the sequence 'value'.
    Returns None if out of range or on error.
    Usage in template: {{ mylist|get_index:forloop.counter0 }}
    """
    try:
        idx = int(arg)
    except (ValueError, TypeError):
        return None
    try:
        return value[idx]
    except Exception:
        return None
