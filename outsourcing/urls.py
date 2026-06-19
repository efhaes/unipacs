from outsourcing.views.supervisor import customer_create
from django.urls import path
from outsourcing import views
from outsourcing.views.auth import login_view, logout_view, dashboard_redirect
from outsourcing.views.admin import (
    dashboard_view as admin_dashboard,
    perusahaan_list, perusahaan_create, perusahaan_detail,
    perusahaan_edit, perusahaan_delete,
    jenis_jasa_list, jenis_jasa_create, jenis_jasa_edit, jenis_jasa_delete,
    akun_list, akun_create_kepala, akun_create_customer, akun_edit, akun_edit_kepala, akun_toggle_aktif,
    area_list, area_create, area_edit, area_delete,
    subarea_create, subarea_edit, subarea_delete,
    laporan_list as admin_laporan_list, laporan_detail as admin_laporan_detail,
)
from outsourcing.views.kepala_supervisor import (
    dashboard_view as kepala_dashboard,
    supervisor_staff_list, supervisor_create,
    supervisor_edit, supervisor_toggle_aktif,
    penugasan_list, penugasan_create, penugasan_edit, penugasan_delete,
    laporan_list as kepala_laporan_list, laporan_detail as kepala_laporan_detail,
    area_list, area_create, area_edit, area_delete,pilih_supervisor,set_acting_supervisor,clear_acting_supervisor
)
from outsourcing.views.staff.item import item_hapus_foto_tambahan_ajax, item_upload_foto_tambahan_ajax
from outsourcing.views.staff.item import item_hapus_foto_tambahan_ajax
from outsourcing.views.supervisor import (
    dashboard_view as supervisor_dashboard,
    laporan_list, laporan_create, laporan_detail, laporan_edit, laporan_delete,
    laporan_selesai, laporan_toggle_aktif,
    item_create, item_edit, item_delete, item_approve as supervisor_item_approve,
    staff_list as spv_staff_list,   # ← ganti alias ini
    staff_create, staff_edit, staff_toggle_aktif, staff_delete,
    subarea_list, subarea_create, subarea_edit, subarea_delete,
    task_list, task_create, task_edit, task_delete,
    qr_list, qr_generate, qr_nonaktifkan,
    absensi_rekap, absensi_detail, supervisor_absensi_staff_detail, izin_review,
    lokasi_list, lokasi_tambah, lokasi_hapus, lokasi_toggle_aktif, lokasi_detail_json,
)

from outsourcing.views.staff import (
    dashboard_view as staff_dashboard,
    item_list, item_update, item_update_jam,item_create_insidental,
    qr_scan_landing, qr_scan_page, absensi_riwayat, api_today_status,izin_submit,
    izin_detail,
    izin_batal,item_upload_foto_tambahan, item_hapus_foto_tambahan,
)
from outsourcing.views.customer import (
    dashboard_view as customer_dashboard,
    laporan_list as customer_laporan_list,
    laporan_detail as customer_laporan_detail,
    item_approve as customer_item_approve,
    absensi_list,
    absensi_staff_detail,
    item_approval_list as customer_item_approval_list,
)

from outsourcing.views.reporting import generate_laporan_bulanan
from outsourcing.views.supervisor.absensi import api_update_overtime_status, lokasi_edit

urlpatterns = [
    # Auth: login, logout, dashboard redirect
    path('', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard_redirect, name='dashboard'),

    # Admin
    path('admin/', admin_dashboard, name='admin_dashboard'),
    path('admin/perusahaan/', perusahaan_list, name='admin_perusahaan_list'),
    path('admin/perusahaan/tambah/', perusahaan_create, name='admin_perusahaan_create'),
    path('admin/perusahaan/<int:pk>/', perusahaan_detail, name='admin_perusahaan_detail'),
    path('admin/perusahaan/<int:pk>/edit/', perusahaan_edit, name='admin_perusahaan_edit'),
    path('admin/perusahaan/<int:pk>/hapus/', perusahaan_delete, name='admin_perusahaan_delete'),
    path('admin/jenis-jasa/', jenis_jasa_list, name='admin_jenis_jasa_list'),
    path('admin/jenis-jasa/tambah/', jenis_jasa_create, name='admin_jenis_jasa_create'),
    path('admin/jenis-jasa/<int:pk>/edit/', jenis_jasa_edit, name='admin_jenis_jasa_edit'),
    path('admin/jenis-jasa/<int:pk>/hapus/', jenis_jasa_delete, name='admin_jenis_jasa_delete'),
    path('admin/akun/', akun_list, name='admin_akun_list'),
    path('admin/akun/create/kepala/', akun_create_kepala, name='admin_akun_create_kepala'),
    path('admin/akun/create/customer/', akun_create_customer, name='admin_akun_create_customer'),
    path('admin/akun/<int:pk>/edit/', akun_edit, name='admin_akun_edit'),
    path('admin/akun/<int:pk>/edit/kepala/', akun_edit_kepala, name='admin_akun_edit_kepala'),
    path('admin/akun/<int:pk>/toggle/', akun_toggle_aktif, name='admin_akun_toggle_aktif'),
    path('admin/perusahaan/<int:perusahaan_pk>/area/', area_list, name='admin_area_list'),
    path('admin/perusahaan/<int:perusahaan_pk>/area/tambah/', area_create, name='admin_area_create'),
    path('admin/area/<int:pk>/edit/', area_edit, name='admin_area_edit'),
    path('admin/area/<int:pk>/hapus/', area_delete, name='admin_area_delete'),
    path('admin/area/<int:area_pk>/subarea/tambah/', subarea_create, name='admin_subarea_create'),
    path('admin/subarea/<int:pk>/edit/', subarea_edit, name='admin_subarea_edit'),
    path('admin/subarea/<int:pk>/hapus/', subarea_delete, name='admin_subarea_delete'),
    path('admin/laporan/', admin_laporan_list, name='admin_laporan_list'),
    path('admin/laporan/<int:pk>/', admin_laporan_detail, name='admin_laporan_detail'),
    path('admin/laporan/bulanan/<int:perusahaan_id>/<int:tahun>/<int:bulan>/<int:jenis_jasa_id>/download/<str:format>/', 
         generate_laporan_bulanan, name='admin_download_laporan_bulanan'),

    # Kepala Supervisor
    path('kepala/', kepala_dashboard, name='kepala_dashboard'),
    path('kepala/akun/', supervisor_staff_list, name='kepala_akun_list'),
    path('kepala/supervisor/tambah/', supervisor_create, name='kepala_supervisor_create'),
    path('kepala/supervisor/<int:pk>/edit/', supervisor_edit, name='kepala_supervisor_edit'),
    path('kepala/supervisor/<int:pk>/toggle/', supervisor_toggle_aktif, name='kepala_supervisor_toggle_aktif'),
    path('kepala/penugasan/', penugasan_list, name='kepala_penugasan_list'),
    path('kepala/penugasan/tambah/', penugasan_create, name='kepala_penugasan_create'),
    path('kepala/penugasan/<int:pk>/edit/', penugasan_edit, name='kepala_penugasan_edit'),
    path('kepala/penugasan/<int:pk>/hapus/', penugasan_delete, name='kepala_penugasan_delete'),
    path('kepala/laporan/', kepala_laporan_list, name='kepala_laporan_list'),
    path('kepala/laporan/<int:pk>/', kepala_laporan_detail, name='kepala_laporan_detail'),
    path('kepala/area/', area_list, name='kepala_area_list'),
    path('kepala/area/tambah/', area_create, name='kepala_area_create'),
    path('kepala/area/<int:pk>/edit/', area_edit, name='kepala_area_edit'),
    path('kepala/area/<int:pk>/hapus/', area_delete, name='kepala_area_delete'),
    path('kepala/pilih-supervisor/', pilih_supervisor, name='kepala_pilih_supervisor'),
    path('kepala/akses-supervisor/<int:supervisor_id>/', set_acting_supervisor, name='kepala_set_acting_supervisor'),
    path('kepala/keluar-supervisor/', clear_acting_supervisor, name='kepala_clear_acting_supervisor'),
        # Supervisor
    path('supervisor/', supervisor_dashboard, name='supervisor_dashboard'),
    path('supervisor/laporan/', laporan_list, name='supervisor_laporan_list'),
    path('supervisor/laporan/tambah/', laporan_create, name='supervisor_laporan_create'),
    path('supervisor/laporan/<int:pk>/', laporan_detail, name='supervisor_laporan_detail'),
    path('supervisor/laporan/<int:pk>/edit/', laporan_edit, name='supervisor_laporan_edit'),
    path('supervisor/laporan/<int:pk>/hapus/', laporan_delete, name='supervisor_laporan_delete'),
    path('supervisor/laporan/<int:pk>/selesai/', laporan_selesai, name='supervisor_laporan_selesai'),
    path('supervisor/laporan/<int:laporan_pk>/item/tambah/', item_create, name='supervisor_item_create'),
    path('supervisor/laporan/<int:pk>/toggle-aktif/', laporan_toggle_aktif, name='supervisor_laporan_toggle_aktif'),
    path('supervisor/item/<int:pk>/edit/', item_edit, name='supervisor_item_edit'),
    path('supervisor/item/<int:pk>/hapus/', item_delete, name='supervisor_item_delete'),
    path('supervisor/item/<int:pk>/approve/', supervisor_item_approve, name='supervisor_item_approve'),
    path('supervisor/staff/', spv_staff_list, name='supervisor_staff_list'), 
    path('supervisor/staff/tambah/', staff_create, name='supervisor_staff_create'), # ← spv_staff_list    path('supervisor/staff/tambah/', staff_create, name='supervisor_staff_create'),
    path('supervisor/staff/<int:pk>/edit/', staff_edit, name='supervisor_staff_edit'),
    path('supervisor/staff/<int:pk>/toggle/', staff_toggle_aktif, name='supervisor_staff_toggle_aktif'),
    path('supervisor/staff/<int:pk>/delete/', staff_delete, name='supervisor_staff_delete'),
    path('supervisor/subarea/', subarea_list, name='supervisor_subarea_list'),
    path('supervisor/area/<int:area_pk>/subarea/',subarea_list,name='supervisor_subarea_by_area'),
    path('supervisor/subarea/tambah/', subarea_create, name='supervisor_subarea_create'),
    path('supervisor/subarea/<int:pk>/edit/', subarea_edit, name='supervisor_subarea_edit'),
    path('supervisor/subarea/<int:pk>/hapus/', subarea_delete, name='supervisor_subarea_delete'),
    path('supervisor/task/', task_list, name='supervisor_task_list'),
    path('supervisor/task/create/', task_create, name='supervisor_task_create'),
    path('supervisor/task/<int:pk>/edit/', task_edit, name='supervisor_task_edit'),
    path('supervisor/task/<int:pk>/delete/', task_delete, name='supervisor_task_delete'),
    path('supervisor/customer/tambah/', customer_create, name='supervisor_customer_create'),
    path('supervisor/qr/', qr_list, name='supervisor_qr_list'),
    path('supervisor/qr/generate/', qr_generate, name='supervisor_qr_generate'),
    path('supervisor/qr/<int:pk>/nonaktifkan/', qr_nonaktifkan, name='supervisor_qr_nonaktifkan'),
    path('supervisor/absensi/rekap/', absensi_rekap, name='supervisor_absensi_rekap'),
    path('supervisor/absensi/staff/<int:staff_pk>/', supervisor_absensi_staff_detail, name='supervisor_absensi_staff_detail'),
    path('supervisor/absensi/<int:pk>/', absensi_detail, name='supervisor_absensi_detail'),
    path('supervisor/laporan/bulanan/<int:perusahaan_id>/<int:tahun>/<int:bulan>/<int:jenis_jasa_id>/download/<str:format>/',generate_laporan_bulanan, name='download_laporan_bulanan'),
    path('supervisor/absensi/<int:pk>/overtime-status/',api_update_overtime_status,name='supervisor_absensi_overtime_status',),
    path('supervisor/absensi/izin/<int:pk>/review/', izin_review, name='supervisor_izin_review'),
    path('supervisor/lokasi/',                lokasi_list,         name='supervisor_lokasi_list'),
    path('supervisor/lokasi/tambah/',         lokasi_tambah,       name='supervisor_lokasi_tambah'),
    path('supervisor/lokasi/<int:pk>/edit/',  lokasi_edit,         name='supervisor_lokasi_edit'),
    path('supervisor/lokasi/<int:pk>/hapus/', lokasi_hapus,        name='supervisor_lokasi_hapus'),
    path('supervisor/lokasi/<int:pk>/toggle/',lokasi_toggle_aktif, name='supervisor_lokasi_toggle'),
    path('supervisor/lokasi/<int:pk>/json/',  lokasi_detail_json,  name='supervisor_lokasi_json'),

    # Staff
    path('staff/', staff_dashboard, name='staff_dashboard'),
    path('staff/item/', item_list, name='staff_item_list'),
    path("staff/item/insidental/create/", item_create_insidental, name="staff_item_create_insidental"),
    path('staff/item/<int:pk>/update/', item_update, name='staff_item_update'),
    path('staff/item/update-jam/', item_update_jam, name='staff_item_update_jam'),
    path('absensi/scan/<uuid:token>/', qr_scan_landing, name='staff_qr_scan_landing'),
    path('staff/absensi/scan/', qr_scan_page, name='staff_absensi_scan'),
    path('staff/absensi/riwayat/', absensi_riwayat, name='staff_absensi_riwayat'),
    path('staff/api/today-status/', api_today_status, name='staff_api_today_status'),
    path('staff/izin/ajukan/',         izin_submit, name='staff_izin_submit'),
    path('staff/izin/<int:pk>/batal/', izin_batal,  name='staff_izin_batal'),
    path('staff/item/<int:pk>/foto-tambahan/',         item_upload_foto_tambahan, name='staff_item_foto_tambahan'),
    path('staff/item/foto-tambahan/<int:foto_pk>/hapus/', item_hapus_foto_tambahan,  name='staff_item_foto_tambahan_hapus'),
    path("staff/item/<int:pk>/foto-tambahan/ajax/",item_upload_foto_tambahan_ajax,name="staff_item_foto_tambahan_ajax"),
    path("staff/item/foto-tambahan/<int:foto_pk>/hapus/ajax/",  item_hapus_foto_tambahan_ajax,name="staff_item_foto_tambahan_hapus_ajax"),

   # Customer
    path('customer/', customer_dashboard, name='customer_dashboard'),
    path('customer/laporan/', customer_laporan_list, name='customer_laporan_list'),
    path('customer/laporan/<int:pk>/', customer_laporan_detail, name='customer_laporan_detail'),
    path('customer/item/<int:pk>/approve/', customer_item_approve, name='customer_item_approve'),  # ← tambah ini
    path('customer/absensi/',absensi_list,name='customer_absensi_list'),
    path('customer/absensi/staff/<int:staff_pk>/',absensi_staff_detail,name='customer_absensi_staff_detail'),
]
