# outsourcing/views/admin/laporan.py

from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from outsourcing.decorators import admin_required
from outsourcing.models import LaporanKegiatan, Perusahaan, JenisJasa, StatusLaporan


@admin_required
def laporan_list(request):
    """
    Admin melihat semua laporan kegiatan dari seluruh perusahaan & supervisor.
    Bisa filter berdasarkan perusahaan, jenis jasa, status, dan pencarian nama.
    """
    q            = request.GET.get('q', '').strip()
    perusahaan_id = request.GET.get('perusahaan', '').strip()
    jenis_jasa_id = request.GET.get('jenis_jasa', '').strip()
    status        = request.GET.get('status', '').strip()

    laporan = LaporanKegiatan.objects.select_related(
        'perusahaan', 'jenis_jasa', 'area', 'supervisor'
    ).all()

    if q:
        laporan = laporan.filter(
            Q(nama_laporan__icontains=q) |
            Q(perusahaan__nama_perusahaan__icontains=q) |
            Q(supervisor__nama_lengkap__icontains=q)
        )
    if perusahaan_id:
        laporan = laporan.filter(perusahaan_id=perusahaan_id)
    if jenis_jasa_id:
        laporan = laporan.filter(jenis_jasa_id=jenis_jasa_id)
    if status:
        laporan = laporan.filter(status=status)

    context = {
        'laporan_list'    : laporan,
        'perusahaan_list' : Perusahaan.objects.filter(is_active=True),
        'jenis_jasa_list' : JenisJasa.objects.filter(is_active=True),
        'status_choices'  : StatusLaporan.choices,
        'q'               : q,
        'filter_perusahaan': perusahaan_id,
        'filter_jenis_jasa': jenis_jasa_id,
        'filter_status'   : status,
        'page_title'      : 'Semua Laporan Kegiatan',
    }
    return render(request, 'admin/laporan/list.html', context)


@admin_required
def laporan_detail(request, pk):
    """
    Admin melihat detail laporan beserta seluruh item kegiatan di dalamnya.
    """
    laporan    = get_object_or_404(
        LaporanKegiatan.objects.select_related(
            'perusahaan', 'jenis_jasa', 'area', 'supervisor'
        ),
        pk=pk,
    )
    item_list = laporan.item_kegiatan.select_related(
        'sub_area', 'task'
    ).prefetch_related('staff').all()

    # Ringkasan status item untuk ditampilkan di detail
    total         = item_list.count()
    total_selesai = item_list.filter(status='selesai').count()
    total_progress = item_list.filter(status='on_progress').count()
    total_terjadwal = item_list.filter(status='terjadwal').count()
    total_menunggu_approval = item_list.filter(status='menunggu_approval').count()

    context = {
        'laporan'         : laporan,
        'item_list'       : item_list,
        'total'           : total,
        'total_selesai'   : total_selesai,
        'total_progress'  : total_progress,
        'total_terjadwal' : total_terjadwal,
        'total_menunggu_approval': total_menunggu_approval,
        'page_title'      : f'Detail Laporan — {laporan.nama_laporan}',
    }
    return render(request, 'admin/laporan/detail.html', context)