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


from django import forms
from outsourcing.models import LokasiAbsensi


class LokasiAbsensiForm(forms.ModelForm):
    """
    Form untuk tambah/edit LokasiAbsensi dengan validasi koordinat dan radius.
    Template menangani rendering, jadi widgets di-minimize.
    """
    class Meta:
        model  = LokasiAbsensi
        fields = ['nama', 'latitude', 'longitude', 'radius_meter', 'is_active']
        widgets = {
            # Minimal widgets — template override sebagian besar rendering
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

    def clean_nama(self):
        """Validasi nama tidak kosong dan tidak duplikat untuk supervisor yang sama."""
        nama = self.cleaned_data.get('nama', '').strip()
        if not nama:
            raise forms.ValidationError('Nama lokasi wajib diisi.')
        
        # Cek duplikat hanya jika tambah (bukan edit)
        if not self.instance.pk:
            supervisor = getattr(self, '_supervisor', None)
            if supervisor:
                exists = LokasiAbsensi.objects.filter(
                    supervisor=supervisor,
                    nama__iexact=nama
                ).exists()
                if exists:
                    raise forms.ValidationError(
                        f'Lokasi dengan nama "{nama}" sudah ada untuk supervisor ini.'
                    )
        
        return nama

    def clean_latitude(self):
        """
        Validasi latitude:
        - Wajib diisi
        - Range -90 hingga 90
        - Handle string dengan koma (locale ID)
        """
        val = self.cleaned_data.get('latitude')
        if val is None or str(val).strip() == '':
            raise forms.ValidationError('Latitude wajib diisi.')
        
        # Handle locale: ganti koma ke titik jika string
        if isinstance(val, str):
            val = val.replace(',', '.')
        
        try:
            val = float(val)
        except (TypeError, ValueError):
            raise forms.ValidationError('Latitude harus berupa angka desimal.')
        
        if not (-90 <= val <= 90):
            raise forms.ValidationError('Latitude harus antara -90 dan 90.')
        
        return val

    def clean_longitude(self):
        """
        Validasi longitude:
        - Wajib diisi
        - Range -180 hingga 180
        - Handle string dengan koma (locale ID)
        """
        val = self.cleaned_data.get('longitude')
        if val is None or str(val).strip() == '':
            raise forms.ValidationError('Longitude wajib diisi.')
        
        if isinstance(val, str):
            val = val.replace(',', '.')
        
        try:
            val = float(val)
        except (TypeError, ValueError):
            raise forms.ValidationError('Longitude harus berupa angka desimal.')
        
        if not (-180 <= val <= 180):
            raise forms.ValidationError('Longitude harus antara -180 dan 180.')
        
        return val

    def clean_radius_meter(self):
        """
        Validasi radius:
        - Wajib diisi
        - Range 10 hingga 1000 meter (sesuai slider client)
        """
        radius = self.cleaned_data.get('radius_meter')
        if radius is None or str(radius).strip() == '':
            raise forms.ValidationError('Radius wajib diisi.')
        
        try:
            radius = int(radius) if isinstance(radius, (int, float, str)) else 0
        except (TypeError, ValueError):
            raise forms.ValidationError('Radius harus berupa angka bulat.')
        
        if not (10 <= radius <= 1000):
            raise forms.ValidationError('Radius harus antara 10 hingga 1000 meter.')
        
        return radius