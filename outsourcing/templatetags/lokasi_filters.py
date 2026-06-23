from django import template
from outsourcing.utils.koordinat import KoordinatHelper

register = template.Library()


@register.filter
def js_float(value):
    """
    Render koordinat Decimal/string/None ke float string
    yang aman untuk dirender langsung di JavaScript.

    Contoh output:
      Decimal('-6.208763000000') → '-6.208763'
      None / ''                 → ''
      'invalid'                 → ''
    """
    if value is None or str(value).strip() == '':
        return ''
    return KoordinatHelper.format_for_js(value)