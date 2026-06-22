"""
forms/absensi.py
================
Form layer untuk modul Absensi.
Match 100% dengan model final (QR Permanen, JadwalKerja, KeteranganAbsensi).

Model yang di-cover:
  - QRAbsensi          (permanen, unique_together supervisor+tipe)
  - LokasiAbsensi      (create/edit)
  - AbsenMasukForm     (staff scan masuk)
  - AbsenPulangForm    (staff scan pulang)
  - KeteranganAbsensi  (alasan terlambat / pulang cepat / luar jadwal)
  - IzinStaff          (pengajuan izin)
  - JadwalKerja        (konfigurasi jadwal supervisor)
"""

from django import forms
from django.core.exceptions import ValidationError

from outsourcing.models import (
    QRAbsensi, QRTypeChoices,
    Absensi,
    IzinStaff, TipeIzinChoices,
    LokasiAbsensi,
    KeteranganAbsensi, TipeKeteranganChoices,
    JadwalKerja,
)
from outsourcing.constants import (
    LATITUDE_MIN, LATITUDE_MAX,
    LONGITUDE_MIN, LONGITUDE_MAX,
    RADIUS_MIN, RADIUS_MAX,
    KOORDINAT_DECIMAL_PLACES,
)
from outsourcing.utils.koordinat import KoordinatHelper


# ============================================================
# QR Absensi — Create / Edit (Supervisor)
# ============================================================

class QRAbsensiForm(forms.ModelForm):
    """
    Form buat/edit QR Absensi permanen.

    - supervisor & token di-inject dari view (commit=False), tidak ditampilkan.
    - 1 supervisor hanya boleh punya 1 QR per tipe (unique_together dijaga
      di model, tapi kita validasi lebih awal di clean() agar pesan error
      lebih ramah pengguna).
    - lokasi bersifat opsional sesuai help_text model.
    """

    class Meta:
        model  = QRAbsensi
        fields = ['lokasi', 'tipe', 'is_active']
        labels = {
            'lokasi'   : 'Lokasi Absensi',
            'tipe'     : 'Tipe QR',
            'is_active': 'Aktif',
        }
        widgets = {
            'tipe'     : forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'lokasi': 'Biarkan kosong jika absensi tidak perlu validasi GPS.',
        }

    def __init__(self, *args, supervisor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._supervisor = supervisor

        # Filter lokasi hanya milik supervisor yang sedang login
        if supervisor:
            self.fields['lokasi'].queryset = LokasiAbsensi.objects.filter(
                supervisor=supervisor,
                is_active=True,
            ).order_by('nama')
        else:
            self.fields['lokasi'].queryset = LokasiAbsensi.objects.none()

        self.fields['lokasi'].required = False
        self.fields['lokasi'].empty_label = '— Tanpa validasi lokasi —'

    def clean_tipe(self):
        tipe = self.cleaned_data.get('tipe')
        supervisor = self._supervisor

        if supervisor and tipe:
            qs = QRAbsensi.objects.filter(supervisor=supervisor, tipe=tipe)
            # Saat edit, exclude diri sendiri
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                label = dict(QRTypeChoices.choices).get(tipe, tipe)
                raise forms.ValidationError(
                    f'QR {label} untuk supervisor ini sudah ada. '
                    f'Edit atau nonaktifkan QR yang ada.'
                )
        return tipe


# ============================================================
# Absen Masuk — Staff Scan QR Masuk
# ============================================================

class AbsenMasukForm(forms.ModelForm):
    """
    Diisi otomatis dari view:
      - staff, tanggal, qr_masuk, status
    Staff hanya mengirim koordinat GPS (hidden field dari JS).

    Alasan terlambat (jika berlaku) ditangani terpisah via KeteranganAbsensiForm.
    """
    lat_masuk = forms.DecimalField(
        widget=forms.HiddenInput(),
        required=False,
        max_digits=9,
        decimal_places=6,
    )
    lon_masuk = forms.DecimalField(
        widget=forms.HiddenInput(),
        required=False,
        max_digits=9,
        decimal_places=6,
    )

    class Meta:
        model  = Absensi
        fields = ['lat_masuk', 'lon_masuk']


# ============================================================
# Absen Pulang — Staff Scan QR Pulang
# ============================================================

class AbsenPulangForm(forms.ModelForm):
    """
    Diisi otomatis dari view:
      - waktu_pulang, qr_pulang, status, is_overtime
    Staff hanya mengirim koordinat GPS (hidden field dari JS).

    Alasan pulang cepat (jika berlaku) ditangani terpisah via KeteranganAbsensiForm.
    """
    lat_pulang = forms.DecimalField(
        widget=forms.HiddenInput(),
        required=False,
        max_digits=9,
        decimal_places=6,
    )
    lon_pulang = forms.DecimalField(
        widget=forms.HiddenInput(),
        required=False,
        max_digits=9,
        decimal_places=6,
    )

    class Meta:
        model  = Absensi
        fields = ['lat_pulang', 'lon_pulang']


# ============================================================
# Keterangan Absensi — Popup Alasan
# ============================================================

class KeteranganAbsensiForm(forms.ModelForm):
    """
    Muncul sebagai popup saat:
      - Staff terlambat masuk       → tipe=TERLAMBAT
      - Staff pulang lebih awal     → tipe=PULANG_CEPAT
      - Staff scan di luar jadwal   → tipe=DI_LUAR_JADWAL

    Field 'tipe' dan 'selisih_menit' diisi dari view (hidden),
    bukan dipilih staff.
    """
    alasan = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows'       : 3,
            'placeholder': 'Jelaskan alasanmu...',
            'class'      : 'form-control',
        }),
        label='Alasan',
    )
    tipe = forms.ChoiceField(
        choices=TipeKeteranganChoices.choices,
        widget=forms.HiddenInput(),
    )
    selisih_menit = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=False,
        initial=0,
    )

    class Meta:
        model  = KeteranganAbsensi
        fields = ['tipe', 'alasan', 'selisih_menit']

    def clean_alasan(self):
        alasan = self.cleaned_data.get('alasan', '').strip()
        if not alasan:
            raise forms.ValidationError('Alasan wajib diisi.')
        if len(alasan) < 10:
            raise forms.ValidationError('Alasan terlalu singkat (minimal 10 karakter).')
        return alasan


# ============================================================
# Review Keterangan — Supervisor Approve / Reject
# ============================================================

class ReviewKeteranganForm(forms.Form):
    """
    Form sederhana untuk supervisor review KeteranganAbsensi.
    Dipakai di view AJAX maupun normal POST.
    """
    ACTION_CHOICES = [
        ('approved', 'Setujui'),
        ('rejected', 'Tolak'),
    ]
    action          = forms.ChoiceField(choices=ACTION_CHOICES)
    catatan_supervisor = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        label='Catatan (opsional)',
    )

    def clean_action(self):
        action = self.cleaned_data.get('action')
        if action not in ('approved', 'rejected'):
            raise forms.ValidationError('Pilihan tidak valid.')
        return action


# ============================================================
# Izin Staff
# ============================================================

class IzinStaffForm(forms.ModelForm):
    class Meta:
        model  = IzinStaff
        fields = ['tipe', 'tanggal_mulai', 'tanggal_selesai', 'keterangan', 'lampiran']
        widgets = {
            'tipe'           : forms.Select(attrs={'class': 'form-select'}),
            'tanggal_mulai'  : forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'tanggal_selesai': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'keterangan'     : forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def clean(self):
        cleaned         = super().clean()
        tipe            = cleaned.get('tipe')
        tanggal_mulai   = cleaned.get('tanggal_mulai')
        tanggal_selesai = cleaned.get('tanggal_selesai')
        lampiran        = cleaned.get('lampiran')

        if tanggal_mulai and tanggal_selesai:
            if tanggal_selesai < tanggal_mulai:
                raise forms.ValidationError(
                    'Tanggal selesai tidak boleh sebelum tanggal mulai.'
                )

        if tipe == TipeIzinChoices.SAKIT and not lampiran:
            raise forms.ValidationError(
                'Surat dokter wajib dilampirkan untuk izin sakit.'
            )

        return cleaned


# ============================================================
# Lokasi Absensi
# ============================================================

class LokasiAbsensiForm(forms.ModelForm):
    """Form dengan validasi koordinat centralized via KoordinatHelper."""

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
            'radius_meter': f'Radius (meter, {RADIUS_MIN}–{RADIUS_MAX})',
            'is_active'   : 'Aktif',
        }

    def __init__(self, *args, supervisor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._supervisor = supervisor

    def clean_nama(self):
        nama = self.cleaned_data.get('nama', '').strip()
        if not nama:
            raise forms.ValidationError('Nama lokasi wajib diisi.')

        supervisor = self._supervisor
        if supervisor:
            qs = LokasiAbsensi.objects.filter(
                supervisor=supervisor,
                nama__iexact=nama,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f'Lokasi "{nama}" sudah ada untuk supervisor ini.'
                )
        return nama

    def clean_latitude(self):
        val = self.cleaned_data.get('latitude')
        if val is None or str(val).strip() == '':
            raise forms.ValidationError('Latitude wajib diisi.')
        try:
            normalized = KoordinatHelper.normalize(val)
        except ValueError:
            raise forms.ValidationError('Latitude harus berupa angka desimal.')
        if not (LATITUDE_MIN <= float(normalized) <= LATITUDE_MAX):
            raise forms.ValidationError(
                f'Latitude harus antara {LATITUDE_MIN} dan {LATITUDE_MAX}.'
            )
        return normalized

    def clean_longitude(self):
        val = self.cleaned_data.get('longitude')
        if val is None or str(val).strip() == '':
            raise forms.ValidationError('Longitude wajib diisi.')
        try:
            normalized = KoordinatHelper.normalize(val)
        except ValueError:
            raise forms.ValidationError('Longitude harus berupa angka desimal.')
        if not (LONGITUDE_MIN <= float(normalized) <= LONGITUDE_MAX):
            raise forms.ValidationError(
                f'Longitude harus antara {LONGITUDE_MIN} dan {LONGITUDE_MAX}.'
            )
        return normalized

    def clean_radius_meter(self):
        radius = self.cleaned_data.get('radius_meter')
        if radius is None:
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


# ============================================================
# Jadwal Kerja (Supervisor konfigurasi per hari)
# ============================================================

class JadwalKerjaForm(forms.ModelForm):
    """
    Supervisor mengatur jam masuk/pulang per hari.
    supervisor di-inject dari view.
    """

    class Meta:
        model  = JadwalKerja
        fields = ['hari', 'jam_masuk', 'jam_pulang', 'is_active']
        widgets = {
            'hari'      : forms.Select(attrs={'class': 'form-select'}),
            'jam_masuk' : forms.TimeInput(
                attrs={'type': 'time', 'class': 'form-control'},
                format='%H:%M',
            ),
            'jam_pulang': forms.TimeInput(
                attrs={'type': 'time', 'class': 'form-control'},
                format='%H:%M',
            ),
            'is_active' : forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'hari'      : 'Hari',
            'jam_masuk' : 'Jam Masuk',
            'jam_pulang': 'Jam Pulang',
            'is_active' : 'Aktif',
        }

    def __init__(self, *args, supervisor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._supervisor = supervisor

    def clean(self):
        cleaned     = super().clean()
        jam_masuk   = cleaned.get('jam_masuk')
        jam_pulang  = cleaned.get('jam_pulang')
        hari        = cleaned.get('hari')
        supervisor  = self._supervisor

        if jam_masuk and jam_pulang:
            if jam_pulang <= jam_masuk:
                raise forms.ValidationError('Jam pulang harus setelah jam masuk.')

        # Cek duplikat hari per supervisor
        if supervisor and hari is not None:
            qs = JadwalKerja.objects.filter(supervisor=supervisor, hari=hari)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                from outsourcing.models import HariChoices
                nama_hari = dict(HariChoices.choices).get(hari, str(hari))
                raise forms.ValidationError(
                    f'Jadwal untuk hari {nama_hari} sudah ada. Edit jadwal yang ada.'
                )

        return cleaned