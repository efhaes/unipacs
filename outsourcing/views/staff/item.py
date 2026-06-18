# outsourcing/views/staff_views.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import wraps
from typing import Callable

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.db.models import Case, Count, IntegerField, Q, Value, When

from outsourcing.decorators import staff_required
from outsourcing.forms.staff_forms import (
    ItemKegiatanStaffForm,
    ItemKegiatanInsidentalForm,
    FotoTambahanForm,
)
from outsourcing.models import ItemKegiatan, FotoItemKegiatan, StatusLaporan


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class Status:
    TERJADWAL          = "terjadwal"
    ON_PROGRESS        = "on_progress"
    MENUNGGU_APPROVAL  = "menunggu_approval"
    SELESAI            = "selesai"

LOCKED_STATUSES = {Status.MENUNGGU_APPROVAL, Status.SELESAI}

# Batas keterlambatan yang mewajibkan keterangan (dalam menit)
OVERTIME_WAJIB_KETERANGAN = 60  # 1 jam


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def _is_past_jam_selesai(item: ItemKegiatan) -> bool:
    if not (item.jam_selesai and item.tanggal):
        return False
    deadline = timezone.make_aware(
        datetime.combine(item.tanggal, item.jam_selesai),
        timezone.get_current_timezone(),
    )
    return timezone.now() >= deadline


def _hitung_overtime(item: ItemKegiatan) -> timedelta | None:
    """
    Hitung selisih antara waktu_selesai_aktual dan jam_selesai jadwal.
    Return timedelta positif jika terlambat, None jika belum ada data.
    """
    if not (item.waktu_selesai_aktual and item.jam_selesai and item.tanggal):
        return None

    jadwal_selesai = timezone.make_aware(
        datetime.combine(item.tanggal, item.jam_selesai),
        timezone.get_current_timezone(),
    )
    selisih = item.waktu_selesai_aktual - jadwal_selesai
    return selisih if selisih.total_seconds() > 0 else None


def _format_durasi(td: timedelta) -> str:
    """Ubah timedelta jadi string '1 jam 23 menit'."""
    total_menit = int(td.total_seconds() // 60)
    jam         = total_menit // 60
    menit       = total_menit % 60
    if jam and menit:
        return f"{jam} jam {menit} menit"
    if jam:
        return f"{jam} jam"
    return f"{menit} menit"


def _derive_status(item: ItemKegiatan) -> str:
    if item.foto_after and _is_past_jam_selesai(item):
        return Status.MENUNGGU_APPROVAL
    if item.foto_on_progress or item.jam_mulai:
        return Status.ON_PROGRESS
    return item.status


def _suggest_jam_mulai(staff_user, tanggal: date, buffer_minutes: int = 2):
    latest_selesai = (
        ItemKegiatan.objects
        .filter(staff=staff_user, tanggal=tanggal)
        .exclude(jam_selesai=None)
        .order_by("-jam_selesai")
        .values_list("jam_selesai", flat=True)
        .first()
    )
    if latest_selesai is None:
        return None
    suggested_dt = datetime.combine(tanggal, latest_selesai) + timedelta(minutes=buffer_minutes)
    return suggested_dt.time()


def _item_locked_message(item: ItemKegiatan) -> str | None:
    """
    Return pesan jika item terkunci (tidak bisa diedit), None jika masih bisa.
    Item terkunci jika:
    - laporan induk sudah SELESAI (final), atau
    - status item sendiri di LOCKED_STATUSES.
    """
    if item.laporan.status == StatusLaporan.SELESAI:
        return "Laporan untuk pekerjaan ini sudah diselesaikan dan tidak dapat diedit lagi."

    if item.status in LOCKED_STATUSES:
        if item.status == Status.MENUNGGU_APPROVAL:
            if item.is_insidental:
                return "Pekerjaan ini sedang menunggu approval customer dan tidak dapat diedit."
            return "Pekerjaan ini sedang menunggu approval supervisor dan tidak dapat diedit."
        return "Pekerjaan ini sudah selesai dan tidak dapat diedit."

    return None


# ---------------------------------------------------------------------------
# Guard decorator
# ---------------------------------------------------------------------------

def item_not_done(view_fn: Callable) -> Callable:
    @wraps(view_fn)
    def _wrapper(request: HttpRequest, pk: int, *args, **kwargs):
        item = get_object_or_404(
            ItemKegiatan.objects.select_related("laporan"),
            pk=pk,
            staff=request.user,
        )
        locked_msg = _item_locked_message(item)
        if locked_msg:
            messages.info(request, locked_msg)
            return redirect("staff_item_list")
        return view_fn(request, *args, item=item, **kwargs)
    return _wrapper



def _render_update_page(request: HttpRequest, item: ItemKegiatan, form=None) -> HttpResponse:
    """
    Satu tempat untuk render halaman update — dipakai oleh GET maupun
    handler yang perlu kembali ke halaman dengan form error.
    """
    if form is None:
        form = ItemKegiatanStaffForm(instance=item)
        if not item.jam_mulai:
            suggested = _suggest_jam_mulai(request.user, item.tanggal)
            if suggested:
                form.initial["jam_mulai"] = suggested.strftime("%H:%M")

    foto_tambahan = item.foto_tambahan.all()

    overtime_td     = _hitung_overtime(item)
    overtime_durasi = _format_durasi(overtime_td) if overtime_td else None
    overtime_menit  = int(overtime_td.total_seconds() // 60) if overtime_td else 0

    estimasi_overtime_menit = 0
    if not item.foto_after and item.jam_selesai and item.tanggal:
        jadwal_dt = timezone.make_aware(
            datetime.combine(item.tanggal, item.jam_selesai),
            timezone.get_current_timezone(),
        )
        selisih = (timezone.now() - jadwal_dt).total_seconds()
        estimasi_overtime_menit = max(0, int(selisih // 60))

    return render(request, "staff/item/update.html", {
        "form"                      : form,
        "item"                      : item,
        "page_title"                : item.nama_item,
        "disable_save"              : not _is_past_jam_selesai(item),
        "foto_tambahan"             : foto_tambahan,
        "jumlah_foto"               : foto_tambahan.count(),
        "sisa_slot"                 : FotoItemKegiatan.MAKS_FOTO - foto_tambahan.count(),
        "maks_foto"                 : FotoItemKegiatan.MAKS_FOTO,
        "overtime_durasi"           : overtime_durasi,
        "overtime_menit"            : overtime_menit,
        "estimasi_overtime_menit"   : estimasi_overtime_menit,
        "overtime_wajib_threshold"  : OVERTIME_WAJIB_KETERANGAN,
        "keterangan_overtime_wajib" : estimasi_overtime_menit >= OVERTIME_WAJIB_KETERANGAN,
        "foto_tambahan_form"        : FotoTambahanForm(),
    })


def _handle_foto_progress(request: HttpRequest, item: ItemKegiatan) -> HttpResponse:
    foto = request.FILES.get("foto_on_progress")
    if not foto:
        messages.warning(request, "Pilih foto terlebih dahulu sebelum menyimpan.")
        return redirect("staff_item_update", pk=item.pk)

    item.foto_on_progress = foto
    if item.status == Status.TERJADWAL:
        item.status = Status.ON_PROGRESS

    item.save(update_fields=["foto_on_progress", "status"])
    messages.success(request, "✓ Foto sedang berjalan berhasil disimpan.")
    return redirect("staff_item_update", pk=item.pk)


def _handle_foto_after(request: HttpRequest, item: ItemKegiatan) -> HttpResponse:
    foto = request.FILES.get("foto_after")
    if not foto:
        messages.warning(request, "Pilih foto terlebih dahulu sebelum menyimpan.")
        return redirect("staff_item_update", pk=item.pk)

    if not _is_past_jam_selesai(item):
        messages.error(
            request,
            f"Belum bisa upload foto 'Setelah Selesai' karena jam selesai "
            f"({item.jam_selesai.strftime('%H:%M')}) belum tiba.",
        )
        return redirect("staff_item_update", pk=item.pk)

    waktu_aktual      = timezone.now()
    jadwal_selesai_dt = timezone.make_aware(
        datetime.combine(item.tanggal, item.jam_selesai),
        timezone.get_current_timezone(),
    )
    selisih_detik  = (waktu_aktual - jadwal_selesai_dt).total_seconds()
    overtime_menit = max(0, int(selisih_detik // 60))

    keterangan_overtime = request.POST.get("keterangan_overtime", "").strip()

    if overtime_menit >= OVERTIME_WAJIB_KETERANGAN and not keterangan_overtime:
        selisih_td = timedelta(minutes=overtime_menit)
        messages.error(
            request,
            f"Pekerjaan terlambat {_format_durasi(selisih_td)} dari jadwal. "
            f"Keterangan alasan keterlambatan wajib diisi sebelum menyimpan.",
        )
        return redirect("staff_item_update", pk=item.pk)

    item.foto_after           = foto
    item.status               = Status.MENUNGGU_APPROVAL
    item.waktu_selesai_aktual = waktu_aktual

    if keterangan_overtime:
        item.keterangan_overtime = keterangan_overtime

    keterangan_after = request.POST.get("keterangan_after", "").strip()
    if keterangan_after:
        existing = item.catatan_staff.strip()
        item.catatan_staff = f"{existing}\n\n[Keterangan selesai]: {keterangan_after}".strip()

    item.save(update_fields=[
        "foto_after",
        "status",
        "waktu_selesai_aktual",
        "keterangan_overtime",
        "catatan_staff",
    ])

    approver = "customer" if item.is_insidental else "supervisor"

    if overtime_menit > 0:
        selisih_td = timedelta(minutes=overtime_menit)
        messages.warning(
            request,
            f"✓ Foto disimpan. Pekerjaan selesai {_format_durasi(selisih_td)} "
            f"lebih lambat dari jadwal. Menunggu approval {approver}.",
        )
    else:
        messages.success(
            request,
            f"✓ Foto selesai disimpan. Pekerjaan menunggu approval dari {approver}.",
        )

    return redirect("staff_item_list")


def _handle_save_all(request: HttpRequest, item: ItemKegiatan) -> HttpResponse:
    """
    Handle save_type='all'.
    Selalu return HttpResponse — konsisten dengan handler lain.
    Form error di-render ulang di halaman yang sama.
    """
    form = ItemKegiatanStaffForm(request.POST, request.FILES, instance=item)

    if not form.is_valid():
        messages.error(request, "Periksa kembali isian form.")
        return _render_update_page(request, item, form=form)

    updated_item = form.save(commit=False)

    if form.cleaned_data.get("foto_after") and not _is_past_jam_selesai(updated_item):
        messages.error(
            request,
            f"Belum bisa upload foto 'Setelah Selesai' karena jam selesai "
            f"({updated_item.jam_selesai.strftime('%H:%M')}) belum tiba.",
        )
        return _render_update_page(request, item, form=form)

    updated_item.status = _derive_status(updated_item)
    updated_item.save()
    messages.success(request, f"Pekerjaan \"{updated_item.nama_item}\" berhasil diperbarui.")
    return redirect("staff_item_list")


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

SAVE_HANDLERS: dict[str, Callable[[HttpRequest, ItemKegiatan], HttpResponse]] = {
    "foto_progress": _handle_foto_progress,
    "foto_after"   : _handle_foto_after,
    "all"          : _handle_save_all,
}


# ---------------------------------------------------------------------------
# Views — Staff
# ---------------------------------------------------------------------------

@staff_required
def item_list(request: HttpRequest):
    tahun_dipilih = request.GET.get("tahun", "").strip()
    bulan_dipilih = request.GET.get("bulan", "").strip()
    status        = request.GET.get("status", "").strip()

    base_qs = (
        ItemKegiatan.objects
        .filter(staff=request.user)
        .select_related("laporan__perusahaan", "laporan__area", "sub_area")
        .order_by("-tanggal", "jam_mulai")
    )

    tahun_qs = (
        base_qs
        .values_list("tanggal__year", flat=True)
        .distinct()
        .order_by("tanggal__year")
    )
    tahun_list = []
    for tahun in tahun_qs:
        if tahun:
            total   = base_qs.filter(tanggal__year=tahun).count()
            selesai = base_qs.filter(tanggal__year=tahun, status=Status.SELESAI).count()
            tahun_list.append({"tahun": tahun, "total": total, "selesai": selesai})

    NAMA_BULAN = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    bulan_list = []
    if tahun_dipilih:
        bulan_qs = (
            base_qs
            .filter(tanggal__year=tahun_dipilih)
            .values_list("tanggal__month", flat=True)
            .distinct()
            .order_by("tanggal__month")
        )
        for bulan in bulan_qs:
            if bulan:
                total   = base_qs.filter(tanggal__year=tahun_dipilih, tanggal__month=bulan).count()
                selesai = base_qs.filter(tanggal__year=tahun_dipilih, tanggal__month=bulan, status=Status.SELESAI).count()
                bulan_list.append({
                    "bulan"      : bulan,
                    "nama_bulan" : NAMA_BULAN[bulan],
                    "total"      : total,
                    "selesai"    : selesai,
                })

    item_qs = None
    if tahun_dipilih and bulan_dipilih:
        item_qs = base_qs.filter(
            tanggal__year=tahun_dipilih,
            tanggal__month=bulan_dipilih,
        )
        if status:
            item_qs = item_qs.filter(status=status)

        today = timezone.localdate()
        item_qs = item_qs.annotate(
            is_today=Case(
                When(tanggal=today, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            status_order=Case(
                When(status=Status.TERJADWAL,         then=Value(0)),
                When(status=Status.ON_PROGRESS,       then=Value(1)),
                When(status=Status.MENUNGGU_APPROVAL, then=Value(2)),
                When(status=Status.SELESAI,           then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            ),
        ).order_by("is_today", "status_order", "tanggal", "jam_mulai")

    return render(request, "staff/item/list.html", {
        "tahun_list"    : tahun_list,
        "bulan_list"    : bulan_list,
        "item_list"     : item_qs,
        "tahun_dipilih" : tahun_dipilih,
        "bulan_dipilih" : bulan_dipilih,
        "filter_status" : status,
        "nama_bulan"    : NAMA_BULAN[int(bulan_dipilih)] if bulan_dipilih else "",
        "page_title"    : "Jadwal Pekerjaan Saya",
    })


@staff_required
@item_not_done
def item_update(request: HttpRequest, item: ItemKegiatan):
    if request.method == "POST":
        save_type = request.POST.get("save_type", "all")
        handler   = SAVE_HANDLERS.get(save_type, _handle_save_all)
        return handler(request, item)

    return _render_update_page(request, item)


@staff_required
def item_update_jam(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    item_pk     = request.POST.get("item_pk")
    jam_mulai   = request.POST.get("jam_mulai", "").strip()
    jam_selesai = request.POST.get("jam_selesai", "").strip()

    if not item_pk:
        return JsonResponse({"success": False, "error": "Item ID diperlukan"})

    if not jam_mulai or not jam_selesai:
        return JsonResponse({"success": False, "error": "Jam mulai dan jam selesai wajib diisi"})

    item = get_object_or_404(
        ItemKegiatan.objects.select_related("laporan"),
        pk=item_pk,
        staff=request.user,
    )

    locked_msg = _item_locked_message(item)
    if locked_msg:
        return JsonResponse({"success": False, "error": locked_msg})

    try:
        parsed_mulai   = datetime.strptime(jam_mulai,   "%H:%M").time()
        parsed_selesai = datetime.strptime(jam_selesai, "%H:%M").time()
    except ValueError:
        return JsonResponse({"success": False, "error": "Format jam tidak valid (HH:MM)"})

    if parsed_selesai <= parsed_mulai:
        return JsonResponse({"success": False, "error": "Jam selesai harus setelah jam mulai"})

    item.jam_mulai   = parsed_mulai
    item.jam_selesai = parsed_selesai
    item.status      = Status.ON_PROGRESS
    item.save(update_fields=["jam_mulai", "jam_selesai", "status"])

    suggested_next = _suggest_jam_mulai(request.user, item.tanggal)

    return JsonResponse({
        "success"            : True,
        "redirect_url"       : f"/staff/item/{item.pk}/update/",
        "suggested_jam_mulai": suggested_next.strftime("%H:%M") if suggested_next else None,
    })


@staff_required
def item_create_insidental(request: HttpRequest):
    if request.method == "POST":
        form = ItemKegiatanInsidentalForm(
            request.POST,
            request.FILES,
            user=request.user,
        )
        if form.is_valid():
            item = form.save(commit=False)
            item.is_insidental = True
            item.task          = None
            item.sub_area      = None
            item.status        = Status.TERJADWAL
            item.save()
            item.staff.add(request.user)

            messages.success(
                request,
                f'Kegiatan insidental "{item.nama_item}" dibuat. Sekarang isi jam dan foto.',
            )
            return redirect("staff_item_list")
    else:
        form = ItemKegiatanInsidentalForm(user=request.user)

    return render(request, "staff/item/create_insidental.html", {
        "form"            : form,
        "laporan_otomatis": getattr(form, "laporan_otomatis", None),
        "page_title"      : "Tambah Kegiatan Insidental",
    })


# ---------------------------------------------------------------------------
# Views — Foto Tambahan (halaman terpisah — tetap dipertahankan)
# ---------------------------------------------------------------------------

@staff_required
def item_upload_foto_tambahan(request: HttpRequest, pk: int):
    item = get_object_or_404(
        ItemKegiatan.objects.select_related("laporan"),
        pk=pk,
        staff=request.user,
    )

    locked_msg = _item_locked_message(item)
    if locked_msg:
        messages.info(request, f"{locked_msg} Foto tidak dapat ditambahkan.")
        return redirect("staff_item_update", pk=pk)

    jumlah_foto = item.foto_tambahan.count()
    sudah_penuh = jumlah_foto >= FotoItemKegiatan.MAKS_FOTO

    if request.method == "POST":
        if sudah_penuh:
            messages.error(
                request,
                f"Batas maksimal {FotoItemKegiatan.MAKS_FOTO} foto tambahan sudah tercapai.",
            )
            return redirect("staff_item_update", pk=item.pk)

        form = FotoTambahanForm(request.POST, request.FILES)
        if form.is_valid():
            foto_obj      = form.save(commit=False)
            foto_obj.item = item
            last = (
                item.foto_tambahan
                .order_by("-urutan")
                .values_list("urutan", flat=True)
                .first()
            )
            foto_obj.urutan = (last or 0) + 1
            foto_obj.save()
            messages.success(request, "✓ Foto tambahan berhasil disimpan.")
            return redirect("staff_item_update", pk=item.pk)
    else:
        form = FotoTambahanForm()

    return render(request, "staff/item/foto_tambahan_form.html", {
        "form"       : form,
        "item"       : item,
        "jumlah_foto": jumlah_foto,
        "sisa_slot"  : FotoItemKegiatan.MAKS_FOTO - jumlah_foto,
        "sudah_penuh": sudah_penuh,
        "maks_foto"  : FotoItemKegiatan.MAKS_FOTO,
        "page_title" : f"Foto Tambahan — {item.nama_item}",
    })


@staff_required
def item_hapus_foto_tambahan(request: HttpRequest, foto_pk: int):
    foto = get_object_or_404(
        FotoItemKegiatan.objects.select_related("item", "item__laporan"),
        pk=foto_pk,
        item__staff=request.user,
    )
    item_pk = foto.item_id

    locked_msg = _item_locked_message(foto.item)
    if locked_msg:
        messages.info(request, f"{locked_msg} Foto tidak dapat dihapus.")
        return redirect("staff_item_update", pk=item_pk)

    foto.delete()
    messages.success(request, "Foto tambahan dihapus.")
    return redirect("staff_item_update", pk=item_pk)

# ---------------------------------------------------------------------------
# Views — Foto Tambahan (AJAX/JSON — untuk modal inline)
# ---------------------------------------------------------------------------

@staff_required
def item_upload_foto_tambahan_ajax(request: HttpRequest, pk: int):
    """Upload foto tambahan via AJAX — return JSON."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    item = get_object_or_404(
        ItemKegiatan.objects.select_related("laporan"),
        pk=pk,
        staff=request.user,
    )

    locked_msg = _item_locked_message(item)
    if locked_msg:
        return JsonResponse({"success": False, "error": locked_msg})

    jumlah_foto = item.foto_tambahan.count()
    if jumlah_foto >= FotoItemKegiatan.MAKS_FOTO:
        return JsonResponse({
            "success": False,
            "error"  : f"Batas maksimal {FotoItemKegiatan.MAKS_FOTO} foto sudah tercapai.",
        })

    form = FotoTambahanForm(request.POST, request.FILES)
    if not form.is_valid():
        errors = "; ".join(
            f"{f}: {', '.join(e)}" for f, e in form.errors.items()
        )
        return JsonResponse({"success": False, "error": errors})

    foto_obj      = form.save(commit=False)
    foto_obj.item = item
    last = (
        item.foto_tambahan
        .order_by("-urutan")
        .values_list("urutan", flat=True)
        .first()
    )
    foto_obj.urutan = (last or 0) + 1
    foto_obj.save()

    jumlah_baru = item.foto_tambahan.count()

    return JsonResponse({
        "success"    : True,
        "foto_pk"    : foto_obj.pk,
        "foto_url"   : foto_obj.foto.url,
        "jenis_label": foto_obj.get_jenis_display(),
        "keterangan" : foto_obj.keterangan or "",
        # hapus_url disertakan dari server — JS tidak perlu hardcode URL pattern
        "hapus_url"  : reverse("staff_item_foto_tambahan_hapus_ajax", args=[foto_obj.pk]),
        "jumlah"     : jumlah_baru,
        "sisa_slot"  : FotoItemKegiatan.MAKS_FOTO - jumlah_baru,
        "maks_foto"  : FotoItemKegiatan.MAKS_FOTO,
    })


@staff_required
def item_hapus_foto_tambahan_ajax(request: HttpRequest, foto_pk: int):
    """Hapus foto tambahan via AJAX — return JSON."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    foto = get_object_or_404(
        FotoItemKegiatan.objects.select_related("item", "item__laporan"),
        pk=foto_pk,
        item__staff=request.user,
    )

    locked_msg = _item_locked_message(foto.item)
    if locked_msg:
        return JsonResponse({"success": False, "error": locked_msg})

    item = foto.item
    foto.delete()

    jumlah_baru = item.foto_tambahan.count()

    return JsonResponse({
        "success"  : True,
        "jumlah"   : jumlah_baru,
        "sisa_slot": FotoItemKegiatan.MAKS_FOTO - jumlah_baru,
        "maks_foto": FotoItemKegiatan.MAKS_FOTO,
    })