from django import forms
from outsourcing.models import QRAbsensi, Absensi,IzinStaff, TipeIzinChoices,LokasiAbsensi
from outsourcing.utils.koordinat import KoordinatHelper
from outsourcing.constants import (
    LATITUDE_MIN, LATITUDE_MAX,
    LONGITUDE_MIN, LONGITUDE_MAX,
    RADIUS_MIN, RADIUS_MAX,
)


class QRAbsensiForm(forms.ModelForm):
    class Meta:
        model  = QRAbsensi
        fields = ['tanggal', 'berlaku_hingga']  # hapus 'laporan'
        widgets = {
            'tanggal'        : forms.DateInput(attrs={'type': 'date'}),
            'berlaku_hingga' : forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class AbsenMasukForm(forms.ModelForm):
    """
    Form untuk Staff absen masuk setelah scan QR.
    Field qr_absensi, staff, laporan, tanggal diisi otomatis dari view.
    """
    lat_masuk = forms.DecimalField(
        widget=forms.HiddenInput(), required=False
    )
    lon_masuk = forms.DecimalField(
        widget=forms.HiddenInput(), required=False
    )

    class Meta:
        model  = Absensi
        fields = ['lat_masuk', 'lon_masuk']


class AbsenPulangForm(forms.ModelForm):
    """
    Form untuk Staff absen pulang.
    """
    lat_pulang = forms.DecimalField(
        widget=forms.HiddenInput(), required=False
    )
    lon_pulang = forms.DecimalField(
        widget=forms.HiddenInput(), required=False
    )

    class Meta:
        model  = Absensi
        fields = [ 'lat_pulang', 'lon_pulang']
        


class IzinStaffForm(forms.ModelForm):
    class Meta:
        model  = IzinStaff
        fields = ['tipe', 'tanggal_mulai', 'tanggal_selesai', 'keterangan', 'lampiran']
        widgets = {
            'tipe'            : forms.Select(),
            'tanggal_mulai'   : forms.DateInput(attrs={'type': 'date'}),
            'tanggal_selesai' : forms.DateInput(attrs={'type': 'date'}),
            'keterangan'      : forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        tipe             = cleaned.get('tipe')
        tanggal_mulai    = cleaned.get('tanggal_mulai')
        tanggal_selesai  = cleaned.get('tanggal_selesai')
        lampiran         = cleaned.get('lampiran')

        if tanggal_mulai and tanggal_selesai:
            if tanggal_selesai < tanggal_mulai:
                raise forms.ValidationError('Tanggal selesai tidak boleh sebelum tanggal mulai.')

        if tipe == TipeIzinChoices.SAKIT and not lampiran:
            raise forms.ValidationError('Surat dokter wajib dilampirkan untuk izin sakit.')

        return cleaned



class LokasiAbsensiForm(forms.ModelForm):
    """Form dengan validasi koordinat yang jelas & centralized."""
    
    class Meta:
        model  = LokasiAbsensi
        fields = ['nama', 'latitude', 'longitude', 'radius_meter', 'is_active']
        widgets = {
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nama'        : 'Nama Lokasi',
            'latitude'    : 'Latitude',
            'longitude'   : 'Longitude',
            'radius_meter': 'Radius (meter)',
            'is_active'   : 'Aktif',
        }
    
    def clean_nama(self):
        nama = self.cleaned_data.get('nama', '').strip()
        if not nama:
            raise forms.ValidationError('Nama lokasi wajib diisi.')
        
        if not self.instance.pk:
            supervisor = getattr(self, '_supervisor', None)
            if supervisor:
                exists = LokasiAbsensi.objects.filter(
                    supervisor=supervisor,
                    nama__iexact=nama
                ).exists()
                if exists:
                    raise forms.ValidationError(
                        f'Lokasi "{nama}" sudah ada untuk supervisor ini.'
                    )
        
        return nama
    
    def clean_latitude(self):
        """Gunakan KoordinatHelper untuk consistency."""
        val = self.cleaned_data.get('latitude')
        if val is None or str(val).strip() == '':
            raise forms.ValidationError('Latitude wajib diisi.')
        
        try:
            normalized = KoordinatHelper.normalize(val)
        except ValueError:
            raise forms.ValidationError('Latitude harus berupa angka desimal.')
        
        latitude_float = float(normalized)
        if not (LATITUDE_MIN <= latitude_float <= LATITUDE_MAX):
            raise forms.ValidationError(
                f'Latitude harus antara {LATITUDE_MIN} dan {LATITUDE_MAX}.'
            )
        
        return normalized
    
    def clean_longitude(self):
        """Gunakan KoordinatHelper untuk consistency."""
        val = self.cleaned_data.get('longitude')
        if val is None or str(val).strip() == '':
            raise forms.ValidationError('Longitude wajib diisi.')
        
        try:
            normalized = KoordinatHelper.normalize(val)
        except ValueError:
            raise forms.ValidationError('Longitude harus berupa angka desimal.')
        
        longitude_float = float(normalized)
        if not (LONGITUDE_MIN <= longitude_float <= LONGITUDE_MAX):
            raise forms.ValidationError(
                f'Longitude harus antara {LONGITUDE_MIN} dan {LONGITUDE_MAX}.'
            )
        
        return normalized
    
    def clean_radius_meter(self):
        radius = self.cleaned_data.get('radius_meter')
        if radius is None or str(radius).strip() == '':
            raise forms.ValidationError('Radius wajib diisi.')
        
        try:
            radius = int(radius)
        except (TypeError, ValueError):
            raise forms.ValidationError('Radius harus berupa angka bulat.')
        
        if not (RADIUS_MIN <= radius <= RADIUS_MAX):
            raise forms.ValidationError(
                f'Radius harus antara {RADIUS_MIN} dan {RADIUS_MAX} meter.'
            )
        
        return radius