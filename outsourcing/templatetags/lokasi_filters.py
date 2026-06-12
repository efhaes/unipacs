from django import template

register = template.Library()


@register.filter
def js_float(value):
    """
    Render nilai desimal aman untuk JavaScript dan input HTML.
    
    - Ganti koma ke titik (handle locale ID)
    - Format dengan presisi 7 desimal (untuk GPS koordinat)
    - Remove trailing zeros dan decimal point jika integer
    - Return string kosong jika value None/kosong
    
    Contoh:
      106.845678901 → '106.8456789'
      106.0 → '106'
      -6.2 → '-6.2'
      None → ''
      '' → ''
    """
    if value is None or str(value).strip() == '':
        return ''
    
    try:
        # Konversi string dengan koma ke format dengan titik
        float_val = float(str(value).replace(',', '.'))
        
        # Format dengan 7 decimal places (standar GPS presisi tinggi)
        formatted = '{:.7f}'.format(float_val)
        
        # Remove trailing zeros dan decimal point jika diperlukan
        # Contoh: '106.0000000' → '106'
        #         '106.1234500' → '106.12345'
        formatted = formatted.rstrip('0').rstrip('.')
        
        return formatted
    except (TypeError, ValueError):
        return ''