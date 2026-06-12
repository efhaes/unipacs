from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from outsourcing.decorators import customer_required
from outsourcing.models import LaporanKegiatan, ItemKegiatan


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_perusahaan_or_render(request):
    """Return (perusahaan, None) atau (None, response) jika belum terhubung."""
    perusahaan = getattr(request.user, 'perusahaan_customer', None)
    if not perusahaan:
        response = render(request, 'customer/no_perusahaan.html', {
            'page_title': 'Akun Belum Terhubung'
        })
        return None, response
    return perusahaan, None


# ---------------------------------------------------------------------------
# Laporan
# ---------------------------------------------------------------------------

@customer_required
def laporan_list(request):
    perusahaan, err = _get_perusahaan_or_render(request)
    if err:
        return err

    q          = request.GET.get('q', '').strip()
    tgl_dari   = request.GET.get('tgl_dari', '').strip()
    tgl_sampai = request.GET.get('tgl_sampai', '').strip()

    # FIX (jangka panjang): tambahkan select_related('supervisor__user') jika
    # ada relasi user, dan gunakan index DB pada tanggal_laporan + perusahaan
    # untuk performa saat data besar. Pertimbangkan pagination (Paginator) jika
    # laporan bisa ribuan.
    laporan = (
        LaporanKegiatan.objects
        .filter(perusahaan=perusahaan)
        # FIX: supervisor bisa null jika user supervisor dihapus.
        # select_related tetap aman (menghasilkan LEFT JOIN), tapi template
        # harus guard: {% if l.supervisor %} — sudah diperbaiki di template.
        .select_related('jenis_jasa', 'area', 'supervisor')
        .order_by('-tanggal_laporan')
    )

    if q:
        laporan = laporan.filter(
            Q(nama_laporan__icontains=q) |
            Q(jenis_jasa__nama_jasa__icontains=q) |
            # FIX: area juga bisa dicari, konsisten dengan data-attr di template
            Q(area__nama_area__icontains=q) |
            Q(supervisor__nama_lengkap__icontains=q)
        )
    if tgl_dari:
        laporan = laporan.filter(tanggal_laporan__gte=tgl_dari)
    if tgl_sampai:
        # FIX (jangka pendek): jika tanggal_laporan adalah DateTimeField,
        # `__lte` akan miss record di hari tgl_sampai setelah 00:00:00.
        # Gunakan __date__lte atau tambah 1 hari dengan __lt.
        # Jika DateField, ini sudah benar.
        # Contoh aman untuk DateTimeField:
        #   from datetime import timedelta, date
        #   try:
        #       d = date.fromisoformat(tgl_sampai)
        #       laporan = laporan.filter(tanggal_laporan__date__lte=d)
        #   except ValueError:
        #       pass
        # Untuk DateField (paling umum), biarkan seperti ini:
        laporan = laporan.filter(tanggal_laporan__lte=tgl_sampai)

    # FIX (jangka pendek): jangan pakai |length di template — itu memanggil
    # len() pada queryset yang sudah di-evaluate, tidak masalah secara
    # fungsional tapi tidak konsisten. Kirim count eksplisit dari sini
    # supaya template bisa pakai {{ laporan_count }} tanpa evaluasi ulang.
    # evaluate queryset sekali dengan list() agar tidak dua kali hit DB
    laporan_list_evaluated = list(laporan)

    return render(request, 'customer/laporan/list.html', {
        'laporan_list'  : laporan_list_evaluated,
        'laporan_count' : len(laporan_list_evaluated),
        'perusahaan'    : perusahaan,
        'q'             : q,
        'tgl_dari'      : tgl_dari,
        'tgl_sampai'    : tgl_sampai,
        'page_title'    : 'Laporan Kegiatan',
    })


@customer_required
def laporan_detail(request, pk):
    perusahaan, err = _get_perusahaan_or_render(request)
    if err:
        return err

    laporan = get_object_or_404(
        LaporanKegiatan,
        pk=pk,
        perusahaan=perusahaan,
    )

    item_list = (
        ItemKegiatan.objects
        .filter(laporan=laporan)
        .select_related('sub_area')
        .prefetch_related('staff')
        .order_by('tanggal', 'jam_mulai')
    )

    # FIX: evaluate item_list sekali — item_list.count() di dalam stats
    # sebelumnya akan trigger query ke DB lagi padahal queryset yang sama
    # sudah di-iterate di loop counts. Gunakan list() supaya konsisten.
    item_list_evaluated = list(item_list)

    counts = {s: 0 for s in ['terjadwal', 'on_progress', 'menunggu_approval', 'selesai']}
    for item in item_list_evaluated:
        if item.status in counts:
            counts[item.status] += 1

    stats = {
        'total'        : len(item_list_evaluated),
        **counts,
        'semua_selesai': (
            counts['terjadwal']         == 0 and
            counts['on_progress']       == 0 and
            counts['menunggu_approval'] == 0
        ),
    }

    return render(request, 'customer/laporan/detail.html', {
        'laporan'   : laporan,
        'item_list' : item_list_evaluated,
        'stats'     : stats,
        'perusahaan': perusahaan,
        'page_title': f'Laporan — {laporan.nama_laporan}',
    })


# ---------------------------------------------------------------------------
# Approval Item
# ---------------------------------------------------------------------------

@customer_required
def item_approval_list(request):
    """
    Semua item menunggu approval milik perusahaan customer, lintas laporan.
    """
    perusahaan, err = _get_perusahaan_or_render(request)
    if err:
        return err

    items = (
        ItemKegiatan.objects
        .filter(
            status='menunggu_approval',
            laporan__perusahaan=perusahaan,
        )
        .select_related('laporan__area', 'laporan__jenis_jasa', 'sub_area')
        .prefetch_related('staff')
        .order_by('tanggal', 'jam_mulai')
    )

    return render(request, 'customer/item/approval_list.html', {
        'item_list' : items,
        'perusahaan': perusahaan,
        'page_title': 'Pekerjaan Menunggu Approval',
    })


@customer_required
def item_approve(request, pk):
    """
    Customer menyetujui satu item kegiatan.

    Hanya item.status yang diubah → 'selesai'.
    laporan.status TIDAK disentuh — supervisor yang mengontrol status laporan.
    """
    perusahaan, err = _get_perusahaan_or_render(request)
    if err:
        return err

    item = get_object_or_404(
        ItemKegiatan,
        pk=pk,
        status='menunggu_approval',
        laporan__perusahaan=perusahaan,
    )

    if request.method == 'POST':
        item.status = 'selesai'
        item.save(update_fields=['status'])

        messages.success(
            request,
            f'✓ Pekerjaan "{item.nama_item}" disetujui dan dinyatakan Selesai.',
        )
        return redirect('customer_laporan_detail', pk=item.laporan_id)

    return render(request, 'customer/item/approve_confirm.html', {
        'item'      : item,
        'page_title': f'Setujui Pekerjaan: {item.nama_item}',
    })