"""
Konstanta & konfigurasi global untuk geolocation & koordinat.
Single source of truth untuk presisi, validasi, dll.
"""

# ── Presisi Koordinat ──────────────────────────────────────────
# 6 decimal places = akurasi ±0.11 meter (ideal untuk geolocation)
# Jangan ubah sembarangan — impact ke model, filter, JS, validation
KOORDINAT_DECIMAL_PLACES = 6
KOORDINAT_MAX_DIGITS     = 10

# Accuracy di dunia real:
# 5 places = ±1.1 meter (terlalu ketat, GPS error)
# 6 places = ±0.11 meter (perfect untuk absensi)
# 7 places = ±1.1 cm (overkill, floating point issues)

# ── Range Validasi ─────────────────────────────────────────────
LATITUDE_MIN  = -90.0
LATITUDE_MAX  = 90.0
LONGITUDE_MIN = -180.0
LONGITUDE_MAX = 180.0

# ── Radius Absensi ──────────────────────────────────────────────
RADIUS_MIN     = 15    # meter — minimum radius lokasi absensi
RADIUS_MAX     = 500   # meter — maksimum radius lokasi absensi
RADIUS_DEFAULT = 50    # meter — default saat buat lokasi baru

# ── Rekomendasi untuk UX ───────────────────────────────────────
RADIUS_REKOMENDASI = {
    'gedung_tunggal': (50, 100),
    'area_luas': (150, 300),
    'kompleks_besar': (300, 500),
}