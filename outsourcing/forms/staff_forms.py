from django import forms
from django.utils import timezone
from datetime import date
from outsourcing.models import ItemKegiatan, LaporanKegiatan,FotoItemKegiatan


class ItemKegiatanStaffForm(forms.ModelForm):
    """
    Form khusus Staff untuk mengisi progress pekerjaan.
    Jam mulai & jam selesai diisi via modal AJAX di halaman list.
    Form ini hanya untuk: foto on progress, foto after, catatan.
    """
    class Meta:
        model  = ItemKegiatan
        fields = [
            # 'jam_mulai' dan 'jam_selesai' DIHAPUS
            # karena sudah diisi via modal AJAX di list.html
            'foto_on_progress',
            'foto_after',
            'catatan_staff',
        ]
        widgets = {
            # widget jam_mulai & jam_selesai DIHAPUS
            'catatan_staff': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            # label jam_mulai & jam_selesai DIHAPUS
            'foto_on_progress': 'Foto On Progress',
            'foto_after'      : 'Foto Setelah Selesai',
            'catatan_staff'   : 'Catatan',
        }

    def clean(self):
        cleaned_data     = super().clean()
        foto_on_progress = cleaned_data.get('foto_on_progress')
        foto_after       = cleaned_data.get('foto_after')

        # Validasi jam dihapus karena jam diisi di step sebelumnya (modal AJAX)
        # Validasi foto_after vs jam_selesai ditangani di views.py
        # karena form tidak punya akses ke instance.jam_selesai secara langsung

        return cleaned_data


from django import forms
from django.utils import timezone

from outsourcing.models import ItemKegiatan, LaporanKegiatan


# ============================================================
# FORM 1 — Staff mengisi progress item yang sudah dijadwalkan
# ============================================================

class ItemKegiatanStaffForm(forms.ModelForm):
    """
    Form khusus Staff untuk mengisi progress pekerjaan.
    Jam mulai & jam selesai diisi via modal AJAX di halaman list.
    Form ini hanya untuk: foto on progress, foto after, catatan.
    """
    class Meta:
        model  = ItemKegiatan
        fields = [
            'foto_on_progress',
            'foto_after',
            'catatan_staff',
        ]
        widgets = {
            'catatan_staff': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'foto_on_progress': 'Foto On Progress',
            'foto_after'      : 'Foto Setelah Selesai',
            'catatan_staff'   : 'Catatan',
        }

    def clean(self):
        cleaned_data = super().clean()
        # Validasi foto_after vs jam_selesai ditangani di views.py
        return cleaned_data


# ============================================================
# FORM 2 — Staff membuat item insidental (di luar jadwal)
# ============================================================
class ItemKegiatanInsidentalForm(forms.ModelForm):
    """
    Form untuk staff membuat item kegiatan insidental (di luar jadwal).

    Flow:
    1. Staff isi nama, keterangan, tanggal -> simpan
    2. Redirect ke update.html -> isi jam via modal + upload foto

    Batasan:
    - Laporan hanya yang berstatus 'draft' milik supervisor staff ini.
    - task & sub_area sengaja tidak diekspos -- keduanya null untuk insidental.
    - jam & foto TIDAK ada di sini -- diisi di update.html setelah item dibuat.
    - is_insidental diset True secara programatik di view, bukan dari form.
    """

    laporan = forms.ModelChoiceField(
        queryset=LaporanKegiatan.objects.none(),  # di-override di __init__
        label="Laporan",
        empty_label=None,
        widget=forms.HiddenInput(),               # disembunyikan dari staff
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set default tanggal ke hari ini jika belum ada value
        if not self.instance.pk:
            self.fields['tanggal'].initial = date.today()
 
    class Meta:
        model  = ItemKegiatan
        fields = [
            "laporan",
            "nama_item",
            "catatan_staff",
            "tanggal",
        ]
        widgets = {
            "nama_item": forms.TextInput(attrs={
                "class"      : "form-control",
                "placeholder": "Contoh: Bantu packing barang customer",
                "autofocus"  : True,
            }),
            "catatan_staff": forms.Textarea(attrs={
                "class"      : "form-control",
                "rows"       : 3,
                "placeholder": "Ceritakan singkat kenapa pekerjaan ini muncul...",
            }),
            "tanggal": forms.DateInput(attrs={
                "class": "form-control",
                "type" : "date",
            }),
        }
        labels = {
            "nama_item"    : "Nama Kegiatan",
            "catatan_staff": "Keterangan / Alasan",
            "tanggal"      : "Tanggal",
        }
 
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
 
        # Default tanggal ke hari ini
        if not self.initial.get("tanggal"):
            self.initial["tanggal"] = timezone.localdate()
 
        if user is not None:
            from outsourcing.models import StaffSupervisor
 
            supervisor_ids = (
                StaffSupervisor.objects
                .filter(staff=user, is_active=True)
                .values_list("supervisor_id", flat=True)
            )
 
            # Hanya laporan berstatus DRAFT milik supervisor staff ini.
            # Tidak filter per bulan karena tanggal_laporan bisa berbeda
            # dari bulan laporan (misal laporan Maret dibuat di April).
            qs = (
                LaporanKegiatan.objects
                .filter(
                    supervisor_id__in=supervisor_ids,
                    status="draft",
                )
                .select_related("perusahaan", "area")
                .order_by("-tanggal_laporan")
            )
 
            self.fields["laporan"].queryset = qs
 
            # Auto-select laporan draft terbaru
            laporan_terpilih = qs.first()
            if laporan_terpilih:
                self.initial["laporan"] = laporan_terpilih.pk
                self.laporan_otomatis   = laporan_terpilih
            else:
                self.laporan_otomatis = None
 
    """
    Form untuk staff membuat item kegiatan insidental (di luar jadwal).

    Batasan:
    - Laporan hanya yang berstatus 'draft' milik supervisor staff ini.
    - task & sub_area sengaja tidak diekspos — keduanya null untuk insidental.
    - is_insidental diset True secara programatik di view, bukan dari form.
    """

    laporan = forms.ModelChoiceField(
        queryset=LaporanKegiatan.objects.none(),  # di-override di __init__
        label="Laporan",
        empty_label=None,
        widget=forms.HiddenInput(),               # disembunyikan dari staff
        required=True,
    )

    class Meta:
        model  = ItemKegiatan
        fields = [
            "laporan",
            "nama_item",
            "catatan_staff",
            "tanggal",
            "jam_mulai",
            "jam_selesai",
            "foto_on_progress",
            "foto_after",
        ]
        widgets = {
            "nama_item": forms.TextInput(attrs={
                "class"      : "form-control",
                "placeholder": "Contoh: Bantu packing barang customer",
                "autofocus"  : True,
            }),
            "catatan_staff": forms.Textarea(attrs={
                "class"      : "form-control",
                "rows"       : 3,
                "placeholder": "Ceritakan singkat kenapa pekerjaan ini muncul…",
            }),
            "tanggal": forms.DateInput(attrs={
                "class": "form-control",
                "type" : "date",
            }),
            "jam_mulai": forms.TimeInput(attrs={
                "class": "form-control",
                "type" : "time",
            }),
            "jam_selesai": forms.TimeInput(attrs={
                "class": "form-control",
                "type" : "time",
            }),
            "foto_on_progress": forms.ClearableFileInput(attrs={
                "class" : "form-control",
                "accept": "image/*",
            }),
            "foto_after": forms.ClearableFileInput(attrs={
                "class" : "form-control",
                "accept": "image/*",
            }),
        }
        labels = {
            "nama_item"       : "Nama Kegiatan",
            "catatan_staff"   : "Keterangan / Alasan",
            "tanggal"         : "Tanggal",
            "jam_mulai"       : "Jam Mulai",
            "jam_selesai"     : "Jam Selesai",
            "foto_on_progress": "Foto Sedang Berjalan",
            "foto_after"      : "Foto Setelah Selesai",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Default tanggal ke hari ini
        if not self.initial.get("tanggal"):
            self.initial["tanggal"] = timezone.localdate()

        if user is not None:
            from outsourcing.models import StaffSupervisor

            supervisor_ids = (
                StaffSupervisor.objects
                .filter(staff=user, is_active=True)
                .values_list("supervisor_id", flat=True)
            )

            # Hanya laporan berstatus DRAFT milik supervisor staff ini
            # Tidak filter per bulan karena tanggal_laporan bisa berbeda
            # dari bulan laporan yang dimaksud (misal laporan Maret dibuat di April)
            qs = (
                LaporanKegiatan.objects
                .filter(
                    supervisor_id__in=supervisor_ids,
                    status="draft",
                )
                .select_related("perusahaan", "area")
                .order_by("-tanggal_laporan")
            )

            self.fields["laporan"].queryset = qs

            # Auto-select laporan draft terbaru
            laporan_terpilih = qs.first()
            if laporan_terpilih:
                self.initial["laporan"] = laporan_terpilih.pk
                self.laporan_otomatis   = laporan_terpilih
            else:
                self.laporan_otomatis = None

    def clean(self):
        cleaned     = super().clean()
        jam_mulai   = cleaned.get("jam_mulai")
        jam_selesai = cleaned.get("jam_selesai")

        if jam_mulai and jam_selesai and jam_selesai <= jam_mulai:
            self.add_error("jam_selesai", "Jam selesai harus setelah jam mulai.")

        return cleaned

# forms/staff_forms.py



class FotoTambahanForm(forms.ModelForm):
    class Meta:
        model  = FotoItemKegiatan
        fields = ['foto', 'jenis', 'keterangan']
        widgets = {
            'keterangan': forms.TextInput(attrs={
                'placeholder': 'Contoh: Kondisi saluran air sebelah utara...',
                'maxlength'  : 300,
            }),
        }
