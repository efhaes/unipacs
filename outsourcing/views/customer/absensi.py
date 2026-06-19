"""
Tambahkan ke customer/views.py (atau file views absensi terpisah).

Import tambahan yang dibutuhkan:
    from outsourcing.models import (
        Absensi, SupervisorPerusahaan, StaffSupervisor, HariLiburNasional
    )
"""

from datetime import date, timedelta
import calendar

from django.shortcuts import render, get_object_or_404
from django.db.models import Q

from outsourcing.decorators import customer_required
from outsourcing.models import (
    Absensi,
    SupervisorPerusahaan,
    StaffSupervisor,
    HariLiburNasional,
    User,
    IzinStaff,
    StatusIzinChoices,
)


# ── helper (sudah ada di file views.py utama, tidak perlu duplikat) ──────────
def _get_perusahaan_or_render(request):
    perusahaan = getattr(request.user, 'perusahaan_customer', None)
    if not perusahaan:
        from django.shortcuts import render as _render
        return None, _render(request, 'customer/no_perusahaan.html', {
            'page_title': 'Akun Belum Terhubung'
        })
    return perusahaan, None


# ---------------------------------------------------------------------------
# Absensi List — semua staff di perusahaan ini, dikelompokkan per supervisor
# ---------------------------------------------------------------------------

@customer_required
def absensi_list(request):
    perusahaan, err = _get_perusahaan_or_render(request)
    if err:
        return err

    # ── Parameter filter ────────────────────────────────────────────────────
    q          = request.GET.get('q', '').strip()
    tgl_str    = request.GET.get('tgl', '').strip()
    spv_filter = request.GET.get('spv', '').strip()

    # Tanggal yang ditampilkan (default: hari ini)
    try:
        tgl_tampil = date.fromisoformat(tgl_str)
        tgl_custom = True
    except ValueError:
        tgl_tampil = date.today()
        tgl_custom = False

    tgl_display = tgl_tampil.strftime('%d %B %Y')

    # ── Ambil supervisor aktif di perusahaan ini ─────────────────────────────
    # Satu supervisor bisa punya >1 penugasan (beda jasa), group by supervisor user
    spv_penugasan = (
        SupervisorPerusahaan.objects
        .filter(perusahaan=perusahaan, is_active=True)
        .select_related('supervisor', 'jenis_jasa')
        .order_by('supervisor__nama_lengkap')
    )

    if spv_filter:
        spv_penugasan = spv_penugasan.filter(supervisor_id=spv_filter)

    # Deduplicate supervisor (group jasa per supervisor)
    supervisor_map = {}
    for pen in spv_penugasan:
        spv = pen.supervisor
        if spv.pk not in supervisor_map:
            supervisor_map[spv.pk] = {'supervisor': spv, 'jasa': []}
        supervisor_map[spv.pk]['jasa'].append(pen.jenis_jasa.nama_jasa)

    supervisor_list_all = [v['supervisor'] for v in supervisor_map.values()]

    # ── Untuk setiap supervisor, ambil staff aktifnya ────────────────────────
    staff_ids_all = []
    supervisor_data = []

    for spv_pk, spv_info in supervisor_map.items():
        spv = spv_info['supervisor']

        staff_rels = (
            StaffSupervisor.objects
            .filter(supervisor=spv, is_active=True)
            .select_related('staff')
            .order_by('staff__nama_lengkap')
        )

        # Filter nama / NIK jika ada query
        if q:
            staff_rels = staff_rels.filter(
                Q(staff__nama_lengkap__icontains=q) |
                Q(staff__nik__icontains=q)
            )

        staff_list = [rel.staff for rel in staff_rels]
        staff_ids_all.extend([s.pk for s in staff_list])

        supervisor_data.append({
            'supervisor' : spv,
            'jasa_list'  : spv_info['jasa'],
            'total_staff': len(staff_list),
            'staff_list' : staff_list,  # sementara, diisi absensi di bawah
        })

    # ── Bulk fetch absensi untuk semua staff sekaligus (1 query) ────────────
    absensi_qs = Absensi.objects.filter(
        staff_id__in=staff_ids_all,
        tanggal=tgl_tampil,
    ).select_related('staff')

    absensi_map = {a.staff_id: a for a in absensi_qs}

    # ── Bulk fetch izin untuk semua staff ───────────────────────────────────
    izin_qs = IzinStaff.objects.filter(
        staff_id__in=staff_ids_all,
        tanggal_mulai__lte=tgl_tampil,
        tanggal_selesai__gte=tgl_tampil,
        status=StatusIzinChoices.APPROVED
    ).select_related('staff')
    
    izin_map = {i.staff_id: i for i in izin_qs}

    # ── Hitung stats dan gabungkan data ─────────────────────────────────────
    total_staff  = 0
    count_hadir  = 0
    count_belum  = 0
    count_izin   = 0

    STATUS_HADIR = {'masuk', 'pulang', 'terlambat', 'overtime'}
    STATUS_IZIN  = {'I', 'L', 'DC'}  # status_harian

    final_supervisor_data = []
    for item in supervisor_data:
        staff_data = []
        sv_hadir = sv_izin = sv_belum = 0

        for staff in item['staff_list']:
            absensi = absensi_map.get(staff.pk)
            izin = izin_map.get(staff.pk)
            staff_data.append({'staff': staff, 'absensi': absensi, 'izin': izin})

            total_staff += 1
            if absensi:
                sh = absensi.status_harian
                st = absensi.status
                if sh in STATUS_IZIN:
                    count_izin += 1; sv_izin += 1
                elif st in STATUS_HADIR:
                    count_hadir += 1; sv_hadir += 1
                else:
                    count_belum += 1; sv_belum += 1
            elif izin:
                count_izin += 1; sv_izin += 1
            else:
                count_belum += 1; sv_belum += 1

        final_supervisor_data.append({
            **item,
            'staff_data'  : staff_data,
            'count_hadir' : sv_hadir,
            'count_izin'  : sv_izin,
            'count_belum' : sv_belum,
        })

    stats = {
        'total_staff' : total_staff,
        'hadir'       : count_hadir,
        'belum_absen' : count_belum,
        'izin'        : count_izin,
    }

    return render(request, 'customer/absensi/list.html', {
        'supervisor_data'  : final_supervisor_data,
        'supervisor_list'  : supervisor_list_all,
        'stats'            : stats,
        'tgl'              : tgl_str or tgl_tampil.isoformat(),
        'tgl_display'      : tgl_display,
        'tgl_custom'       : tgl_custom,
        'q'                : q,
        'spv_filter'       : spv_filter,
        'page_title'       : 'Absensi Staff',
    })


# ---------------------------------------------------------------------------
# Absensi Staff Detail — riwayat bulanan satu staff
# ---------------------------------------------------------------------------

@customer_required
def absensi_staff_detail(request, staff_pk):
    perusahaan, err = _get_perusahaan_or_render(request)
    if err:
        return err

    # Pastikan staff ini memang bekerja di perusahaan customer
    # (lewat supervisor yang terdaftar di perusahaan)
    spv_di_perusahaan = SupervisorPerusahaan.objects.filter(
        perusahaan=perusahaan, is_active=True
    ).values_list('supervisor_id', flat=True)

    staff_valid = StaffSupervisor.objects.filter(
        staff_id=staff_pk,
        supervisor_id__in=spv_di_perusahaan,
        is_active=True,
    ).exists()

    if not staff_valid:
        from django.http import Http404
        raise Http404("Staff tidak ditemukan atau tidak terkait perusahaan Anda.")

    staff = get_object_or_404(User, pk=staff_pk, role='staff')

    # Supervisor aktif staff ini
    spv_rel = StaffSupervisor.objects.filter(
        staff=staff, is_active=True
    ).select_related('supervisor').first()
    supervisor_aktif = spv_rel.supervisor if spv_rel else None

    # ── Bulan yang ditampilkan ───────────────────────────────────────────────
    bulan_str = request.GET.get('bulan', '').strip()  # format: YYYY-MM
    today = date.today()

    try:
        year, month = map(int, bulan_str.split('-'))
        current_date = date(year, month, 1)
    except Exception:
        current_date = date(today.year, today.month, 1)

    is_current_month = (current_date.year == today.year and current_date.month == today.month)

    # Navigasi bulan
    first_of_prev = (current_date - timedelta(days=1)).replace(day=1)
    prev_bulan = first_of_prev.strftime('%Y-%m')

    first_of_next = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    has_next_month = first_of_next <= today.replace(day=1)
    next_bulan = first_of_next.strftime('%Y-%m')

    bulan_display = current_date.strftime('%B %Y')

    # ── Hari-hari dalam bulan ────────────────────────────────────────────────
    _, days_in_month = calendar.monthrange(current_date.year, current_date.month)
    all_dates = [date(current_date.year, current_date.month, d) for d in range(1, days_in_month + 1)]

    # ── Hari libur nasional di bulan ini ────────────────────────────────────
    libur_qs = HariLiburNasional.objects.filter(
        tahun=current_date.year,
        bulan=current_date.month,
    )
    libur_map = {h.tanggal: h.nama_libur for h in libur_qs}

    # ── Absensi staff di bulan ini (1 query) ────────────────────────────────
    absensi_qs = Absensi.objects.filter(
        staff=staff,
        tanggal__year=current_date.year,
        tanggal__month=current_date.month,
    ).order_by('tanggal')

    absensi_map = {a.tanggal: a for a in absensi_qs}

    # ── Izin staff di bulan ini ─────────────────────────────────────────────
    akhir_bulan = date(current_date.year, current_date.month, days_in_month)
    awal_bulan  = date(current_date.year, current_date.month, 1)

    izin_qs = IzinStaff.objects.filter(
        staff=staff,
        status=StatusIzinChoices.APPROVED,
        tanggal_selesai__gte=awal_bulan,
        tanggal_mulai__lte=akhir_bulan,
    )
    izin_map_per_date = {}
    for izin in izin_qs:
        d = izin.tanggal_mulai
        while d <= izin.tanggal_selesai:
            izin_map_per_date[d] = izin
            d += timedelta(days=1)

    # ── Bangun calendar rows ─────────────────────────────────────────────────
    STATUS_HADIR = {'masuk', 'pulang', 'terlambat', 'overtime'}
    STATUS_IZIN_SH = {'I', 'L', 'DC'}

    calendar_rows = []
    count_hadir = count_alpa = count_izin = 0
    total_detik = 0
    total_hari_kerja = 0

    for d in all_dates:
        is_weekend = d.weekday() >= 5  # Sabtu=5, Minggu=6
        is_libur   = d in libur_map
        is_today   = d == today
        is_future  = d > today
        libur_nama = libur_map.get(d, '')
        absensi    = absensi_map.get(d)
        izin       = izin_map_per_date.get(d)

        # Hitung stats (hanya hari kerja non-libur non-weekend non-future)
        if not is_weekend and not is_libur and not is_future:
            total_hari_kerja += 1
            if absensi:
                sh = absensi.status_harian
                st = absensi.status
                if sh in STATUS_IZIN_SH:
                    count_izin += 1
                elif st in STATUS_HADIR:
                    count_hadir += 1
                    dur = absensi.durasi_kerja()
                    if dur:
                        total_detik += int(dur.total_seconds())
                else:
                    count_alpa += 1
            elif izin:
                count_izin += 1
            else:
                count_alpa += 1

        calendar_rows.append({
            'tanggal'   : d,
            'absensi'   : absensi,
            'izin'      : izin,
            'is_weekend': is_weekend,
            'is_libur'  : is_libur,
            'is_today'  : is_today,
            'is_future' : is_future,
            'libur_nama': libur_nama,
        })

    # Total jam kerja dalam bulan
    jam_total  = total_detik // 3600
    menit_total = (total_detik % 3600) // 60
    total_kerja_str = f"{jam_total}j {menit_total}m" if jam_total else (f"{menit_total}m" if menit_total else '—')

    monthly_stats = {
        'hadir'          : count_hadir,
        'alpa'           : count_alpa,
        'izin'           : count_izin,
        'total_kerja_str': total_kerja_str,
    }

    return render(request, 'customer/absensi/staff_detail.html', {
        'staff'            : staff,
        'supervisor_aktif' : supervisor_aktif,
        'calendar_rows'    : calendar_rows,
        'monthly_stats'    : monthly_stats,
        'total_hari_kerja' : total_hari_kerja,
        'bulan_display'    : bulan_display,
        'prev_bulan'       : prev_bulan,
        'next_bulan'       : next_bulan,
        'has_next_month'   : has_next_month,
        'is_current_month' : is_current_month,
        'page_title'       : f'Absensi — {staff.nama_lengkap}',
    })