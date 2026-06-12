
document.addEventListener('DOMContentLoaded', function () {

  // ── Referensi elemen DOM ─────────────────────────────────────────────────
  var latInput    = document.getElementById('id_latitude');
  var lonInput    = document.getElementById('id_longitude');
  var radiusInput = document.getElementById('id_radius_meter');
  var slider      = document.getElementById('radiusSlider');
  var radDisplay  = document.getElementById('radiusDisplay');
  var coordDisp   = document.getElementById('coordDisplay');
  var mapEl       = document.getElementById('map-picker');

  // ── Global Config dari Django Template ────────────────────────────────────
  // Parse string values dari template ke numbers
  var KOORDINAT_DECIMAL_PLACES = parseInt('{{ koordinat_decimal_places }}') || 6;
  var RADIUS_MIN = parseInt('{{ radius_min }}') || 10;
  var RADIUS_MAX = parseInt('{{ radius_max }}') || 1000;

  console.log('🔧 Lokasi Form Init');
  console.log('  - Koordinat decimal places:', KOORDINAT_DECIMAL_PLACES);
  console.log('  - Radius range:', RADIUS_MIN, '-', RADIUS_MAX);

  // ── Map Variables ────────────────────────────────────────────────────────
  var map    = null;
  var marker = null;
  var circle = null;

  // ═════════════════════════════════════════════════════════════════════════
  // 1. SLIDER RADIUS
  // ═════════════════════════════════════════════════════════════════════════

  function initSlider() {
    // Sinkronisasi slider dengan hidden input value saat page load
    if (radiusInput.value) {
      var initialRadius = parseInt(radiusInput.value) || 100;
      slider.value = initialRadius;
      radDisplay.textContent = initialRadius + 'm';
    }

    slider.addEventListener('input', function () {
      var val = parseInt(this.value);
      
      // Validation warning (jangan update jika out of range)
      if (val < RADIUS_MIN || val > RADIUS_MAX) {
        console.warn(`⚠️ Radius harus antara ${RADIUS_MIN} dan ${RADIUS_MAX}`);
        return;
      }
      
      // Update display & hidden input
      radDisplay.textContent = val + 'm';
      radiusInput.value      = val;
      
      // Update circle on map jika sudah ada
      if (circle) {
        circle.setRadius(val);
      }
    });
  }

  // ═════════════════════════════════════════════════════════════════════════
  // 2. MAP INITIALIZATION
  // ═════════════════════════════════════════════════════════════════════════

  function initMap() {
    // Tentukan initial view berdasarkan mode (edit vs tambah)
    var initLat  = {% if mode == 'edit' %}{{ lokasi.latitude|js_float }}{% else %}-6.2088{% endif %};
    var initLon  = {% if mode == 'edit' %}{{ lokasi.longitude|js_float }}{% else %}106.8456{% endif %};
    var initZoom = {% if mode == 'edit' %}16{% else %}12{% endif %};

    // Initialize Leaflet map
    map = L.map('map-picker').setView([initLat, initLon], initZoom);

    // Add OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);

    // Klik di peta → set pin
    map.on('click', function (e) {
      setPin(e.latlng.lat, e.latlng.lng, false);
    });

    // Init pin jika mode edit
    {% if mode == 'edit' %}
      setPin({{ lokasi.latitude|js_float }}, {{ lokasi.longitude|js_float }}, false);
    {% endif %}

    console.log('✅ Map initialized at', initLat, initLon);
  }

  // ═════════════════════════════════════════════════════════════════════════
  // 3. SET PIN - Core Function
  // ═════════════════════════════════════════════════════════════════════════

  function getRadius() {
    return parseInt(radiusInput.value) || 100;
  }

  function setPin(lat, lon, fly) {
    /*
     * Letakkan marker & circle di peta, update input fields
     * @param {number} lat - latitude
     * @param {number} lon - longitude
     * @param {boolean} fly - fly to location dengan animasi?
     */
    var r = getRadius();

    // Remove existing marker & circle
    if (marker) marker.remove();
    if (circle) circle.remove();

    // Create new marker (draggable)
    marker = L.marker([lat, lon], { draggable: true }).addTo(map);

    // Create radius circle
    circle = L.circle([lat, lon], {
      radius     : r,
      color      : '#a5b4fc',
      fillColor  : '#a5b4fc',
      fillOpacity: 0.12,
      weight     : 2,
    }).addTo(map);

    // Update input fields dengan KOORDINAT_DECIMAL_PLACES precision
    latInput.value = lat.toFixed(KOORDINAT_DECIMAL_PLACES);
    lonInput.value = lon.toFixed(KOORDINAT_DECIMAL_PLACES);

    // Update coord display
    coordDisp.textContent = '📍 ' + lat.toFixed(6) + ', ' + lon.toFixed(6);
    coordDisp.className   = 'map-coord-display pinned';
    mapEl.classList.add('has-pin');

    // Fly to location jika diminta
    if (fly) {
      map.flyTo([lat, lon], 16, { duration: 1 });
    }

    // Handle marker drag
    marker.on('dragend', function (e) {
      var pos = e.target.getLatLng();
      circle.setLatLng(pos);
      latInput.value        = pos.lat.toFixed(KOORDINAT_DECIMAL_PLACES);
      lonInput.value        = pos.lng.toFixed(KOORDINAT_DECIMAL_PLACES);
      coordDisp.textContent = '📍 ' + pos.lat.toFixed(6) + ', ' + pos.lng.toFixed(6);
      console.log('📍 Marker dragged to:', pos.lat, pos.lng);
    });

    console.log('📌 Pin set at:', lat, lon);
  }

  // ═════════════════════════════════════════════════════════════════════════
  // 4. MANUAL COORDINATE INPUT SYNC
  // ═════════════════════════════════════════════════════════════════════════

  function syncFromInput() {
    /*
     * Sinkronisasi peta ketika user mengetik koordinat manual
     */
    var lat = parseFloat(latInput.value);
    var lon = parseFloat(lonInput.value);

    if (!isNaN(lat) && !isNaN(lon)) {
      // Validate range
      if (lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
        setPin(lat, lon, true);
        console.log('🔄 Synced from input:', lat, lon);
      } else {
        console.warn('⚠️ Koordinat out of range:', lat, lon);
      }
    }
  }

  latInput.addEventListener('blur', syncFromInput);
  lonInput.addEventListener('blur', syncFromInput);

  // ═════════════════════════════════════════════════════════════════════════
  // 5. GPS BUTTON
  // ═════════════════════════════════════════════════════════════════════════

  var gpsBtn   = document.getElementById('gpsBtn');
  var gpsLabel = document.getElementById('gpsBtnLabel');

  gpsBtn.addEventListener('click', function (e) {
    e.preventDefault();

    if (!navigator.geolocation) {
      alert('❌ Browser kamu tidak mendukung GPS.');
      return;
    }

    gpsBtn.disabled        = true;
    gpsLabel.textContent   = 'Mendapatkan lokasi…';
    gpsLabel.style.opacity = '0.7';

    navigator.geolocation.getCurrentPosition(
      function (pos) {
        // Success callback
        setPin(pos.coords.latitude, pos.coords.longitude, true);
        gpsBtn.disabled        = false;
        gpsLabel.textContent   = 'Pakai Lokasi GPS Saya Sekarang';
        gpsLabel.style.opacity = '1';
        console.log('✅ GPS lokasi berhasil:', pos.coords.latitude, pos.coords.longitude);
      },
      function (error) {
        // Error callback
        console.error('❌ Geolocation error:', error);
        
        var errorMsg = 'Gagal mendapatkan lokasi.';
        if (error.code === error.PERMISSION_DENIED) {
          errorMsg += ' Aktifkan izin GPS di browser.';
        } else if (error.code === error.POSITION_UNAVAILABLE) {
          errorMsg += ' Lokasi tidak tersedia.';
        } else if (error.code === error.TIMEOUT) {
          errorMsg += ' Request timeout.';
        }
        
        alert(errorMsg);
        gpsBtn.disabled        = false;
        gpsLabel.textContent   = 'Pakai Lokasi GPS Saya Sekarang';
        gpsLabel.style.opacity = '1';
      },
      {
        enableHighAccuracy: true,
        timeout: 12000,
        maximumAge: 0
      }
    );
  });

  // ═════════════════════════════════════════════════════════════════════════
  // 6. PANDUAN TOGGLE
  // ═════════════════════════════════════════════════════════════════════════

  var pandToggle = document.getElementById('panduan-toggle');
  var pandBody   = document.getElementById('panduan-body');

  pandToggle.addEventListener('click', function (e) {
    e.preventDefault();
    var open = pandBody.classList.toggle('show');
    pandToggle.classList.toggle('open', open);
  });

  // ═════════════════════════════════════════════════════════════════════════
  // 7. GOOGLE MAPS LINK/KOORDINAT PARSER
  // ═════════════════════════════════════════════════════════════════════════

  var gmapsInput    = document.getElementById('gmapsInput');
  var gmapsParseBtn = document.getElementById('gmapsParseBtn');
  var pasteFeedback = document.getElementById('pasteFeedback');

  gmapsParseBtn.addEventListener('click', function (e) {
    e.preventDefault();
    parseGoogleMapsInput();
  });

  gmapsInput.addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      parseGoogleMapsInput();
    }
  });

  function parseGoogleMapsInput() {

    var raw = gmapsInput.value.trim();
    if (!raw) return;

    pasteFeedback.style.display = 'none';
    pasteFeedback.className     = 'paste-feedback';

    var lat = null, lon = null;

    // 1. Direct coordinates: "-6.208763, 106.845599" atau "-6.208763,106.845599"
    var directMatch = raw.match(/^(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)$/);
    if (directMatch) {
      lat = parseFloat(directMatch[1]);
      lon = parseFloat(directMatch[2]);
      console.log('✅ Parsed direct coordinates:', lat, lon);
    }

    // 2. Google Maps URL dengan @ notation
    if (!lat) {
      var atMatch = raw.match(/@(-?\d+\.?\d+),(-?\d+\.?\d+)/);
      if (atMatch) {
        lat = parseFloat(atMatch[1]);
        lon = parseFloat(atMatch[2]);
        console.log('✅ Parsed @ notation:', lat, lon);
      }
    }

    // 3. Google Maps URL dengan ?q= parameter
    if (!lat) {
      var qMatch = raw.match(/[?&]q=(-?\d+\.?\d+),(-?\d+\.?\d+)/);
      if (qMatch) {
        lat = parseFloat(qMatch[1]);
        lon = parseFloat(qMatch[2]);
        console.log('✅ Parsed ?q= parameter:', lat, lon);
      }
    }

    // 4. Google Maps URL dengan ?ll= parameter
    if (!lat) {
      var llMatch = raw.match(/[?&]ll=(-?\d+\.?\d+),(-?\d+\.?\d+)/);
      if (llMatch) {
        lat = parseFloat(llMatch[1]);
        lon = parseFloat(llMatch[2]);
        console.log('✅ Parsed ?ll= parameter:', lat, lon);
      }
    }

    // Validate & set pin
    if (lat && lon && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
      setPin(lat, lon, true);
      gmapsInput.value            = '';
      pasteFeedback.textContent   = '✓ Koordinat berhasil diambil: ' + lat.toFixed(6) + ', ' + lon.toFixed(6);
      pasteFeedback.className     = 'paste-feedback ok';
      pasteFeedback.style.display = 'block';
      console.log('✅ Google Maps input processed successfully');
    } else {
      pasteFeedback.textContent   = '✗ Format tidak dikenali. Coba tempel link Google Maps atau koordinat langsung (contoh: -6.208763, 106.845599)';
      pasteFeedback.className     = 'paste-feedback err';
      pasteFeedback.style.display = 'block';
      console.error('❌ Invalid coordinates or format:', lat, lon);
    }
  }

  // ═════════════════════════════════════════════════════════════════════════
  // INITIALIZATION SEQUENCE
  // ═════════════════════════════════════════════════════════════════════════

  try {
    initSlider();
    initMap();
    console.log('✅ Lokasi form fully initialized');
  } catch (error) {
    console.error('❌ Initialization error:', error);
  }

});
