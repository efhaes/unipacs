from .dashboard import dashboard_view
from .akun import (supervisor_staff_list,supervisor_create,
    supervisor_edit, supervisor_toggle_aktif,
    pilih_supervisor,set_acting_supervisor,clear_acting_supervisor
)
from .penugasan import (
    penugasan_list, penugasan_create, penugasan_edit, penugasan_delete
)
from .laporan import laporan_list, laporan_detail
from .area_kerja import (
    area_list, area_create, area_edit, area_delete,
)