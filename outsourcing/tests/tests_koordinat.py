from decimal import Decimal
from django.test import TestCase
from outsourcing.utils.koordinat import KoordinatHelper
from outsourcing.constants import KOORDINAT_DECIMAL_PLACES


class KoordinatHelperTestCase(TestCase):
    
    def test_normalize_float(self):
        """Test normalize dengan float dari GPS."""
        result = KoordinatHelper.normalize(-6.208763400000001)
        expected = Decimal('-6.208763')
        self.assertEqual(result, expected)
    
    def test_normalize_string_with_comma(self):
        """Test normalize dengan string koma (locale ID)."""
        result = KoordinatHelper.normalize('-6,208763')
        expected = Decimal('-6.208763')
        self.assertEqual(result, expected)
    
    def test_normalize_decimal(self):
        """Test normalize dengan Decimal yang sudah valid."""
        result = KoordinatHelper.normalize(Decimal('-6.208763'))
        expected = Decimal('-6.208763')
        self.assertEqual(result, expected)
    
    def test_format_for_js(self):
        """Test format untuk JavaScript."""
        # Trailing zeros removed
        self.assertEqual(KoordinatHelper.format_for_js(Decimal('-6.200000')), '-6.2')
        # Integer
        self.assertEqual(KoordinatHelper.format_for_js(Decimal('106.000000')), '106')
        # None
        self.assertEqual(KoordinatHelper.format_for_js(None), '')
    
    def test_to_json_safe(self):
        """Test JSON serialization."""
        result = KoordinatHelper.to_json_safe(
            Decimal('-6.208763'),
            Decimal('106.845599')
        )
        self.assertEqual(result['latitude'], -6.208763)
        self.assertEqual(result['longitude'], 106.845599)
        self.assertEqual(result['latitude_display'], '-6.208763')