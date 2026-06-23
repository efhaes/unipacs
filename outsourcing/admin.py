from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from outsourcing.models import (
    User, RoleChoices,
    JenisJasa, Perusahaan, AreaKerja, SubArea,
    KepalaSupervisorJasa, SupervisorPerusahaan, StaffSupervisor,
    LaporanKegiatan, ItemKegiatan,
    QRAbsensi, Absensi, LokasiAbsensi,
)


# ============================================================
# USER
# ============================================================

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display  = ['username', 'nama_lengkap', 'role', 'telepon', 'is_active', 'dibuat_pada']
    list_filter   = ['role', 'is_active']
    search_fields = ['username', 'nama_lengkap', 'telepon']
    ordering      = ['nama_lengkap']

    fieldsets = UserAdmin.fieldsets + (
    ('Info Tambahan', {
        'fields': ('role', 'nama_lengkap', 'telepon', 'foto_profil')
        # is_active dihapus — sudah ada di UserAdmin.fieldsets bawaan
    }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Info Tambahan', {
            'fields': ('role', 'nama_lengkap', 'telepon', 'foto_profil')
        }),
    )


# ============================================================
# MASTER DATA
# ============================================================

@admin.register(JenisJasa)
class JenisJasaAdmin(admin.ModelAdmin):
    list_display  = ['nama_jasa', 'is_active', 'dibuat_pada']
    list_filter   = ['is_active']
    search_fields = ['nama_jasa']
    ordering      = ['nama_jasa']


class AreaKerjaInline(admin.TabularInline):
    model  = AreaKerja
    extra  = 0
    fields = ['nama_area', 'keterangan', 'is_active']


@admin.register(Perusahaan)
class PerusahaanAdmin(admin.ModelAdmin):
    list_display  = ['nama_perusahaan', 'foto_perusahaan', 'telepon', 'email', 'customer', 'is_active', 'dibuat_pada']
    list_filter   = ['is_active', 'jenis_jasa']
    search_fields = ['nama_perusahaan', 'telepon', 'email']
    filter_horizontal = ['jenis_jasa']
    inlines   = [AreaKerjaInline]
    ordering  = ['nama_perusahaan']


class SubAreaInline(admin.TabularInline):
    model  = SubArea
    extra  = 0
    fields = ['nama_sub_area', 'keterangan', 'is_active']


@admin.register(AreaKerja)
class AreaKerjaAdmin(admin.ModelAdmin):
    list_display  = ['nama_area', 'perusahaan', 'is_active']
    list_filter   = ['is_active', 'perusahaan']
    search_fields = ['nama_area', 'perusahaan__nama_perusahaan']
    inlines       = [SubAreaInline]
    ordering      = ['perusahaan', 'nama_area']


@admin.register(SubArea)
class SubAreaAdmin(admin.ModelAdmin):
    list_display  = ['nama_sub_area', 'area', 'is_active']
    list_filter   = ['is_active', 'area__perusahaan']
    search_fields = ['nama_sub_area', 'area__nama_area']
    ordering      = ['area', 'nama_sub_area']


# ============================================================
# HIERARKI AKUN
# ============================================================

@admin.register(KepalaSupervisorJasa)
class KepalaSupervisorJasaAdmin(admin.ModelAdmin):
    list_display  = ['kepala_supervisor', 'jenis_jasa', 'dibuat_pada']
    list_filter   = ['jenis_jasa']
    search_fields = ['kepala_supervisor__nama_lengkap', 'jenis_jasa__nama_jasa']
    autocomplete_fields = ['kepala_supervisor', 'jenis_jasa']


@admin.register(SupervisorPerusahaan)
class SupervisorPerusahaanAdmin(admin.ModelAdmin):
    list_display  = ['supervisor', 'perusahaan', 'jenis_jasa', 'kepala_supervisor', 'is_active']
    list_filter   = ['is_active', 'jenis_jasa', 'perusahaan']
    search_fields = [
        'supervisor__nama_lengkap',
        'perusahaan__nama_perusahaan',
        'kepala_supervisor__nama_lengkap',
    ]
    autocomplete_fields = ['supervisor', 'perusahaan', 'jenis_jasa', 'kepala_supervisor']


@admin.register(StaffSupervisor)
class StaffSupervisorAdmin(admin.ModelAdmin):
    list_display  = ['staff', 'supervisor', 'is_active', 'dibuat_pada']
    list_filter   = ['is_active']
    search_fields = ['staff__nama_lengkap', 'supervisor__nama_lengkap']
    autocomplete_fields = ['staff', 'supervisor']


# ============================================================
# LAPORAN KEGIATAN
# ============================================================

class ItemKegiatanInline(admin.TabularInline):
    model  = ItemKegiatan
    extra  = 0
    fields = ['nama_item', 'sub_area', 'tanggal', 'jam_mulai', 'jam_selesai', 'status', 'is_insidental']
    readonly_fields = ['status']
    show_change_link = True


@admin.register(LaporanKegiatan)
class LaporanKegiatanAdmin(admin.ModelAdmin):
    list_display  = ['nama_laporan', 'perusahaan', 'jenis_jasa', 'area', 'supervisor', 'tanggal_laporan', 'status']
    list_filter   = ['status', 'jenis_jasa', 'perusahaan', 'tanggal_laporan']
    search_fields = [
        'nama_laporan',
        'perusahaan__nama_perusahaan',
        'supervisor__nama_lengkap',
    ]
    autocomplete_fields = ['perusahaan', 'jenis_jasa', 'area', 'supervisor']
    readonly_fields     = ['dibuat_pada', 'diubah_pada']
    inlines             = [ItemKegiatanInline]
    ordering            = ['-tanggal_laporan']
    date_hierarchy      = 'tanggal_laporan'

    fieldsets = (
        ('Info Laporan', {
            'fields': ('nama_laporan', 'tanggal_laporan', 'status', 'catatan')
        }),
        ('Relasi', {
            'fields': ('perusahaan', 'jenis_jasa', 'area', 'supervisor')
        }),
        ('Timestamps', {
            'fields': ('dibuat_pada', 'diubah_pada'),
            'classes': ('collapse',),
        }),
    )


# ============================================================
# ITEM KEGIATAN
# ============================================================

@admin.register(ItemKegiatan)
class ItemKegiatanAdmin(admin.ModelAdmin):
    list_display   = ['nama_item', 'laporan', 'tanggal', 'jam_mulai', 'jam_selesai', 'status', 'is_insidental', 'foto_status']
    list_filter    = ['status', 'is_insidental', 'tanggal']
    search_fields  = ['nama_item', 'laporan__nama_laporan']
    autocomplete_fields = ['laporan', 'sub_area']
    filter_horizontal = ['staff']
    readonly_fields     = ['dibuat_pada', 'diubah_pada']
    ordering            = ['-tanggal', 'jam_mulai']
    date_hierarchy      = 'tanggal'

    fieldsets = (
        ('Info Pekerjaan', {
            'fields': ('nama_item', 'deskripsi', 'laporan', 'sub_area', 'staff', 'is_insidental')
        }),
        ('Jadwal', {
            'fields': ('tanggal', 'jam_mulai', 'jam_selesai', 'status')
        }),
        ('Dokumentasi Staff', {
            'fields': ('foto_on_progress', 'foto_after', 'catatan_staff')
        }),
        ('Timestamps', {
            'fields': ('dibuat_pada', 'diubah_pada'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Foto')
    def foto_status(self, obj):
        icons = []
        if obj.foto_on_progress:
            icons.append('📸 Progress')
        if obj.foto_after:
            icons.append('✅ After')

        if not icons:
            return '—'

        return format_html("{}", ' &nbsp; '.join(icons))

@admin.register(LokasiAbsensi)
class LokasiAbsensiAdmin(admin.ModelAdmin):
    list_display  = ['nama', 'supervisor', 'radius_meter', 'is_active', 'diperbarui']
    list_filter   = ['is_active']
    search_fields = ['nama', 'supervisor__nama_lengkap', 'supervisor__username']
    autocomplete_fields = ['supervisor']
    readonly_fields = ['dibuat_pada', 'diperbarui']
    ordering = ['nama']
    
# ============================================================
# QR ABSENSI
# ============================================================

@admin.register(QRAbsensi)
class QRAbsensiAdmin(admin.ModelAdmin):
    list_display  = ['supervisor', 'tipe', 'lokasi', 'is_active', 'dibuat_pada']
    list_filter   = ['tipe', 'is_active']
    search_fields = ['supervisor__nama_lengkap', 'supervisor__username']
    autocomplete_fields = ['supervisor', 'lokasi']
    readonly_fields = ['token', 'dibuat_pada', 'diperbarui']
    ordering = ['supervisor', 'tipe']

    fieldsets = (
        ('Info QR', {
            'fields': ('supervisor', 'tipe', 'lokasi', 'token')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('dibuat_pada', 'diperbarui'),
            'classes': ('collapse',),
        }),
    )


# ============================================================
# ABSENSI
# ============================================================

@admin.register(Absensi)
class AbsensiAdmin(admin.ModelAdmin):
    list_display  = ['staff', 'tanggal', 'waktu_masuk', 'waktu_pulang', 'status', 'status_harian', 'durasi_kerja_str']
    list_filter   = ['status', 'status_harian', 'tanggal']
    search_fields = ['staff__nama_lengkap', 'staff__username']
    autocomplete_fields = ['staff', 'qr_masuk', 'qr_pulang']
    readonly_fields = ['dibuat_pada', 'diubah_pada', 'sudah_masuk', 'sudah_pulang', 'durasi_kerja_str']
    ordering = ['-tanggal']
    date_hierarchy = 'tanggal'

    fieldsets = (
        ('Info Staff', {
            'fields': ('staff', 'tanggal')
        }),
        ('QR Code', {
            'fields': ('qr_masuk', 'qr_pulang')
        }),
        ('Absen Masuk', {
            'fields': ('waktu_masuk', 'lat_masuk', 'lon_masuk')
        }),
        ('Absen Pulang', {
            'fields': ('waktu_pulang', 'lat_pulang', 'lon_pulang')
        }),
        ('Status', {
            'fields': ('status', 'status_harian', 'catatan')
        }),
        ('Info Tambahan', {
            'fields': ('sudah_masuk', 'sudah_pulang', 'durasi_kerja_str'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('dibuat_pada', 'diubah_pada'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Durasi')
    def durasi_kerja_str(self, obj):
         return obj.durasi_str