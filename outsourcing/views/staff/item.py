# outsourcing/views/staff_views.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import wraps
from typing import Callable

from django.contrib import messages
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from outsourcing.decorators import staff_required
from outsourcing.forms.staff_forms import ItemKegiatanStaffForm, ItemKegiatanInsidentalForm
from outsourcing.models import ItemKegiatan
from django.db.models import Case, Count, IntegerField, Q, Value, When


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class Status:
    TERJADWAL          = "terjadwal"
    ON_PROGRESS        = "on_progress"
    MENUNGGU_APPROVAL  = "menunggu_approval"   # ← baru
    SELESAI            = "selesai"

# Status yang membuat item "terkunci" dari editing oleh staff
LOCKED_STATUSES = {Status.MENUNGGU_APPROVAL, Status.SELESAI}


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def _is_past_jam_selesai(item: ItemKegiatan) -> bool:
    """Return True kalau waktu sekarang sudah melewati jam_selesai item."""
    if not (item.jam_selesai and item.tanggal):
        return False
    deadline = timezone.make_aware(
        datetime.combine(item.tanggal, item.jam_selesai),
        timezone.get_current_timezone(),
    )
    return timezone.now() >= deadline


def _derive_status(item: ItemKegiatan) -> str:
    """
    Hitung status yang seharusnya berdasarkan state item saat ini.
    - Foto after + jam selesai tiba  → menunggu_approval (bukan langsung selesai)
    - Ada foto progress atau jam mulai → on_progress
    - Selainnya → status tidak berubah
    """
    if item.foto_after and _is_past_jam_selesai(item):
        return Status.MENUNGGU_APPROVAL          # ← diubah dari SELESAI
    if item.foto_on_progress or item.jam_mulai:
        return Status.ON_PROGRESS
    return item.status


def _suggest_jam_mulai(staff_user, tanggal: date, buffer_minutes: int = 2):
    """
    Kembalikan jam_mulai yang disarankan untuk pekerjaan berikutnya
    pada tanggal yang sama, berdasarkan jam_selesai terbaru staff hari itu.

    Return None jika belum ada item selesai pada tanggal tersebut.
    """
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


# ---------------------------------------------------------------------------
# Guard decorator
# ---------------------------------------------------------------------------

def item_not_done(view_fn: Callable) -> Callable:
    """
    Decorator untuk view yang menerima kwarg `pk`.
    Redirect ke list jika item sudah terkunci (menunggu_approval atau selesai).
    Staff tetap bisa mengerjakan item LAIN — hanya item ini yang dikunci.
    """
    @wraps(view_fn)
    def _wrapper(request: HttpRequest, pk: int, *args, **kwargs):
        item = get_object_or_404(ItemKegiatan, pk=pk, staff=request.user)
        if item.status in LOCKED_STATUSES:
            label = (
                "sedang menunggu approval customer"
                if item.status == Status.MENUNGGU_APPROVAL
                else "sudah selesai"
            )
            messages.info(request, f"Pekerjaan ini {label} dan tidak dapat diedit.")
            return redirect("staff_item_list")
        return view_fn(request, *args, item=item, **kwargs)
    return _wrapper


# ---------------------------------------------------------------------------
# Save-type handlers
# ---------------------------------------------------------------------------

def _handle_foto_progress(request: HttpRequest, item: ItemKegiatan):
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


def _handle_foto_after(request: HttpRequest, item: ItemKegiatan):
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

    item.foto_after = foto
    item.status     = Status.MENUNGGU_APPROVAL

    # Simpan keterangan keterlambatan jika diisi staff
    keterangan = request.POST.get("keterangan_after", "").strip()
    if keterangan:
        # Append ke catatan_staff yang mungkin sudah ada, tidak menimpa
        existing = item.catatan_staff.strip()
        item.catatan_staff = f"{existing}\n\n[Keterangan selesai]: {keterangan}".strip()

    item.save(update_fields=["foto_after", "status", "catatan_staff"])
    messages.success(
        request,
        "✓ Foto selesai disimpan. Pekerjaan menunggu approval dari customer.",
    )
    return redirect("staff_item_list")


def _handle_save_all(request: HttpRequest, item: ItemKegiatan):
    form = ItemKegiatanStaffForm(request.POST, request.FILES, instance=item)

    if not form.is_valid():
        return None, form

    updated_item = form.save(commit=False)

    if form.cleaned_data.get("foto_after") and not _is_past_jam_selesai(updated_item):
        messages.error(
            request,
            f"Belum bisa upload foto 'Setelah Selesai' karena jam selesai "
            f"({updated_item.jam_selesai.strftime('%H:%M')}) belum tiba.",
        )
        return None, form

    updated_item.status = _derive_status(updated_item)
    updated_item.save()
    messages.success(request, f"Pekerjaan \"{updated_item.nama_item}\" berhasil diperbarui.")
    return redirect("staff_item_list"), None


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
                When(status=Status.TERJADWAL,          then=Value(0)),
                When(status=Status.ON_PROGRESS,        then=Value(1)),
                When(status=Status.MENUNGGU_APPROVAL,  then=Value(2)),  # ← baru
                When(status=Status.SELESAI,            then=Value(3)),
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
    SAVE_HANDLERS: dict[str, Callable] = {
        "foto_progress": _handle_foto_progress,
        "foto_after"   : _handle_foto_after,
    }

    if request.method == "POST":
        save_type = request.POST.get("save_type", "all")
        handler   = SAVE_HANDLERS.get(save_type)

        if handler:
            return handler(request, item)

        response, form = _handle_save_all(request, item)
        if response:
            return response
    else:
        form = ItemKegiatanStaffForm(instance=item)

        # ── Auto-suggest jam_mulai jika belum terisi ──────────────────── #
        if not item.jam_mulai:
            suggested = _suggest_jam_mulai(request.user, item.tanggal)
            if suggested:
                # Isi initial form (tidak disimpan ke DB sampai staff submit)
                form.initial["jam_mulai"] = suggested.strftime("%H:%M")

    return render(request, "staff/item/update.html", {
        "form"        : form,
        "item"        : item,
        "page_title"  : item.nama_item,
        "disable_save": not _is_past_jam_selesai(item),
    })


@staff_required
def item_update_jam(request: HttpRequest):
    """AJAX view untuk menyimpan jam mulai dan jam selesai."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    item_pk     = request.POST.get("item_pk")
    jam_mulai   = request.POST.get("jam_mulai", "").strip()
    jam_selesai = request.POST.get("jam_selesai", "").strip()

    if not item_pk:
        return JsonResponse({"success": False, "error": "Item ID diperlukan"})

    if not jam_mulai or not jam_selesai:
        return JsonResponse({"success": False, "error": "Jam mulai dan jam selesai wajib diisi"})

    item = get_object_or_404(ItemKegiatan, pk=item_pk, staff=request.user)

    if item.status in LOCKED_STATUSES:
        return JsonResponse({"success": False, "error": "Pekerjaan sudah terkunci"})

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

    # Kembalikan saran jam_mulai untuk item berikutnya (info tambahan untuk frontend)
    suggested_next = _suggest_jam_mulai(request.user, item.tanggal)

    return JsonResponse({
        "success"           : True,
        "redirect_url"      : f"/staff/item/{item.pk}/update/",
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
        "form"             : form,
        "laporan_otomatis" : getattr(form, "laporan_otomatis", None),
        "page_title"       : "Tambah Kegiatan Insidental",
    })

