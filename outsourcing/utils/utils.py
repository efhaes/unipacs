from django.db.models import Q, Count
from django.utils import timezone


# ============================================================
# IMPORT MODEL (lazy untuk hindari circular import)
# ============================================================

def get_models():
    from outsourcing.models import (
        User, Perusahaan, AreaKerja, SubArea,
        LaporanKegiatan, ItemKegiatan,
        KepalaSupervisorJasa, SupervisorPerusahaan, StaffSupervisor,
    )
    return {
        'User': User,
        'Perusahaan': Perusahaan,
        'AreaKerja': AreaKerja,
        'SubArea': SubArea,
        'LaporanKegiatan': LaporanKegiatan,
        'ItemKegiatan': ItemKegiatan,
        'KepalaSupervisorJasa': KepalaSupervisorJasa,
        'SupervisorPerusahaan': SupervisorPerusahaan,
        'StaffSupervisor': StaffSupervisor,
    }


# ============================================================
# REDIRECT DASHBOARD BERDASARKAN ROLE
# ============================================================

def get_dashboard_url(user):
    """
    Kembalikan URL dashboard sesuai role user.
    Dipakai setelah login berhasil.
    """
    role_url_map = {
        'admin'             : 'admin_dashboard',
        'kepala_supervisor' : 'kepala_dashboard',
        'supervisor'        : 'supervisor_dashboard',
        'staff'             : 'staff_dashboard',
        'customer'          : 'customer_dashboard',
    }
    return role_url_map.get(user.role, 'login')


# ============================================================
# FILTER DATA BERDASARKAN ROLE
# ============================================================

def get_supervisor_list(user):
    """
    Ambil daftar supervisor yang bisa dilihat oleh user.
    - Admin         : semua supervisor
    - Kepala Spv    : supervisor yang di bawah dia (termasuk yang belum ditugaskan)
    - Supervisor    : diri sendiri
    """
    m = get_models()
    User = m['User']
    SupervisorPerusahaan = m['SupervisorPerusahaan']

    if user.role == 'admin':
        return User.objects.filter(role='supervisor', is_active=True)

    elif user.role == 'kepala_supervisor':
        # Ambil supervisor yang terhubung lewat SupervisorPerusahaan
        supervisor_ids = SupervisorPerusahaan.objects.filter(
            kepala_supervisor=user,
            is_active=True,
        ).values_list('supervisor_id', flat=True)
        
        # Tambahkan supervisor yang belum memiliki penugasan sama sekali (newly created)
        all_supervisor_ids = SupervisorPerusahaan.objects.values_list('supervisor_id', flat=True)
        unassigned_supervisors = User.objects.filter(
            role='supervisor',
            is_active=True
        ).exclude(id__in=all_supervisor_ids).values_list('id', flat=True)
        
        # Gabungkan kedua set
        all_ids = set(supervisor_ids) | set(unassigned_supervisors)
        
        return User.objects.filter(id__in=all_ids, is_active=True)

    elif user.role == 'supervisor':
        return User.objects.filter(id=user.id)

    return User.objects.none()


def get_staff_list(user):
    """
    Ambil daftar staff yang bisa dilihat oleh user.
    - Admin         : semua staff
    - Kepala Spv    : staff yang di bawah supervisor-nya
    - Supervisor    : staff yang langsung di bawah dia
    - Staff         : diri sendiri
    """
    m = get_models()
    User = m['User']
    StaffSupervisor = m['StaffSupervisor']
    SupervisorPerusahaan = m['SupervisorPerusahaan']

    if user.role == 'admin':
        return User.objects.filter(role='staff',is_active=True)

    elif user.role == 'kepala_supervisor':
        supervisor_ids = SupervisorPerusahaan.objects.filter(
            kepala_supervisor=user,
            is_active=True,
        ).values_list('supervisor_id', flat=True)
        staff_ids = StaffSupervisor.objects.filter(
            supervisor_id__in=supervisor_ids,
            is_active=True,
        ).values_list('staff_id', flat=True)
        return User.objects.filter(id__in=staff_ids,is_active=True)

    elif user.role == 'supervisor':
        staff_ids = StaffSupervisor.objects.filter(
            supervisor=user,
            is_active=True,
        ).values_list('staff_id', flat=True)
        return User.objects.filter(id__in=staff_ids,is_active=True)

    elif user.role == 'staff':
        return User.objects.filter(id=user.id)

    return User.objects.none()


def get_perusahaan_list(user):
    """
    Ambil daftar perusahaan yang bisa dilihat oleh user.
    - Admin         : semua perusahaan
    - Kepala Spv    : perusahaan yang supervisor-nya di bawah dia
    - Supervisor    : perusahaan yang dia tangani
    - Customer      : perusahaan milik dia sendiri
    """
    m = get_models()
    Perusahaan = m['Perusahaan']
    SupervisorPerusahaan = m['SupervisorPerusahaan']

    if user.role == 'admin':
        return Perusahaan.objects.filter(is_active=True)

    elif user.role == 'kepala_supervisor':
        perusahaan_ids = SupervisorPerusahaan.objects.filter(
            kepala_supervisor=user,
            is_active=True,
        ).values_list('perusahaan_id', flat=True)
        return Perusahaan.objects.filter(id__in=perusahaan_ids,is_active=True)

    elif user.role == 'supervisor':
        perusahaan_ids = SupervisorPerusahaan.objects.filter(
            supervisor=user,
            is_active=True,
        ).values_list('perusahaan_id', flat=True)
        return Perusahaan.objects.filter(id__in=perusahaan_ids,is_active=True)

    elif user.role == 'customer':
        return Perusahaan.objects.filter(customer=user,is_active=True)

    return Perusahaan.objects.none()


def get_laporan_list(user):
    """
    Ambil daftar laporan kegiatan yang bisa dilihat oleh user.
    - Admin         : semua laporan
    - Kepala Spv    : laporan dari supervisor yang di bawah dia
    - Supervisor    : laporan yang dia buat
    - Staff         : laporan yang berisi item kegiatan milik dia
    - Customer      : laporan dari perusahaan dia, status dikirim_customer
    """
    m = get_models()
    LaporanKegiatan = m['LaporanKegiatan']
    SupervisorPerusahaan = m['SupervisorPerusahaan']

    if user.role == 'admin':
        return LaporanKegiatan.objects.all()

    elif user.role == 'kepala_supervisor':
        supervisor_ids = SupervisorPerusahaan.objects.filter(
            kepala_supervisor=user,
            is_active=True,
        ).values_list('supervisor_id', flat=True)
        return LaporanKegiatan.objects.filter(supervisor_id__in=supervisor_ids)

    elif user.role == 'supervisor':
        return LaporanKegiatan.objects.filter(supervisor=user)

    elif user.role == 'staff':
        laporan_ids = m['ItemKegiatan'].objects.filter(
            staff=user,
        ).values_list('laporan_id', flat=True)
        return LaporanKegiatan.objects.filter(id__in=laporan_ids)

    elif user.role == 'customer':
        return LaporanKegiatan.objects.filter(
            perusahaan__customer=user,
            status='dikirim_customer',
        )

    return LaporanKegiatan.objects.none()


def get_item_kegiatan_list(user):
    """
    Ambil daftar item kegiatan yang bisa dilihat oleh user.
    - Admin         : semua item
    - Kepala Spv    : item dari laporan supervisor di bawah dia
    - Supervisor    : item dari laporan yang dia buat
    - Staff         : item yang ditugaskan ke dia
    - Customer      : item dari laporan perusahaan dia (status dikirim)
    """
    m = get_models()
    ItemKegiatan = m['ItemKegiatan']
    SupervisorPerusahaan = m['SupervisorPerusahaan']

    if user.role == 'admin':
        return ItemKegiatan.objects.all()

    elif user.role == 'kepala_supervisor':
        supervisor_ids = SupervisorPerusahaan.objects.filter(
            kepala_supervisor=user,
            is_actif=True,
        ).values_list('supervisor_id', flat=True)
        return ItemKegiatan.objects.filter(laporan__supervisor_id__in=supervisor_ids)

    elif user.role == 'supervisor':
        return ItemKegiatan.objects.filter(laporan__supervisor=user)

    elif user.role == 'staff':
        return ItemKegiatan.objects.filter(staff=user)

    elif user.role == 'customer':
        return ItemKegiatan.objects.filter(
            laporan__perusahaan__customer=user,
            laporan__status='dikirim_customer',
        )

    return ItemKegiatan.objects.none()


# ============================================================
# utils.py  —  get_dashboard_stats
# ============================================================

import json
from calendar import monthrange
from datetime import date, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from outsourcing.models import (
    Absensi, AbsensiStatusChoices,
    IzinStaff, StatusIzinChoices,
    ItemKegiatan, StatusItem,
    LaporanKegiatan, StatusLaporan,
    OvertimeStatusChoices,
    Perusahaan, User, RoleChoices,
    JenisJasa, AreaKerja,
    StaffSupervisor,
)

BULAN_LABEL = [
    '', 'Jan','Feb','Mar','Apr','Mei','Jun',
    'Jul','Agu','Sep','Okt','Nov','Des',
]
BULAN_FULL = [
    '', 'Januari','Februari','Maret','April','Mei','Juni',
    'Juli','Agustus','September','Oktober','November','Desember',
]


def _date_range(tahun, bulan):
    """Return (start, end) date for given year/month. If bulan=None → full year."""
    if bulan:
        last = monthrange(tahun, bulan)[1]
        return date(tahun, bulan, 1), date(tahun, bulan, last)
    return date(tahun, 1, 1), date(tahun, 12, 31)


def _prev_period(tahun, bulan):
    """Return (tahun, bulan) for the previous comparable period."""
    if bulan:
        if bulan == 1:
            return tahun - 1, 12
        return tahun, bulan - 1
    return tahun - 1, None


def _safe_pct(num, den):
    if not den:
        return 0
    return round(num / den * 100)


def get_dashboard_stats(user, bulan=None, tahun=None):
    today = date.today()
    tahun = tahun or today.year
    bulan = bulan  # may be None → all year

    start, end = _date_range(tahun, bulan)
    prev_tahun, prev_bulan = _prev_period(tahun, bulan)
    prev_start, prev_end  = _date_range(prev_tahun, prev_bulan or bulan or today.month)

    # ── Label ─────────────────────────────────────────
    if bulan:
        bulan_label = BULAN_FULL[bulan]
    else:
        bulan_label = 'Semua Bulan'

    # ════════════════════════════════════════════════════
    #  SDM
    # ════════════════════════════════════════════════════
    total_perusahaan = Perusahaan.objects.filter(is_active=True).count()
    total_kepala     = User.objects.filter(role=RoleChoices.KEPALA_SUPERVISOR, is_active=True).count()
    total_supervisor = User.objects.filter(role=RoleChoices.SUPERVISOR, is_active=True).count()
    total_staff      = User.objects.filter(role=RoleChoices.STAFF, is_active=True).count()
    total_customer   = User.objects.filter(role=RoleChoices.CUSTOMER, is_active=True).count()
    total_jenis_jasa = JenisJasa.objects.filter(is_active=True).count()
    total_area       = AreaKerja.objects.filter(is_active=True).count()

    # ════════════════════════════════════════════════════
    #  TODAY PULSE
    # ════════════════════════════════════════════════════
    absensi_today = Absensi.objects.filter(tanggal=today)

    today_hadir      = absensi_today.filter(waktu_masuk__isnull=False).count()
    today_terlambat  = absensi_today.filter(status=AbsensiStatusChoices.TERLAMBAT).count()
    today_overtime   = absensi_today.filter(is_overtime=True).count()
    today_belum_absen = max(total_staff - today_hadir, 0)

    # Izin yang cover hari ini (approved)
    today_izin = IzinStaff.objects.filter(
        tanggal_mulai__lte=today,
        tanggal_selesai__gte=today,
        status=StatusIzinChoices.APPROVED,
    ).count()

    today_laporan_aktif = LaporanKegiatan.objects.filter(
    tanggal_laporan__lte=today,
    status=StatusLaporan.DRAFT,  # draft = masih berjalan
    ).count()

    # ════════════════════════════════════════════════════
    #  ALERT STRIP
    # ════════════════════════════════════════════════════
    alert_ot_pending = Absensi.objects.filter(
        is_overtime=True,
        overtime_status=OvertimeStatusChoices.BELUM_REVIEW,
    ).count()

    alert_izin_pending = IzinStaff.objects.filter(
        status=StatusIzinChoices.PENDING,
    ).count()

    # Laporan stuck di draft lebih dari 7 hari
    stuck_threshold = today - timedelta(days=7)
    alert_laporan_stuck = LaporanKegiatan.objects.filter(
        status=StatusLaporan.DRAFT,
        dibuat_pada__date__lte=stuck_threshold,
    ).count()

    # ════════════════════════════════════════════════════
    #  LAPORAN PERIODE
    # ════════════════════════════════════════════════════
    laporan_qs      = LaporanKegiatan.objects.filter(tanggal_laporan__range=(start, end))
    total_laporan   = laporan_qs.count()
    laporan_selesai = laporan_qs.filter(
        status__in=[StatusLaporan.SELESAI, StatusLaporan.DIKIRIM_CUSTOMER]
    ).count()
    laporan_dikirim = laporan_qs.filter(status=StatusLaporan.DIKIRIM_CUSTOMER).count()
    completion_rate = _safe_pct(laporan_selesai, total_laporan)

    # Prev period
    laporan_prev      = LaporanKegiatan.objects.filter(tanggal_laporan__range=(prev_start, prev_end))
    prev_laporan      = laporan_prev.count()
    prev_selesai      = laporan_prev.filter(
        status__in=[StatusLaporan.SELESAI, StatusLaporan.DIKIRIM_CUSTOMER]
    ).count()
    prev_completion   = _safe_pct(prev_selesai, prev_laporan)

    delta_laporan     = total_laporan - prev_laporan
    delta_completion  = completion_rate - prev_completion

    laporan_terbaru = (
        LaporanKegiatan.objects
        .select_related('perusahaan', 'supervisor', 'jenis_jasa')
        .order_by('-dibuat_pada')[:10]
    )

    # ════════════════════════════════════════════════════
    #  ITEM KEGIATAN
    # ════════════════════════════════════════════════════
    item_qs = ItemKegiatan.objects.filter(tanggal__range=(start, end))
    total_item_terjadwal  = item_qs.filter(status=StatusItem.TERJADWAL).count()
    total_item_progress   = item_qs.filter(status=StatusItem.ON_PROGRESS).count()
    total_item_selesai    = item_qs.filter(status=StatusItem.SELESAI).count()
    total_item_insidental = item_qs.filter(is_insidental=True).count()

    prev_item_selesai = ItemKegiatan.objects.filter(
        tanggal__range=(prev_start, prev_end),
        status=StatusItem.SELESAI,
    ).count()
    delta_item = total_item_selesai - prev_item_selesai

    # ════════════════════════════════════════════════════
    #  ABSENSI PERIODE
    # ════════════════════════════════════════════════════
    absensi_qs = Absensi.objects.filter(tanggal__range=(start, end))

    absensi_hadir     = absensi_qs.filter(waktu_masuk__isnull=False).count()
    absensi_terlambat = absensi_qs.filter(status=AbsensiStatusChoices.TERLAMBAT).count()
    absensi_overtime  = absensi_qs.filter(is_overtime=True).count()
    # Alpa: staff yang sama sekali tidak absen — sulit hitung eksak tanpa roster,
    # pakai proxy: record yang dibuat tapi waktu_masuk null
    absensi_alpa = absensi_qs.filter(waktu_masuk__isnull=True).count()

    ot_belum_review = absensi_qs.filter(
        is_overtime=True,
        overtime_status=OvertimeStatusChoices.BELUM_REVIEW,
    ).count()
    ot_paid = absensi_qs.filter(
        is_overtime=True,
        overtime_status=OvertimeStatusChoices.PAID,
    ).count()
    total_overtime_bulan = absensi_overtime

    # Avg kehadiran: (hadir / (total_staff * hari_kerja)) — estimasi dengan hari di rentang
    hari_rentang = (end - start).days + 1
    expected_absensi = total_staff * hari_rentang
    avg_kehadiran = _safe_pct(absensi_hadir, expected_absensi) if expected_absensi else 0

    prev_absensi    = Absensi.objects.filter(tanggal__range=(prev_start, prev_end))
    prev_hadir      = prev_absensi.filter(waktu_masuk__isnull=False).count()
    prev_hari       = (prev_end - prev_start).days + 1
    prev_expected   = total_staff * prev_hari
    prev_kehadiran  = _safe_pct(prev_hadir, prev_expected) if prev_expected else 0
    delta_kehadiran = avg_kehadiran - prev_kehadiran

    # ════════════════════════════════════════════════════
    #  IZIN PERIODE
    # ════════════════════════════════════════════════════
    izin_qs       = IzinStaff.objects.filter(
        tanggal_mulai__lte=end,
        tanggal_selesai__gte=start,
    )
    total_izin_bulan = izin_qs.count()
    izin_pending     = izin_qs.filter(status=StatusIzinChoices.PENDING).count()
    izin_approved    = izin_qs.filter(status=StatusIzinChoices.APPROVED).count()
    izin_rejected    = izin_qs.filter(status=StatusIzinChoices.REJECTED).count()

    prev_izin     = IzinStaff.objects.filter(
        tanggal_mulai__lte=prev_end,
        tanggal_selesai__gte=prev_start,
    ).count()
    delta_izin    = total_izin_bulan - prev_izin

    # ════════════════════════════════════════════════════
    #  TOP SUPERVISOR (by laporan selesai periode ini)
    # ════════════════════════════════════════════════════
    top_sv_raw = (
        LaporanKegiatan.objects
        .filter(
            tanggal_laporan__range=(start, end),
            status__in=[StatusLaporan.SELESAI, StatusLaporan.DIKIRIM_CUSTOMER],
        )
        .values('supervisor__id', 'supervisor__nama_lengkap', 'supervisor__username',
                'perusahaan__nama_perusahaan')
        .annotate(total=Count('id'))
        .order_by('-total')[:8]
    )
    top_supervisor = [
        {
            'nama'      : sv['supervisor__nama_lengkap'] or sv['supervisor__username'],
            'perusahaan': sv['perusahaan__nama_perusahaan'],
            'total'     : sv['total'],
        }
        for sv in top_sv_raw
    ]

    # ════════════════════════════════════════════════════
    #  PERUSAHAAN HEALTH (% completion laporan)
    # ════════════════════════════════════════════════════
    perusahaan_list = (
        LaporanKegiatan.objects
        .filter(tanggal_laporan__range=(start, end))
        .values('perusahaan__id', 'perusahaan__nama_perusahaan')
        .annotate(
            total=Count('id'),
            selesai=Count('id', filter=Q(
                status__in=[StatusLaporan.SELESAI, StatusLaporan.DIKIRIM_CUSTOMER]
            )),
        )
        .order_by('perusahaan__nama_perusahaan')
    )
    perusahaan_health = [
        {
            'nama': p['perusahaan__nama_perusahaan'],
            'pct' : _safe_pct(p['selesai'], p['total']),
        }
        for p in perusahaan_list
    ]

    # ════════════════════════════════════════════════════
    #  CHART DATA — tren per bulan (tahun yang dipilih)
    # ════════════════════════════════════════════════════
    bulan_labels_list = []
    chart_total   = []
    chart_selesai = []
    chart_dikirim = []

    for m in range(1, 13):
        ms, me = _date_range(tahun, m)
        qs = LaporanKegiatan.objects.filter(tanggal_laporan__range=(ms, me))
        bulan_labels_list.append(BULAN_LABEL[m])
        chart_total.append(qs.count())
        chart_selesai.append(qs.filter(
            status__in=[StatusLaporan.SELESAI, StatusLaporan.DIKIRIM_CUSTOMER]
        ).count())
        chart_dikirim.append(qs.filter(status=StatusLaporan.DIKIRIM_CUSTOMER).count())

    return {
        # Meta
        'bulan_label'          : bulan_label,
        'tahun'                : tahun,

        # SDM
        'total_perusahaan'     : total_perusahaan,
        'total_kepala'         : total_kepala,
        'total_supervisor'     : total_supervisor,
        'total_staff'          : total_staff,
        'total_customer'       : total_customer,
        'total_jenis_jasa'     : total_jenis_jasa,
        'total_area'           : total_area,

        # Today pulse
        'today_hadir'          : today_hadir,
        'today_terlambat'      : today_terlambat,
        'today_overtime'       : today_overtime,
        'today_belum_absen'    : today_belum_absen,
        'today_izin'           : today_izin,
        'today_laporan_aktif'  : today_laporan_aktif,

        # Alerts
        'alert_ot_pending'     : alert_ot_pending,
        'alert_izin_pending'   : alert_izin_pending,
        'alert_laporan_stuck'  : alert_laporan_stuck,

        # KPI periode
        'total_laporan'        : total_laporan,
        'laporan_selesai'      : laporan_selesai,
        'laporan_dikirim'      : laporan_dikirim,
        'completion_rate'      : completion_rate,
        'delta_laporan'        : delta_laporan,
        'delta_completion'     : delta_completion,

        # Item
        'total_item_terjadwal' : total_item_terjadwal,
        'total_item_progress'  : total_item_progress,
        'total_item_selesai'   : total_item_selesai,
        'total_item_insidental': total_item_insidental,
        'delta_item'           : delta_item,

        # Absensi
        'absensi_hadir'        : absensi_hadir,
        'absensi_terlambat'    : absensi_terlambat,
        'absensi_overtime'     : absensi_overtime,
        'absensi_alpa'         : absensi_alpa,
        'avg_kehadiran'        : avg_kehadiran,
        'delta_kehadiran'      : delta_kehadiran,
        'total_overtime_bulan' : total_overtime_bulan,
        'ot_belum_review'      : ot_belum_review,
        'ot_paid'              : ot_paid,

        # Izin
        'total_izin_bulan'     : total_izin_bulan,
        'izin_pending'         : izin_pending,
        'izin_approved'        : izin_approved,
        'izin_rejected'        : izin_rejected,
        'delta_izin'           : delta_izin,

        # Leaderboard & health
        'top_supervisor'       : top_supervisor,
        'perusahaan_health'    : perusahaan_health,

        # Tabel
        'laporan_terbaru'      : laporan_terbaru,

        # Chart JSON
        'bulan_labels_json'    : json.dumps(bulan_labels_list),
        'chart_total_json'     : json.dumps(chart_total),
        'chart_selesai_json'   : json.dumps(chart_selesai),
        'chart_dikirim_json'   : json.dumps(chart_dikirim),
    }
# ============================================================
# HELPER VALIDASI AKSES OBJECT
# ============================================================

def user_can_access_laporan(user, laporan):
    """
    Cek apakah user boleh mengakses laporan tertentu.
    Kembalikan True/False.
    """
    if user.role == 'admin':
        return True

    elif user.role == 'kepala_supervisor':
        m = get_models()
        return m['SupervisorPerusahaan'].objects.filter(
            kepala_supervisor=user,
            supervisor=laporan.supervisor,
            is_active=True,
        ).exists()

    elif user.role == 'supervisor':
        return laporan.supervisor == user

    elif user.role == 'staff':
        m = get_models()
        return m['ItemKegiatan'].objects.filter(
            laporan=laporan, staff=user
        ).exists()

    elif user.role == 'customer':
        return (
            laporan.perusahaan.customer == user
            and laporan.status == 'dikirim_customer'
        )

    return False


def user_can_access_item(user, item):
    """
    Cek apakah user boleh mengakses item kegiatan tertentu.
    Kembalikan True/False.
    """
    if user.role == 'admin':
        return True

    elif user.role == 'kepala_supervisor':
        m = get_models()
        return m['SupervisorPerusahaan'].objects.filter(
            kepala_supervisor=user,
            supervisor=item.laporan.supervisor,
            is_active=True,
        ).exists()

    elif user.role == 'supervisor':
        return item.laporan.supervisor == user

    elif user.role == 'staff':
        return item.staff == user

    elif user.role == 'customer':
        return (
            item.laporan.perusahaan.customer == user
            and item.laporan.status == 'dikirim_customer'
        )

    return False