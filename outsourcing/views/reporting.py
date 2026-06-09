from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.conf import settings

import os
import calendar
from datetime import date

from outsourcing.models import (
    LaporanKegiatan, ItemKegiatan, Absensi,
    StaffSupervisor, SupervisorPerusahaan,
    Perusahaan, JenisJasa
)

from outsourcing.views.holiday_service import get_hari_libur_set


# ──────────────────────────────────────────────────
# HELPER: BUILD DATA KALENDER
# ──────────────────────────────────────────────────

def build_jadwal_kalender(item_list, bulan, tahun):
    _, days_in_month = calendar.monthrange(int(tahun), int(bulan))
    jadwal = {}
    staff_per_sub_area = {}

    for item in item_list:
        sub_area_name = item.sub_area.nama_sub_area if item.sub_area else 'Tanpa Sub Area'
        if sub_area_name not in jadwal:
            jadwal[sub_area_name] = {}
            staff_per_sub_area[sub_area_name] = set()

        key = item.pk
        if key not in jadwal[sub_area_name]:
            staff_names = (
                ', '.join([staff.nama_lengkap or staff.username for staff in item.staff.all()])
                if item.staff.exists() else '-'
            )
            jadwal[sub_area_name][key] = {
                'nama_item'    : item.nama_item,
                'task'         : item.task.nama_task if item.task else '-',
                'standar'      : item.task.standar if item.task and item.task.standar else '-',
                'sub_area'     : item.sub_area.nama_sub_area if item.sub_area else '-',
                'staff'        : staff_names,
                'tanggal_aktif': set(),
            }

        for staff in item.staff.all():
            staff_per_sub_area[sub_area_name].add(staff.nama_lengkap or staff.username)

        if item.tanggal:
            jadwal[sub_area_name][key]['tanggal_aktif'].add(item.tanggal.day)

    jadwal_final = {}
    for sub_area_name, items_dict in jadwal.items():
        items_list = list(items_dict.values())
        if items_list:
            unique_staff = sorted(staff_per_sub_area[sub_area_name])
            items_list[0]['staff_unik'] = ', '.join(unique_staff)
        jadwal_final[sub_area_name] = items_list

    return jadwal_final, days_in_month

def build_absensi_kalender(absensi_list, bulan, tahun, libur_set=None):


    if libur_set is None:
        libur_set = set()

    _, days_in_month = calendar.monthrange(int(tahun), int(bulan))

    # Precompute info per hari: Minggu atau libur nasional?
    info_hari = {}
    for day in range(1, days_in_month + 1):
        tgl               = date(int(tahun), int(bulan), day)
        tgl_str           = str(tgl)
        is_minggu         = tgl.weekday() == 6       # 6 = Minggu
        is_libur_nasional = tgl_str in libur_set
        info_hari[day] = {
            'is_libur'   : is_minggu or is_libur_nasional,
            'is_minggu'  : is_minggu,
            'is_nasional': is_libur_nasional,
        }

    absensi_map = {}

    for ab in absensi_list:
        sid = ab.staff_id
        if sid not in absensi_map:
            absensi_map[sid] = {
                'nama'         : ab.staff.nama_lengkap or ab.staff.username,
                'nik'          : ab.staff.nik or '-',
                'foto'         : ab.staff.foto_profil.url if ab.staff.foto_profil else None,
                'jumlah_hadir' : 0,
                'jumlah_alpa'  : 0,
                'jumlah_izin'  : 0,
                'jumlah_cuti'  : 0,
                'jumlah_dokter': 0,
                'keterangan'   : '',
            }

        if ab.tanggal:
            status_harian = getattr(ab, 'status_harian', None)
            if status_harian and status_harian.strip():
                status = status_harian.strip()
            else:
                status = 'P' if ab.waktu_masuk else 'A'

            absensi_map[sid][f'd_{ab.tanggal.day}'] = status

            if status == 'P':
                absensi_map[sid]['jumlah_hadir'] += 1
            elif status == 'A':
                absensi_map[sid]['jumlah_alpa'] += 1
            elif status == 'I':
                absensi_map[sid]['jumlah_izin'] += 1
            elif status == 'L':
                absensi_map[sid]['jumlah_cuti'] += 1
            elif status == 'DC':
                absensi_map[sid]['jumlah_dokter'] += 1

    # Build hari_list sebagai list of dict per staff
    for sid, data in absensi_map.items():
        hari_list = []
        for d in range(1, days_in_month + 1):
            status   = data.get(f'd_{d}', '')
            is_libur = info_hari[d]['is_libur']
            # Hari libur tanpa absensi → otomatis 'LB'
            if is_libur and not status:
                status = 'LB'
            hari_list.append({
                'status'  : status,
                'is_libur': is_libur,
            })
        data['hari_list'] = hari_list

    return absensi_map, days_in_month, info_hari


def build_laporan_dengan_jadwal(laporan_list, days_in_month):
    result = []
    for laporan in laporan_list:
        items_data = []
        for item in laporan.item_kegiatan.select_related('task', 'sub_area').all():
            hari_list = [''] * days_in_month
            if item.tanggal:
                idx = item.tanggal.day - 1
                if 0 <= idx < days_in_month:
                    hari_list[idx] = '✓'
            items_data.append({
                'nama_item': item.nama_item,
                'standar'  : item.task.standar if item.task and item.task.standar else '-',
                'sub_area' : item.sub_area.nama_sub_area if item.sub_area else '-',
                'task'     : item.task.nama_task if item.task else '-',
                'frek'     : 'H' if item.jam_mulai else 'M',
                'hari_list': hari_list,
            })
        result.append({
            'laporan'   : laporan,
            'area_nama' : laporan.area.nama_area if laporan.area else '-',
            'supervisor': laporan.supervisor.nama_lengkap or laporan.supervisor.username,
            'items'     : items_data,
        })
    return result


# ──────────────────────────────────────────────────
# MAIN DATA GETTER
# ──────────────────────────────────────────────────

def get_data_laporan_bulanan(perusahaan_id, bulan, tahun, jenis_jasa_id):
    laporan_list = LaporanKegiatan.objects.filter(
        perusahaan_id=perusahaan_id,
        jenis_jasa_id=jenis_jasa_id,
        tanggal_laporan__year=tahun,
        tanggal_laporan__month=bulan,
    ).prefetch_related(
        'item_kegiatan__staff',
        'item_kegiatan__task',
        'item_kegiatan__sub_area',
    ).select_related('supervisor', 'area', 'jenis_jasa')

    supervisor_ids = list(
        laporan_list.values_list('supervisor_id', flat=True).distinct()
    )

    staff_list = StaffSupervisor.objects.filter(
        supervisor_id__in=supervisor_ids,
        is_active=True,
    ).select_related('staff', 'supervisor')

    staff_ids = list(staff_list.values_list('staff_id', flat=True).distinct())

    absensi_list = Absensi.objects.filter(
        staff_id__in=staff_ids,
        tanggal__year=tahun,
        tanggal__month=bulan,
    ).select_related('staff').order_by('staff__nama_lengkap', 'tanggal')

    item_list = ItemKegiatan.objects.filter(
        laporan__in=laporan_list,
    ).prefetch_related('staff').select_related(
        'task', 'sub_area', 'laporan__area'
    ).order_by('laporan__area__nama_area', 'tanggal')

    libur_set = get_hari_libur_set(tahun=int(tahun), bulan=int(bulan))

    jadwal_kalender, days_in_month = build_jadwal_kalender(item_list, bulan, tahun)

    absensi_kalender, _, info_hari = build_absensi_kalender(
        absensi_list, bulan, tahun, libur_set=libur_set
    )

    laporan_dengan_jadwal = build_laporan_dengan_jadwal(laporan_list, days_in_month)

    staff_subarea_map_raw = {}
    for item in item_list:
        sub_area_nama = item.sub_area.nama_sub_area if item.sub_area else '-'
        for staff in item.staff.all():
            if staff.pk not in staff_subarea_map_raw:
                staff_subarea_map_raw[staff.pk] = set()
            staff_subarea_map_raw[staff.pk].add(sub_area_nama)

    staff_subarea_map = {
        pk: ', '.join(sorted(subs))
        for pk, subs in staff_subarea_map_raw.items()
    }

    absensi_totals = {
        'hadir' : sum(d.get('jumlah_hadir',  0) for d in absensi_kalender.values()),
        'alpa'  : sum(d.get('jumlah_alpa',   0) for d in absensi_kalender.values()),
        'izin'  : sum(d.get('jumlah_izin',   0) for d in absensi_kalender.values()),
        'cuti'  : sum(d.get('jumlah_cuti',   0) for d in absensi_kalender.values()),
        'dokter': sum(d.get('jumlah_dokter', 0) for d in absensi_kalender.values()),
    }

    return {
        'laporan_list'         : laporan_list,
        'staff_list'           : staff_list,
        'absensi_list'         : absensi_list,
        'item_list'            : item_list,
        'supervisor_ids'       : supervisor_ids,
        'staff_ids'            : staff_ids,
        'jadwal_kalender'      : jadwal_kalender,
        'absensi_kalender'     : absensi_kalender,
        'laporan_dengan_jadwal': laporan_dengan_jadwal,
        'days_in_month'        : days_in_month,
        'days_range'           : list(range(1, days_in_month + 1)),
        'info_hari'            : info_hari,
        'staff_subarea_map'    : staff_subarea_map,
        'absensi_totals'       : absensi_totals,
    }  


# ──────────────────────────────────────────────────
# VIEW UTAMA
# ──────────────────────────────────────────────────

@login_required
def generate_laporan_bulanan(request, perusahaan_id, tahun, bulan, jenis_jasa_id, format):
    try:
        user       = request.user
        perusahaan = get_object_or_404(Perusahaan, pk=perusahaan_id)
        jenis_jasa = get_object_or_404(JenisJasa, pk=jenis_jasa_id)

        if not (user.is_admin or user.is_kepala_supervisor):
            is_assigned = SupervisorPerusahaan.objects.filter(
                supervisor=user,
                perusahaan=perusahaan,
                jenis_jasa=jenis_jasa,
                is_active=True,
            ).exists()
            if not is_assigned:
                return HttpResponse("Tidak punya akses.", status=403)

        data = get_data_laporan_bulanan(perusahaan_id, bulan, tahun, jenis_jasa_id)

        nama_bulan_list = [
            '', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
            'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
        ]
        nama_bulan = nama_bulan_list[int(bulan)]

        nama_perusahaan_safe = "".join(
            c for c in perusahaan.nama_perusahaan if c.isalnum() or c in (' ', '-', '_')
        ).strip().replace(' ', '_')

        context = {
            **data,
            'perusahaan': perusahaan,
            'jenis_jasa': jenis_jasa,
            'bulan'     : bulan,
            'tahun'     : tahun,
            'nama_bulan': nama_bulan,
            'nama_file' : f"Laporan_{nama_perusahaan_safe}_{nama_bulan}_{tahun}",
        }

        if format == 'pdf':
            return _generate_pdf(request, context)
        elif format == 'word':
            return _generate_word(request, context)
        else:
            return HttpResponse("Format tidak dikenal. Gunakan 'pdf' atau 'word'.", status=400)

    except Exception as e:
        return HttpResponse(f"Gagal generate laporan: {e}", status=500)


# ──────────────────────────────────────────────────
# PDF & WORD GENERATOR
# ──────────────────────────────────────────────────

def _fetch_resources(uri, rel):
    if uri.startswith(settings.MEDIA_URL):
        return os.path.join(
            settings.MEDIA_ROOT,
            uri.replace(settings.MEDIA_URL, '').lstrip('/')
        )
    if uri.startswith(settings.STATIC_URL):
        static_root = getattr(settings, 'STATIC_ROOT', None) or ''
        return os.path.join(
            static_root,
            uri.replace(settings.STATIC_URL, '').lstrip('/')
        )
    return uri


def _generate_pdf(request, context):
    try:
        from weasyprint import HTML
        html_string = render_to_string('laporan_bulanan_pdf.html', context, request=request)
        base_url    = request.build_absolute_uri('/')
        pdf_bytes   = HTML(string=html_string, base_url=base_url).write_pdf()
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{context["nama_file"]}.pdf"'
        return response
    except Exception as e:
        return HttpResponse(f"Error PDF: {e}", status=500)


# Ganti HANYA fungsi ini di views lo

"""
_generate_word menggunakan python-docx murni.
Paste fungsi-fungsi ini ke views.py lo (atau file terpisah lalu import).

Struktur section:
  Cover          → portrait
  Daftar Isi     → portrait
  I.  Karyawan   → portrait
  II. Organisasi → portrait
  III.Jadwal     → LANDSCAPE
  IV. Absensi    → LANDSCAPE
  V.  Program    → LANDSCAPE
  VI. Foto       → portrait
  VII.Penutup    → portrait
"""

import io
from docx import Document
from docx.shared import Pt, RGBColor, Cm, Inches, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree


# ══════════════════════════════════════════════════════
# WARNA BRAND
# ══════════════════════════════════════════════════════
C_NAVY    = RGBColor(0x1a, 0x3a, 0x5c)   # header utama
C_NAVY2   = RGBColor(0x2c, 0x4e, 0x6e)   # header tabel kalender
C_WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
C_GRAY    = RGBColor(0x60, 0x70, 0x80)
C_LGRAY   = RGBColor(0x80, 0x99, 0xb0)
C_GREEN   = RGBColor(0x1a, 0x6b, 0x3a)
C_RED     = RGBColor(0xc0, 0x39, 0x2b)
C_ORANGE  = RGBColor(0xbf, 0x6b, 0x00)
C_BLUE    = RGBColor(0x00, 0x5b, 0xb5)
C_BGLIGHT = "F4F7FB"   # hex string untuk shading
C_BGROW   = "F9FBFD"
C_BORDER  = "C8D4E0"


# ══════════════════════════════════════════════════════
# XML HELPERS
# ══════════════════════════════════════════════════════

def set_cell_bg(cell, hex_color):
    """Set background warna cell tabel."""
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  hex_color)
    # hapus shd lama kalau ada
    for old in tcPr.findall(qn('w:shd')):
        tcPr.remove(old)
    tcPr.append(shd)


def set_cell_borders(cell, color="C8D4E0", size=4):
    """Set border semua sisi cell."""
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for side in ['top', 'left', 'bottom', 'right']:
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'),   'single')
        el.set(qn('w:sz'),    str(size))
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), color)
        tcBorders.append(el)
    for old in tcPr.findall(qn('w:tcBorders')):
        tcPr.remove(old)
    tcPr.append(tcBorders)


def set_cell_margins(cell, top=60, bottom=60, left=100, right=100):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for side, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:w'),    str(val))
        el.set(qn('w:type'), 'dxa')
        tcMar.append(el)
    for old in tcPr.findall(qn('w:tcMar')):
        tcPr.remove(old)
    tcPr.append(tcMar)


def set_cell_valign(cell, align='center'):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    vAlign = OxmlElement('w:vAlign')
    vAlign.set(qn('w:val'), align)
    for old in tcPr.findall(qn('w:vAlign')):
        tcPr.remove(old)
    tcPr.append(vAlign)


def add_page_break(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    br  = OxmlElement('w:br')
    br.set(qn('w:type'), 'page')
    run._r.append(br)
    return p


def set_section_landscape(section):
    """Ubah section menjadi landscape A4."""
    section.orientation = 1   # WD_ORIENT.LANDSCAPE
    section.page_width  = Cm(29.7)
    section.page_height = Cm(21.0)
    section.left_margin   = Cm(1.5)
    section.right_margin  = Cm(1.5)
    section.top_margin    = Cm(1.2)
    section.bottom_margin = Cm(1.2)


def set_section_portrait(section):
    """Ubah section menjadi portrait A4."""
    section.orientation = 0   # WD_ORIENT.PORTRAIT
    section.page_width  = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin   = Cm(1.5)
    section.right_margin  = Cm(1.5)
    section.top_margin    = Cm(1.5)
    section.bottom_margin = Cm(2.0)


def content_width_dxa(section):
    """Hitung lebar konten dalam DXA (twips)."""
    return int((section.page_width - section.left_margin - section.right_margin) / 914.4 * 1440)


def add_section_break(doc, landscape=False):
    """
    Tambahkan section break (next page) dan set orientasi section baru.
    Return section baru.
    """
    new_section = doc.add_section(2)   # 2 = WD_SECTION.NEW_PAGE (next page break)
    if landscape:
        set_section_landscape(new_section)
    else:
        set_section_portrait(new_section)
    return new_section


# ══════════════════════════════════════════════════════
# HEADING / PARAGRAPH HELPERS
# ══════════════════════════════════════════════════════

def add_section_header(doc, number, title, subtitle=''):
    """Tambah section heading bergaya UNIPACS."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after  = Pt(6)
    # border bawah
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'),   'single')
    bottom.set(qn('w:sz'),    '4')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'C8D4E0')
    pBdr.append(bottom)
    pPr.append(pBdr)

    run = p.add_run(f'{number}.  {title}')
    run.bold       = True
    run.font.size  = Pt(11)
    run.font.color.rgb = C_NAVY
    if subtitle:
        p.add_run(f'  —  {subtitle}').font.color.rgb = C_GRAY
    return p


def add_info_bar(doc, text, sub=''):
    """Bar biru navy di atas tabel (mirip .kal-info)."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(0)
    # background biru via highlight tidak bisa, pakai tabel 1 row
    tbl = doc.add_table(rows=1, cols=1)
    tbl.style = 'Table Grid'
    cell = tbl.rows[0].cells[0]
    set_cell_bg(cell, '1A3A5C')
    set_cell_margins(cell, 60, 60, 120, 120)
    cp = cell.paragraphs[0]
    r  = cp.add_run(text)
    r.bold           = True
    r.font.size      = Pt(7.5)
    r.font.color.rgb = C_WHITE
    if sub:
        r2 = cp.add_run(f'    {sub}')
        r2.font.size      = Pt(6.5)
        r2.font.color.rgb = RGBColor(0xdd, 0xee, 0xff)
    return tbl


def header_cell(cell, text, font_size=7, bg='1A3A5C'):
    set_cell_bg(cell, bg)
    set_cell_borders(cell, color='3A5F80', size=4)
    set_cell_margins(cell, 40, 40, 80, 80)
    set_cell_valign(cell, 'center')
    p    = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run  = p.add_run(text)
    run.bold           = True
    run.font.size      = Pt(font_size)
    run.font.color.rgb = C_WHITE


def data_cell(cell, text, font_size=7.5, align=WD_ALIGN_PARAGRAPH.LEFT,
              bold=False, color=None, bg=None):
    if bg:
        set_cell_bg(cell, bg)
    set_cell_borders(cell, color='D5DDE8', size=4)
    set_cell_margins(cell, 40, 40, 80, 80)
    set_cell_valign(cell, 'center')
    p   = cell.paragraphs[0]
    p.alignment = align
    run = p.add_run(str(text) if text is not None else '-')
    run.bold          = bold
    run.font.size     = Pt(font_size)
    if color:
        run.font.color.rgb = color


# ══════════════════════════════════════════════════════
# SECTION BUILDERS
# ══════════════════════════════════════════════════════

def build_cover(doc, ctx):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(40)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('LAPORAN BULANAN')
    r.bold = True; r.font.size = Pt(24); r.font.color.rgb = C_NAVY

    p2 = doc.add_paragraph(ctx['perusahaan'].nama_perusahaan)
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.runs[0].bold = True; p2.runs[0].font.size = Pt(16); p2.runs[0].font.color.rgb = C_NAVY

    p3 = doc.add_paragraph(ctx['jenis_jasa'].nama_jasa)
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.runs[0].font.size = Pt(12); p3.runs[0].font.color.rgb = C_GRAY

    p4 = doc.add_paragraph(f"Periode: {ctx['nama_bulan']} {ctx['tahun']}")
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p4.runs[0].font.size = Pt(12)

    if ctx['perusahaan'].alamat:
        p5 = doc.add_paragraph(ctx['perusahaan'].alamat)
        p5.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p5.runs[0].font.size = Pt(10); p5.runs[0].font.color.rgb = C_GRAY

    # Info grid (tabel 2x2)
    doc.add_paragraph()
    tbl = doc.add_table(rows=2, cols=2)
    tbl.style = 'Table Grid'
    labels = [['Klien / Lokasi', 'Periode'],
              ['Jenis Jasa',     'Supervisor']]
    supervisor = ''
    for l in ctx['laporan_list']:
        supervisor = l.supervisor.nama_lengkap or l.supervisor.username
        break
    values = [
        [ctx['perusahaan'].nama_perusahaan, f"{ctx['nama_bulan'].upper()} {ctx['tahun']}"],
        [ctx['jenis_jasa'].nama_jasa,       supervisor],
    ]
    for ri, row in enumerate(tbl.rows):
        for ci, cell in enumerate(row.cells):
            set_cell_bg(cell, 'F4F7FB')
            set_cell_borders(cell, color='C8D4E0')
            set_cell_margins(cell)
            p = cell.paragraphs[0]
            rl = p.add_run(labels[ri][ci] + '\n')
            rl.font.size = Pt(6.5); rl.font.color.rgb = C_LGRAY; rl.bold = True
            rv = p.add_run(values[ri][ci])
            rv.font.size = Pt(9); rv.font.color.rgb = C_NAVY; rv.bold = True

    # Foto perusahaan
    if hasattr(ctx['perusahaan'], 'foto_perusahaan') and ctx['perusahaan'].foto_perusahaan:
        try:
            doc.add_paragraph()
            doc.add_picture(ctx['perusahaan'].foto_perusahaan.path, width=Cm(17))
        except Exception:
            pass


def build_daftar_isi(doc, ctx):
    add_section_header(doc, '', 'DAFTAR ISI', f"{ctx['nama_bulan']} {ctx['tahun']}")
    items = [
        ('I.',   'Data Karyawan',                    '3'),
        ('II.',  'Struktur Organisasi',               '4'),
        ('III.', 'Jadwal dan Ploting Kerja',          '5'),
        ('IV.',  'Rekap Absensi Karyawan',            '6'),
        ('V.',   'Program dan Pelaksanaan Pekerjaan', '7'),
        ('VI.',  'Foto Progres',                      '8'),
        ('VII.', 'Penutup',                           '9'),
    ]
    for num, title, pg in items:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after  = Pt(4)
        # border bawah dotted
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement('w:pBdr')
        bot = OxmlElement('w:bottom')
        bot.set(qn('w:val'), 'dotted')
        bot.set(qn('w:sz'), '4')
        bot.set(qn('w:space'), '1')
        bot.set(qn('w:color'), 'C8D4E0')
        pBdr.append(bot)
        pPr.append(pBdr)
        r1 = p.add_run(f'{num}  {title}')
        r1.font.size = Pt(11)
        r1.bold = True if num in ['I.', 'II.', 'III.', 'IV.', 'V.', 'VI.', 'VII.'] else False
        r1.font.color.rgb = C_NAVY


def build_karyawan(doc, ctx):
    add_section_header(doc, 'I', 'DATA KARYAWAN',
                       f"Total {len(ctx['staff_list'])} karyawan aktif — {ctx['nama_bulan']} {ctx['tahun']}")

    cols    = [5, 35, 18, 27, 15]   # persen
    headers = ['No', 'Nama Lengkap', 'NIK', 'Sub Area', 'Status']

    # hitung lebar kolom dalam DXA
    sec   = doc.sections[-1]
    total = content_width_dxa(sec)
    widths = [int(total * c / 100) for c in cols]

    tbl = doc.add_table(rows=1, cols=5)
    tbl.style = 'Table Grid'
    for i, cell in enumerate(tbl.rows[0].cells):
        cell.width = Twips(widths[i])
        header_cell(cell, headers[i])

    for idx, rel in enumerate(ctx['staff_list']):
        row   = tbl.add_row()
        cells = row.cells
        bg    = 'F9FBFD' if idx % 2 == 1 else 'FFFFFF'
        subarea = ctx['staff_subarea_map'].get(rel.staff.pk, '-')
        data_cell(cells[0], idx + 1,            align=WD_ALIGN_PARAGRAPH.CENTER, bg=bg)
        data_cell(cells[1], (rel.staff.nama_lengkap or rel.staff.username).upper(),
                  bold=True, bg=bg)
        data_cell(cells[2], rel.staff.nik or '-', align=WD_ALIGN_PARAGRAPH.CENTER, bg=bg)
        data_cell(cells[3], subarea,              bg=bg)
        data_cell(cells[4], 'Aktif',              align=WD_ALIGN_PARAGRAPH.CENTER,
                  color=C_GREEN, bg=bg)

    if not ctx['staff_list']:
        row = tbl.add_row()
        data_cell(row.cells[0], 'Tidak ada data karyawan.',
                  align=WD_ALIGN_PARAGRAPH.CENTER)


def build_organisasi(doc, ctx):
    add_section_header(doc, 'II', 'STRUKTUR ORGANISASI',
                       f"Area {ctx['perusahaan'].nama_perusahaan}")

    supervisor = ''
    for l in ctx['laporan_list']:
        supervisor = l.supervisor.nama_lengkap or l.supervisor.username
        break

    # Kotak SPV
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.rows[0].cells[0]
    set_cell_bg(cell, '1A3A5C')
    set_cell_margins(cell, 80, 80, 200, 200)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p.add_run(f'SPV {ctx["jenis_jasa"].nama_jasa.upper()}\n')
    r1.bold = True; r1.font.size = Pt(9); r1.font.color.rgb = C_WHITE
    r2 = p.add_run(supervisor)
    r2.font.size = Pt(8); r2.font.color.rgb = RGBColor(0xdd, 0xee, 0xff)

    # Panah
    pa = doc.add_paragraph('↓')
    pa.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pa.runs[0].font.color.rgb = C_NAVY

    # Tabel staff (6 kolom per baris, auto-wrap)
    cols_per_row = 6
    staff_rows_data = [ctx['staff_list'][i:i+cols_per_row]
                       for i in range(0, len(ctx['staff_list']), cols_per_row)]

    sec   = doc.sections[-1]
    total = content_width_dxa(sec)
    col_w = total // cols_per_row

    for row_data in staff_rows_data:
        # pad biar selalu 6 kolom
        while len(row_data) < cols_per_row:
            row_data.append(None)
        tbl2 = doc.add_table(rows=1, cols=cols_per_row)
        tbl2.style = 'Table Grid'
        for ci, rel in enumerate(row_data):
            cell = tbl2.rows[0].cells[ci]
            cell.width = Twips(col_w)
            set_cell_margins(cell, 60, 60, 60, 60)
            if rel is None:
                set_cell_bg(cell, 'FFFFFF')
                set_cell_borders(cell, color='FFFFFF')
                continue
            set_cell_bg(cell, 'F4F7FB')
            set_cell_borders(cell, color='C8D4E0')
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(rel.staff.nama_lengkap or rel.staff.username)
            r.bold = True; r.font.size = Pt(6.5); r.font.color.rgb = C_NAVY
        doc.add_paragraph()


def build_jadwal(doc, ctx):
    """Section III — Jadwal (landscape)."""
    add_section_header(doc, 'III', 'JADWAL DAN PLOTING KERJA',
                       f"{ctx['nama_bulan']} {ctx['tahun']}")

    sec   = doc.sections[-1]
    total = content_width_dxa(sec)
    days  = ctx['days_range']
    n_days = len(days)

    # Lebar kolom (DXA): no=300, item=1800, std=1500, task=1500, hari=sisa dibagi n_days
    fixed = 300 + 1800 + 1500 + 1500
    day_w = max(int((total - fixed) / n_days), 200)
    col_widths = [300, 1800, 1500, 1500] + [day_w] * n_days

    for sub_area_name, items in ctx['jadwal_kalender'].items():
        staff_unik = items[0].get('staff_unik', '-') if items else '-'
        add_info_bar(doc,
                     f'PELAKSANAAN KERJA BULANAN — {ctx["jenis_jasa"].nama_jasa.upper()}',
                     f'{ctx["perusahaan"].nama_perusahaan.upper()} — {ctx["nama_bulan"]} {ctx["tahun"]}')

        # Bar lokasi
        loc_p = doc.add_paragraph()
        loc_p.paragraph_format.space_before = Pt(0)
        loc_p.paragraph_format.space_after  = Pt(2)
        r = loc_p.add_run(f'Lokasi: {sub_area_name}    Staff: {staff_unik}')
        r.font.size = Pt(7); r.font.color.rgb = C_NAVY; r.bold = True

        tbl = doc.add_table(rows=1, cols=4 + n_days)
        tbl.style = 'Table Grid'

        # Header row
        hrow = tbl.rows[0]
        for i, cell in enumerate(hrow.cells):
            cell.width = Twips(col_widths[i])
        header_cell(hrow.cells[0], 'No',       6)
        header_cell(hrow.cells[1], 'Item Job',  6, bg='2C4E6E')
        header_cell(hrow.cells[2], 'Standard',  6, bg='2C4E6E')
        header_cell(hrow.cells[3], 'Task',      6, bg='2C4E6E')
        for di, d in enumerate(days):
            header_cell(hrow.cells[4 + di], str(d), 5, bg='2C4E6E')

        for idx, item in enumerate(items):
            row  = tbl.add_row()
            bg   = 'F7F9FC' if idx % 2 == 1 else 'FFFFFF'
            for ci in range(len(row.cells)):
                row.cells[ci].width = Twips(col_widths[ci])
            data_cell(row.cells[0], idx + 1,          font_size=6, align=WD_ALIGN_PARAGRAPH.CENTER, bg=bg)
            data_cell(row.cells[1], item['nama_item'], font_size=6, bg=bg)
            data_cell(row.cells[2], item['standar'],   font_size=6, bg=bg)
            data_cell(row.cells[3], item['task'],      font_size=6, bg=bg)
            for di, d in enumerate(days):
                mark = 'A' if d in item['tanggal_aktif'] else ''
                data_cell(row.cells[4 + di], mark, font_size=5,
                          align=WD_ALIGN_PARAGRAPH.CENTER,
                          bold=bool(mark), color=C_NAVY if mark else None, bg=bg)

        doc.add_paragraph()


def build_absensi(doc, ctx):
    """Section IV — Absensi (landscape)."""
    add_section_header(doc, 'IV', 'REKAP ABSENSI KARYAWAN',
                       f"Divisi: {ctx['jenis_jasa'].nama_jasa}  —  {ctx['nama_bulan'].upper()} {ctx['tahun']}")

    # Summary cards (tabel 5 kolom)
    tbl_s = doc.add_table(rows=2, cols=5)
    tbl_s.style = 'Table Grid'
    labels = ['Hadir', 'Alpa', 'Izin', 'Cuti', 'Srt. Dokter']
    colors = ['1A6B3A', 'C0392B', 'BF6B00', '1A3A5C', '005BB5']
    vals   = [
        ctx['absensi_totals']['hadir'],
        ctx['absensi_totals']['alpa'],
        ctx['absensi_totals']['izin'],
        ctx['absensi_totals']['cuti'],
        ctx['absensi_totals']['dokter'],
    ]
    for ci in range(5):
        header_cell(tbl_s.rows[0].cells[ci], labels[ci], 7, bg=colors[ci])
        cell = tbl_s.rows[1].cells[ci]
        set_cell_bg(cell, 'FFFFFF')
        set_cell_borders(cell, color='C8D4E0')
        set_cell_margins(cell, 60, 60, 60, 60)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(str(vals[ci]))
        r.bold = True; r.font.size = Pt(14)
        r.font.color.rgb = RGBColor(
            int(colors[ci][:2], 16),
            int(colors[ci][2:4], 16),
            int(colors[ci][4:], 16),
        )
    doc.add_paragraph()

    # Tabel absensi 31 kolom
    sec   = doc.sections[-1]
    total = content_width_dxa(sec)
    days  = ctx['days_range']
    n_days = len(days)

    fixed = 280 + 1400 + 900   # no + nama + nik
    sum_cols = 5                # P A I L DC
    ket_col  = 600
    day_w    = max(int((total - fixed - sum_cols * 280 - ket_col) / n_days), 200)

    col_widths = ([280, 1400, 900]
                  + [day_w] * n_days
                  + [280, 280, 280, 280, 280, ket_col])

    tbl = doc.add_table(rows=1, cols=3 + n_days + 6)
    tbl.style = 'Table Grid'

    hrow = tbl.rows[0]
    for i, cell in enumerate(hrow.cells):
        cell.width = Twips(col_widths[i])
    header_cell(hrow.cells[0], 'No',   5.5)
    header_cell(hrow.cells[1], 'Nama', 5.5)
    header_cell(hrow.cells[2], 'NIK',  5.5)
    for di, d in enumerate(days):
        info = ctx['info_hari'].get(d, {})
        bg   = 'C0392B' if info.get('is_libur') else '1A3A5C'
        header_cell(hrow.cells[3 + di], str(d), 5, bg=bg)
    for ci2, lbl in enumerate(['P', 'A', 'I', 'L', 'DC', 'Ket']):
        header_cell(hrow.cells[3 + n_days + ci2], lbl, 5.5)

    status_colors = {
        'P': C_GREEN, 'A': C_RED, 'I': C_ORANGE,
        'L': C_NAVY,  'DC': C_BLUE, 'LB': C_LGRAY,
    }

    for idx, (staff_id, data) in enumerate(ctx['absensi_kalender'].items()):
        row = tbl.add_row()
        bg  = 'F7F9FC' if idx % 2 == 1 else 'FFFFFF'
        for ci in range(len(row.cells)):
            row.cells[ci].width = Twips(col_widths[ci])
        data_cell(row.cells[0], idx + 1, font_size=5.5,
                  align=WD_ALIGN_PARAGRAPH.CENTER, bg=bg)
        data_cell(row.cells[1], data['nama'].upper(), font_size=5.5,
                  bold=True, bg=bg)
        data_cell(row.cells[2], data['nik'], font_size=5.5,
                  align=WD_ALIGN_PARAGRAPH.CENTER, bg=bg)

        for di, h in enumerate(data['hari_list']):
            s      = h['status']
            is_lib = h['is_libur']
            cell   = row.cells[3 + di]
            cell_bg = 'FDE8E8' if is_lib else bg
            color   = status_colors.get(s, RGBColor(0x11, 0x11, 0x11))
            data_cell(cell, s, font_size=4.5,
                      align=WD_ALIGN_PARAGRAPH.CENTER,
                      bold=(s in ('P', 'A', 'I', 'L', 'DC')),
                      color=color, bg=cell_bg)

        sum_vals = [
            (data.get('jumlah_hadir',  0), C_GREEN),
            (data.get('jumlah_alpa',   0), C_RED),
            (data.get('jumlah_izin',   0), C_ORANGE),
            (data.get('jumlah_cuti',   0), C_NAVY),
            (data.get('jumlah_dokter', 0), C_BLUE),
        ]
        for ci2, (val, col) in enumerate(sum_vals):
            data_cell(row.cells[3 + n_days + ci2], str(val), font_size=5.5,
                      align=WD_ALIGN_PARAGRAPH.CENTER, bold=True, color=col, bg=bg)
        data_cell(row.cells[3 + n_days + 5], '', font_size=5.5, bg=bg)

    # Baris TOTAL
    if ctx['absensi_kalender']:
        trow = tbl.add_row()
        for ci in range(len(trow.cells)):
            trow.cells[ci].width = Twips(col_widths[ci])
            set_cell_bg(trow.cells[ci], 'F0F4FA')
            set_cell_borders(trow.cells[ci], color='1A3A5C', size=6)
        # Merge 3 kolom pertama untuk label TOTAL
        trow.cells[0].merge(trow.cells[2])
        p = trow.cells[0].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r = p.add_run('TOTAL')
        r.bold = True; r.font.size = Pt(6); r.font.color.rgb = C_NAVY
        for di in range(n_days):
            data_cell(trow.cells[1 + di], '', font_size=5, bg='F0F4FA')
        for ci2, (val, col) in enumerate([
            (ctx['absensi_totals']['hadir'],  C_GREEN),
            (ctx['absensi_totals']['alpa'],   C_RED),
            (ctx['absensi_totals']['izin'],   C_ORANGE),
            (ctx['absensi_totals']['cuti'],   C_NAVY),
            (ctx['absensi_totals']['dokter'], C_BLUE),
        ]):
            data_cell(trow.cells[1 + n_days + ci2], str(val),
                      font_size=5.5, align=WD_ALIGN_PARAGRAPH.CENTER,
                      bold=True, color=col, bg='F0F4FA')

    # Keterangan
    kp = doc.add_paragraph()
    kp.paragraph_format.space_before = Pt(4)
    kp.add_run('Keterangan: ').bold = True
    kp.add_run('P=Hadir  A=Alpa  I=Izin  L=Cuti  DC=Surat Dokter  LB=Libur'
               ).font.size = Pt(7)


def build_program(doc, ctx):
    """Section V — Program & Pelaksanaan (landscape)."""
    add_section_header(doc, 'V', 'PROGRAM DAN PELAKSANAAN PEKERJAAN',
                       f"{ctx['perusahaan'].nama_perusahaan} — {ctx['nama_bulan']} {ctx['tahun']}")

    sec   = doc.sections[-1]
    total = content_width_dxa(sec)
    days  = ctx['days_range']
    n_days = len(days)

    fixed = 1600 + 1400 + 1200 + 300   # obj + std + job + frek
    day_w = max(int((total - fixed) / n_days), 200)
    col_widths = [1600, 1400, 1200, 300] + [day_w] * n_days

    for entry in ctx['laporan_dengan_jadwal']:
        add_info_bar(doc,
                     f'MONTHLY SCHEDULE {ctx["jenis_jasa"].nama_jasa.upper()}',
                     ctx['perusahaan'].nama_perusahaan.upper())
        loc_p = doc.add_paragraph()
        r = loc_p.add_run(
            f'Lokasi: {entry["area_nama"]}    '
            f'Supervisor: {entry["supervisor"]}    '
            f'Bulan: {ctx["nama_bulan"]} {ctx["tahun"]}'
        )
        r.font.size = Pt(7); r.font.color.rgb = C_NAVY; r.bold = True

        tbl = doc.add_table(rows=1, cols=4 + n_days)
        tbl.style = 'Table Grid'
        hrow = tbl.rows[0]
        for i in range(len(hrow.cells)):
            hrow.cells[i].width = Twips(col_widths[i])
        header_cell(hrow.cells[0], 'Object',       6, bg='2C4E6E')
        header_cell(hrow.cells[1], 'Standar',       6, bg='2C4E6E')
        header_cell(hrow.cells[2], 'Job/Pekerjaan', 6, bg='2C4E6E')
        header_cell(hrow.cells[3], 'Frek',          6, bg='2C4E6E')
        for di, d in enumerate(days):
            header_cell(hrow.cells[4 + di], str(d), 5, bg='2C4E6E')

        for idx, item in enumerate(entry['items']):
            row = tbl.add_row()
            bg  = 'F7F9FC' if idx % 2 == 1 else 'FFFFFF'
            for ci in range(len(row.cells)):
                row.cells[ci].width = Twips(col_widths[ci])
            data_cell(row.cells[0], item['nama_item'], font_size=6, bold=True, bg=bg)
            data_cell(row.cells[1], item['standar'],   font_size=6, bg=bg)
            data_cell(row.cells[2], item['task'],      font_size=6, bg=bg)
            data_cell(row.cells[3], item['frek'],      font_size=6,
                      align=WD_ALIGN_PARAGRAPH.CENTER, bg=bg)
            for di, mark in enumerate(item['hari_list']):
                data_cell(row.cells[4 + di], mark, font_size=5,
                          align=WD_ALIGN_PARAGRAPH.CENTER,
                          bold=bool(mark), color=C_NAVY if mark else None, bg=bg)

        doc.add_paragraph()


def _foto_cell_inner(cell, item_title, tanggal_str, foto_progress, foto_after, foto_width_cm):
    """
    Isi satu cell (setengah halaman) dengan:
      - judul item + tanggal (center, bold)
      - sub-tabel 2 kolom: On Progress | After
    """
    set_cell_bg(cell, 'FFFFFF')
    set_cell_borders(cell, color='C8D4E0')
    set_cell_margins(cell, 60, 60, 80, 80)

    # Judul item
    p_title = cell.paragraphs[0]
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rt = p_title.add_run(item_title.upper())
    rt.bold = True; rt.font.size = Pt(7.5); rt.font.color.rgb = C_NAVY
    if tanggal_str:
        p_title.add_run(f'  —  {tanggal_str}').font.color.rgb = C_GRAY

    # Sub-tabel 2 kolom: On Progress | After
    sub_tbl = OxmlElement('w:tbl')

    def make_foto_col(label, foto_field):
        """Buat satu kolom (label + foto/N/A + caption) sebagai XML tc."""
        tc = OxmlElement('w:tc')
        tcPr = OxmlElement('w:tcPr')
        tcW = OxmlElement('w:tcW')
        tcW.set(qn('w:w'), '0'); tcW.set(qn('w:type'), 'auto')
        tcPr.append(tcW)
        tc.append(tcPr)

        # paragraf label
        p_lbl = OxmlElement('w:p')
        pPr   = OxmlElement('w:pPr')
        jc    = OxmlElement('w:jc'); jc.set(qn('w:val'), 'center')
        pPr.append(jc); p_lbl.append(pPr)
        r_lbl = OxmlElement('w:r')
        rPr   = OxmlElement('w:rPr')
        b     = OxmlElement('w:b')
        sz    = OxmlElement('w:sz'); sz.set(qn('w:val'), '12')   # 6pt
        color = OxmlElement('w:color'); color.set(qn('w:val'), '607080')
        rPr.append(b); rPr.append(sz); rPr.append(color)
        r_lbl.append(rPr)
        t = OxmlElement('w:t'); t.text = label.upper()
        r_lbl.append(t); p_lbl.append(r_lbl)
        tc.append(p_lbl)

        return tc   # foto akan ditambah via python-docx di bawah

    # Kita tidak bisa insert gambar via pure XML — pakai trik:
    # tambahkan sub-tabel dulu sebagai tabel biasa via doc.add_table,
    # lalu pindahkan ke dalam cell.
    # Cara termudah: cukup tambahkan paragraf-paragraf ke cell langsung.

    # Label row
    p_labels = cell.add_paragraph()
    p_labels.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_labels.paragraph_format.space_before = Pt(4)

    # Buat tabel 1 row 4 kolom: [label_prog | foto_prog | label_after | foto_after]
    # tapi lebih simpel: 2 kolom, masing-masing isi label+foto
    # Kita pakai tabel nested sederhana
    inner_tbl = cell._tc.getparent().getparent()   # placeholder — kita pakai cara lain

    # Cara paling reliable: tambah paragraf label, lalu gambar, side by side tidak bisa
    # di python-docx tanpa nested table.
    # Kita pakai nested table approach yang proper:
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsmap

    # Tambahkan nested tabel 1 row 2 kolom langsung ke cell body
    nested = OxmlElement('w:tbl')
    # tblPr
    ntPr = OxmlElement('w:tblPr')
    ntW  = OxmlElement('w:tblW'); ntW.set(qn('w:w'), '0'); ntW.set(qn('w:type'), 'auto')
    ntPr.append(ntW)
    ntLayout = OxmlElement('w:tblLayout'); ntLayout.set(qn('w:type'), 'autofit')
    ntPr.append(ntLayout)
    nested.append(ntPr)

    tr = OxmlElement('w:tr')
    for label, foto_field in [('ON PROGRESS', foto_progress), ('AFTER', foto_after)]:
        tc = OxmlElement('w:tc')
        tcPr2 = OxmlElement('w:tcPr')
        tcW2  = OxmlElement('w:tcW'); tcW2.set(qn('w:w'), '0'); tcW2.set(qn('w:type'), 'auto')
        tcPr2.append(tcW2)
        tc.append(tcPr2)

        # Label paragraph
        p_l = OxmlElement('w:p')
        ppPr = OxmlElement('w:pPr')
        jc2  = OxmlElement('w:jc'); jc2.set(qn('w:val'), 'center')
        ppPr.append(jc2); p_l.append(ppPr)
        r_l = OxmlElement('w:r')
        rPr2 = OxmlElement('w:rPr')
        b2   = OxmlElement('w:b')
        sz2  = OxmlElement('w:sz'); sz2.set(qn('w:val'), '12')
        col2 = OxmlElement('w:color'); col2.set(qn('w:val'), '607080')
        rPr2.append(b2); rPr2.append(sz2); rPr2.append(col2)
        r_l.append(rPr2)
        t_l = OxmlElement('w:t'); t_l.text = label
        r_l.append(t_l); p_l.append(r_l)
        tc.append(p_l)

        tr.append(tc)
    nested.append(tr)
    cell._tc.append(nested)

    # Sekarang tambahkan gambar via paragraf biasa di cell
    # (nested table di atas hanya untuk label row)
    # Untuk gambar, kita tambah paragraf baru di cell dan insert picture
    for label, foto_field in [('ON PROGRESS', foto_progress), ('AFTER', foto_after)]:
        pass   # handled below via paragraphs

    # Reset: gunakan approach yang benar-benar works — hapus nested table,
    # cukup tambahkan label + gambar dalam paragraf yang sama (center)
    cell._tc.remove(nested)

    for label, foto_field in [('ON PROGRESS', foto_progress), ('AFTER', foto_after)]:
        p_lbl2 = cell.add_paragraph()
        p_lbl2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_lbl2.paragraph_format.space_before = Pt(3)
        rl2 = p_lbl2.add_run(label)
        rl2.bold = True; rl2.font.size = Pt(6.5); rl2.font.color.rgb = C_GRAY

        p_img = cell.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if foto_field:
            try:
                p_img.add_run().add_picture(foto_field.path, width=Cm(foto_width_cm))
            except Exception:
                p_img.add_run('[ Foto tidak dapat dimuat ]').font.color.rgb = C_LGRAY
        else:
            rna = p_img.add_run('N/A')
            rna.font.color.rgb = C_LGRAY; rna.italic = True; rna.font.size = Pt(8)

        # Caption
        p_cap = cell.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        rc = p_cap.add_run(item_title.upper())
        rc.font.size = Pt(6.5); rc.font.color.rgb = C_GRAY


def build_foto(doc, ctx):
    """
    Section VI — Foto Progres (portrait).
    Layout: 2 item per baris, masing-masing item punya On Progress + After.
    Persis seperti tampilan PDF.
    """
    add_section_header(doc, 'VI', 'FOTO DOKUMENTASI PROGRES',
                       f"{ctx['nama_bulan']} {ctx['tahun']}")

    from itertools import groupby
    keyfunc = lambda item: (item.sub_area.nama_sub_area if item.sub_area else 'Tanpa Sub Area')
    sorted_items = sorted(ctx['item_list'], key=keyfunc)

    sec   = doc.sections[-1]
    total = content_width_dxa(sec)
    half  = total // 2
    # Foto width: tiap cell setengah halaman, ada 2 foto per cell → tiap foto ~1/4 halaman
    foto_w_cm = 3.8  # cm per foto, cukup untuk 2 foto side by side dalam setengah halaman

    for sub_area_name, group_items in groupby(sorted_items, key=keyfunc):
        # Filter hanya item yang punya foto
        items_with_foto = [i for i in group_items
                           if i.foto_on_progress or i.foto_after]
        if not items_with_foto:
            continue

        # Sub area heading
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after  = Pt(4)
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement('w:pBdr')
        bot = OxmlElement('w:bottom')
        bot.set(qn('w:val'), 'single'); bot.set(qn('w:sz'), '6')
        bot.set(qn('w:space'), '1'); bot.set(qn('w:color'), '1A3A5C')
        pBdr.append(bot); pPr.append(pBdr)
        r = p.add_run(sub_area_name.upper())
        r.bold = True; r.font.size = Pt(10); r.font.color.rgb = C_NAVY

        # Pasangkan item 2 per baris
        pairs = [items_with_foto[i:i+2] for i in range(0, len(items_with_foto), 2)]

        for pair in pairs:
            # Tabel 2 kolom (tiap kolom = 1 item)
            tbl = doc.add_table(rows=1, cols=2)
            tbl.style = 'Table Grid'

            for ci in range(2):
                cell = tbl.rows[0].cells[ci]
                cell.width = Twips(half)

                if ci < len(pair):
                    item = pair[ci]
                    tanggal_str = item.tanggal.strftime('%d %b %Y') if item.tanggal else ''
                    _foto_cell_inner(
                        cell,
                        item.nama_item,
                        tanggal_str,
                        item.foto_on_progress,
                        item.foto_after,
                        foto_w_cm,
                    )
                else:
                    # Cell kosong untuk baris ganjil
                    set_cell_bg(cell, 'FFFFFF')
                    set_cell_borders(cell, color='FFFFFF')

            doc.add_paragraph()


def build_penutup(doc, ctx):
    """Section VII — Penutup (portrait)."""
    add_section_header(doc, 'VII', 'PENUTUP')

    supervisor = ''
    for l in ctx['laporan_list']:
        supervisor = l.supervisor.nama_lengkap or l.supervisor.username
        break

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after  = Pt(8)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    txt = (
        f'Demikian Laporan Bulanan periode bulan {ctx["nama_bulan"]} {ctx["tahun"]} '
        f'ini dibuat sebagai bentuk pertanggungjawaban pelaksanaan jasa '
        f'{ctx["jenis_jasa"].nama_jasa} di lingkungan '
        f'{ctx["perusahaan"].nama_perusahaan}. '
        f'Semua kegiatan telah dilaksanakan sesuai dengan jadwal dan standar yang telah '
        f'ditetapkan. Kami berkomitmen untuk terus meningkatkan kualitas layanan demi '
        f'kepuasan seluruh pengguna fasilitas.'
    )
    r = p.add_run(txt)
    r.font.size = Pt(10)

    # Lokasi & tanggal
    loc_p = doc.add_paragraph()
    loc_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    loc_p.paragraph_format.space_before = Pt(16)
    loc_p.add_run(
        f'{ctx["perusahaan"].alamat or "Karawang"}, {ctx["nama_bulan"]} {ctx["tahun"]}'
    ).font.color.rgb = C_GRAY

    # Tabel TTD
    doc.add_paragraph()
    tbl = doc.add_table(rows=1, cols=3)
    tbl.style = 'Table Grid'
    ttd_data = [
        ('Dibuat oleh,',    supervisor,              f'SPV {ctx["jenis_jasa"].nama_jasa}'),
        ('Diketahui oleh,', '_' * 25,               'Kepala Supervisor'),
        ('Disetujui oleh,', '_' * 25,               ctx['perusahaan'].nama_perusahaan),
    ]
    sec   = doc.sections[-1]
    total = content_width_dxa(sec)
    col_w = total // 3
    for ci, (label, name, role) in enumerate(ttd_data):
        cell = tbl.rows[0].cells[ci]
        cell.width = Twips(col_w)
        set_cell_bg(cell, 'FFFFFF')
        set_cell_borders(cell, color='C8D4E0')
        set_cell_margins(cell, 80, 80, 120, 120)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(label + '\n\n\n\n').font.size = Pt(9)
        r_name = p.add_run(f'( {name} )\n')
        r_name.bold = True; r_name.font.size = Pt(9)
        r_role = p.add_run(role)
        r_role.font.size = Pt(8); r_role.font.color.rgb = C_GRAY


# ══════════════════════════════════════════════════════
# MAIN: _generate_word
# ══════════════════════════════════════════════════════

def _generate_word(request, context):
    """
    Drop-in replacement untuk _generate_word di views.py lo.
    Import fungsi ini lalu ganti fungsi lama.
    """
    from django.http import HttpResponse

    try:
        doc = Document()

        # Default style
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(9)

        # ── Section 1: Cover + Daftar Isi + Karyawan + Organisasi (portrait) ──
        sec1 = doc.sections[0]
        set_section_portrait(sec1)

        build_cover(doc, context)
        add_page_break(doc)
        build_daftar_isi(doc, context)
        add_page_break(doc)
        build_karyawan(doc, context)
        add_page_break(doc)
        build_organisasi(doc, context)

        # ── Section 2: Jadwal (landscape) ──
        add_section_break(doc, landscape=True)
        build_jadwal(doc, context)

        # ── Section 3: Absensi (landscape) ──
        add_section_break(doc, landscape=True)
        build_absensi(doc, context)

        # ── Section 4: Program (landscape) ──
        add_section_break(doc, landscape=True)
        build_program(doc, context)

        # ── Section 5: Foto + Penutup (portrait) ──
        add_section_break(doc, landscape=False)
        build_foto(doc, context)
        add_page_break(doc)
        build_penutup(doc, context)

        # ── Save ke buffer ──
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

        response = HttpResponse(
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{context["nama_file"]}.docx"'
        )
        return response

    except Exception as e:
        import traceback
        from django.http import HttpResponse
        return HttpResponse(
            f'Error Word:\n{traceback.format_exc()}',
            status=500,
            content_type='text/plain',
        )