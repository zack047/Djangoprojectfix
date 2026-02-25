from django import template
from ..models import StudentInterest

register = template.Library()

@register.filter
def interest_label(value):
    """Convert interest key -> human-readable label"""
    choices = dict(StudentInterest.INTEREST_CHOICES)
    return choices.get(value, value)
