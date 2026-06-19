from calendar import calendar
import qrcode
import io
import base64
from calendar import monthrange
from datetime import datetime, time, date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.utils.timezone import localtime
from django.views.decorators.http import require_POST
from django.db.models import Q

from outsourcing.constants import KOORDINAT_DECIMAL_PLACES, RADIUS_DEFAULT, RADIUS_MAX, RADIUS_MIN
from outsourcing.decorators import supervisor_or_kepala_required
from outsourcing.models import (
    QRAbsensi, QRTypeChoices,
    Absensi, OvertimeStatusChoices,
    StaffSupervisor, IzinStaff, StatusIzinChoices,
    User, AbsensiStatusChoices, StatusHarianChoices, LokasiAbsensi,
)
from outsourcing.forms import LokasiAbsensiForm
from datetime import datetime, time, date, timedelta

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _qr_to_base64(url: str) -> str:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def _get_supervisor(request):
    return getattr(request, 'supervisor_context', request.user)


def _staff_ids(supervisor):
    return StaffSupervisor.objects.filter(
        supervisor=supervisor,
        is_active=True,
    ).values_list('staff_id', flat=True)


# ─────────────────────────────────────────────
# QR — List
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def qr_list(request):
    supervisor = _get_supervisor(request)
    qr_qs = (
        QRAbsensi.objects
        .filter(supervisor=supervisor)
        .select_related('lokasi')
        .order_by('-tanggal', 'tipe')
    )
    return render(request, 'supervisor/absensi/qr_list.html', {
        'qr_list'   : qr_qs,
        'supervisor': supervisor,
    })


# ─────────────────────────────────────────────
# QR — Generate
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def qr_generate(request):
    supervisor = _get_supervisor(request)
    hari_ini   = timezone.localdate()
    akhir_hari = timezone.make_aware(
        datetime.combine(hari_ini, time(23, 59, 59))
    )

    qr_masuk  = QRAbsensi.objects.filter(
        supervisor=supervisor, tanggal=hari_ini, tipe=QRTypeChoices.MASUK,
    ).first()
    qr_pulang = QRAbsensi.objects.filter(
        supervisor=supervisor, tanggal=hari_ini, tipe=QRTypeChoices.PULANG,
    ).first()

    lokasi_list = LokasiAbsensi.objects.filter(
        supervisor=supervisor,
        is_active=True,
    ).order_by('nama')

    # ── AJAX POST ─────────────────────────────
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        jam_masuk_str  = request.POST.get('jam_masuk', '').strip()
        jam_pulang_str = request.POST.get('jam_pulang', '').strip()
        lokasi_id      = request.POST.get('lokasi_id', '').strip()

        if not jam_masuk_str or not jam_pulang_str:
            return JsonResponse({'ok': False, 'error': 'Jam masuk dan jam pulang wajib diisi.'})

        try:
            h, m         = map(int, jam_masuk_str.split(':'))
            jam_masuk_dt = timezone.make_aware(datetime.combine(hari_ini, time(hour=h, minute=m)))
        except (ValueError, AttributeError):
            return JsonResponse({'ok': False, 'error': 'Format jam masuk tidak valid.'})

        try:
            h, m          = map(int, jam_pulang_str.split(':'))
            jam_pulang_dt = timezone.make_aware(datetime.combine(hari_ini, time(hour=h, minute=m)))
        except (ValueError, AttributeError):
            return JsonResponse({'ok': False, 'error': 'Format jam pulang tidak valid.'})

        if jam_pulang_dt <= jam_masuk_dt:
            return JsonResponse({'ok': False, 'error': 'Jam pulang harus setelah jam masuk.'})

        lokasi_obj = None
        if lokasi_id and lokasi_id != '0':
            try:
                lokasi_obj = LokasiAbsensi.objects.get(
                    pk=lokasi_id,
                    supervisor=supervisor,
                    is_active=True,
                )
            except LokasiAbsensi.DoesNotExist:
                return JsonResponse({'ok': False, 'error': 'Lokasi tidak ditemukan.'})

        if qr_masuk:
            qr_masuk.jam_berlaku_mulai = jam_masuk_dt
            qr_masuk.berlaku_hingga    = akhir_hari
            qr_masuk.lokasi            = lokasi_obj
            qr_masuk.save(update_fields=['jam_berlaku_mulai', 'berlaku_hingga', 'lokasi'])
        else:
            qr_masuk = QRAbsensi.objects.create(
                supervisor        = supervisor,
                tanggal           = hari_ini,
                tipe              = QRTypeChoices.MASUK,
                berlaku_hingga    = akhir_hari,
                jam_berlaku_mulai = jam_masuk_dt,
                lokasi            = lokasi_obj,
            )

        if qr_pulang:
            qr_pulang.jam_berlaku_mulai = jam_pulang_dt
            qr_pulang.berlaku_hingga    = akhir_hari
            qr_pulang.lokasi            = lokasi_obj
            qr_pulang.save(update_fields=['jam_berlaku_mulai', 'berlaku_hingga', 'lokasi'])
        else:
            qr_pulang = QRAbsensi.objects.create(
                supervisor        = supervisor,
                tanggal           = hari_ini,
                tipe              = QRTypeChoices.PULANG,
                berlaku_hingga    = akhir_hari,
                jam_berlaku_mulai = jam_pulang_dt,
                lokasi            = lokasi_obj,
            )

        staff_ids = list(_staff_ids(supervisor))
        existing  = set(
            Absensi.objects
            .filter(staff_id__in=staff_ids, tanggal=hari_ini)
            .values_list('staff_id', flat=True)
        )
        absensi_bulk = [
            Absensi(
                staff_id      = sid,
                tanggal       = hari_ini,
                status        = AbsensiStatusChoices.BELUM_ABSEN,
                status_harian = StatusHarianChoices.HADIR,
            )
            for sid in staff_ids if sid not in existing
        ]
        if absensi_bulk:
            Absensi.objects.bulk_create(absensi_bulk, ignore_conflicts=True)

        url_masuk  = request.build_absolute_uri(f'/absensi/scan/{qr_masuk.token}/')
        url_pulang = request.build_absolute_uri(f'/absensi/scan/{qr_pulang.token}/')

        return JsonResponse({
            'ok'              : True,
            'qr_masuk_b64'    : _qr_to_base64(url_masuk),
            'qr_pulang_b64'   : _qr_to_base64(url_pulang),
            'url_masuk'       : url_masuk,
            'url_pulang'      : url_pulang,
            'staff_disiapkan' : len(absensi_bulk),
            'lokasi_nama'     : lokasi_obj.nama if lokasi_obj else None,
            'lokasi_radius'   : lokasi_obj.radius_meter if lokasi_obj else None,
        })

    # ── GET ───────────────────────────────────
    qr_masuk_b64 = qr_pulang_b64 = url_masuk = url_pulang = None

    if qr_masuk:
        url_masuk    = request.build_absolute_uri(f'/absensi/scan/{qr_masuk.token}/')
        qr_masuk_b64 = _qr_to_base64(url_masuk)

    if qr_pulang:
        url_pulang    = request.build_absolute_uri(f'/absensi/scan/{qr_pulang.token}/')
        qr_pulang_b64 = _qr_to_base64(url_pulang)

    return render(request, 'supervisor/absensi/qr_generate.html', {
        'hari_ini'     : hari_ini,
        'qr_masuk'     : qr_masuk,
        'qr_pulang'    : qr_pulang,
        'qr_masuk_b64' : qr_masuk_b64,
        'qr_pulang_b64': qr_pulang_b64,
        'url_masuk'    : url_masuk,
        'url_pulang'   : url_pulang,
        'supervisor'   : supervisor,
        'lokasi_list'  : lokasi_list,
        'lokasi_aktif' : qr_masuk.lokasi if qr_masuk else None,
    })


# ─────────────────────────────────────────────
# QR — Nonaktifkan
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
@require_POST
def qr_nonaktifkan(request, pk):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    supervisor = _get_supervisor(request)
    qr_obj     = get_object_or_404(QRAbsensi, pk=pk, supervisor=supervisor)

    if not qr_obj.is_active:
        return JsonResponse({'ok': False, 'error': 'QR sudah tidak aktif.'})

    qr_obj.is_active = False
    qr_obj.save(update_fields=['is_active'])

    return JsonResponse({
        'ok'     : True,
        'message': f'QR {qr_obj.get_tipe_display()} berhasil dinonaktifkan.',
        'qr_pk'  : qr_obj.pk,
    })


# ─────────────────────────────────────────────
# Rekap Absensi
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def absensi_rekap(request):
    supervisor      = _get_supervisor(request)
    ids             = _staff_ids(supervisor)
    staff_qs        = User.objects.filter(id__in=ids)
    
    search_nama     = request.GET.get('q', '').strip()
    tgl_filter      = request.GET.get('tgl', '').strip()
    active_tab      = request.GET.get('tab', 'absensi')
    bulan_filter    = request.GET.get('bulan', '').strip()
    bulan_sekarang  = date.today().strftime('%Y-%m')
    
    if search_nama:
        staff_qs = staff_qs.filter(
            Q(nama_lengkap__icontains=search_nama) |
            Q(username__icontains=search_nama)
        )

    # ── TAB 1: ABSENSI (Harian) ──
    try:
        if tgl_filter:
            tgl_obj = datetime.strptime(tgl_filter, '%Y-%m-%d').date()
            tgl_custom = True
        else:
            tgl_obj = date.today()
            tgl_custom = False
    except ValueError:
        tgl_obj = date.today()
        tgl_custom = False

    tgl_str = tgl_obj.strftime('%Y-%m-%d')
    if tgl_obj == date.today():
        tgl_display = f"{tgl_obj.strftime('%d %B %Y')} (Hari ini)"
    else:
        tgl_display = tgl_obj.strftime('%d %B %Y')

    absensi_harian = Absensi.objects.filter(
        staff__in=staff_qs,
        tanggal=tgl_obj
    ).select_related('qr_masuk', 'qr_pulang')
    absensi_map = {a.staff_id: a for a in absensi_harian}

    izin_harian = IzinStaff.objects.filter(
        staff__in=staff_qs,
        status=StatusIzinChoices.APPROVED,
        tanggal_mulai__lte=tgl_obj,
        tanggal_selesai__gte=tgl_obj
    )
    izin_map = {i.staff_id: i for i in izin_harian}

    staff_data = []
    stats = {'total_staff': len(staff_qs), 'hadir': 0, 'belum_absen': 0, 'izin': 0}

    for staff in staff_qs:
        absen = absensi_map.get(staff.id)
        izin = izin_map.get(staff.id)
        
        # Determine status for stats
        if absen:
            s = absen.status
            sh = absen.status_harian
            if sh in ('I', 'L', 'DC') or s == 'izin':
                stats['izin'] += 1
            elif s in ('masuk', 'pulang', 'terlambat', 'overtime'):
                stats['hadir'] += 1
            else:
                stats['belum_absen'] += 1
        elif izin:
            stats['izin'] += 1
        else:
            stats['belum_absen'] += 1

        staff_data.append({
            'staff': staff,
            'absensi': absen,
            'izin': izin,
        })

    # Sort staff_data by name
    staff_data.sort(key=lambda x: (x['staff'].nama_lengkap or x['staff'].username).lower())

    # ── TAB 2: IZIN (Bulanan) ──
    if not bulan_filter:
        bulan_filter = bulan_sekarang

    try:
        tahun_int, bulan_int = map(int, bulan_filter.split('-'))
    except ValueError:
        tahun_int, bulan_int = date.today().year, date.today().month

    last_day    = monthrange(tahun_int, bulan_int)[1]
    bulan_start = date(tahun_int, bulan_int, 1)
    bulan_end   = date(tahun_int, bulan_int, last_day)

    izin_qs = IzinStaff.objects.filter(
        staff__in=staff_qs,
        tanggal_mulai__lte=bulan_end,
        tanggal_selesai__gte=bulan_start,
    ).select_related('staff', 'direview_oleh').order_by('-tanggal_mulai')

    return render(request, 'supervisor/absensi/rekap.html', {
        'active_tab'     : active_tab,
        'search_nama'    : search_nama,
        
        # Absensi variables
        'staff_data'     : staff_data,
        'tgl_str'        : tgl_str,
        'tgl_display'    : tgl_display,
        'tgl_tampil'     : tgl_obj,
        'tgl_custom'     : tgl_custom,
        'stats'          : stats,
        'total'          : stats['total_staff'],  # For the tab badge
        
        # Izin variables
        'izin_qs'        : izin_qs,
        'bulan_filter'   : bulan_filter,
        'total_izin'     : izin_qs.count(),
        'izin_pending'   : izin_qs.filter(status=StatusIzinChoices.PENDING).count(),
        'izin_approved'  : izin_qs.filter(status=StatusIzinChoices.APPROVED).count(),
        'izin_rejected'  : izin_qs.filter(status=StatusIzinChoices.REJECTED).count(),
        
        'supervisor'     : supervisor,
    })


# ─────────────────────────────────────────────
# Detail Absensi
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def absensi_detail(request, pk):
    supervisor = _get_supervisor(request)
    absensi    = get_object_or_404(
        Absensi,
        pk=pk,
        staff_id__in=_staff_ids(supervisor),
    )
    
    # Check if there is an approved Izin for this day
    izin = IzinStaff.objects.filter(
        staff=absensi.staff,
        status=StatusIzinChoices.APPROVED,
        tanggal_mulai__lte=absensi.tanggal,
        tanggal_selesai__gte=absensi.tanggal,
    ).first()
    absensi.izin_staff = izin

    return render(request, 'supervisor/absensi/detail.html', {
        'absensi'   : absensi,
        'durasi'    : absensi.durasi_str,
        'supervisor': supervisor,
    })

@supervisor_or_kepala_required
def supervisor_absensi_staff_detail(request, staff_pk):
    """
    Menampilkan detail absensi sebulan penuh untuk 1 staff.
    """
    supervisor = _get_supervisor(request)
    staff_ids  = _staff_ids(supervisor)
    staff      = get_object_or_404(User, pk=staff_pk, id__in=staff_ids)

    today = date.today()

    bulan_str = request.GET.get('bulan', '').strip()
    try:
        tahun, bln = map(int, bulan_str.split('-'))
        dt_start = date(tahun, bln, 1)
    except ValueError:
        dt_start = today.replace(day=1)
        tahun, bln = dt_start.year, dt_start.month

    last_day = monthrange(tahun, bln)[1]
    dt_end   = date(tahun, bln, last_day)

    # ── Fetch Absensi ──
    absensi_qs = Absensi.objects.filter(
        staff=staff,
        tanggal__range=[dt_start, dt_end],
    ).select_related('qr_masuk', 'qr_pulang')
    absensi_map = {a.tanggal: a for a in absensi_qs}

    # ── Fetch Izin (approved) ──
    izin_qs = IzinStaff.objects.filter(
        staff=staff,
        status=StatusIzinChoices.APPROVED,
        tanggal_mulai__lte=dt_end,
        tanggal_selesai__gte=dt_start,
    )
    izin_map = {}
    for iz in izin_qs:
        curr = iz.tanggal_mulai
        while curr <= iz.tanggal_selesai:
            if dt_start <= curr <= dt_end:
                izin_map[curr] = iz
            curr += timedelta(days=1)

    # ── Build calendar_rows + statistik ──
    calendar_rows = []
    total_durasi  = timedelta()
    hadir = alpa = izin_count = 0

    curr = dt_start
    while curr <= dt_end:
        absen = absensi_map.get(curr)
        izin  = izin_map.get(curr)
        if absen:
            absen.izin_staff = izin

        is_weekend = curr.weekday() >= 5   # Sabtu=5, Minggu=6
        is_future  = curr > today

        if absen and absen.status in ('masuk', 'pulang', 'terlambat', 'overtime'):
            hadir += 1
            if absen.waktu_masuk and absen.waktu_pulang:
                masuk  = datetime.combine(curr, absen.waktu_masuk)
                pulang = datetime.combine(curr, absen.waktu_pulang)
                if pulang > masuk:
                    total_durasi += (pulang - masuk)
        elif izin or (absen and absen.status_harian in ('I', 'L', 'DC')):
            izin_count += 1
        elif absen and absen.status_harian == 'A':
            alpa += 1
        elif not is_future and not is_weekend:
            # belum absen di hari kerja yang sudah lewat → dihitung alpa
            alpa += 1

        calendar_rows.append({
            'tanggal'    : curr,
            'is_today'   : curr == today,
            'is_weekend' : is_weekend,
            'is_libur'   : False,      # belum ada model hari libur, default False dulu
            'libur_nama' : None,
            'is_future'  : is_future,
            'absensi'    : absen,
            'izin'       : izin,
        })
        curr += timedelta(days=1)

    total_jam   = int(total_durasi.total_seconds() // 3600)
    total_menit = int((total_durasi.total_seconds() % 3600) // 60)
    total_kerja_str = f"{total_jam}j {total_menit}m"

    # ── Navigasi bulan ──
    bulan_ini_pertama = today.replace(day=1)
    is_current_month  = (tahun == today.year and bln == today.month)

    prev_month_date = (dt_start - timedelta(days=1)).replace(day=1)
    prev_bulan = prev_month_date.strftime('%Y-%m')

    if dt_start < bulan_ini_pertama:
        next_month_date = dt_end + timedelta(days=1)
        next_bulan      = next_month_date.strftime('%Y-%m')
        has_next_month  = True
    else:
        next_bulan     = None
        has_next_month = False

    return render(request, 'supervisor/absensi/staff_detail.html', {
        'staff'           : staff,
        'calendar_rows'   : calendar_rows,
        'bulan_sekarang'  : f"{tahun}-{bln:02d}",
        'bulan_display'   : dt_start.strftime('%B %Y'),
        'prev_bulan'      : prev_bulan,
        'next_bulan'      : next_bulan,
        'is_current_month': is_current_month,
        'has_next_month'  : has_next_month,
        'total_hari_kerja': sum(1 for r in calendar_rows if not r['is_weekend'] and not r['is_libur']),
        'monthly_stats'   : {
            'hadir'          : hadir,
            'alpa'           : alpa,
            'izin'           : izin_count,
            'total_kerja_str': total_kerja_str,
        },
        'supervisor': supervisor,
    })


# ─────────────────────────────────────────────
# Overtime — List
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def overtime_list(request):
    supervisor = _get_supervisor(request)
    ids        = _staff_ids(supervisor)

    overtime_qs = (
        Absensi.objects
        .filter(staff_id__in=ids, is_overtime=True)
        .select_related('staff', 'qr_pulang', 'overtime_reviewed_by')
        .order_by('-tanggal')
    )

    return render(request, 'supervisor/absensi/overtime_list.html', {
        'belum_review': overtime_qs.filter(overtime_status=OvertimeStatusChoices.BELUM_REVIEW),
        'sudah_review': overtime_qs.exclude(overtime_status=OvertimeStatusChoices.BELUM_REVIEW),
        'supervisor'  : supervisor,
    })


# ─────────────────────────────────────────────
# Overtime — Klasifikasi (AJAX POST)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
@require_POST
def overtime_klasifikasi(request, absensi_id):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    supervisor = _get_supervisor(request)
    absensi    = get_object_or_404(
        Absensi,
        id=absensi_id,
        staff_id__in=_staff_ids(supervisor),
        is_overtime=True,
    )

    keputusan = request.POST.get('keputusan', '').strip()
    if keputusan not in [OvertimeStatusChoices.PAID, OvertimeStatusChoices.UNPAID]:
        return JsonResponse({'ok': False, 'error': 'Pilihan tidak valid. Harus paid atau unpaid.'})

    absensi.overtime_status      = keputusan
    absensi.overtime_reviewed_by = request.user
    absensi.overtime_reviewed_at = timezone.now()
    absensi.save(update_fields=[
        'overtime_status',
        'overtime_reviewed_by',
        'overtime_reviewed_at',
    ])

    nama  = absensi.staff.nama_lengkap or absensi.staff.username
    label = '💰 Dibayar' if keputusan == OvertimeStatusChoices.PAID else '🔵 Tidak Dibayar'

    return JsonResponse({
        'ok'         : True,
        'message'    : f'Overtime {nama} → {label}',
        'keputusan'  : keputusan,
        'label'      : label,
        'absensi_id' : absensi.id,
        'reviewed_at': localtime(absensi.overtime_reviewed_at).strftime('%d/%m/%Y %H:%M'),
        'reviewed_by': request.user.nama_lengkap or request.user.username,
    })


# ─────────────────────────────────────────────
# Overtime — Update Status dari Rekap (AJAX POST)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
@require_POST
def api_update_overtime_status(request, pk):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    supervisor = _get_supervisor(request)
    absensi    = get_object_or_404(
        Absensi,
        pk=pk,
        staff_id__in=_staff_ids(supervisor),
    )

    if not absensi.is_overtime:
        return JsonResponse({'success': False, 'error': 'Absensi ini tidak memiliki overtime.'}, status=400)

    new_status = (request.POST.get('action') or request.POST.get('status', '')).strip()
    valid      = [c[0] for c in OvertimeStatusChoices.choices]

    if new_status not in valid:
        return JsonResponse({
            'success': False,
            'error'  : f'Status tidak valid. Pilihan: {", ".join(valid)}',
        }, status=400)

    absensi.overtime_status      = new_status
    absensi.overtime_reviewed_by = request.user
    absensi.overtime_reviewed_at = timezone.now()
    absensi.save(update_fields=[
        'overtime_status',
        'overtime_reviewed_by',
        'overtime_reviewed_at',
    ])

    label_map = {
        OvertimeStatusChoices.PAID        : '💰 Dibayar',
        OvertimeStatusChoices.UNPAID      : '🔵 Tidak Dibayar',
        OvertimeStatusChoices.BELUM_REVIEW: '⏱ Belum Review',
    }

    return JsonResponse({
        'success'    : True,
        'status'     : new_status,
        'label'      : label_map.get(new_status, new_status),
        'reviewed_at': localtime(absensi.overtime_reviewed_at).strftime('%d/%m/%Y %H:%M'),
        'reviewed_by': request.user.nama_lengkap or request.user.username,
    })


# ─────────────────────────────────────────────
# Izin — Review
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
@require_POST
def izin_review(request, pk):
    supervisor = _get_supervisor(request)
    ids        = _staff_ids(supervisor)
    izin       = get_object_or_404(IzinStaff, pk=pk, staff_id__in=ids)
    action     = request.POST.get('action')
    catatan    = request.POST.get('catatan', '').strip()

    if action not in ('approved', 'rejected', 'pending'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Action tidak valid.'}, status=400)
        messages.error(request, 'Action tidak valid.')
        return redirect(request.META.get('HTTP_REFERER', 'supervisor_absensi_rekap'))

    izin.status             = action
    izin.catatan_supervisor = catatan
    izin.direview_oleh      = request.user if action != 'pending' else None
    izin.direview_pada      = timezone.now() if action != 'pending' else None
    izin.save(update_fields=[
        'status', 'catatan_supervisor',
        'direview_oleh', 'direview_pada',
    ])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success'           : True,
            'new_status'        : izin.status,
            'new_status_display': izin.get_status_display(),
        })

    label = 'disetujui' if action == 'approved' else 'ditolak'
    messages.success(request, f'Izin {izin.staff.nama_lengkap} berhasil {label}.')
    return redirect(request.META.get('HTTP_REFERER', 'supervisor_absensi_rekap'))


def _lokasi_json(lokasi):
    """Helper — serialisasi lokasi ke dict untuk JsonResponse."""
    return {
        'ok'          : True,
        'pk'          : lokasi.pk,
        'nama'        : lokasi.nama,
        'latitude'    : float(lokasi.latitude),
        'longitude'   : float(lokasi.longitude),
        'radius_meter': lokasi.radius_meter,
        'is_active'   : lokasi.is_active,
    }


def _get_form_with_supervisor(request, form_class, *args, **kwargs):
    """
    Instantiate form dan inject supervisor (request.user) untuk
    validasi duplikat nama di clean_nama().
    """
    form = form_class(*args, **kwargs)
    form._supervisor = request.user
    return form


@supervisor_or_kepala_required
def lokasi_list(request):
    """List semua lokasi absensi milik supervisor."""
    supervisor = _get_supervisor(request)
    lokasi_qs  = (
        LokasiAbsensi.objects
        .filter(supervisor=supervisor)
        .order_by('nama')
    )
    return render(request, 'supervisor/lokasi/list.html', {
        'lokasi_qs' : lokasi_qs,
        'supervisor': supervisor,
    })


@supervisor_or_kepala_required
def lokasi_tambah(request):
    """Tambah lokasi absensi baru."""
    supervisor = _get_supervisor(request)
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = _get_form_with_supervisor(request, LokasiAbsensiForm, request.POST)
        
        if form.is_valid():
            lokasi            = form.save(commit=False)
            lokasi.supervisor = supervisor
            lokasi.save()
            
            if is_ajax:
                return JsonResponse(_lokasi_json(lokasi))
            
            messages.success(request, f'Lokasi "{lokasi.nama}" berhasil ditambahkan.')
            return redirect('supervisor_lokasi_list')
        else:
            if is_ajax:
                return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
    else:
        form = _get_form_with_supervisor(request, LokasiAbsensiForm)

    return render(request, 'supervisor/lokasi/form.html', {
        'form'      : form,
        'mode'      : 'tambah',
        'supervisor': supervisor,
         'koordinat_decimal_places': KOORDINAT_DECIMAL_PLACES,
        'radius_min': RADIUS_MIN,
        'radius_max': RADIUS_MAX,
        'radius_default': RADIUS_DEFAULT,
    })


@supervisor_or_kepala_required
def lokasi_edit(request, pk):
    """Edit lokasi absensi existing."""
    supervisor = _get_supervisor(request)
    lokasi     = get_object_or_404(LokasiAbsensi, pk=pk, supervisor=supervisor)
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = _get_form_with_supervisor(
            request, 
            LokasiAbsensiForm, 
            request.POST, 
            instance=lokasi
        )
        
        if form.is_valid():
            lokasi = form.save()  # Assign hasil save untuk data terbaru
            
            if is_ajax:
                return JsonResponse(_lokasi_json(lokasi))
            
            messages.success(request, f'Lokasi "{lokasi.nama}" berhasil diperbarui.')
            return redirect('supervisor_lokasi_list')
        else:
            if is_ajax:
                return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
    else:
        form = _get_form_with_supervisor(request, LokasiAbsensiForm, instance=lokasi)

    return render(request, 'supervisor/lokasi/form.html', {
        'form'      : form,
        'lokasi'    : lokasi,
        'mode'      : 'edit',
        'supervisor': supervisor,
        'koordinat_decimal_places': KOORDINAT_DECIMAL_PLACES,
        'radius_min': RADIUS_MIN,
        'radius_max': RADIUS_MAX,
        'radius_default': RADIUS_DEFAULT,
    })


@supervisor_or_kepala_required
@require_POST
def lokasi_hapus(request, pk):
    """Hapus lokasi absensi (dengan validasi QR aktif)."""
    supervisor = _get_supervisor(request)
    lokasi     = get_object_or_404(LokasiAbsensi, pk=pk, supervisor=supervisor)
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Cek apakah lokasi masih aktif di QR hari ini
    qr_aktif = QRAbsensi.objects.filter(
        lokasi    = lokasi,
        tanggal   = timezone.localdate(),
        is_active = True,
    ).exists()

    if qr_aktif:
        msg = 'Lokasi masih digunakan oleh QR aktif hari ini. Nonaktifkan QR terlebih dahulu.'
        if is_ajax:
            return JsonResponse({'ok': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect('supervisor_lokasi_list')

    nama = lokasi.nama
    lokasi.delete()

    if is_ajax:
        return JsonResponse({'ok': True, 'pk': pk, 'nama': nama})
    
    messages.success(request, f'Lokasi "{nama}" berhasil dihapus.')
    return redirect('supervisor_lokasi_list')


@supervisor_or_kepala_required
@require_POST
def lokasi_toggle_aktif(request, pk):
    """Toggle is_active status lokasi (AJAX only)."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not is_ajax:
        return JsonResponse({'ok': False, 'error': 'AJAX only.'}, status=400)

    supervisor       = _get_supervisor(request)
    lokasi           = get_object_or_404(LokasiAbsensi, pk=pk, supervisor=supervisor)
    lokasi.is_active = not lokasi.is_active
    lokasi.save(update_fields=['is_active'])

    return JsonResponse({
        'ok'       : True,
        'is_active': lokasi.is_active,
        'label'    : 'Aktif' if lokasi.is_active else 'Nonaktif',
    })


@supervisor_or_kepala_required
def lokasi_detail_json(request, pk):
    """Get detail lokasi as JSON (AJAX only)."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not is_ajax:
        return JsonResponse({'ok': False, 'error': 'AJAX only.'}, status=400)

    supervisor = _get_supervisor(request)
    lokasi     = get_object_or_404(LokasiAbsensi, pk=pk, supervisor=supervisor)
    return JsonResponse(_lokasi_json(lokasi))