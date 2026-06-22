"""
views/absensi.py
================
Views untuk modul Absensi — match 100% dengan model final.

Flow Scan (per kesepakatan):
  MASUK  → cek QR aktif → cek lokasi GPS → cek sudah masuk? →
           bandingkan now() vs JadwalKerja.jam_masuk →
           terlambat? → simpan KeteranganAbsensi (PENDING) →
           simpan Absensi(waktu_masuk, status)

  PULANG → cek QR aktif → cek lokasi GPS → cek sudah masuk? →
           bandingkan now() vs JadwalKerja.jam_pulang →
           pulang cepat? → simpan KeteranganAbsensi (PENDING) →
           hitung overtime → simpan Absensi(waktu_pulang)

  Tidak ada jadwal hari itu → scan boleh, tapi wajib isi alasan
  (tipe=DI_LUAR_JADWAL), langsung pending approval supervisor.
"""

import qrcode
import io
import base64
from calendar import monthrange
from datetime import datetime, time, date, timedelta, timezone as dt_timezone

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.utils.timezone import localtime
from django.views.decorators.http import require_POST, require_GET
from django.db import transaction
from django.db.models import Q

from outsourcing.constants import (
    KOORDINAT_DECIMAL_PLACES,
    RADIUS_DEFAULT, RADIUS_MAX, RADIUS_MIN,
)
from outsourcing.decorators import supervisor_or_kepala_required, staff_required
from outsourcing.models import (
    QRAbsensi, QRTypeChoices,
    Absensi, AbsensiStatusChoices, StatusHarianChoices, OvertimeStatusChoices,
    KeteranganAbsensi, TipeKeteranganChoices, StatusKeteranganChoices,
    JadwalKerja,
    StaffSupervisor,
    IzinStaff, StatusIzinChoices,
    LokasiAbsensi,
    User,
)
from outsourcing.forms import (
    QRAbsensiForm,
    AbsenMasukForm,
    AbsenPulangForm,
    KeteranganAbsensiForm,
    ReviewKeteranganForm,
    IzinStaffForm,
    LokasiAbsensiForm,
    JadwalKerjaForm,
)


# ─────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────

def _qr_to_base64(url: str) -> str:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def _get_supervisor(request):
    """Kepala bisa act-as supervisor via request.supervisor_context."""
    return getattr(request, 'supervisor_context', request.user)


def _staff_ids(supervisor):
    return StaffSupervisor.objects.filter(
        supervisor=supervisor,
        is_active=True,
    ).values_list('staff_id', flat=True)


def _lokasi_json(lokasi) -> dict:
    return {
        'ok'          : True,
        'pk'          : lokasi.pk,
        'nama'        : lokasi.nama,
        'latitude'    : float(lokasi.latitude),
        'longitude'   : float(lokasi.longitude),
        'radius_meter': lokasi.radius_meter,
        'is_active'   : lokasi.is_active,
    }


def _get_jadwal_hari_ini(supervisor) -> JadwalKerja | None:
    """Ambil jadwal aktif supervisor untuk hari ini (weekday 0=Senin)."""
    hari = timezone.localdate().weekday()
    return JadwalKerja.objects.filter(
        supervisor=supervisor,
        hari=hari,
        is_active=True,
    ).first()


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
        .order_by('tipe')              # tanggal sudah dihapus dari model
    )
    return render(request, 'supervisor/absensi/qr_list.html', {
        'qr_list'   : qr_qs,
        'supervisor': supervisor,
    })


# ─────────────────────────────────────────────
# QR — Generate / Kelola (Supervisor)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def qr_kelola(request):
    """
    Halaman kelola QR permanen supervisor.

    GET  → tampilkan QR masuk & pulang yang sudah ada (atau buat baru via form).
    POST AJAX → update lokasi QR yang sudah ada, atau create get_or_create.
    """
    supervisor = _get_supervisor(request)

    # Ambil QR permanen (paling 1 per tipe per supervisor)
    qr_masuk  = QRAbsensi.objects.filter(supervisor=supervisor, tipe=QRTypeChoices.MASUK).first()
    qr_pulang = QRAbsensi.objects.filter(supervisor=supervisor, tipe=QRTypeChoices.PULANG).first()

    lokasi_list = LokasiAbsensi.objects.filter(
        supervisor=supervisor, is_active=True,
    ).order_by('nama')

    # ── AJAX POST — update lokasi ─────────────────────────
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        lokasi_id = request.POST.get('lokasi_id', '').strip()

        lokasi_obj = None
        if lokasi_id and lokasi_id != '0':
            try:
                lokasi_obj = LokasiAbsensi.objects.get(
                    pk=lokasi_id, supervisor=supervisor, is_active=True,
                )
            except LokasiAbsensi.DoesNotExist:
                return JsonResponse({'ok': False, 'error': 'Lokasi tidak ditemukan.'})

        with transaction.atomic():
            qr_masuk, _ = QRAbsensi.objects.get_or_create(
                supervisor=supervisor,
                tipe=QRTypeChoices.MASUK,
                defaults={'lokasi': lokasi_obj},
            )
            if not _:                          # sudah ada → update lokasi
                qr_masuk.lokasi = lokasi_obj
                qr_masuk.save(update_fields=['lokasi', 'diperbarui'])

            qr_pulang, _ = QRAbsensi.objects.get_or_create(
                supervisor=supervisor,
                tipe=QRTypeChoices.PULANG,
                defaults={'lokasi': lokasi_obj},
            )
            if not _:
                qr_pulang.lokasi = lokasi_obj
                qr_pulang.save(update_fields=['lokasi', 'diperbarui'])

            # Siapkan record Absensi hari ini untuk semua staff aktif
            hari_ini  = timezone.localdate()
            staff_ids = list(_staff_ids(supervisor))
            existing  = set(
                Absensi.objects
                .filter(staff_id__in=staff_ids, tanggal=hari_ini)
                .values_list('staff_id', flat=True)
            )
            bulk = [
                Absensi(
                    staff_id      = sid,
                    tanggal       = hari_ini,
                    status        = AbsensiStatusChoices.BELUM_ABSEN,
                    status_harian = StatusHarianChoices.HADIR,
                )
                for sid in staff_ids if sid not in existing
            ]
            if bulk:
                Absensi.objects.bulk_create(bulk, ignore_conflicts=True)

        url_masuk  = request.build_absolute_uri(f'/absensi/scan/{qr_masuk.token}/')
        url_pulang = request.build_absolute_uri(f'/absensi/scan/{qr_pulang.token}/')

        return JsonResponse({
            'ok'             : True,
            'qr_masuk_b64'   : _qr_to_base64(url_masuk),
            'qr_pulang_b64'  : _qr_to_base64(url_pulang),
            'url_masuk'      : url_masuk,
            'url_pulang'     : url_pulang,
            'staff_disiapkan': len(bulk),
            'lokasi_nama'    : lokasi_obj.nama if lokasi_obj else None,
            'lokasi_radius'  : lokasi_obj.radius_meter if lokasi_obj else None,
        })

    # ── GET ───────────────────────────────────────────────
    url_masuk = url_pulang = qr_masuk_b64 = qr_pulang_b64 = None

    if qr_masuk and qr_masuk.is_active:
        url_masuk    = request.build_absolute_uri(f'/absensi/scan/{qr_masuk.token}/')
        qr_masuk_b64 = _qr_to_base64(url_masuk)

    if qr_pulang and qr_pulang.is_active:
        url_pulang    = request.build_absolute_uri(f'/absensi/scan/{qr_pulang.token}/')
        qr_pulang_b64 = _qr_to_base64(url_pulang)

    return render(request, 'supervisor/absensi/qr_kelola.html', {
        'qr_masuk'     : qr_masuk,
        'qr_pulang'    : qr_pulang,
        'qr_masuk_b64' : qr_masuk_b64,
        'qr_pulang_b64': qr_pulang_b64,
        'url_masuk'    : url_masuk,
        'url_pulang'   : url_pulang,
        'lokasi_list'  : lokasi_list,
        'lokasi_aktif' : qr_masuk.lokasi if qr_masuk else None,
        'supervisor'   : supervisor,
    })


# ─────────────────────────────────────────────
# QR — Toggle Aktif (AJAX POST)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
@require_POST
def qr_toggle_aktif(request, pk):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    supervisor = _get_supervisor(request)
    qr_obj     = get_object_or_404(QRAbsensi, pk=pk, supervisor=supervisor)
    qr_obj.is_active = not qr_obj.is_active
    qr_obj.save(update_fields=['is_active', 'diperbarui'])

    return JsonResponse({
        'ok'      : True,
        'is_active': qr_obj.is_active,
        'label'   : 'Aktif' if qr_obj.is_active else 'Nonaktif',
        'message' : f'QR {qr_obj.get_tipe_display()} → {"diaktifkan" if qr_obj.is_active else "dinonaktifkan"}.',
    })


# ─────────────────────────────────────────────
# SCAN — Entry point staff (GET publik)
# ─────────────────────────────────────────────

@staff_required
def absensi_scan(request, token):
    """
    Staff membuka URL QR → halaman scan muncul.
    Validasi QR aktif di sini; proses absen di view terpisah (POST).
    """
    qr = get_object_or_404(QRAbsensi, token=token)

    valid, err = qr.is_valid()
    if not valid:
        return render(request, 'absensi/scan_error.html', {'pesan': err})

    hari_ini = timezone.localdate()
    absensi  = Absensi.objects.filter(staff=request.user, tanggal=hari_ini).first()

    # Tentukan apakah sudah masuk / sudah pulang
    sudah_masuk  = absensi and absensi.sudah_masuk
    sudah_pulang = absensi and absensi.sudah_pulang

    # Cek apakah perlu popup keterangan nanti (dihitung di client)
    # — supervisor bisa null kalau QR baru dibuat dan supervisor belum punya jadwal
    supervisor   = qr.supervisor
    jadwal       = JadwalKerja.objects.filter(
        supervisor=supervisor,
        hari=hari_ini.weekday(),
        is_active=True,
    ).first()

    context = {
        'qr'            : qr,
        'absensi'       : absensi,
        'sudah_masuk'   : sudah_masuk,
        'sudah_pulang'  : sudah_pulang,
        'jadwal'        : jadwal,
        'ada_jadwal'    : jadwal is not None,
        'jam_masuk_str' : jadwal.jam_masuk.strftime('%H:%M') if jadwal else None,
        'jam_pulang_str': jadwal.jam_pulang.strftime('%H:%M') if jadwal else None,
        'lokasi'        : qr.lokasi,
    }
    return render(request, 'absensi/scan.html', context)


# ─────────────────────────────────────────────
# SCAN — Proses Masuk (AJAX POST)
# ─────────────────────────────────────────────

@staff_required
@require_POST
def absensi_proses_masuk(request, token):
    """
    Diproses via AJAX dari halaman scan.
    Response JSON — template menangani popup/redirect.
    """
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    qr = get_object_or_404(QRAbsensi, token=token)

    # 1. Cek QR aktif
    valid, err = qr.is_valid()
    if not valid:
        return JsonResponse({'ok': False, 'error': err})

    staff    = request.user
    hari_ini = timezone.localdate()
    now      = timezone.now()

    # 2. Cek sudah absen masuk hari ini
    absensi, _ = Absensi.objects.get_or_create(
        staff=staff, tanggal=hari_ini,
        defaults={
            'status'       : AbsensiStatusChoices.BELUM_ABSEN,
            'status_harian': StatusHarianChoices.HADIR,
            'qr_masuk'     : qr,
        },
    )
    if absensi.sudah_masuk:
        waktu = localtime(absensi.waktu_masuk).strftime('%H:%M')
        return JsonResponse({'ok': False, 'error': f'Kamu sudah absen masuk pukul {waktu}.'})

    # 3. Validasi GPS
    lat = request.POST.get('lat')
    lon = request.POST.get('lon')
    lokasi = qr.lokasi
    if lokasi and lat and lon:
        dalam_radius, jarak = lokasi.validasi_koordinat(lat, lon)
        if not dalam_radius:
            return JsonResponse({
                'ok'   : False,
                'error': (
                    f'Kamu berada {jarak:.0f}m dari lokasi absensi '
                    f'(radius: {lokasi.radius_meter}m). Mendekat ke {lokasi.nama}.'
                ),
            })

    # 4. Cek jadwal — tentukan apakah terlambat / luar jadwal
    supervisor = qr.supervisor
    jadwal = JadwalKerja.objects.filter(
        supervisor=supervisor,
        hari=hari_ini.weekday(),
        is_active=True,
    ).first()

    now_time = localtime(now).time()

    if jadwal is None:
        # Tidak ada jadwal → luar jadwal, perlu alasan
        return JsonResponse({
            'ok'          : True,
            'perlu_alasan': True,
            'tipe_alasan' : TipeKeteranganChoices.DI_LUAR_JADWAL,
            'selisih_menit': 0,
            'pesan'       : 'Hari ini di luar jadwal kerja resmi. Isi alasan kehadiran.',
        })

    selisih = int(
        (
            datetime.combine(hari_ini, now_time) -
            datetime.combine(hari_ini, jadwal.jam_masuk)
        ).total_seconds() / 60
    )

    if selisih > 0:
        # Terlambat → perlu alasan sebelum disimpan
        return JsonResponse({
            'ok'           : True,
            'perlu_alasan' : True,
            'tipe_alasan'  : TipeKeteranganChoices.TERLAMBAT,
            'selisih_menit': selisih,
            'pesan'        : f'Kamu terlambat {selisih} menit. Isi alasan terlambat.',
        })

    # 5. Simpan absen masuk (tepat waktu)
    _simpan_masuk(absensi, qr, now, lat, lon)

    return JsonResponse({
        'ok'     : True,
        'pesan'  : f'Absen masuk berhasil pukul {localtime(now).strftime("%H:%M")}.',
        'redirect': '/absensi/sukses/',
    })


@staff_required
@require_POST
def absensi_konfirmasi_masuk(request, token):
    """
    Dipanggil setelah staff mengisi popup alasan (terlambat / luar jadwal).
    Menerima alasan, simpan KeteranganAbsensi + Absensi.
    """
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    qr = get_object_or_404(QRAbsensi, token=token)
    valid, err = qr.is_valid()
    if not valid:
        return JsonResponse({'ok': False, 'error': err})

    form = KeteranganAbsensiForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

    staff    = request.user
    hari_ini = timezone.localdate()
    now      = timezone.now()
    lat      = request.POST.get('lat')
    lon      = request.POST.get('lon')

    with transaction.atomic():
        absensi, _ = Absensi.objects.get_or_create(
            staff=staff, tanggal=hari_ini,
            defaults={
                'status'       : AbsensiStatusChoices.BELUM_ABSEN,
                'status_harian': StatusHarianChoices.HADIR,
            },
        )
        if absensi.sudah_masuk:
            return JsonResponse({'ok': False, 'error': 'Kamu sudah absen masuk hari ini.'})

        _simpan_masuk(absensi, qr, now, lat, lon)

        tipe          = form.cleaned_data['tipe']
        alasan        = form.cleaned_data['alasan']
        selisih_menit = form.cleaned_data.get('selisih_menit') or 0

        KeteranganAbsensi.objects.create(
            absensi      = absensi,
            tipe         = tipe,
            alasan       = alasan,
            selisih_menit= selisih_menit,
            status       = StatusKeteranganChoices.PENDING,
        )

    return JsonResponse({
        'ok'     : True,
        'pesan'  : f'Absen masuk berhasil. Alasan kamu menunggu persetujuan supervisor.',
        'redirect': '/absensi/sukses/',
    })


def _simpan_masuk(absensi: Absensi, qr: QRAbsensi, now, lat, lon):
    """Helper — update field masuk dan tentukan status."""
    absensi.qr_masuk    = qr
    absensi.waktu_masuk = now
    if lat:
        absensi.lat_masuk = lat
    if lon:
        absensi.lon_masuk = lon
    absensi.status = AbsensiStatusChoices.MASUK
    absensi.save(update_fields=[
        'qr_masuk', 'waktu_masuk', 'lat_masuk', 'lon_masuk', 'status', 'diubah_pada',
    ])


# ─────────────────────────────────────────────
# SCAN — Proses Pulang (AJAX POST)
# ─────────────────────────────────────────────

@staff_required
@require_POST
def absensi_proses_pulang(request, token):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    qr = get_object_or_404(QRAbsensi, token=token)
    valid, err = qr.is_valid()
    if not valid:
        return JsonResponse({'ok': False, 'error': err})

    staff    = request.user
    hari_ini = timezone.localdate()
    now      = timezone.now()

    # 1. Wajib sudah masuk
    absensi = Absensi.objects.filter(staff=staff, tanggal=hari_ini).first()
    if not absensi or not absensi.sudah_masuk:
        return JsonResponse({'ok': False, 'error': 'Kamu belum absen masuk hari ini.'})
    if absensi.sudah_pulang:
        waktu = localtime(absensi.waktu_pulang).strftime('%H:%M')
        return JsonResponse({'ok': False, 'error': f'Kamu sudah absen pulang pukul {waktu}.'})

    # 2. Validasi GPS
    lat    = request.POST.get('lat')
    lon    = request.POST.get('lon')
    lokasi = qr.lokasi
    if lokasi and lat and lon:
        dalam_radius, jarak = lokasi.validasi_koordinat(lat, lon)
        if not dalam_radius:
            return JsonResponse({
                'ok'   : False,
                'error': (
                    f'Kamu berada {jarak:.0f}m dari lokasi absensi '
                    f'(radius: {lokasi.radius_meter}m). Mendekat ke {lokasi.nama}.'
                ),
            })

    # 3. Cek jadwal — tentukan pulang cepat / luar jadwal
    supervisor = qr.supervisor
    jadwal = JadwalKerja.objects.filter(
        supervisor=supervisor,
        hari=hari_ini.weekday(),
        is_active=True,
    ).first()

    now_time = localtime(now).time()

    if jadwal is None:
        return JsonResponse({
            'ok'           : True,
            'perlu_alasan' : True,
            'tipe_alasan'  : TipeKeteranganChoices.DI_LUAR_JADWAL,
            'selisih_menit': 0,
            'pesan'        : 'Hari ini di luar jadwal kerja resmi. Isi alasan kepulangan.',
        })

    selisih = int(
        (
            datetime.combine(hari_ini, jadwal.jam_pulang) -
            datetime.combine(hari_ini, now_time)
        ).total_seconds() / 60
    )

    if selisih > 0:
        # Pulang lebih awal → perlu alasan
        return JsonResponse({
            'ok'           : True,
            'perlu_alasan' : True,
            'tipe_alasan'  : TipeKeteranganChoices.PULANG_CEPAT,
            'selisih_menit': selisih,
            'pesan'        : f'Kamu pulang {selisih} menit lebih awal. Isi alasan.',
        })

    # 4. Simpan pulang (tepat / overtime)
    _simpan_pulang(absensi, qr, now, lat, lon)

    overtime_menit = absensi.hitung_overtime_menit()
    pesan = f'Absen pulang berhasil pukul {localtime(now).strftime("%H:%M")}.'
    if overtime_menit:
        pesan += f' Overtime {overtime_menit} menit tercatat.'

    return JsonResponse({'ok': True, 'pesan': pesan, 'redirect': '/absensi/sukses/'})


@staff_required
@require_POST
def absensi_konfirmasi_pulang(request, token):
    """
    Staff mengisi alasan pulang cepat / luar jadwal via popup.
    """
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    qr = get_object_or_404(QRAbsensi, token=token)
    valid, err = qr.is_valid()
    if not valid:
        return JsonResponse({'ok': False, 'error': err})

    form = KeteranganAbsensiForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

    staff    = request.user
    hari_ini = timezone.localdate()
    now      = timezone.now()
    lat      = request.POST.get('lat')
    lon      = request.POST.get('lon')

    with transaction.atomic():
        absensi = get_object_or_404(Absensi, staff=staff, tanggal=hari_ini)
        if not absensi.sudah_masuk:
            return JsonResponse({'ok': False, 'error': 'Kamu belum absen masuk.'})
        if absensi.sudah_pulang:
            return JsonResponse({'ok': False, 'error': 'Kamu sudah absen pulang hari ini.'})

        _simpan_pulang(absensi, qr, now, lat, lon)

        tipe           = form.cleaned_data['tipe']
        alasan         = form.cleaned_data['alasan']
        selisih_menit  = form.cleaned_data.get('selisih_menit') or 0

        KeteranganAbsensi.objects.create(
            absensi      = absensi,
            tipe         = tipe,
            alasan       = alasan,
            selisih_menit= selisih_menit,
            status       = StatusKeteranganChoices.PENDING,
        )

    return JsonResponse({
        'ok'     : True,
        'pesan'  : 'Absen pulang berhasil. Alasan kamu menunggu persetujuan supervisor.',
        'redirect': '/absensi/sukses/',
    })


def _simpan_pulang(absensi: Absensi, qr: QRAbsensi, now, lat, lon):
    """Helper — update field pulang, hitung overtime, save."""
    absensi.qr_pulang    = qr
    absensi.waktu_pulang = now
    if lat:
        absensi.lat_pulang = lat
    if lon:
        absensi.lon_pulang = lon

    absensi.update_overtime()   # set is_overtime berdasarkan JadwalKerja

    # Tentukan status akhir
    if absensi.is_overtime:
        absensi.status = AbsensiStatusChoices.OVERTIME
    else:
        absensi.status = AbsensiStatusChoices.PULANG

    absensi.save(update_fields=[
        'qr_pulang', 'waktu_pulang', 'lat_pulang', 'lon_pulang',
        'status', 'is_overtime', 'overtime_status',
        'overtime_reviewed_by', 'overtime_reviewed_at',
        'diubah_pada',
    ])


# ─────────────────────────────────────────────
# Rekap Absensi (Supervisor)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def absensi_rekap(request):
    supervisor     = _get_supervisor(request)
    ids            = _staff_ids(supervisor)
    staff_qs       = User.objects.filter(id__in=ids)

    search_nama    = request.GET.get('q', '').strip()
    tgl_filter     = request.GET.get('tgl', '').strip()
    active_tab     = request.GET.get('tab', 'absensi')
    bulan_filter   = request.GET.get('bulan', '').strip()

    if search_nama:
        staff_qs = staff_qs.filter(
            Q(nama_lengkap__icontains=search_nama) |
            Q(username__icontains=search_nama)
        )

    # ── TAB 1: Harian ──
    try:
        tgl_obj    = datetime.strptime(tgl_filter, '%Y-%m-%d').date() if tgl_filter else date.today()
        tgl_custom = bool(tgl_filter)
    except ValueError:
        tgl_obj    = date.today()
        tgl_custom = False

    tgl_str     = tgl_obj.strftime('%Y-%m-%d')
    tgl_display = (
        f"{tgl_obj.strftime('%d %B %Y')} (Hari ini)"
        if tgl_obj == date.today()
        else tgl_obj.strftime('%d %B %Y')
    )

    absensi_map = {
        a.staff_id: a
        for a in Absensi.objects.filter(staff__in=staff_qs, tanggal=tgl_obj)
            .select_related('qr_masuk', 'qr_pulang', 'staff')
    }
    izin_map = {
        i.staff_id: i
        for i in IzinStaff.objects.filter(
            staff__in=staff_qs,
            status=StatusIzinChoices.APPROVED,
            tanggal_mulai__lte=tgl_obj,
            tanggal_selesai__gte=tgl_obj,
        )
    }

    stats      = {'total_staff': staff_qs.count(), 'hadir': 0, 'belum_absen': 0, 'izin': 0}
    staff_data = []

    for staff in staff_qs:
        absen = absensi_map.get(staff.id)
        izin  = izin_map.get(staff.id)

        if absen:
            sh = absen.status_harian
            s  = absen.status
            if sh in ('I', 'L', 'DC') or (izin and not absen.sudah_masuk):
                stats['izin'] += 1
            elif s in (
                AbsensiStatusChoices.MASUK,
                AbsensiStatusChoices.PULANG,
                AbsensiStatusChoices.TERLAMBAT,
                AbsensiStatusChoices.OVERTIME,
            ):
                stats['hadir'] += 1
            else:
                stats['belum_absen'] += 1
        elif izin:
            stats['izin'] += 1
        else:
            stats['belum_absen'] += 1

        staff_data.append({'staff': staff, 'absensi': absen, 'izin': izin})

    staff_data.sort(key=lambda x: (x['staff'].nama_lengkap or x['staff'].username).lower())

    # Pending keterangan hari itu untuk badge
    keterangan_pending = KeteranganAbsensi.objects.filter(
        absensi__staff__in=ids,
        absensi__tanggal=tgl_obj,
        status=StatusKeteranganChoices.PENDING,
    ).count()

    # ── TAB 2: Izin (Bulanan) ──
    if not bulan_filter:
        bulan_filter = date.today().strftime('%Y-%m')
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
        'active_tab'          : active_tab,
        'search_nama'         : search_nama,
        'staff_data'          : staff_data,
        'tgl_str'             : tgl_str,
        'tgl_display'         : tgl_display,
        'tgl_tampil'          : tgl_obj,
        'tgl_custom'          : tgl_custom,
        'stats'               : stats,
        'total'               : stats['total_staff'],
        'keterangan_pending'  : keterangan_pending,
        'izin_qs'             : izin_qs,
        'bulan_filter'        : bulan_filter,
        'total_izin'          : izin_qs.count(),
        'izin_pending'        : izin_qs.filter(status=StatusIzinChoices.PENDING).count(),
        'izin_approved'       : izin_qs.filter(status=StatusIzinChoices.APPROVED).count(),
        'izin_rejected'       : izin_qs.filter(status=StatusIzinChoices.REJECTED).count(),
        'supervisor'          : supervisor,
    })


# ─────────────────────────────────────────────
# Detail Absensi (Supervisor)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def absensi_detail(request, pk):
    supervisor = _get_supervisor(request)
    absensi    = get_object_or_404(
        Absensi,
        pk=pk,
        staff_id__in=_staff_ids(supervisor),
    )
    izin = IzinStaff.objects.filter(
        staff=absensi.staff,
        status=StatusIzinChoices.APPROVED,
        tanggal_mulai__lte=absensi.tanggal,
        tanggal_selesai__gte=absensi.tanggal,
    ).first()
    absensi.izin_staff = izin

    keterangan_qs = absensi.keterangan_set.select_related('direview_oleh').order_by('dibuat_pada')

    return render(request, 'supervisor/absensi/detail.html', {
        'absensi'       : absensi,
        'durasi'        : absensi.durasi_str,
        'keterangan_qs' : keterangan_qs,
        'supervisor'    : supervisor,
    })


# ─────────────────────────────────────────────
# Detail Absensi per Staff (Bulanan)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def supervisor_absensi_staff_detail(request, staff_pk):
    supervisor = _get_supervisor(request)
    staff      = get_object_or_404(User, pk=staff_pk, id__in=_staff_ids(supervisor))
    today      = date.today()

    bulan_str = request.GET.get('bulan', '').strip()
    try:
        tahun, bln = map(int, bulan_str.split('-'))
        dt_start   = date(tahun, bln, 1)
    except ValueError:
        dt_start   = today.replace(day=1)
        tahun, bln = dt_start.year, dt_start.month

    last_day = monthrange(tahun, bln)[1]
    dt_end   = date(tahun, bln, last_day)

    absensi_map = {
        a.tanggal: a
        for a in Absensi.objects.filter(
            staff=staff,
            tanggal__range=[dt_start, dt_end],
        ).select_related('qr_masuk', 'qr_pulang').prefetch_related('keterangan_set')
    }

    izin_map = {}
    for iz in IzinStaff.objects.filter(
        staff=staff,
        status=StatusIzinChoices.APPROVED,
        tanggal_mulai__lte=dt_end,
        tanggal_selesai__gte=dt_start,
    ):
        curr = iz.tanggal_mulai
        while curr <= iz.tanggal_selesai:
            if dt_start <= curr <= dt_end:
                izin_map[curr] = iz
            curr += timedelta(days=1)

    calendar_rows = []
    total_durasi  = timedelta()
    hadir = alpa = izin_count = 0

    curr = dt_start
    while curr <= dt_end:
        absen      = absensi_map.get(curr)
        izin       = izin_map.get(curr)
        is_weekend = curr.weekday() >= 5
        is_future  = curr > today

        if absen:
            absen.izin_staff = izin

        if absen and absen.status in (
            AbsensiStatusChoices.MASUK,
            AbsensiStatusChoices.PULANG,
            AbsensiStatusChoices.TERLAMBAT,
            AbsensiStatusChoices.OVERTIME,
        ):
            hadir += 1
            # Gunakan langsung DateTimeField — tidak perlu combine
            if absen.waktu_masuk and absen.waktu_pulang:
                durasi = absen.waktu_pulang - absen.waktu_masuk
                if durasi.total_seconds() > 0:
                    total_durasi += durasi
        elif izin or (absen and absen.status_harian in ('I', 'L', 'DC')):
            izin_count += 1
        elif absen and absen.status_harian == 'A':
            alpa += 1
        elif not is_future and not is_weekend:
            alpa += 1   # hari kerja lewat tanpa absen

        calendar_rows.append({
            'tanggal'   : curr,
            'is_today'  : curr == today,
            'is_weekend': is_weekend,
            'is_libur'  : False,
            'libur_nama': None,
            'is_future' : is_future,
            'absensi'   : absen,
            'izin'      : izin,
        })
        curr += timedelta(days=1)

    total_detik     = int(total_durasi.total_seconds())
    total_kerja_str = f"{total_detik // 3600}j {(total_detik % 3600) // 60}m"

    bulan_ini_pertama = today.replace(day=1)
    prev_bulan        = (dt_start - timedelta(days=1)).replace(day=1).strftime('%Y-%m')
    has_next_month    = dt_start < bulan_ini_pertama
    next_bulan        = (dt_end + timedelta(days=1)).strftime('%Y-%m') if has_next_month else None

    return render(request, 'supervisor/absensi/staff_detail.html', {
        'staff'           : staff,
        'calendar_rows'   : calendar_rows,
        'bulan_sekarang'  : f'{tahun}-{bln:02d}',
        'bulan_display'   : dt_start.strftime('%B %Y'),
        'prev_bulan'      : prev_bulan,
        'next_bulan'      : next_bulan,
        'is_current_month': (tahun == today.year and bln == today.month),
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
# Keterangan — Review (Supervisor)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def keterangan_list(request):
    """Daftar semua KeteranganAbsensi pending milik supervisor."""
    supervisor = _get_supervisor(request)
    ids        = _staff_ids(supervisor)

    ket_qs = (
        KeteranganAbsensi.objects
        .filter(absensi__staff_id__in=ids)
        .select_related('absensi__staff', 'direview_oleh')
        .order_by('-dibuat_pada')
    )
    tab        = request.GET.get('tab', 'pending')
    pending_qs = ket_qs.filter(status=StatusKeteranganChoices.PENDING)
    done_qs    = ket_qs.exclude(status=StatusKeteranganChoices.PENDING)

    return render(request, 'supervisor/absensi/keterangan_list.html', {
        'pending_qs': pending_qs,
        'done_qs'   : done_qs,
        'active_tab': tab,
        'supervisor': supervisor,
    })


@supervisor_or_kepala_required
@require_POST
def keterangan_review(request, pk):
    """Review (approve/reject) satu KeteranganAbsensi — support AJAX dan POST biasa."""
    supervisor = _get_supervisor(request)
    ids        = _staff_ids(supervisor)
    ket        = get_object_or_404(KeteranganAbsensi, pk=pk, absensi__staff_id__in=ids)

    form = ReviewKeteranganForm(request.POST)
    if not form.is_valid():
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
        messages.error(request, 'Input tidak valid.')
        return redirect(request.META.get('HTTP_REFERER', 'supervisor_keterangan_list'))

    action             = form.cleaned_data['action']
    ket.status         = action
    ket.catatan_supervisor = form.cleaned_data.get('catatan_supervisor', '')
    ket.direview_oleh  = request.user
    ket.direview_pada  = timezone.now()
    ket.save(update_fields=[
        'status', 'catatan_supervisor', 'direview_oleh', 'direview_pada',
    ])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok'            : True,
            'new_status'    : ket.status,
            'status_display': ket.get_status_display(),
            'pk'            : ket.pk,
        })

    label = 'disetujui' if action == 'approved' else 'ditolak'
    messages.success(request, f'Keterangan berhasil {label}.')
    return redirect(request.META.get('HTTP_REFERER', 'supervisor_keterangan_list'))


# ─────────────────────────────────────────────
# Overtime — List & Klasifikasi
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def overtime_list(request):
    supervisor  = _get_supervisor(request)
    ids         = _staff_ids(supervisor)
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
        return JsonResponse({'ok': False, 'error': 'Pilihan tidak valid (paid / unpaid).'})

    absensi.overtime_status      = keputusan
    absensi.overtime_reviewed_by = request.user
    absensi.overtime_reviewed_at = timezone.now()
    absensi.save(update_fields=[
        'overtime_status', 'overtime_reviewed_by', 'overtime_reviewed_at',
    ])

    label = '💰 Dibayar' if keputusan == OvertimeStatusChoices.PAID else '🔵 Tidak Dibayar'
    nama  = absensi.staff.nama_lengkap or absensi.staff.username
    return JsonResponse({
        'ok'         : True,
        'message'    : f'Overtime {nama} → {label}',
        'keputusan'  : keputusan,
        'label'      : label,
        'absensi_id' : absensi.id,
        'reviewed_at': localtime(absensi.overtime_reviewed_at).strftime('%d/%m/%Y %H:%M'),
        'reviewed_by': request.user.nama_lengkap or request.user.username,
    })


@supervisor_or_kepala_required
@require_POST
def api_update_overtime_status(request, pk):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'Request tidak valid.'}, status=400)

    supervisor = _get_supervisor(request)
    absensi    = get_object_or_404(
        Absensi, pk=pk, staff_id__in=_staff_ids(supervisor),
    )

    if not absensi.is_overtime:
        return JsonResponse({'success': False, 'error': 'Absensi ini tidak memiliki overtime.'}, status=400)

    new_status = (request.POST.get('action') or request.POST.get('status', '')).strip()
    valid      = [c[0] for c in OvertimeStatusChoices.choices]
    if new_status not in valid:
        return JsonResponse({'success': False, 'error': f'Status tidak valid. Pilihan: {", ".join(valid)}'}, status=400)

    absensi.overtime_status      = new_status
    absensi.overtime_reviewed_by = request.user
    absensi.overtime_reviewed_at = timezone.now()
    absensi.save(update_fields=[
        'overtime_status', 'overtime_reviewed_by', 'overtime_reviewed_at',
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
# Izin — Review (Supervisor)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
@require_POST
def izin_review(request, pk):
    supervisor = _get_supervisor(request)
    izin       = get_object_or_404(IzinStaff, pk=pk, staff_id__in=_staff_ids(supervisor))
    action     = request.POST.get('action')
    catatan    = request.POST.get('catatan', '').strip()
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if action not in ('approved', 'rejected', 'pending'):
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Action tidak valid.'}, status=400)
        messages.error(request, 'Action tidak valid.')
        return redirect(request.META.get('HTTP_REFERER', 'supervisor_absensi_rekap'))

    izin.status             = action
    izin.catatan_supervisor = catatan
    izin.direview_oleh      = request.user if action != 'pending' else None
    izin.direview_pada      = timezone.now() if action != 'pending' else None
    izin.save(update_fields=[
        'status', 'catatan_supervisor', 'direview_oleh', 'direview_pada',
    ])

    if is_ajax:
        return JsonResponse({
            'success'           : True,
            'new_status'        : izin.status,
            'new_status_display': izin.get_status_display(),
        })

    label = 'disetujui' if action == 'approved' else 'ditolak'
    messages.success(request, f'Izin {izin.staff.nama_lengkap} berhasil {label}.')
    return redirect(request.META.get('HTTP_REFERER', 'supervisor_absensi_rekap'))


# ─────────────────────────────────────────────
# Jadwal Kerja (Supervisor CRUD)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def jadwal_list(request):
    supervisor = _get_supervisor(request)
    jadwal_qs  = (
        JadwalKerja.objects
        .filter(supervisor=supervisor)
        .order_by('hari')
    )
    return render(request, 'supervisor/jadwal/list.html', {
        'jadwal_qs' : jadwal_qs,
        'supervisor': supervisor,
    })


@supervisor_or_kepala_required
def jadwal_tambah(request):
    supervisor = _get_supervisor(request)
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = JadwalKerjaForm(request.POST, supervisor=supervisor)
        if form.is_valid():
            jadwal            = form.save(commit=False)
            jadwal.supervisor = supervisor
            jadwal.save()
            if is_ajax:
                return JsonResponse({'ok': True, 'pk': jadwal.pk, 'nama': str(jadwal)})
            messages.success(request, f'Jadwal {jadwal.get_hari_display()} berhasil ditambahkan.')
            return redirect('supervisor_jadwal_list')
        if is_ajax:
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
    else:
        form = JadwalKerjaForm(supervisor=supervisor)

    return render(request, 'supervisor/jadwal/form.html', {
        'form'      : form,
        'mode'      : 'tambah',
        'supervisor': supervisor,
    })


@supervisor_or_kepala_required
def jadwal_edit(request, pk):
    supervisor = _get_supervisor(request)
    jadwal     = get_object_or_404(JadwalKerja, pk=pk, supervisor=supervisor)
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = JadwalKerjaForm(request.POST, instance=jadwal, supervisor=supervisor)
        if form.is_valid():
            jadwal = form.save()
            if is_ajax:
                return JsonResponse({'ok': True, 'pk': jadwal.pk, 'nama': str(jadwal)})
            messages.success(request, f'Jadwal {jadwal.get_hari_display()} berhasil diperbarui.')
            return redirect('supervisor_jadwal_list')
        if is_ajax:
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
    else:
        form = JadwalKerjaForm(instance=jadwal, supervisor=supervisor)

    return render(request, 'supervisor/jadwal/form.html', {
        'form'      : form,
        'jadwal'    : jadwal,
        'mode'      : 'edit',
        'supervisor': supervisor,
    })


@supervisor_or_kepala_required
@require_POST
def jadwal_hapus(request, pk):
    supervisor = _get_supervisor(request)
    jadwal     = get_object_or_404(JadwalKerja, pk=pk, supervisor=supervisor)
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    nama = jadwal.get_hari_display()
    jadwal.delete()

    if is_ajax:
        return JsonResponse({'ok': True, 'pk': pk, 'nama': nama})
    messages.success(request, f'Jadwal {nama} berhasil dihapus.')
    return redirect('supervisor_jadwal_list')


@supervisor_or_kepala_required
@require_POST
def jadwal_toggle_aktif(request, pk):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'AJAX only.'}, status=400)

    supervisor       = _get_supervisor(request)
    jadwal           = get_object_or_404(JadwalKerja, pk=pk, supervisor=supervisor)
    jadwal.is_active = not jadwal.is_active
    jadwal.save(update_fields=['is_active', 'diperbarui'])

    return JsonResponse({
        'ok'       : True,
        'is_active': jadwal.is_active,
        'label'    : 'Aktif' if jadwal.is_active else 'Nonaktif',
    })


# ─────────────────────────────────────────────
# Lokasi Absensi (Supervisor CRUD)
# ─────────────────────────────────────────────

@supervisor_or_kepala_required
def lokasi_list(request):
    supervisor = _get_supervisor(request)
    lokasi_qs  = LokasiAbsensi.objects.filter(supervisor=supervisor).order_by('nama')
    return render(request, 'supervisor/lokasi/list.html', {
        'lokasi_qs' : lokasi_qs,
        'supervisor': supervisor,
    })


@supervisor_or_kepala_required
def lokasi_tambah(request):
    supervisor = _get_supervisor(request)
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = LokasiAbsensiForm(request.POST, supervisor=supervisor)
        if form.is_valid():
            lokasi            = form.save(commit=False)
            lokasi.supervisor = supervisor
            lokasi.save()
            if is_ajax:
                return JsonResponse(_lokasi_json(lokasi))
            messages.success(request, f'Lokasi "{lokasi.nama}" berhasil ditambahkan.')
            return redirect('supervisor_lokasi_list')
        if is_ajax:
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
    else:
        form = LokasiAbsensiForm(supervisor=supervisor)

    return render(request, 'supervisor/lokasi/form.html', {
        'form'                    : form,
        'mode'                    : 'tambah',
        'supervisor'              : supervisor,
        'koordinat_decimal_places': KOORDINAT_DECIMAL_PLACES,
        'radius_min'              : RADIUS_MIN,
        'radius_max'              : RADIUS_MAX,
        'radius_default'          : RADIUS_DEFAULT,
    })


@supervisor_or_kepala_required
def lokasi_edit(request, pk):
    supervisor = _get_supervisor(request)
    lokasi     = get_object_or_404(LokasiAbsensi, pk=pk, supervisor=supervisor)
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = LokasiAbsensiForm(request.POST, instance=lokasi, supervisor=supervisor)
        if form.is_valid():
            lokasi = form.save()
            if is_ajax:
                return JsonResponse(_lokasi_json(lokasi))
            messages.success(request, f'Lokasi "{lokasi.nama}" berhasil diperbarui.')
            return redirect('supervisor_lokasi_list')
        if is_ajax:
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
    else:
        form = LokasiAbsensiForm(instance=lokasi, supervisor=supervisor)

    return render(request, 'supervisor/lokasi/form.html', {
        'form'                    : form,
        'lokasi'                  : lokasi,
        'mode'                    : 'edit',
        'supervisor'              : supervisor,
        'koordinat_decimal_places': KOORDINAT_DECIMAL_PLACES,
        'radius_min'              : RADIUS_MIN,
        'radius_max'              : RADIUS_MAX,
        'radius_default'          : RADIUS_DEFAULT,
    })


@supervisor_or_kepala_required
@require_POST
def lokasi_hapus(request, pk):
    supervisor = _get_supervisor(request)
    lokasi     = get_object_or_404(LokasiAbsensi, pk=pk, supervisor=supervisor)
    is_ajax    = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Cek apakah lokasi masih dipakai QR aktif — field 'tanggal' tidak ada lagi
    qr_aktif = QRAbsensi.objects.filter(lokasi=lokasi, is_active=True).exists()
    if qr_aktif:
        msg = 'Lokasi masih digunakan QR aktif. Nonaktifkan QR terlebih dahulu.'
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
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'AJAX only.'}, status=400)

    supervisor       = _get_supervisor(request)
    lokasi           = get_object_or_404(LokasiAbsensi, pk=pk, supervisor=supervisor)
    lokasi.is_active = not lokasi.is_active
    lokasi.save(update_fields=['is_active', 'diperbarui'])

    return JsonResponse({
        'ok'       : True,
        'is_active': lokasi.is_active,
        'label'    : 'Aktif' if lokasi.is_active else 'Nonaktif',
    })


@supervisor_or_kepala_required
def lokasi_detail_json(request, pk):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': 'AJAX only.'}, status=400)

    supervisor = _get_supervisor(request)
    lokasi     = get_object_or_404(LokasiAbsensi, pk=pk, supervisor=supervisor)
    return JsonResponse(_lokasi_json(lokasi))