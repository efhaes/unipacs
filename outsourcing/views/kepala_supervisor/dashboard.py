from django.shortcuts import render
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from outsourcing.decorators import kepala_supervisor_required
from outsourcing.utils import get_dashboard_stats
from django.utils import timezone
import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q
import json
import datetime

from outsourcing.models import (
    User, SupervisorPerusahaan, StaffSupervisor,
    LaporanKegiatan, StatusLaporan, ItemKegiatan, StatusItem,
    Absensi, AbsensiStatusChoices, StatusHarianChoices,
    IzinStaff, StatusIzinChoices,
)


# ── HELPER ────────────────────────────────────────────────────────────────────

def _bulan_choices():
    return [
        (1, 'Januari'), (2, 'Februari'), (3, 'Maret'),
        (4, 'April'), (5, 'Mei'), (6, 'Juni'),
        (7, 'Juli'), (8, 'Agustus'), (9, 'September'),
        (10, 'Oktober'), (11, 'November'), (12, 'Desember'),
    ]


def _inisial(nama):
    """Ambil 2 huruf pertama dari nama lengkap."""
    parts = (nama or '').strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return '??'


# ── VIEW ───────────────────────────────────────────────────────────────────────

@login_required
def dashboard_view(request):
    """
    Dashboard untuk Kepala Supervisor.
    Focus: progress laporan bulanan per supervisor/perusahaan,
    bukan volume laporan.
    """
    today = timezone.localdate()

    # ── Filter bulan/tahun ────────────────────────────────
    try:
        bulan = int(request.GET.get('bulan', today.month))
    except (ValueError, TypeError):
        bulan = today.month
    try:
        tahun = int(request.GET.get('tahun', today.year))
    except (ValueError, TypeError):
        tahun = today.year

    bulan_choices = _bulan_choices()
    tahun_choices = list(range(today.year, today.year - 4, -1))

    # ── Ambil supervisor di bawah kepala ini ─────────────
    # SupervisorPerusahaan yang kepala_supervisor-nya adalah user ini
    spv_penugasan = SupervisorPerusahaan.aktif.filter(
        kepala_supervisor=request.user
    ).select_related('supervisor', 'perusahaan', 'jenis_jasa')

    supervisor_ids = spv_penugasan.values_list('supervisor_id', flat=True).distinct()
    supervisors    = User.objects.filter(pk__in=supervisor_ids)

    # ── Stat: total supervisor & staff ───────────────────
    total_supervisor = supervisors.count()
    total_staff = StaffSupervisor.aktif.filter(
        supervisor_id__in=supervisor_ids
    ).values('staff_id').distinct().count()

    # ── Laporan bulan ini ─────────────────────────────────
    laporan_bulan = LaporanKegiatan.objects.filter(
        supervisor_id__in=supervisor_ids,
        tanggal_laporan__year=tahun,
        tanggal_laporan__month=bulan,
    )

    laporan_selesai = laporan_bulan.filter(status=StatusLaporan.SELESAI).count()
    laporan_draft   = laporan_bulan.filter(status=StatusLaporan.DRAFT).count()

    # ── Hitung perusahaan yang WAJIB ada laporan bulan ini
    # yaitu semua (supervisor, perusahaan, jenis_jasa) dari penugasan aktif
    # yang supervisornya di bawah kepala ini
    total_penugasan = spv_penugasan.count()  # = jumlah (spv, perusahaan, jenis_jasa) unik

    # Berapa penugasan yang sudah ada laporannya bulan ini
    penugasan_ada_laporan = set()
    for lap in laporan_bulan.select_related('supervisor', 'perusahaan', 'jenis_jasa'):
        penugasan_ada_laporan.add((lap.supervisor_id, lap.perusahaan_id, lap.jenis_jasa_id))

    belum_laporan = total_penugasan - len(penugasan_ada_laporan)
    belum_laporan = max(belum_laporan, 0)

    completion_rate = 0
    if total_penugasan > 0:
        done = laporan_selesai
        completion_rate = round((done / total_penugasan) * 100)

    # ── Perusahaan belum laporan ───────────────────────────
    perusahaan_belum_laporan = []
    for sp in spv_penugasan:
        key = (sp.supervisor_id, sp.perusahaan_id, sp.jenis_jasa_id)
        if key not in penugasan_ada_laporan:
            perusahaan_belum_laporan.append(sp)

    # ── Progress per supervisor ────────────────────────────
    spv_progress = []
    for spv in supervisors:
        # Semua penugasan spv ini di bawah kepala ini
        penugasan_spv = spv_penugasan.filter(supervisor=spv)
        total_prs = penugasan_spv.count()

        lap_spv = laporan_bulan.filter(supervisor=spv)
        ada = set()
        d_count = s_count = dr_count = 0
        for lap in lap_spv:
            ada.add((lap.perusahaan_id, lap.jenis_jasa_id))
            if lap.status == StatusLaporan.SELESAI:
                s_count += 1
            elif lap.status == StatusLaporan.DRAFT:
                dr_count += 1

        blm = total_prs - len(ada)
        blm = max(blm, 0)

        pct_done   = round(((d_count + s_count) / total_prs * 100)) if total_prs else 0
        pct_dikirim = round((d_count / total_prs * 100)) if total_prs else 0
        pct_selesai = round((s_count / total_prs * 100)) if total_prs else 0
        pct_draft   = round((dr_count / total_prs * 100)) if total_prs else 0

        spv_progress.append({
            'nama_lengkap': spv.nama_lengkap or spv.username,
            'inisial': _inisial(spv.nama_lengkap or spv.username),
            'total_perusahaan': total_prs,
            'dikirim': d_count,
            'selesai': s_count,
            'draft': dr_count,
            'belum': blm,
            'pct_done': pct_done,
            'pct_dikirim': pct_dikirim,
            'pct_selesai': pct_selesai,
            'pct_draft': pct_draft,
        })

    # Sort: yang paling rendah progress-nya tampil di atas
    spv_progress.sort(key=lambda x: x['pct_done'])

    # ── Laporan draft > 7 hari ────────────────────────────
    tujuh_hari_lalu = today - datetime.timedelta(days=7)
    draft_lama = laporan_bulan.filter(
        status=StatusLaporan.DRAFT,
        dibuat_pada__date__lte=tujuh_hari_lalu,
    ).count()

    # ── Izin pending ──────────────────────────────────────
    staff_ids = StaffSupervisor.aktif.filter(
        supervisor_id__in=supervisor_ids
    ).values_list('staff_id', flat=True)

    izin_pending = IzinStaff.objects.filter(
        staff_id__in=staff_ids,
        status=StatusIzinChoices.PENDING,
    ).count()

    # ── Overtime pending ──────────────────────────────────
    overtime_pending = Absensi.objects.filter(
        staff_id__in=staff_ids,
        is_overtime=True,
        overtime_status='belum_review',
    ).count()

    # ── Notif count ───────────────────────────────────────
    notif_count = sum([
        1 if belum_laporan > 0 else 0,
        1 if izin_pending > 0 else 0,
        1 if overtime_pending > 0 else 0,
        1 if draft_lama > 0 else 0,
    ])

    # ── Absensi hari ini ──────────────────────────────────
    absen_hari_ini = Absensi.objects.filter(
        staff_id__in=staff_ids,
        tanggal=today,
    )
    absensi_hari_ini = {
        'masuk':    absen_hari_ini.filter(waktu_masuk__isnull=False).count(),
        'alpa':     absen_hari_ini.filter(status_harian=StatusHarianChoices.ALPA).count(),
        'izin':     absen_hari_ini.filter(
                        status_harian__in=[StatusHarianChoices.IZIN, StatusHarianChoices.CUTI, StatusHarianChoices.DOKTER]
                    ).count(),
        'overtime': absen_hari_ini.filter(is_overtime=True).count(),
        'terlambat': absen_hari_ini.filter(status=AbsensiStatusChoices.TERLAMBAT).count(),
        'belum':    staff_ids.count() - absen_hari_ini.filter(waktu_masuk__isnull=False).count(),
    }
    absensi_hari_ini['belum'] = max(absensi_hari_ini['belum'], 0)

    # Absensi per supervisor (mini)
    absensi_per_spv = []
    for spv in supervisors:
        staff_spv = StaffSupervisor.aktif.filter(
            supervisor=spv
        ).values_list('staff_id', flat=True)
        total_staff_spv = staff_spv.count()
        hadir = Absensi.objects.filter(
            staff_id__in=staff_spv,
            tanggal=today,
            waktu_masuk__isnull=False,
        ).count()
        nama = spv.nama_lengkap or spv.username
        # Ambil nama singkat (maks 12 karakter)
        nama_singkat = nama[:14] + '…' if len(nama) > 14 else nama
        absensi_per_spv.append({
            'nama_singkat': nama_singkat,
            'hadir': hadir,
            'total': total_staff_spv,
        })

    # ── Item kegiatan hari ini ────────────────────────────
    item_hari_ini = ItemKegiatan.objects.filter(
        laporan__supervisor_id__in=supervisor_ids,
        tanggal=today,
    ).select_related(
        'laporan', 'laporan__perusahaan', 'task'
    ).prefetch_related('staff').order_by('jam_mulai')

    item_stats = {
        'terjadwal':   item_hari_ini.filter(status=StatusItem.TERJADWAL).count(),
        'on_progress': item_hari_ini.filter(status=StatusItem.ON_PROGRESS).count(),
        'selesai':     item_hari_ini.filter(status=StatusItem.SELESAI).count(),
    }

    # ── Laporan terbaru ───────────────────────────────────
    laporan_terbaru = laporan_bulan.select_related(
        'perusahaan', 'supervisor', 'jenis_jasa'
    ).order_by('-dibuat_pada')[:8]

    # ── Chart data (JSON) ─────────────────────────────────
    chart_donut_data = json.dumps([
        item_stats['terjadwal'],
        item_stats['on_progress'],
        item_stats['selesai'],
    ])
    chart_completion_data = json.dumps([
        laporan_selesai,
        laporan_draft,
        belum_laporan,
    ])

    context = {
        'page_title': 'Dashboard Kepala Supervisor',
        'bulan': bulan,
        'tahun': tahun,
        'bulan_choices': bulan_choices,
        'tahun_choices': tahun_choices,

        # Stat cards
        'stats': {
            'total_supervisor': total_supervisor,
            'total_staff': total_staff,
            'total_perusahaan': total_penugasan,
            'belum_laporan': belum_laporan,
            'laporan_selesai': laporan_selesai,
            'laporan_draft': laporan_draft,
            'completion_rate': completion_rate,
            'izin_pending': izin_pending,
            'overtime_pending': overtime_pending,
            'draft_lama': draft_lama,
        },

        # Progress tracker
        'spv_progress': spv_progress,
        'perusahaan_belum_laporan': perusahaan_belum_laporan,
        'notif_count': notif_count,

        # Absensi
        'absensi_hari_ini': absensi_hari_ini,
        'absensi_per_spv': absensi_per_spv,

        # Item & laporan
        'item_hari_ini': item_hari_ini,
        'item_stats': item_stats,
        'laporan_terbaru': laporan_terbaru,

        # Chart JSON
        'chart_donut_data': chart_donut_data,
        'chart_completion_data': chart_completion_data,
    }

    return render(request, 'kepala_supervisor/dashboard.html', context)