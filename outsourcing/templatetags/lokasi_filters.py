from django import template
from outsourcing.utils.koordinat import KoordinatHelper

register = template.Library()

@register.filter
def js_float(value):
    """Render koordinat safe untuk JavaScript."""
    return KoordinatHelper.format_for_js(value)