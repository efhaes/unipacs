# views.py (staff)

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localtime

from outsourcing.models import (
    QRAbsensi, QRTypeChoices,
    Absensi, AbsensiStatusChoices, OvertimeStatusChoices,
    StaffSupervisor, IzinStaff,
)
from outsourcing.decorators import staff_required


@staff_required
def qr_scan_page(request):
    return render(request, 'staff/absensi/qr_scan.html')


@staff_required
def qr_scan_landing(request, token):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not is_ajax:
        from django.shortcuts import redirect
        return redirect('qr_scan_page')

    if not request.user.is_staff_lapangan:
        return JsonResponse({'success': False, 'error': 'Hanya staff lapangan yang bisa absen.'})

    qr_obj = get_object_or_404(QRAbsensi, token=token)

    valid, alasan = qr_obj.is_valid()
    if not valid:
        return JsonResponse({
            'success'   : False,
            'error'     : alasan,
            'tipe'      : qr_obj.tipe,
            'supervisor': qr_obj.supervisor.nama_lengkap or qr_obj.supervisor.username,
        })

    hari_ini  = timezone.localdate()
    terdaftar = StaffSupervisor.objects.filter(
        staff      = request.user,
        supervisor = qr_obj.supervisor,
        is_active  = True,
    ).exists()

    if not terdaftar:
        return JsonResponse({
            'success'   : False,
            'error'     : 'Kamu tidak terdaftar di bawah supervisor ini.',
            'tipe'      : qr_obj.tipe,
            'supervisor': qr_obj.supervisor.nama_lengkap or qr_obj.supervisor.username,
        })

    # ── Validasi Lokasi (jika QR punya lokasi) ────────────────────────
    lat_staff = None
    lon_staff = None

    if qr_obj.lokasi:
        lat_staff = request.POST.get('lat') or request.GET.get('lat')
        lon_staff = request.POST.get('lon') or request.GET.get('lon')

        if not lat_staff or not lon_staff:
            return JsonResponse({
                'success'      : False,
                'need_location': True,
                'error'        : 'Izinkan akses lokasi untuk absen di titik ini.',
                'tipe'         : qr_obj.tipe,
            })

        try:
            valid_lokasi, jarak = qr_obj.lokasi.validasi_koordinat(lat_staff, lon_staff)
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error'  : 'Format koordinat tidak valid.',
                'tipe'   : qr_obj.tipe,
            })

        if not valid_lokasi:
            return JsonResponse({
                'success': False,
                'error'  : f'Kamu berada {jarak:.0f}m dari lokasi absen. Maksimal {qr_obj.lokasi.radius_meter}m.',
                'tipe'   : qr_obj.tipe,
                'jarak'  : jarak,
                'radius' : qr_obj.lokasi.radius_meter,
            })

    # ── Get or create absensi ──────────────────────────────────────────
    absensi, _ = Absensi.objects.get_or_create(
        staff   = request.user,
        tanggal = hari_ini,
        defaults={'qr_masuk': None, 'qr_pulang': None},
    )

    if qr_obj.tipe == QRTypeChoices.MASUK:
        absensi.qr_masuk = qr_obj
    else:
        absensi.qr_pulang = qr_obj
    absensi.save(update_fields=['qr_masuk', 'qr_pulang'])

    # ── QR MASUK ──────────────────────────────────────────────────────
    if qr_obj.tipe == QRTypeChoices.MASUK:
        if absensi.sudah_masuk:
            return JsonResponse({
                'success'      : False,
                'error'        : 'Kamu sudah absen masuk hari ini.',
                'tipe'         : 'masuk',
                'already_absen': True,
                'waktu'        : localtime(absensi.waktu_masuk).strftime('%H:%M'),
            })

        update_fields = ['waktu_masuk', 'status']
        absensi.waktu_masuk = timezone.now()
        absensi.status      = AbsensiStatusChoices.MASUK

        if lat_staff and lon_staff:
            absensi.lat_masuk = lat_staff
            absensi.lon_masuk = lon_staff
            update_fields += ['lat_masuk', 'lon_masuk']

        absensi.save(update_fields=update_fields)

        return JsonResponse({
            'success'   : True,
            'message'   : 'Absen masuk berhasil!',
            'tipe'      : 'masuk',
            'waktu'     : localtime(absensi.waktu_masuk).strftime('%H:%M'),
            'supervisor': qr_obj.supervisor.nama_lengkap or qr_obj.supervisor.username,
        })

    # ── QR PULANG ─────────────────────────────────────────────────────
    elif qr_obj.tipe == QRTypeChoices.PULANG:

        if not absensi.sudah_masuk:
            return JsonResponse({
                'success'   : False,
                'error'     : 'Kamu belum absen masuk hari ini. Scan QR masuk terlebih dahulu.',
                'tipe'      : 'pulang',
                'need_masuk': True,
            })

        if absensi.sudah_pulang:
            return JsonResponse({
                'success'      : False,
                'error'        : 'Kamu sudah absen pulang hari ini.',
                'tipe'         : 'pulang',
                'already_absen': True,
                'waktu'        : localtime(absensi.waktu_pulang).strftime('%H:%M'),
            })

        now              = timezone.now()
        jam_pulang_resmi = qr_obj.jam_berlaku_mulai

        is_pulang_awal = jam_pulang_resmi and now < jam_pulang_resmi

        ot_menit = 0
        is_ot    = False
        if jam_pulang_resmi and not is_pulang_awal:
            selisih  = int((now - jam_pulang_resmi).total_seconds() / 60)
            ot_menit = selisih if selisih >= Absensi.THRESHOLD_OT_MENIT else 0
            is_ot    = ot_menit > 0

        # ── GET → kirim flag, tunggu input dari modal ──────────────
        if request.method == 'GET':
            if is_pulang_awal:
                return JsonResponse({
                    'success'         : False,
                    'need_izin_pulang': True,
                    'jam_pulang_resmi': localtime(jam_pulang_resmi).strftime('%H:%M'),
                    'jam_sekarang'    : localtime(now).strftime('%H:%M'),
                })
            if is_ot:
                return JsonResponse({
                    'success'         : False,
                    'need_keterangan' : True,
                    'overtime_menit'  : ot_menit,
                    'overtime_str'    : f"{ot_menit // 60}j {ot_menit % 60}m",
                    'jam_pulang_resmi': localtime(jam_pulang_resmi).strftime('%H:%M'),
                })

        # ── POST / GET tepat waktu → simpan ────────────────────────
        update_fields = ['waktu_pulang', 'status']

        if is_pulang_awal:
            keterangan_izin = request.POST.get('keterangan_izin', '').strip()
            if not keterangan_izin:
                return JsonResponse({
                    'success': False,
                    'error'  : 'Keterangan izin pulang awal wajib diisi.',
                })
            absensi.izin_pulang_awal       = True
            absensi.keterangan_izin_pulang = keterangan_izin
            update_fields += ['izin_pulang_awal', 'keterangan_izin_pulang']

        if is_ot:
            keterangan_ot = request.POST.get('keterangan_overtime', '').strip()
            if not keterangan_ot:
                return JsonResponse({
                    'success': False,
                    'error'  : 'Keterangan overtime wajib diisi.',
                })
            absensi.is_overtime     = True
            absensi.overtime_status = OvertimeStatusChoices.BELUM_REVIEW
            absensi.status          = AbsensiStatusChoices.OVERTIME
            absensi.catatan         = keterangan_ot
            update_fields += ['is_overtime', 'overtime_status', 'catatan']

        absensi.waktu_pulang = now
        if not is_ot:
            absensi.status = AbsensiStatusChoices.PULANG

        if lat_staff and lon_staff:
            absensi.lat_pulang = lat_staff
            absensi.lon_pulang = lon_staff
            update_fields += ['lat_pulang', 'lon_pulang']

        absensi.save(update_fields=update_fields)

        pesan = 'Absen pulang berhasil!'
        if is_pulang_awal:
            pesan += ' Izin pulang awal tercatat.'
        elif is_ot:
            pesan += f' Overtime {ot_menit // 60}j {ot_menit % 60}m menunggu klasifikasi supervisor.'

        return JsonResponse({
            'success'       : True,
            'message'       : pesan,
            'tipe'          : 'pulang',
            'is_overtime'   : is_ot,
            'is_pulang_awal': is_pulang_awal,
            'waktu'         : localtime(absensi.waktu_pulang).strftime('%H:%M'),
            'durasi'        : absensi.durasi_str,
            'supervisor'    : qr_obj.supervisor.nama_lengkap or qr_obj.supervisor.username,
        })


@staff_required
def absensi_riwayat(request):
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
        last_checkin     = localtime(absensi_hari_ini.waktu_masuk).strftime('%H:%M') if absensi_hari_ini.waktu_masuk else None
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