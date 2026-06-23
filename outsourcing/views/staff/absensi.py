from datetime import datetime

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.utils.timezone import localtime
from django.views.decorators.http import require_POST
from django.db import transaction

from outsourcing.decorators import staff_required
from outsourcing.models import (
    QRAbsensi, QRTypeChoices,
    Absensi, AbsensiStatusChoices, StatusHarianChoices,
    KeteranganAbsensi, TipeKeteranganChoices, StatusKeteranganChoices,
    JadwalKerja,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_jadwal_hari_ini(supervisor, tanggal):
    return JadwalKerja.objects.filter(
        supervisor=supervisor,
        hari=tanggal.weekday(),
        is_active=True,
    ).first()


def _cek_lokasi(qr, lat, lon):
    """Return (ok: bool, error_msg: str|None). QR tanpa lokasi = skip validasi."""
    lokasi = qr.lokasi
    if not lokasi or not lat or not lon:
        return True, None
    dalam_radius, jarak = lokasi.validasi_koordinat(lat, lon)
    if not dalam_radius:
        return False, (
            f'Kamu berada {jarak:.0f}m dari {lokasi.nama} '
            f'(radius maksimal {lokasi.radius_meter}m). Mendekat ke lokasi.'
        )
    return True, None


# ─────────────────────────────────────────────
# SCAN — Entry point (GET, public-ish untuk staff login)
# ─────────────────────────────────────────────

@staff_required
def qr_scan_landing(request, token):
    """
    Staff scan / buka link QR → halaman ini.
    qr.tipe (masuk/pulang) sudah menentukan aksi — staff tidak perlu pilih manual.
    """
    qr = get_object_or_404(QRAbsensi, token=token)
    valid, err = qr.is_valid()
    if not valid:
        return render(request, 'absensi/scan_error.html', {'pesan': err})

    hari_ini = timezone.localdate()
    absensi  = Absensi.objects.filter(staff=request.user, tanggal=hari_ini).first()
    jadwal   = _get_jadwal_hari_ini(qr.supervisor, hari_ini)

    sudah_masuk  = bool(absensi and absensi.sudah_masuk)
    sudah_pulang = bool(absensi and absensi.sudah_pulang)

    # Validasi awal supaya UI bisa langsung tampilkan pesan tanpa nunggu POST gagal
    blokir_pesan = None
    if qr.tipe == QRTypeChoices.MASUK and sudah_masuk:
        blokir_pesan = f"Kamu sudah absen masuk pukul {localtime(absensi.waktu_masuk).strftime('%H:%M')}."
    elif qr.tipe == QRTypeChoices.PULANG and not sudah_masuk:
        blokir_pesan = "Kamu belum absen masuk hari ini. Scan QR Masuk dulu."
    elif qr.tipe == QRTypeChoices.PULANG and sudah_pulang:
        blokir_pesan = f"Kamu sudah absen pulang pukul {localtime(absensi.waktu_pulang).strftime('%H:%M')}."

    context = {
        'qr'            : qr,
        'absensi'       : absensi,
        'jadwal'        : jadwal,
        'jam_masuk_str' : jadwal.jam_masuk.strftime('%H:%M') if jadwal else None,
        'jam_pulang_str': jadwal.jam_pulang.strftime('%H:%M') if jadwal else None,
        'lokasi'        : qr.lokasi,
        'blokir_pesan'  : blokir_pesan,
    }
    return render(request, 'staff/absensi/scan.html', context)


@staff_required
def qr_scan_page(request):
    """Halaman kamera — decode token QR lalu redirect ke qr_scan_landing."""
    return render(request, 'staff/absensi/qr_scan_page.html')


# ─────────────────────────────────────────────
# PROSES — AJAX POST, cabang otomatis dari qr.tipe
# ─────────────────────────────────────────────

@staff_required
@require_POST
def absensi_proses(request, token):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    qr = get_object_or_404(QRAbsensi, token=token)
    valid, err = qr.is_valid()
    if not valid:
        return JsonResponse({'ok': False, 'error': err})

    if qr.tipe == QRTypeChoices.MASUK:
        return _proses_masuk(request, qr)
    return _proses_pulang(request, qr)


def _proses_masuk(request, qr):
    staff    = request.user
    hari_ini = timezone.localdate()
    now      = timezone.now()
    lat      = request.POST.get('lat')
    lon      = request.POST.get('lon')

    absensi, _ = Absensi.objects.get_or_create(
        staff=staff, tanggal=hari_ini,
        defaults={'status': AbsensiStatusChoices.BELUM_ABSEN, 'status_harian': StatusHarianChoices.HADIR},
    )
    if absensi.sudah_masuk:
        waktu = localtime(absensi.waktu_masuk).strftime('%H:%M')
        return JsonResponse({'ok': False, 'error': f'Kamu sudah absen masuk pukul {waktu}.'})

    ok_lokasi, err_lokasi = _cek_lokasi(qr, lat, lon)
    if not ok_lokasi:
        return JsonResponse({'ok': False, 'error': err_lokasi})

    jadwal   = _get_jadwal_hari_ini(qr.supervisor, hari_ini)
    now_time = localtime(now).time()

    if jadwal is None:
        return JsonResponse({
            'ok': True, 'perlu_alasan': True,
            'tipe_alasan'  : TipeKeteranganChoices.DI_LUAR_JADWAL,
            'selisih_menit': 0,
            'pesan': 'Hari ini tidak ada jadwal kerja resmi. Isi alasan kehadiran kamu.',
        })

    selisih = int(
        (datetime.combine(hari_ini, now_time) - datetime.combine(hari_ini, jadwal.jam_masuk)).total_seconds() / 60
    )
    if selisih > 0:
        return JsonResponse({
            'ok': True, 'perlu_alasan': True,
            'tipe_alasan'  : TipeKeteranganChoices.TERLAMBAT,
            'selisih_menit': selisih,
            'pesan': f'Kamu terlambat {selisih} menit. Isi alasan keterlambatan.',
        })

    _simpan_masuk(absensi, qr, now, lat, lon)
    return JsonResponse({
        'ok'      : True,
        'pesan'   : f'Absen masuk berhasil pukul {localtime(now).strftime("%H:%M")}.',
        'redirect': '/staff/absensi/riwayat/',
    })


def _proses_pulang(request, qr):
    staff    = request.user
    hari_ini = timezone.localdate()
    now      = timezone.now()
    lat      = request.POST.get('lat')
    lon      = request.POST.get('lon')

    absensi = Absensi.objects.filter(staff=staff, tanggal=hari_ini).first()
    if not absensi or not absensi.sudah_masuk:
        return JsonResponse({'ok': False, 'error': 'Kamu belum absen masuk hari ini.'})
    if absensi.sudah_pulang:
        waktu = localtime(absensi.waktu_pulang).strftime('%H:%M')
        return JsonResponse({'ok': False, 'error': f'Kamu sudah absen pulang pukul {waktu}.'})

    ok_lokasi, err_lokasi = _cek_lokasi(qr, lat, lon)
    if not ok_lokasi:
        return JsonResponse({'ok': False, 'error': err_lokasi})

    jadwal   = _get_jadwal_hari_ini(qr.supervisor, hari_ini)
    now_time = localtime(now).time()

    if jadwal is None:
        return JsonResponse({
            'ok': True, 'perlu_alasan': True,
            'tipe_alasan'  : TipeKeteranganChoices.DI_LUAR_JADWAL,
            'selisih_menit': 0,
            'pesan': 'Hari ini tidak ada jadwal kerja resmi. Isi alasan kepulangan kamu.',
        })

    selisih = int(
        (datetime.combine(hari_ini, jadwal.jam_pulang) - datetime.combine(hari_ini, now_time)).total_seconds() / 60
    )
    if selisih > 0:
        return JsonResponse({
            'ok': True, 'perlu_alasan': True,
            'tipe_alasan'  : TipeKeteranganChoices.PULANG_CEPAT,
            'selisih_menit': selisih,
            'pesan': f'Kamu pulang {selisih} menit lebih awal. Isi alasan.',
        })

    _simpan_pulang(absensi, qr, now, lat, lon)
    overtime_menit = absensi.hitung_overtime_menit()
    pesan = f'Absen pulang berhasil pukul {localtime(now).strftime("%H:%M")}.'
    if overtime_menit:
        pesan += f' Overtime {overtime_menit} menit tercatat, menunggu review supervisor.'

    return JsonResponse({'ok': True, 'pesan': pesan, 'redirect': '/staff/absensi/riwayat/'})


# ─────────────────────────────────────────────
# KONFIRMASI — popup alasan (terlambat / pulang cepat / luar jadwal)
# ─────────────────────────────────────────────

@staff_required
@require_POST
def absensi_konfirmasi(request, token):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    qr = get_object_or_404(QRAbsensi, token=token)
    valid, err = qr.is_valid()
    if not valid:
        return JsonResponse({'ok': False, 'error': err})

    tipe   = request.POST.get('tipe')
    alasan = (request.POST.get('alasan') or '').strip()
    try:
        selisih_menit = int(request.POST.get('selisih_menit') or 0)
    except ValueError:
        selisih_menit = 0

    if tipe not in TipeKeteranganChoices.values:
        return JsonResponse({'ok': False, 'errors': {'tipe': ['Tipe keterangan tidak valid.']}}, status=400)
    if not alasan:
        return JsonResponse({'ok': False, 'errors': {'alasan': ['Alasan wajib diisi.']}}, status=400)

    staff    = request.user
    hari_ini = timezone.localdate()
    now      = timezone.now()
    lat      = request.POST.get('lat')
    lon      = request.POST.get('lon')

    with transaction.atomic():
        if qr.tipe == QRTypeChoices.MASUK:
            absensi, _ = Absensi.objects.get_or_create(
                staff=staff, tanggal=hari_ini,
                defaults={'status': AbsensiStatusChoices.BELUM_ABSEN, 'status_harian': StatusHarianChoices.HADIR},
            )
            if absensi.sudah_masuk:
                return JsonResponse({'ok': False, 'error': 'Kamu sudah absen masuk hari ini.'})
            _simpan_masuk(absensi, qr, now, lat, lon, tipe_keterangan=tipe)
            pesan = 'Absen masuk berhasil. Alasan kamu menunggu persetujuan supervisor.'
        else:
            absensi = get_object_or_404(Absensi, staff=staff, tanggal=hari_ini)
            if not absensi.sudah_masuk:
                return JsonResponse({'ok': False, 'error': 'Kamu belum absen masuk.'})
            if absensi.sudah_pulang:
                return JsonResponse({'ok': False, 'error': 'Kamu sudah absen pulang hari ini.'})
            _simpan_pulang(absensi, qr, now, lat, lon, tipe_keterangan=tipe)
            pesan = 'Absen pulang berhasil. Alasan kamu menunggu persetujuan supervisor.'

        KeteranganAbsensi.objects.update_or_create(
            absensi=absensi, tipe=tipe,
            defaults={
                'alasan'       : alasan,
                'selisih_menit': selisih_menit,
                'status'       : StatusKeteranganChoices.PENDING,
            },
        )

    return JsonResponse({'ok': True, 'pesan': pesan, 'redirect': '/staff/absensi/riwayat/'})


# ─────────────────────────────────────────────
# Helpers — simpan ke Absensi
# ─────────────────────────────────────────────

def _simpan_masuk(absensi, qr, now, lat, lon, tipe_keterangan=None):
    absensi.qr_masuk    = qr
    absensi.waktu_masuk = now
    if lat: absensi.lat_masuk = lat
    if lon: absensi.lon_masuk = lon

    absensi.status = (
        AbsensiStatusChoices.TERLAMBAT
        if tipe_keterangan == TipeKeteranganChoices.TERLAMBAT
        else AbsensiStatusChoices.MASUK
    )
    absensi.save(update_fields=['qr_masuk', 'waktu_masuk', 'lat_masuk', 'lon_masuk', 'status', 'diubah_pada'])


def _simpan_pulang(absensi, qr, now, lat, lon, tipe_keterangan=None):
    absensi.qr_pulang    = qr
    absensi.waktu_pulang = now
    if lat: absensi.lat_pulang = lat
    if lon: absensi.lon_pulang = lon

    if tipe_keterangan == TipeKeteranganChoices.PULANG_CEPAT:
        absensi.izin_pulang_awal = True

    absensi.update_overtime()
    absensi.status = AbsensiStatusChoices.OVERTIME if absensi.is_overtime else AbsensiStatusChoices.PULANG

    absensi.save(update_fields=[
        'qr_pulang', 'waktu_pulang', 'lat_pulang', 'lon_pulang',
        'status', 'is_overtime', 'overtime_status',
        'overtime_reviewed_by', 'overtime_reviewed_at',
        'izin_pulang_awal', 'diubah_pada',
    ])


# ─────────────────────────────────────────────
# RIWAYAT & API STATUS (tidak berubah dari sebelumnya)
# ─────────────────────────────────────────────

@staff_required
def absensi_riwayat(request):
    from outsourcing.models import IzinStaff

    today        = timezone.localdate()
    bulan_filter = request.GET.get('bulan', '').strip()
    if not bulan_filter:
        bulan_filter = today.strftime('%Y-%m')

    try:
        tahun, bulan = map(int, bulan_filter.split('-'))
    except (ValueError, AttributeError):
        tahun, bulan = today.year, today.month
        bulan_filter = today.strftime('%Y-%m')

    absensi_qs = (
        Absensi.objects
        .filter(staff=request.user, tanggal__year=tahun, tanggal__month=bulan)
        .select_related(
            'qr_masuk', 'qr_masuk__supervisor',
            'qr_pulang', 'qr_pulang__supervisor',
            'overtime_reviewed_by',
        )
        .order_by('-tanggal')
    )

    bulan_tersedia = (
        Absensi.objects
        .filter(staff=request.user)
        .dates('tanggal', 'month', order='DESC')
    )

    izin_qs = (
        IzinStaff.objects
        .filter(staff=request.user)
        .order_by('-dibuat_pada')
    )

    active_tab       = request.GET.get('tab', 'absensi')
    ada_izin_pending = izin_qs.filter(status='pending').exists()

    return render(request, 'staff/absensi/riwayat.html', {
        'absensi_qs'      : absensi_qs,
        'total'           : absensi_qs.count(),
        'total_masuk'     : absensi_qs.filter(waktu_masuk__isnull=False).count(),
        'total_pulang'    : absensi_qs.filter(waktu_pulang__isnull=False).count(),
        'total_overtime'  : absensi_qs.filter(is_overtime=True).count(),
        'bulan_filter'    : bulan_filter,
        'bulan_tersedia'  : bulan_tersedia,
        'bulan_aktif'     : f"{tahun}-{bulan:02d}",
        'izin_qs'         : izin_qs,
        'active_tab'      : active_tab,
        'ada_izin_pending': ada_izin_pending,
    })


@staff_required
def api_today_status(request):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    hari_ini = timezone.localdate()

    try:
        absensi_hari_ini = Absensi.objects.get(staff=request.user, tanggal=hari_ini)
        status_display   = absensi_hari_ini.get_status_display()
        last_checkin      = localtime(absensi_hari_ini.waktu_masuk).strftime('%H:%M') if absensi_hari_ini.waktu_masuk else None
    except Absensi.DoesNotExist:
        status_display = 'Belum Absen'
        last_checkin   = None

    month_start      = hari_ini.replace(day=1)
    this_month_count = Absensi.objects.filter(
        staff        = request.user,
        tanggal__gte = month_start,
        tanggal__lte = hari_ini,
    ).count()

    return JsonResponse({
        'status_display'  : status_display,
        'last_checkin'    : last_checkin,
        'this_month_count': this_month_count,
    })