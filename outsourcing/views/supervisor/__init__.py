from .dashboard import dashboard_view
from .laporan import (
    laporan_list, laporan_create, laporan_detail,
    laporan_edit, laporan_delete ,laporan_selesai,laporan_toggle_aktif,
)
from .item import item_create, item_edit, item_delete, item_approve
from .staff import staff_list, staff_create, staff_edit, staff_toggle_aktif, staff_delete
from .area_kerja import (
    subarea_list, subarea_create, subarea_edit, subarea_delete,
)
from .task import task_list, task_create, task_edit, task_delete
from .customer import customer_create
from .absensi import (
    qr_list, qr_kelola, qr_toggle_aktif,
    absensi_rekap, absensi_detail,
    supervisor_absensi_staff_detail,
    overtime_list, overtime_klasifikasi, api_update_overtime_status,
    keterangan_list, keterangan_review,
    izin_review,
    jadwal_list, jadwal_tambah, jadwal_edit, jadwal_hapus, jadwal_toggle_aktif,
    lokasi_list, lokasi_tambah, lokasi_edit, lokasi_hapus,
    lokasi_toggle_aktif, lokasi_detail_json,
)