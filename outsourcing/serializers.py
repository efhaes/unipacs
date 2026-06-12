from rest_framework import serializers
from outsourcing.models import LokasiAbsensi
from outsourcing.utils.koordinat import KoordinatHelper


class LokasiAbsensiSerializer(serializers.ModelSerializer):
    # 🔧 Override untuk ensure consistency
    latitude_display = serializers.SerializerMethodField()
    longitude_display = serializers.SerializerMethodField()
    
    class Meta:
        model = LokasiAbsensi
        fields = [
            'id', 'nama', 'latitude', 'longitude',
            'latitude_display', 'longitude_display',
            'radius_meter', 'is_active'
        ]
    
    def get_latitude_display(self, obj):
        return KoordinatHelper.format_for_js(obj.latitude)
    
    def get_longitude_display(self, obj):
        return KoordinatHelper.format_for_js(obj.longitude)
    
    def validate_latitude(self, value):
        normalized = KoordinatHelper.normalize(value)
        return normalized
    
    def validate_longitude(self, value):
        normalized = KoordinatHelper.normalize(value)
        return normalized