from .dashboard import dashboard_view
from .laporan import (
    laporan_list, laporan_create, laporan_detail,
    laporan_edit, laporan_delete, laporan_kirim,laporan_selesai,laporan_toggle_aktif,
)
from .item import item_create, item_edit, item_delete
from .staff import staff_list, staff_create, staff_edit, staff_toggle_aktif, staff_delete
from .area_kerja import (
    subarea_list, subarea_create, subarea_edit, subarea_delete,
)
from .task import task_list, task_create, task_edit, task_delete
from .customer import customer_create
from .absensi import qr_list, qr_generate, absensi_detail, qr_nonaktifkan,absensi_rekap,izin_review,lokasi_edit,lokasi_list,lokasi_tambah,lokasi_hapus,lokasi_toggle_aktif,lokasi_detail_json
from .izin_staff import izin_list, izin_detail, izin_approve, izin_reject