from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from outsourcing.decorators import supervisor_or_kepala_required
from outsourcing.models import LaporanKegiatan, StatusLaporan
from outsourcing.forms.laporan_forms import LaporanKegiatanForm

def _get_supervisor(request):
    if request.user.role == 'supervisor':
        return request.user
    return request.supervisor_context

@supervisor_or_kepala_required
def laporan_list(request):
    supervisor = _get_supervisor(request)
    q          = request.GET.get('q', '').strip()
    status     = request.GET.get('status', '').strip()
    aktif      = request.GET.get('aktif', 'true').strip()  # default aktif

    laporan = LaporanKegiatan.objects.filter(
        supervisor=supervisor
    ).select_related('perusahaan', 'jenis_jasa', 'area').order_by('-tanggal_laporan')

    # Filter aktif/nonaktif
    if aktif == 'false':
        laporan = laporan.filter(is_active=False)
    else:
        laporan = laporan.filter(is_active=True)

    if q:
        laporan = laporan.filter(
            Q(nama_laporan__icontains=q) |
            Q(perusahaan__nama_perusahaan__icontains=q)
        )
    if status:
        laporan = laporan.filter(status=status)

    context = {
        'laporan_list'  : laporan,
        'status_choices': StatusLaporan.choices,
        'filter_status' : status,
        'filter_aktif'  : aktif,
        'q'             : q,
        'supervisor'    : supervisor,
        'page_title'    : 'Laporan Kegiatan Saya',
    }
    return render(request, 'supervisor/laporan/list.html', context)


@supervisor_or_kepala_required
def laporan_create(request):
    supervisor = _get_supervisor(request)

    if request.method == 'POST':
        form = LaporanKegiatanForm(request.POST, supervisor=supervisor)
        if form.is_valid():
            laporan = form.save(commit=False)
            laporan.supervisor = supervisor
            laporan.status     = StatusLaporan.DRAFT
            laporan.save()
            messages.success(request, f'Laporan "{laporan.nama_laporan}" berhasil dibuat.')
            return redirect('supervisor_laporan_detail', pk=laporan.pk)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Error {field}: {error}')
    else:
        form = LaporanKegiatanForm(supervisor=supervisor)

    context = {
        'form'      : form,
        'supervisor': supervisor,
        'page_title': 'Buat Laporan Baru',
        'action'    : 'Buat Laporan',
    }
    return render(request, 'supervisor/laporan/form.html', context)


@supervisor_or_kepala_required
def laporan_detail(request, pk):
    supervisor = _get_supervisor(request)
    laporan    = get_object_or_404(LaporanKegiatan, pk=pk, supervisor=supervisor)
    item_list  = laporan.item_kegiatan.select_related('sub_area').prefetch_related('staff').order_by('tanggal', 'jam_mulai')

    stats = {
        'total'      : item_list.count(),
        'terjadwal'  : item_list.filter(status='terjadwal').count(),
        'on_progress': item_list.filter(status='on_progress').count(),
        'selesai'    : item_list.filter(status='selesai').count(),
        'insidental' : item_list.filter(is_insidental=True).count(),
    }

    context = {
        'laporan'   : laporan,
        'item_list' : item_list,
        'stats'     : stats,
        'supervisor': supervisor,
        'page_title': f'{laporan.nama_laporan}',
    }
    return render(request, 'supervisor/laporan/detail.html', context)


@supervisor_or_kepala_required
def laporan_edit(request, pk):
    supervisor = _get_supervisor(request)
    laporan    = get_object_or_404(LaporanKegiatan, pk=pk, supervisor=supervisor)

    if laporan.status != StatusLaporan.DRAFT:
        messages.error(request, 'Laporan yang sudah selesai tidak bisa diedit.')
        return redirect('supervisor_laporan_detail', pk=pk)

    if request.method == 'POST':
        form = LaporanKegiatanForm(request.POST, instance=laporan, supervisor=supervisor)
        if form.is_valid():
            form.save()
            messages.success(request, f'Laporan "{laporan.nama_laporan}" berhasil diperbarui.')
            return redirect('supervisor_laporan_detail', pk=pk)
    else:
        form = LaporanKegiatanForm(instance=laporan, supervisor=supervisor)

    context = {
        'form'      : form,
        'laporan'   : laporan,
        'supervisor': supervisor,
        'page_title': f'Edit Laporan — {laporan.nama_laporan}',
        'action'    : 'Simpan Perubahan',
    }
    return render(request, 'supervisor/laporan/form.html', context)


@supervisor_or_kepala_required
def laporan_delete(request, pk):
    supervisor = _get_supervisor(request)
    laporan    = get_object_or_404(LaporanKegiatan, pk=pk, supervisor=supervisor)

    if laporan.status != StatusLaporan.DRAFT:
        messages.error(request, 'Hanya laporan berstatus Draft yang bisa dihapus.')
        return redirect('supervisor_laporan_detail', pk=pk)

    if request.method == 'POST':
        nama = laporan.nama_laporan
        laporan.delete()
        messages.success(request, f'Laporan "{nama}" berhasil dihapus.')
        return redirect('supervisor_laporan_list')

    context = {
        'laporan'   : laporan,
        'supervisor': supervisor,
        'page_title': f'Hapus Laporan — {laporan.nama_laporan}',
    }
    return render(request, 'supervisor/laporan/confirm_delete.html', context)


@supervisor_or_kepala_required
def laporan_selesai(request, pk):
    supervisor = _get_supervisor(request)
    laporan    = get_object_or_404(LaporanKegiatan, pk=pk, supervisor=supervisor)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method tidak diizinkan.'}, status=405)

    if laporan.status != StatusLaporan.DRAFT:
        return JsonResponse({
            'success': False,
            'message': 'Laporan harus berstatus Draft untuk diselesaikan.'
        }, status=400)

    if not laporan.semua_item_approved:
        belum_approved = laporan.item_kegiatan.exclude(status='selesai').count()
        return JsonResponse({
            'success': False,
            'message': (
                f'Masih ada {belum_approved} item kegiatan yang belum '
                f'di-approve oleh customer. Laporan belum bisa diselesaikan.'
            )
        }, status=400)

    laporan.status = StatusLaporan.SELESAI
    laporan.save()

    return JsonResponse({
        'success': True,
        'message': f'Laporan "{laporan.nama_laporan}" berhasil diselesaikan.'
    })


@supervisor_or_kepala_required
def laporan_toggle_aktif(request, pk):
    supervisor = _get_supervisor(request)
    laporan    = get_object_or_404(LaporanKegiatan, pk=pk, supervisor=supervisor)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method tidak diizinkan.'}, status=405)

    laporan.is_active = not laporan.is_active
    laporan.save(update_fields=['is_active'])

    return JsonResponse({
        'success'  : True,
        'is_active': laporan.is_active,
        'message'  : f'Laporan "{laporan.nama_laporan}" berhasil {"diaktifkan" if laporan.is_active else "dinonaktifkan"}.',
    })