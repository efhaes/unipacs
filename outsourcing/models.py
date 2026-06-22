from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator, MinValueValidator
import uuid
from django.utils import timezone
import math
from datetime import datetime


class AktifManager(models.Manager):
    """
    Manager untuk memfilter hanya record yang aktif.
    Gunakan: Model.aktif.all()
    Tetap gunakan Model.objects.all() untuk akses penuh (admin, dsb).
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

# ============================================================
# ROLE CHOICES
# ============================================================

class RoleChoices(models.TextChoices):
    ADMIN               = 'admin',               'Admin'
    KEPALA_SUPERVISOR   = 'kepala_supervisor',   'Kepala Supervisor'
    SUPERVISOR          = 'supervisor',           'Supervisor Lapangan'
    STAFF               = 'staff',               'Staff Lapangan'
    CUSTOMER            = 'customer',            'Customer'


class GenderChoices(models.TextChoices):
    LAKI_LAKI = 'l', 'Laki-laki'
    PEREMPUAN = 'p', 'Perempuan'


# ============================================================
# USER (Custom)
# ============================================================

telepon_validator = RegexValidator(
    regex=r'^\+?[0-9]{7,20}$',
    message='Nomor telepon hanya boleh berisi angka, dan opsional diawali dengan +. Panjang 7–20 karakter.',
)


class User(AbstractUser):

    role = models.CharField(
        max_length=30,
        choices=RoleChoices.choices,
        default=RoleChoices.STAFF,
    )
    nama_lengkap = models.CharField(max_length=150, blank=True)

    jenis_kelamin = models.CharField(
        max_length=1,
        choices=GenderChoices.choices,
        blank=True,
        null=True,
    )
    nik = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text='NIK / ID Karyawan (contoh: 202403157)',
    )
    telepon      = models.CharField(
        max_length=20,
        blank=True,
        validators=[telepon_validator],
    )
    foto_profil  = models.ImageField(
        upload_to='foto_profil/',
        blank=True,
        null=True,
    )

    dibuat_pada  = models.DateTimeField(auto_now_add=True)
    diubah_pada  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nama_lengkap or self.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == RoleChoices.ADMIN

    @property
    def is_kepala_supervisor(self):
        return self.role == RoleChoices.KEPALA_SUPERVISOR

    @property
    def is_supervisor(self):
        return self.role == RoleChoices.SUPERVISOR

    @property
    def is_staff_lapangan(self):
        return self.role == RoleChoices.STAFF

    @property
    def is_customer(self):
        return self.role == RoleChoices.CUSTOMER

    class Meta:
        verbose_name        = 'Pengguna'
        verbose_name_plural = 'Pengguna'
        ordering            = ['nama_lengkap']


# ============================================================
# MASTER DATA
# ============================================================

class JenisJasa(models.Model):
    """
    Master data jenis jasa outsourcing.
    Contoh: Cleaning Service, Security, Office Boy, dll.
    Dikelola oleh Admin.
    """
    nama_jasa   = models.CharField(max_length=100, unique=True)
    deskripsi   = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    aktif   = AktifManager()

    def __str__(self):
        return self.nama_jasa

    class Meta:
        verbose_name        = 'Jenis Jasa'
        verbose_name_plural = 'Jenis Jasa'
        ordering            = ['nama_jasa']


class Perusahaan(models.Model):
    """
    Data perusahaan klien yang menggunakan jasa outsourcing.
    Satu perusahaan bisa menggunakan banyak jenis jasa (M2M).
    Satu perusahaan memiliki satu akun Customer.
    """
    nama_perusahaan = models.CharField(max_length=200)
    alamat          = models.TextField()
    telepon         = models.CharField(max_length=20, blank=True)
    email           = models.EmailField(blank=True)
    jenis_jasa      = models.ManyToManyField(
        JenisJasa,
        related_name='perusahaan',
        blank=True,
    )
    customer        = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='perusahaan_customer',
        limit_choices_to={'role': RoleChoices.CUSTOMER},
    )
    foto_perusahaan  = models.ImageField(
        upload_to='foto_perusahaan/',
        blank=True,
        null=True,
    )
    is_active    = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    aktif   = AktifManager()

    def clean(self):
        if self.customer and self.customer.role != RoleChoices.CUSTOMER:
            raise ValidationError(
                f"User '{self.customer}' bukan Customer. "
                f"Role saat ini: {self.customer.get_role_display()}."
            )

    def __str__(self):
        return self.nama_perusahaan

    class Meta:
        verbose_name        = 'Perusahaan'
        verbose_name_plural = 'Perusahaan'
        ordering            = ['nama_perusahaan']


class AreaKerja(models.Model):
    """
    Area kerja di dalam satu perusahaan.
    Contoh: Gedung A, Lantai 2, Area Parkir, dll.
    """
    perusahaan  = models.ForeignKey(
        Perusahaan,
        on_delete=models.CASCADE,
        related_name='area_kerja',
    )
    nama_area   = models.CharField(max_length=150)
    keterangan  = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    aktif   = AktifManager()

    def __str__(self):
        return f"{self.perusahaan.nama_perusahaan} — {self.nama_area}"

    class Meta:
        verbose_name        = 'Area Kerja'
        verbose_name_plural = 'Area Kerja'
        ordering            = ['perusahaan', 'nama_area']
        unique_together     = ['perusahaan', 'nama_area']


class SubArea(models.Model):
    """
    Sub area di dalam AreaKerja.
    Contoh: Toilet Lt.1, Lobby, Ruang Rapat, dll.
    """
    area        = models.ForeignKey(
        AreaKerja,
        on_delete=models.CASCADE,
        related_name='sub_area',
    )
    nama_sub_area = models.CharField(max_length=150)
    keterangan    = models.TextField(blank=True)
    is_active      = models.BooleanField(default=True)
    dibuat_pada   = models.DateTimeField(auto_now_add=True)
    diubah_pada   = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    aktif   = AktifManager()

    def __str__(self):
        return f"{self.area} → {self.nama_sub_area}"

    class Meta:
        verbose_name        = 'Sub Area'
        verbose_name_plural = 'Sub Area'
        ordering            = ['area', 'nama_sub_area']
        unique_together     = ['area', 'nama_sub_area']


class Task(models.Model):
    """
    Master data tugas/pekerjaan standar yang bisa di-assign ke staff.
    Contoh: Menyapu lantai, Membersihkan toilet, dll.
    """
    jenis_jasa  = models.ForeignKey(
        JenisJasa,
        on_delete=models.CASCADE,
        related_name='tasks',
    )
    nama_task   = models.CharField(max_length=200)
    standar = models.CharField(
        max_length=200,
        blank=True,
        help_text='Standar kualitas untuk task ini.',
    )
    deskripsi   = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    aktif   = AktifManager()

    def __str__(self):
        return f"{self.nama_task} ({self.jenis_jasa.nama_jasa})"

    class Meta:
        verbose_name        = 'Task'
        verbose_name_plural = 'Task'
        ordering            = ['jenis_jasa', 'nama_task']
        unique_together     = ['jenis_jasa', 'nama_task']


# ============================================================
# HIERARKI AKUN
# ============================================================

class KepalaSupervisorJasa(models.Model):
    """
    Menghubungkan Kepala Supervisor dengan Jenis Jasa yang dia tangani.
    """
    kepala_supervisor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='jasa_yang_dipegang',
        limit_choices_to={'role': RoleChoices.KEPALA_SUPERVISOR},
    )
    jenis_jasa  = models.ForeignKey(
        JenisJasa,
        on_delete=models.CASCADE,
        related_name='kepala_supervisor',
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.kepala_supervisor} → {self.jenis_jasa}"

    class Meta:
        verbose_name        = 'Kepala Supervisor Jasa'
        verbose_name_plural = 'Kepala Supervisor Jasa'
        unique_together     = ['kepala_supervisor', 'jenis_jasa']


class SupervisorPerusahaan(models.Model):
    """
    Menghubungkan Supervisor Lapangan dengan Perusahaan & Jenis Jasa.
    """
    supervisor        = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='penugasan_supervisor',
        limit_choices_to={'role': RoleChoices.SUPERVISOR},
    )
    perusahaan        = models.ForeignKey(
        Perusahaan,
        on_delete=models.CASCADE,
        related_name='supervisor_perusahaan',
    )
    jenis_jasa        = models.ForeignKey(
        JenisJasa,
        on_delete=models.CASCADE,
        related_name='supervisor_perusahaan',
    )
    kepala_supervisor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supervisor_dibawahnya',
        limit_choices_to={'role': RoleChoices.KEPALA_SUPERVISOR},
    )
    is_active    = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    aktif   = AktifManager()

    def clean(self):
        if self.perusahaan_id and self.jenis_jasa_id:
            if not self.perusahaan.jenis_jasa.filter(pk=self.jenis_jasa_id).exists():
                raise ValidationError(
                    f"Perusahaan '{self.perusahaan}' tidak menggunakan jasa '{self.jenis_jasa}'."
                )

        if self.is_active and self.supervisor_id and self.perusahaan_id and self.jenis_jasa_id:
            qs = SupervisorPerusahaan.objects.filter(
                supervisor=self.supervisor_id,
                perusahaan=self.perusahaan_id,
                jenis_jasa=self.jenis_jasa_id,
                is_active=True,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    f"Supervisor '{self.supervisor}' sudah aktif di perusahaan "
                    f"'{self.perusahaan}' untuk jasa '{self.jenis_jasa}'."
                )

    def __str__(self):
        return f"{self.supervisor} → {self.perusahaan} [{self.jenis_jasa}]"

    class Meta:
        verbose_name        = 'Penugasan Supervisor'
        verbose_name_plural = 'Penugasan Supervisor'
        unique_together     = ['supervisor', 'perusahaan', 'jenis_jasa']


class StaffSupervisor(models.Model):
    """
    Menghubungkan Staff Lapangan dengan Supervisor yang mengelolanya.
    """
    staff       = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='supervisor_saya',
        limit_choices_to={'role': RoleChoices.STAFF},
    )
    supervisor  = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='staff_dibawahnya',
        limit_choices_to={'role': RoleChoices.SUPERVISOR},
    )
    is_active    = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    aktif   = AktifManager()

    def clean(self):
        if self.is_active and self.staff_id:
            qs = StaffSupervisor.objects.filter(
                staff=self.staff_id,
                is_active=True,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                existing = qs.first()
                raise ValidationError(
                    f"Staff '{self.staff}' sudah memiliki supervisor aktif: "
                    f"'{existing.supervisor}'. Nonaktifkan relasi lama sebelum "
                    f"menambahkan supervisor baru."
                )

    def __str__(self):
        return f"{self.staff} → dibawah {self.supervisor}"

    class Meta:
        verbose_name        = 'Staff per Supervisor'
        verbose_name_plural = 'Staff per Supervisor'
        unique_together     = ['staff', 'supervisor']


class StaffTask(models.Model):
    """
    Menghubungkan Staff dengan Task yang bisa dia kerjakan.
    """
    staff       = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tasks_saya',
        limit_choices_to={'role': RoleChoices.STAFF},
    )
    task        = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='staff_yang_bisa',
    )
    is_active    = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    aktif   = AktifManager()

    def __str__(self):
        return f"{self.staff} → {self.task.nama_task}"

    class Meta:
        verbose_name        = 'Staff Task'
        verbose_name_plural = 'Staff Task'
        unique_together     = ['staff', 'task']


# ============================================================
# LAPORAN KEGIATAN
# ============================================================

class StatusLaporan(models.TextChoices):
    DRAFT   = 'draft',   'Draft'
    SELESAI = 'selesai', 'Selesai'


class LaporanKegiatan(models.Model):
    """
    Laporan kegiatan yang dibuat oleh Supervisor Lapangan.
    """
    perusahaan    = models.ForeignKey(
        Perusahaan,
        on_delete=models.CASCADE,
        related_name='laporan_kegiatan',
    )
    jenis_jasa    = models.ForeignKey(
        JenisJasa,
        on_delete=models.CASCADE,
        related_name='laporan_kegiatan',
    )
    area          = models.ForeignKey(
        AreaKerja,
        on_delete=models.CASCADE,
        related_name='laporan_kegiatan',
    )
    supervisor    = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='laporan_yang_dibuat',
        limit_choices_to={'role': RoleChoices.SUPERVISOR},
    )
    nama_laporan    = models.CharField(max_length=200)
    tanggal_laporan = models.DateField()
    status          = models.CharField(
        max_length=20,
        choices=StatusLaporan.choices,
        default=StatusLaporan.DRAFT,
    )
    is_active       = models.BooleanField(default=True)
    catatan         = models.TextField(blank=True)
    dibuat_pada     = models.DateTimeField(auto_now_add=True)
    diubah_pada     = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    @property
    def semua_item_approved(self):
        return self.item_kegiatan.exists() and not (
            self.item_kegiatan.exclude(status=StatusItem.SELESAI).exists()
        )

    def clean(self):
        if self.pk:
            try:
                original = LaporanKegiatan.objects.get(pk=self.pk)
                if original.status == StatusLaporan.SELESAI:
                    raise ValidationError(
                        "Laporan yang sudah selesai tidak dapat diubah. "
                        "Hubungi Admin jika diperlukan koreksi."
                    )
            except LaporanKegiatan.DoesNotExist:
                pass

        if self.area_id and self.perusahaan_id:
            if self.area.perusahaan_id != self.perusahaan_id:
                raise ValidationError(
                    f"Area '{self.area}' bukan milik perusahaan '{self.perusahaan}'."
                )

        if self.perusahaan_id and self.jenis_jasa_id:
            if not self.perusahaan.jenis_jasa.filter(pk=self.jenis_jasa_id).exists():
                raise ValidationError(
                    f"Perusahaan '{self.perusahaan}' tidak menggunakan jasa '{self.jenis_jasa}'."
                )

    def delete(self, *args, **kwargs):
        if self.status == StatusLaporan.SELESAI:
            raise ValidationError(
                "Laporan yang sudah selesai tidak dapat dihapus."
            )
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.nama_laporan} — {self.perusahaan} ({self.tanggal_laporan})"

    class Meta:
        verbose_name        = 'Laporan Kegiatan'
        verbose_name_plural = 'Laporan Kegiatan'
        ordering            = ['-tanggal_laporan', 'perusahaan']
        indexes             = [
            models.Index(fields=['status'], name='idx_laporan_status'),
            models.Index(fields=['perusahaan', 'tanggal_laporan'], name='idx_laporan_perusahaan_tgl'),
            models.Index(fields=['supervisor', 'status'], name='idx_laporan_supervisor_status'),
        ]


# ============================================================
# ITEM KEGIATAN
# ============================================================

class StatusItem(models.TextChoices):
    TERJADWAL          = 'terjadwal',          'Terjadwal'
    ON_PROGRESS        = 'on_progress',        'On Progress'
    MENUNGGU_APPROVAL  = 'menunggu_approval',  'Menunggu Approval'
    SELESAI            = 'selesai',            'Selesai'


class ItemKegiatan(models.Model):
    """
    Item kegiatan adalah tugas spesifik untuk satu atau lebih staff di satu sub area.
    """
    laporan     = models.ForeignKey(
        LaporanKegiatan,
        on_delete=models.CASCADE,
        related_name='item_kegiatan',
    )
    task        = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='item_kegiatan',
    )
    sub_area    = models.ForeignKey(
        SubArea,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='item_kegiatan',
    )
    staff       = models.ManyToManyField(
        User,
        related_name='item_kegiatan_saya',
        limit_choices_to={'role': RoleChoices.STAFF},
    )
    nama_item       = models.CharField(max_length=200)
    deskripsi       = models.TextField(blank=True)
    tanggal         = models.DateField()
    jam_mulai       = models.TimeField(null=True, blank=True)
    jam_selesai     = models.TimeField(null=True, blank=True)
    status          = models.CharField(
        max_length=20,
        choices=StatusItem.choices,
        default=StatusItem.TERJADWAL,
    )
    foto_on_progress = models.ImageField(
        upload_to='foto_item/on_progress/',
        blank=True,
        null=True,
    )
    foto_after       = models.ImageField(
        upload_to='foto_item/after/',
        blank=True,
        null=True,
    )
    is_insidental   = models.BooleanField(
        default=False,
        help_text='True jika pekerjaan ini dibuat oleh staff di luar jadwal.',
    )
    catatan_staff   = models.TextField(
        blank=True,
        help_text='Catatan tambahan dari staff lapangan.',
    )
    waktu_selesai_aktual = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Waktu aktual saat staff mengupload foto after (otomatis diisi sistem).',
    )
    keterangan_overtime = models.TextField(
        blank=True,
        help_text='Wajib diisi jika keterlambatan lebih dari 1 jam.',
    )
    dibuat_pada     = models.DateTimeField(auto_now_add=True)
    diubah_pada     = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.jam_mulai and self.jam_selesai:
            if self.jam_selesai <= self.jam_mulai:
                raise ValidationError("Jam selesai harus setelah jam mulai.")

        if self.sub_area_id and self.laporan_id:
            if self.sub_area.area_id != self.laporan.area_id:
                raise ValidationError(
                    f"Sub area '{self.sub_area}' bukan bagian dari area '{self.laporan.area}'."
                )

        if self.task_id and self.laporan_id:
            if self.task.jenis_jasa_id != self.laporan.jenis_jasa_id:
                raise ValidationError(
                    f"Task '{self.task}' bukan bagian dari jenis jasa '{self.laporan.jenis_jasa}'."
                )

        if self.pk and self.laporan_id:
            supervisor = self.laporan.supervisor
            for staff_member in self.staff.all():
                if not self.is_insidental:
                    is_staff_valid = StaffSupervisor.objects.filter(
                        staff=staff_member,
                        supervisor=supervisor,
                        is_active=True,
                    ).exists()
                    if not is_staff_valid:
                        raise ValidationError(
                            f"Staff '{staff_member}' tidak terdaftar di bawah "
                            f"supervisor '{supervisor}'."
                        )
                if self.task_id and not self.is_insidental:
                    has_skill = StaffTask.objects.filter(
                        staff=staff_member,
                        task=self.task_id,
                        is_active=True,
                    ).exists()
                    if not has_skill:
                        raise ValidationError(
                            f"Staff '{staff_member}' tidak memiliki skill untuk "
                            f"task '{self.task.nama_task}'."
                        )

    def __str__(self):
        if not self.pk:
            return self.nama_item or "Item Kegiatan (unsaved)"
        try:
            staff_names = ", ".join([s.nama_lengkap or s.username for s in self.staff.all()])
        except Exception:
            staff_names = "Staff"
        if self.task_id:
            return f"{self.task.nama_task} — {staff_names} ({self.tanggal})"
        return f"{self.nama_item} — {staff_names} ({self.tanggal})"

    class Meta:
        verbose_name        = 'Item Kegiatan'
        verbose_name_plural = 'Item Kegiatan'
        ordering            = ['tanggal', 'jam_mulai']
        indexes             = [
            models.Index(fields=['tanggal', 'status'], name='idx_item_tanggal_status'),
            models.Index(fields=['laporan', 'status'], name='idx_item_laporan_status'),
        ]


class FotoItemKegiatan(models.Model):

    MAKS_FOTO = 6

    class JenisFoto(models.TextChoices):
        TAMBAHAN = 'tambahan', 'Foto Tambahan'
        KONDISI  = 'kondisi',  'Kondisi Lapangan'
        KENDALA  = 'kendala',  'Kendala / Hambatan'
        LAINNYA  = 'lainnya',  'Lainnya'

    item = models.ForeignKey(
        ItemKegiatan,
        on_delete=models.CASCADE,
        related_name='foto_tambahan',
    )
    foto = models.ImageField(upload_to='foto_item/tambahan/')
    jenis = models.CharField(
        max_length=20,
        choices=JenisFoto.choices,
        default=JenisFoto.TAMBAHAN,
    )
    keterangan = models.CharField(
        max_length=300,
        blank=True,
        help_text='Keterangan singkat konteks foto (opsional).',
    )
    urutan        = models.PositiveSmallIntegerField(default=0)
    diunggah_pada = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if not self.item_id:
            return
        existing = FotoItemKegiatan.objects.filter(item=self.item)
        if self.pk:
            existing = existing.exclude(pk=self.pk)
        if existing.count() >= self.MAKS_FOTO:
            raise ValidationError(
                f"Maksimal {self.MAKS_FOTO} foto tambahan per item kegiatan."
            )

    class Meta:
        verbose_name        = 'Foto Tambahan Item Kegiatan'
        verbose_name_plural = 'Foto Tambahan Item Kegiatan'
        ordering            = ['urutan', 'diunggah_pada']
        indexes             = [
            models.Index(fields=['item', 'urutan'], name='idx_foto_item_urutan'),
        ]

    def __str__(self):
        return f"Foto {self.get_jenis_display()} — {self.item.nama_item}"


# ============================================================
# ABSENSI — Helper
# ============================================================
 
def hitung_jarak_meter(lat1, lon1, lat2, lon2) -> float:
    """
    Hitung jarak dua koordinat (decimal degrees) dalam meter.
    Menggunakan formula Haversine — akurasi cukup untuk radius 15–500m.
    """
    R = 6_371_000
    phi1     = math.radians(float(lat1))
    phi2     = math.radians(float(lat2))
    d_phi    = math.radians(float(lat2) - float(lat1))
    d_lambda = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
 
 
# ============================================================
# ABSENSI — Lokasi
# ============================================================
 
from outsourcing.constants import (
    KOORDINAT_DECIMAL_PLACES,
    KOORDINAT_MAX_DIGITS,
    RADIUS_MIN,
    RADIUS_MAX,
    RADIUS_DEFAULT,
)
 
 
class LokasiAbsensi(models.Model):
    supervisor   = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='lokasi_yang_dibuat',
        limit_choices_to={'role': RoleChoices.SUPERVISOR},
    )
    nama         = models.CharField(max_length=120)
    latitude     = models.DecimalField(
        max_digits=KOORDINAT_MAX_DIGITS,
        decimal_places=KOORDINAT_DECIMAL_PLACES,
    )
    longitude    = models.DecimalField(
        max_digits=KOORDINAT_MAX_DIGITS,
        decimal_places=KOORDINAT_DECIMAL_PLACES,
    )
    radius_meter = models.PositiveIntegerField(
        default=RADIUS_DEFAULT,
        validators=[
            MinValueValidator(RADIUS_MIN),
            MaxValueValidator(RADIUS_MAX),
        ]
    )
    is_active    = models.BooleanField(default=True)
    diperbarui   = models.DateTimeField(auto_now=True)
    dibuat_pada  = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name        = 'Lokasi Absensi'
        verbose_name_plural = 'Lokasi Absensi'
        ordering            = ['nama']
 
    def __str__(self):
        return f"{self.nama} (±{self.radius_meter}m)"
 
    def validasi_koordinat(self, lat_staff, lon_staff) -> tuple[bool, float]:
        jarak = hitung_jarak_meter(self.latitude, self.longitude, lat_staff, lon_staff)
        return jarak <= self.radius_meter, round(jarak, 1)
 
 
# ============================================================
# ABSENSI — Choices
# ============================================================
 
class OvertimeStatusChoices(models.TextChoices):
    BELUM_REVIEW = 'belum_review', 'Belum Direview'
    PAID         = 'paid',         'Dibayar'
    UNPAID       = 'unpaid',       'Tidak Dibayar'
 
 
class AbsensiStatusChoices(models.TextChoices):
    BELUM_ABSEN = 'belum_absen', 'Belum Absen'
    MASUK       = 'masuk',       'Masuk'
    PULANG      = 'pulang',      'Pulang'
    TERLAMBAT   = 'terlambat',   'Terlambat'
    OVERTIME    = 'overtime',    'Overtime'
 
 
class StatusHarianChoices(models.TextChoices):
    HADIR  = 'P',  'Hadir'
    CUTI   = 'L',  'Cuti'
    IZIN   = 'I',  'Izin'
    ALPA   = 'A',  'Alpa'
    DOKTER = 'DC', 'Surat Dokter'
    LIBUR  = 'LB', 'Libur'
 
 
class QRTypeChoices(models.TextChoices):
    MASUK  = 'masuk',  'Masuk'
    PULANG = 'pulang', 'Pulang'
 
 
# ============================================================
# ABSENSI — QR Permanen
# ============================================================
 
class QRAbsensi(models.Model):
    """
    QR Permanen — 1 supervisor hanya punya 1 QR masuk + 1 QR pulang.
    Tidak pernah expired, hanya bisa dinonaktifkan manual oleh supervisor.
    Lokasi bisa diubah kapan saja tanpa regenerasi QR.
    """
    lokasi = models.ForeignKey(
        'LokasiAbsensi',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='qr_codes',
        help_text="Kosongkan jika absensi tidak perlu validasi lokasi.",
    )
    supervisor  = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='qr_dibuat',
        limit_choices_to={'role': RoleChoices.SUPERVISOR},
    )
    token       = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    tipe        = models.CharField(max_length=10, choices=QRTypeChoices.choices)
    is_active   = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diperbarui  = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name    = 'QR Absensi'
        unique_together = [['supervisor', 'tipe']]  # 1 QR masuk + 1 QR pulang per supervisor selamanya
        ordering        = ['supervisor', 'tipe']
 
    def is_valid(self):
        """QR valid selama is_active=True — tidak ada expiry."""
        if not self.is_active:
            return False, 'QR tidak aktif. Hubungi supervisor.'
        return True, None
 
    def __str__(self):
        nama = self.supervisor.nama_lengkap or self.supervisor.username
        return f"QR {self.get_tipe_display()} — {nama} ({'Aktif' if self.is_active else 'Nonaktif'})"
 
 
# ============================================================
# ABSENSI — Jadwal Kerja
# ============================================================
 
class HariChoices(models.IntegerChoices):
    SENIN  = 0, 'Senin'
    SELASA = 1, 'Selasa'
    RABU   = 2, 'Rabu'
    KAMIS  = 3, 'Kamis'
    JUMAT  = 4, 'Jumat'
    SABTU  = 5, 'Sabtu'
    MINGGU = 6, 'Minggu'
 
 
class JadwalKerja(models.Model):
    """
    Jadwal kerja per hari per supervisor.
    Berlaku untuk semua staff di bawah supervisor tersebut.
 
    Hari yang tidak dikonfigurasi = di luar jadwal resmi.
    Staff tetap bisa scan, tapi wajib isi alasan (KeteranganAbsensi).
 
    Contoh setup default:
      Senin–Jumat : 07:00 – 17:15
      Sabtu       : 07:00 – 15:00
      Minggu      : tidak dikonfigurasi
    """
    supervisor  = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='jadwal_kerja',
        limit_choices_to={'role': RoleChoices.SUPERVISOR},
    )
    hari        = models.IntegerField(choices=HariChoices.choices)
    jam_masuk   = models.TimeField(help_text="Jam masuk resmi, contoh: 07:00")
    jam_pulang  = models.TimeField(help_text="Jam pulang resmi, contoh: 17:15")
    is_active   = models.BooleanField(default=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diperbarui  = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name        = 'Jadwal Kerja'
        verbose_name_plural = 'Jadwal Kerja'
        unique_together     = [['supervisor', 'hari']]
        ordering            = ['supervisor', 'hari']
 
    def clean(self):
        if self.jam_masuk and self.jam_pulang:
            if self.jam_pulang <= self.jam_masuk:
                raise ValidationError("Jam pulang harus setelah jam masuk.")
 
    def __str__(self):
        nama = self.supervisor.nama_lengkap or self.supervisor.username
        return (
            f"{nama} — {self.get_hari_display()}: "
            f"{self.jam_masuk.strftime('%H:%M')} – {self.jam_pulang.strftime('%H:%M')}"
        )
 
 
# ============================================================
# ABSENSI — Keterangan (Terlambat / Pulang Cepat / Luar Jadwal)
# ============================================================
 
class TipeKeteranganChoices(models.TextChoices):
    TERLAMBAT      = 'terlambat',    'Terlambat Masuk'
    PULANG_CEPAT   = 'pulang_cepat', 'Pulang Lebih Awal'
    DI_LUAR_JADWAL = 'luar_jadwal',  'Di Luar Jadwal Kerja'
 
 
class StatusKeteranganChoices(models.TextChoices):
    PENDING  = 'pending',  'Menunggu Persetujuan'
    APPROVED = 'approved', 'Disetujui'
    REJECTED = 'rejected', 'Ditolak'
 
 
class KeteranganAbsensi(models.Model):
    """
    Catatan alasan ketika staff scan di luar kondisi normal:
      - Terlambat masuk  : waktu scan masuk > jam_masuk JadwalKerja
      - Pulang lebih awal: waktu scan pulang < jam_pulang JadwalKerja
      - Di luar jadwal   : scan di hari yang tidak ada JadwalKerja
 
    Setiap keterangan perlu approval supervisor.
    """
    absensi     = models.ForeignKey(
        'Absensi',
        on_delete=models.CASCADE,
        related_name='keterangan_set',
    )
    tipe        = models.CharField(max_length=20, choices=TipeKeteranganChoices.choices)
    alasan      = models.TextField(help_text="Alasan wajib diisi oleh staff saat scan.")
 
    # Selisih menit untuk keperluan display di rekap
    # Positif  = terlambat masuk atau overtime
    # Negatif  = pulang lebih awal
    selisih_menit = models.IntegerField(
        default=0,
        help_text="Selisih menit terhadap jadwal resmi.",
    )
 
    status             = models.CharField(
        max_length=20,
        choices=StatusKeteranganChoices.choices,
        default=StatusKeteranganChoices.PENDING,
    )
    catatan_supervisor = models.TextField(blank=True)
    direview_oleh      = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='keterangan_reviews',
    )
    direview_pada      = models.DateTimeField(null=True, blank=True)
    dibuat_pada        = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name        = 'Keterangan Absensi'
        verbose_name_plural = 'Keterangan Absensi'
        ordering            = ['-dibuat_pada']
        unique_together     = [['absensi', 'tipe']]  # 1 keterangan per tipe per absensi
 
    def __str__(self):
        nama = self.absensi.staff.nama_lengkap or self.absensi.staff.username
        return (
            f"{self.get_tipe_display()} — {nama} "
            f"({self.absensi.tanggal}) [{self.get_status_display()}]"
        )
 
 
# ============================================================
# ABSENSI — Record Harian
# ============================================================
 
class Absensi(models.Model):
    # ── Relasi ──────────────────────────────────────────────
    qr_masuk  = models.ForeignKey(
        QRAbsensi, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='absensi_masuk',
    )
    qr_pulang = models.ForeignKey(
        QRAbsensi, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='absensi_pulang',
    )
    staff = models.ForeignKey(User, on_delete=models.CASCADE)
 
    # ── Waktu & Lokasi ───────────────────────────────────────
    tanggal      = models.DateField()
    waktu_masuk  = models.DateTimeField(null=True, blank=True)
    lat_masuk    = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lon_masuk    = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    waktu_pulang = models.DateTimeField(null=True, blank=True)
    lat_pulang   = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lon_pulang   = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
 
    # ── Status ───────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=AbsensiStatusChoices.choices,
        default=AbsensiStatusChoices.BELUM_ABSEN,
    )
    status_harian = models.CharField(
        max_length=5,
        choices=StatusHarianChoices.choices,
        default=StatusHarianChoices.HADIR,
        blank=True,
    )
 
    # ── Overtime ─────────────────────────────────────────────
    is_overtime          = models.BooleanField(default=False)
    overtime_status      = models.CharField(
        max_length=20,
        choices=OvertimeStatusChoices.choices,
        default=OvertimeStatusChoices.BELUM_REVIEW,
        blank=True,
    )
    overtime_reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='overtime_reviews',
    )
    overtime_reviewed_at = models.DateTimeField(null=True, blank=True)
 
    # ── Izin Pulang Awal (legacy — dipertahankan, digantikan KeteranganAbsensi) ──
    izin_pulang_awal       = models.BooleanField(default=False)
    keterangan_izin_pulang = models.TextField(blank=True)
 
    # ── Catatan & Timestamp ──────────────────────────────────
    catatan     = models.TextField(blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)
 
    # ── Threshold Overtime ───────────────────────────────────
    THRESHOLD_OT_MENIT = 60  # menit setelah jam pulang resmi
 
    # ── Properties ───────────────────────────────────────────
    @property
    def sudah_masuk(self):
        return self.waktu_masuk is not None
 
    @property
    def sudah_pulang(self):
        return self.waktu_pulang is not None
 
    # ── Methods ──────────────────────────────────────────────
    def durasi_kerja(self):
        if self.waktu_masuk and self.waktu_pulang:
            return self.waktu_pulang - self.waktu_masuk
        return None
 
    @property
    def durasi_str(self):
        durasi = self.durasi_kerja()
        if not durasi:
            return '-'
        total = int(durasi.total_seconds())
        jam   = total // 3600
        menit = (total % 3600) // 60
        if jam:
            return f"{jam}j {menit}m"
        return f"{menit}m"
 
    def _get_jadwal(self):
        """
        Ambil JadwalKerja supervisor untuk hari absensi ini.
        Return None jika tidak ada jadwal (hari libur/tidak dikonfigurasi).
        """
        if not self.qr_pulang:
            return None
        try:
            return JadwalKerja.objects.get(
                supervisor=self.qr_pulang.supervisor,
                hari=self.tanggal.weekday(),
                is_active=True,
            )
        except JadwalKerja.DoesNotExist:
            return None
 
    def hitung_overtime_menit(self):
        """
        Hitung overtime berdasarkan jam pulang resmi dari JadwalKerja supervisor.
        Return 0 jika tidak ada jadwal atau belum pulang.
        """
        if not self.waktu_pulang:
            return 0
 
        jadwal = self._get_jadwal()
        if not jadwal:
            return 0
 
        jam_pulang_resmi = timezone.make_aware(
            datetime.combine(self.tanggal, jadwal.jam_pulang)
        )
        selisih_menit = int(
            (self.waktu_pulang - jam_pulang_resmi).total_seconds() / 60
        )
        return selisih_menit if selisih_menit >= self.THRESHOLD_OT_MENIT else 0
 
    def update_overtime(self):
        """
        Hitung ulang is_overtime.
        Panggil setiap kali waktu_pulang di-set/diubah, lalu save() manual.
        """
        menit = self.hitung_overtime_menit()
        self.is_overtime = menit > 0
        if not self.is_overtime:
            self.overtime_status      = OvertimeStatusChoices.BELUM_REVIEW
            self.overtime_reviewed_by = None
            self.overtime_reviewed_at = None
 
    def clean(self):
        if self.waktu_masuk and self.waktu_pulang:
            if self.waktu_pulang <= self.waktu_masuk:
                raise ValidationError("Waktu pulang harus setelah waktu masuk.")
 
    def __str__(self):
        nama = self.staff.nama_lengkap or self.staff.username
        return f"Absensi {nama} — {self.tanggal} ({self.status})"
 
    class Meta:
        verbose_name        = 'Absensi'
        verbose_name_plural = 'Absensi'
        ordering            = ['-tanggal']
        unique_together     = ['staff', 'tanggal']
        indexes             = [
            models.Index(fields=['tanggal', 'status'], name='idx_absensi_tanggal_status'),
            models.Index(fields=['staff', 'tanggal'],  name='idx_absensi_staff_tgl'),
        ]
 
 
# ============================================================
# ABSENSI — Izin Staff
# ============================================================
 
class TipeIzinChoices(models.TextChoices):
    SAKIT           = 'sakit',    'Sakit'
    CUTI            = 'cuti',     'Cuti'
    URUSAN_KELUARGA = 'keluarga', 'Urusan Keluarga'
    LAINNYA         = 'lainnya',  'Lainnya'
 
 
class StatusIzinChoices(models.TextChoices):
    PENDING  = 'pending',  'Menunggu Persetujuan'
    APPROVED = 'approved', 'Disetujui'
    REJECTED = 'rejected', 'Ditolak'
 
 
class IzinStaff(models.Model):
    staff              = models.ForeignKey(User, on_delete=models.CASCADE, related_name='izin')
    tipe               = models.CharField(max_length=20, choices=TipeIzinChoices.choices)
    tanggal_mulai      = models.DateField()
    tanggal_selesai    = models.DateField()
    keterangan         = models.TextField(blank=True)
    lampiran           = models.FileField(upload_to='izin/', null=True, blank=True)
    status             = models.CharField(
        max_length=20,
        choices=StatusIzinChoices.choices,
        default=StatusIzinChoices.PENDING,
    )
    catatan_supervisor = models.TextField(blank=True)
    direview_oleh      = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='izin_reviews',
    )
    direview_pada      = models.DateTimeField(null=True, blank=True)
    dibuat_pada        = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name        = 'Izin Staff'
        verbose_name_plural = 'Izin Staff'
        ordering            = ['-dibuat_pada']
 
    def __str__(self):
        nama = self.staff.nama_lengkap or self.staff.username
        return f"Izin {self.get_tipe_display()} — {nama} ({self.tanggal_mulai} s/d {self.tanggal_selesai})"
 
    @property
    def jumlah_hari(self):
        return (self.tanggal_selesai - self.tanggal_mulai).days + 1
 
 
# ============================================================
# ABSENSI — Hari Libur Nasional (Cache)
# ============================================================
 
class HariLiburNasional(models.Model):
    """
    Cache hari libur nasional Indonesia dari API libur.deno.dev.
    """
    tanggal     = models.DateField(unique=True)
    nama_libur  = models.CharField(max_length=200)
    tahun       = models.IntegerField(db_index=True)
    bulan       = models.IntegerField()
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diubah_pada = models.DateTimeField(auto_now=True)
 
    def __str__(self):
        return f"{self.tanggal} — {self.nama_libur}"
 
    class Meta:
        verbose_name        = 'Hari Libur Nasional'
        verbose_name_plural = 'Hari Libur Nasional'
        ordering            = ['tanggal']
        indexes             = [
            models.Index(fields=['tahun', 'bulan'], name='idx_libur_tahun_bulan'),
        ]
 
 
class CacheMetaLibur(models.Model):
    """
    Metadata kapan terakhir data libur di-fetch dari API per tahun-bulan.
    """
    tahun        = models.IntegerField()
    bulan        = models.IntegerField()
    last_fetched = models.DateTimeField(auto_now=True)
    fetch_sukses = models.BooleanField(default=True)
 
    class Meta:
        unique_together = ['tahun', 'bulan']
        verbose_name    = 'Cache Meta Libur'
 