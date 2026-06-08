from django import forms
from outsourcing.models import QRAbsensi, Absensi,IzinStaff, TipeIzinChoices,LokasiAbsensi


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
    class Meta:
        model  = LokasiAbsensi
        fields = ['nama', 'latitude', 'longitude', 'radius_meter', 'is_active']
        widgets = {
            'nama': forms.TextInput(attrs={
                'class'      : 'form-control',
                'placeholder': 'Contoh: Kantor Pusat, Gudang A…',
            }),
            'latitude': forms.NumberInput(attrs={
                'class'      : 'form-control',
                'placeholder': '-6.2088',
                'step'       : 'any',
            }),
            'longitude': forms.NumberInput(attrs={
                'class'      : 'form-control',
                'placeholder': '106.8456',
                'step'       : 'any',
            }),
            'radius_meter': forms.NumberInput(attrs={
                'class': 'form-control',
                'min'  : '10',
                'max'  : '5000',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'nama'        : 'Nama Lokasi',
            'latitude'    : 'Latitude',
            'longitude'   : 'Longitude',
            'radius_meter': 'Radius (meter)',
            'is_active'   : 'Aktif',
        }

    def clean_radius_meter(self):
        radius = self.cleaned_data.get('radius_meter')
        if radius is not None and (radius < 10 or radius > 5000):
            raise forms.ValidationError('Radius harus antara 10 hingga 5000 meter.')
        return radius

    def clean(self):
        cleaned = super().clean()
        lat = cleaned.get('latitude')
        lon = cleaned.get('longitude')
        if lat is not None and not (-90 <= float(lat) <= 90):
            self.add_error('latitude', 'Latitude harus antara -90 dan 90.')
        if lon is not None and not (-180 <= float(lon) <= 180):
            self.add_error('longitude', 'Longitude harus antara -180 dan 180.')
        return cleaned