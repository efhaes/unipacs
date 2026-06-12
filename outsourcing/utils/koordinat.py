"""
Utility untuk handle koordinat secara consistent.
Dipakai di form, API, template filter, JavaScript context.
"""

from decimal import Decimal, ROUND_HALF_UP
from outsourcing.constants import KOORDINAT_DECIMAL_PLACES


class KoordinatHelper:
    """Handle koordinat dengan precision & locale awareness."""
    
    DECIMAL_PLACES = KOORDINAT_DECIMAL_PLACES
    
    @staticmethod
    def normalize(value):
        """
        Convert any koordinat value ke Decimal dengan presisi konsisten.
        
        - Handle string dengan koma (locale ID)
        - Quantize ke DECIMAL_PLACES
        - Return Decimal, safe untuk model/DB
        
        Usage:
            KoordinatHelper.normalize('-6.208763456')  # → Decimal('-6.208763')
            KoordinatHelper.normalize(-6.208763456)    # → Decimal('-6.208763')
        """
        if isinstance(value, Decimal):
            return value
        
        # String dengan koma → titik
        if isinstance(value, str):
            value = value.replace(',', '.')
        
        try:
            decimal_val = Decimal(str(float(value)))
        except (TypeError, ValueError):
            raise ValueError(f'Invalid koordinat value: {value}')
        
        # Quantize ke precision model
        # ⚠️ Use KoordinatHelper.DECIMAL_PLACES (not self) untuk static method
        quantized = decimal_val.quantize(
            Decimal(10) ** -KoordinatHelper.DECIMAL_PLACES,
            rounding=ROUND_HALF_UP
        )
        return quantized
    
    @staticmethod
    def format_for_js(value):
        """
        Format untuk JavaScript safety (input HTML, JSON, dll).
        
        - Remove trailing zeros
        - Always use dot notation
        - Return empty string jika None
        
        Usage:
            KoordinatHelper.format_for_js(Decimal('-6.2087634'))  # → '-6.208763'
            KoordinatHelper.format_for_js(None)                   # → ''
        """
        if value is None or str(value).strip() == '':
            return ''
        
        try:
            float_val = float(value)
            # ⚠️ Use KoordinatHelper.DECIMAL_PLACES (not self) untuk static method
            formatted = f'{float_val:.{KoordinatHelper.DECIMAL_PLACES}f}'
            # Remove trailing zeros: '106.0000000' → '106'
            return formatted.rstrip('0').rstrip('.')
        except (TypeError, ValueError):
            return ''
    
    @staticmethod
    def to_json_safe(latitude, longitude):
        """
        Convert model Decimal coordinates ke JSON-safe format.
        Used di API responses, template context, AJAX.
        """
        return {
            'latitude': float(latitude),
            'longitude': float(longitude),
            'latitude_display': KoordinatHelper.format_for_js(latitude),
            'longitude_display': KoordinatHelper.format_for_js(longitude),
        }