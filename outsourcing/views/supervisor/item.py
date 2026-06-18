from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from outsourcing.decorators import supervisor_or_kepala_required
from outsourcing.models import LaporanKegiatan, ItemKegiatan
from outsourcing.forms.laporan_forms import ItemKegiatanForm
import json


def _get_supervisor(request):
    if request.user.role == 'supervisor':
        return request.user
    return request.supervisor_context


@supervisor_or_kepala_required
def item_create(request, laporan_pk):
    supervisor = _get_supervisor(request)
    laporan    = get_object_or_404(LaporanKegiatan, pk=laporan_pk, supervisor=supervisor)

    if laporan.status not in ['draft', 'aktif']:
        messages.error(request, 'Tidak bisa menambah item pada laporan yang sudah selesai.')
        return redirect('supervisor_laporan_detail', pk=laporan_pk)

    if request.method == 'POST':
        form = ItemKegiatanForm(request.POST, laporan=laporan)
        if form.is_valid():
            item         = form.save(commit=False)
            item.laporan = laporan
            item.save()
            form.save_m2m()
            messages.success(request, f'Item "{item.nama_item}" berhasil ditambahkan.')
            return redirect('supervisor_laporan_detail', pk=laporan_pk)
    else:
        form = ItemKegiatanForm(laporan=laporan)

    staff_task_mapping = {}
    for staff in form.fields['staff'].queryset:
        task_ids = list(staff.tasks_saya.filter(is_active=True).values_list('task_id', flat=True))
        staff_task_mapping[str(staff.pk)] = task_ids

    context = {
        'form'              : form,
        'laporan'           : laporan,
        'supervisor'        : supervisor,
        'page_title'        : f'Tambah Item — {laporan.nama_laporan}',
        'action'            : 'Tambah Item',
        'staff_task_mapping': json.dumps(staff_task_mapping),
    }
    return render(request, 'supervisor/item/form.html', context)


@supervisor_or_kepala_required
def item_edit(request, pk):
    supervisor = _get_supervisor(request)
    item       = get_object_or_404(ItemKegiatan, pk=pk, laporan__supervisor=supervisor)
    laporan    = item.laporan

    if laporan.status not in ['draft', 'aktif']:
        messages.error(request, 'Tidak bisa mengedit item pada laporan yang sudah selesai.')
        return redirect('supervisor_laporan_detail', pk=laporan.pk)

    if request.method == 'POST':
        form = ItemKegiatanForm(request.POST, instance=item, laporan=laporan)
        if form.is_valid():
            form.save()
            messages.success(request, f'Item "{item.nama_item}" berhasil diperbarui.')
            return redirect('supervisor_laporan_detail', pk=laporan.pk)
    else:
        form = ItemKegiatanForm(instance=item, laporan=laporan)

    staff_task_mapping = {}
    for staff in form.fields['staff'].queryset:
        task_ids = list(staff.tasks_saya.filter(is_active=True).values_list('task_id', flat=True))
        staff_task_mapping[str(staff.pk)] = task_ids

    context = {
        'form'              : form,
        'item'              : item,
        'laporan'           : laporan,
        'supervisor'        : supervisor,
        'page_title'        : f'Edit Item — {item.nama_item}',
        'action'            : 'Simpan Perubahan',
        'staff_task_mapping': json.dumps(staff_task_mapping),
    }
    return render(request, 'supervisor/item/form.html', context)


@supervisor_or_kepala_required
def item_delete(request, pk):
    supervisor = _get_supervisor(request)
    item       = get_object_or_404(ItemKegiatan, pk=pk, laporan__supervisor=supervisor)
    laporan    = item.laporan

    if request.method == 'POST':
        nama = item.nama_item
        item.delete()
        messages.success(request, f'Item "{nama}" berhasil dihapus.')
        return redirect('supervisor_laporan_detail', pk=laporan.pk)

    context = {
        'item'      : item,
        'laporan'   : laporan,
        'supervisor': supervisor,
        'page_title': f'Hapus Item — {item.nama_item}',
    }
    return render(request, 'supervisor/item/confirm_delete.html', context)


@supervisor_or_kepala_required
def item_approve(request, pk):
    """
    Supervisor menyetujui satu item kegiatan NON-insidental.
    Item insidental di-approve oleh customer, bukan supervisor.
    """
    supervisor = _get_supervisor(request)
    item = get_object_or_404(
        ItemKegiatan,
        pk=pk,
        status='menunggu_approval',
        laporan__supervisor=supervisor,
        is_insidental=False,
    )

    if request.method == 'POST':
        item.status = 'selesai'
        item.save(update_fields=['status'])

        messages.success(
            request,
            f'✓ Pekerjaan "{item.nama_item}" disetujui dan dinyatakan Selesai.',
        )
        return redirect('supervisor_laporan_detail', pk=item.laporan_id)

    return redirect('supervisor_laporan_detail', pk=item.laporan_id)