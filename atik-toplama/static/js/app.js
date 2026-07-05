// Kaba Atık Toplama Rota — istemci tarafı uygulama mantığı
(function () {
  'use strict';

  const state = {
    neighborhoodId: null,
    neighborhoodName: null,
    streets: [],       // {id, name, geometry, visited, ...}
    points: [],        // {id, lat, lon, type, note, resolved, ...}
    streetLayers: {},  // id -> leaflet polyline
    pointLayers: {},    // id -> leaflet marker
    addMode: false,
    pendingLatLng: null,
    voiceOn: true,
    announcedPoints: new Set(),
    lastAnnouncedStreetId: null,
    meMarker: null,
    lastPos: null,
  };

  const POINT_ICONS = {
    kaba_atik_dolu: '🗑️',
    konteyner_yok: '🚫',
    temizlik_gerekli: '🧹',
    toplu_calisma: '👥',
    diger: '📝',
  };

  // ── Yardımcılar ──────────────────────────────────────────
  function toast(msg, ms) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), ms || 3000);
  }

  function speak(text) {
    if (!state.voiceOn || !('speechSynthesis' in window) || !text) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'tr-TR';
      u.rate = 1.0;
      window.speechSynthesis.speak(u);
    } catch (e) { /* speechSynthesis desteklenmiyor */ }
  }

  function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = (d) => (d * Math.PI) / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  function nearestPointOnStreet(street, lat, lon) {
    let best = Infinity;
    for (const [plat, plon] of street.geometry) {
      const d = haversine(lat, lon, plat, plon);
      if (d < best) best = d;
    }
    return best;
  }

  async function api(path, opts) {
    const res = await fetch(path, Object.assign({
      headers: { 'Content-Type': 'application/json' },
    }, opts));
    if (res.status === 401) { window.location.href = '/login'; throw new Error('giriş gerekli'); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'İstek başarısız');
    return data;
  }

  // ── Harita ───────────────────────────────────────────────
  const map = L.map('map', { zoomControl: false }).setView([41.015, 28.979], 14);
  L.control.zoom({ position: 'bottomleft' }).addTo(map);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap katkıda bulunanlar',
  }).addTo(map);

  function streetStyle(street) {
    return {
      color: street.visited ? '#1a7a3c' : '#d6432b',
      weight: 5,
      opacity: 0.85,
    };
  }

  function renderStreets() {
    Object.values(state.streetLayers).forEach((l) => map.removeLayer(l));
    state.streetLayers = {};
    state.streets.forEach((street) => {
      const line = L.polyline(street.geometry, streetStyle(street));
      line.bindTooltip(street.name, { sticky: true });
      line.on('click', () => onStreetClick(street));
      line.addTo(map);
      state.streetLayers[street.id] = line;
    });
  }

  function onStreetClick(street) {
    const willVisit = !street.visited;
    const msg = willVisit ? `"${street.name}" gezildi olarak işaretlensin mi?` : `"${street.name}" işareti kaldırılsın mı?`;
    if (!window.confirm(msg)) return;
    api(`/api/streets/${street.id}/visit`, { method: 'POST', body: JSON.stringify({ visited: willVisit }) })
      .then(() => {
        street.visited = willVisit;
        state.streetLayers[street.id].setStyle(streetStyle(street));
        updateProgress();
        if (willVisit) speak(`${street.name} işaretlendi`);
      })
      .catch((e) => toast(e.message));
  }

  function pointPopupHtml(point) {
    const label = POINT_ICONS[point.type] || '📝';
    const parts = [`<b>${label} ${point.note ? escapeHtml(point.note) : '(not yok)'}</b>`];
    if (point.created_by) parts.push(`<div style="color:#9aa0a8;font-size:12px;">Ekleyen: ${escapeHtml(point.created_by)}</div>`);
    if (point.resolved) {
      parts.push('<div style="color:#1a7a3c;font-size:12px;">✔ Çözüldü</div>');
    } else {
      parts.push(`<button data-resolve="${point.id}">Çözüldü olarak işaretle</button>`);
    }
    parts.push(`<button data-speak="${point.id}">🔊 Sesli Oku</button>`);
    return parts.join('');
  }

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function renderPoints() {
    Object.values(state.pointLayers).forEach((l) => map.removeLayer(l));
    state.pointLayers = {};
    state.points.forEach((point) => {
      const icon = L.divIcon({
        html: `<div style="font-size:26px;line-height:1;filter:${point.resolved ? 'grayscale(1) opacity(.5)' : 'none'};">${POINT_ICONS[point.type] || '📝'}</div>`,
        className: '', iconSize: [26, 26], iconAnchor: [13, 13],
      });
      const marker = L.marker([point.lat, point.lon], { icon });
      marker.bindPopup(pointPopupHtml(point));
      marker.on('popupopen', (e) => {
        const c = e.popup.getElement();
        const resolveBtn = c.querySelector('[data-resolve]');
        const speakBtn = c.querySelector('[data-speak]');
        if (resolveBtn) resolveBtn.onclick = () => resolvePoint(point.id);
        if (speakBtn) speakBtn.onclick = () => speak(point.note || 'Not eklenmemiş');
      });
      marker.addTo(map);
      state.pointLayers[point.id] = marker;
    });
  }

  function resolvePoint(id) {
    api(`/api/points/${id}/resolve`, { method: 'POST' }).then(() => {
      const p = state.points.find((x) => x.id === id);
      if (p) p.resolved = true;
      renderPoints();
    }).catch((e) => toast(e.message));
  }

  function updateProgress() {
    const total = state.streets.length;
    const visited = state.streets.filter((s) => s.visited).length;
    const pct = total ? Math.round((visited / total) * 100) : 0;
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressLabel').textContent = `${visited} / ${total} sokak gezildi`;
  }

  // ── Mahalle yükleme ─────────────────────────────────────
  async function loadNeighborhood(id) {
    const data = await api(`/api/neighborhoods/${id}`);
    state.neighborhoodId = id;
    state.neighborhoodName = data.neighborhood.name;
    state.streets = data.streets;
    state.points = data.points;
    document.getElementById('neighborhoodTitle').textContent = data.neighborhood.name;
    renderStreets();
    renderPoints();
    updateProgress();
    state.announcedPoints.clear();
    if (state.streets.length) {
      const bounds = L.latLngBounds(state.streets.flatMap((s) => s.geometry));
      map.fitBounds(bounds, { padding: [20, 20] });
    } else {
      map.setView([data.neighborhood.center_lat, data.neighborhood.center_lon], 15);
    }
    localStorage.setItem('lastNeighborhoodId', String(id));
  }

  async function refreshNeighborhoodList() {
    const list = await api('/api/neighborhoods');
    const wrap = document.getElementById('neighborhoodListWrap');
    wrap.innerHTML = list.map((n) =>
      `<div class="streetRow"><span>${escapeHtml(n.name)}</span><button data-nb="${n.id}">Seç</button></div>`
    ).join('') || '<div style="color:#9aa0a8;font-size:13px;">Henüz mahalle eklenmedi</div>';
    wrap.querySelectorAll('[data-nb]').forEach((btn) => {
      btn.onclick = () => {
        loadNeighborhood(Number(btn.dataset.nb));
        closeModal('menuModalOverlay');
      };
    });
  }

  // ── Nokta ekleme ─────────────────────────────────────────
  map.on('click', (e) => {
    if (!state.addMode) return;
    if (!state.neighborhoodId) { toast('Önce ☰ menüsünden bir mahalle seçin'); return; }
    state.pendingLatLng = e.latlng;
    openModal('pointModalOverlay');
  });

  document.getElementById('addPointBtn').addEventListener('click', () => {
    state.addMode = !state.addMode;
    document.getElementById('addPointBtn').classList.toggle('primary', state.addMode);
    toast(state.addMode ? 'Haritada bir noktaya dokunun' : 'Nokta ekleme kapatıldı');
  });

  document.getElementById('pointCancelBtn').addEventListener('click', () => closeModal('pointModalOverlay'));
  document.getElementById('pointSaveBtn').addEventListener('click', async () => {
    const type = document.getElementById('pointType').value;
    const note = document.getElementById('pointNote').value.trim();
    const notify = document.getElementById('pointNotify').checked;
    if (!state.pendingLatLng) return;
    try {
      const point = await api('/api/points', {
        method: 'POST',
        body: JSON.stringify({
          neighborhood_id: state.neighborhoodId,
          lat: state.pendingLatLng.lat,
          lon: state.pendingLatLng.lng,
          type, note, notify,
        }),
      });
      state.points.push(point);
      renderPoints();
      document.getElementById('pointNote').value = '';
      closeModal('pointModalOverlay');
      toast('Nokta eklendi' + (notify ? ' ve yetkiliye gönderildi' : ''));
    } catch (e) { toast(e.message); }
  });

  // ── Modallar / menü ──────────────────────────────────────
  function openModal(id) { document.getElementById(id).classList.remove('hidden'); }
  function closeModal(id) { document.getElementById(id).classList.add('hidden'); }

  document.getElementById('menuBtn').addEventListener('click', () => {
    refreshNeighborhoodList();
    openModal('menuModalOverlay');
  });
  document.getElementById('menuCancelBtn').addEventListener('click', () => closeModal('menuModalOverlay'));
  document.getElementById('neighborhoodLoadBtn').addEventListener('click', async () => {
    const q = document.getElementById('neighborhoodInput').value.trim();
    if (!q) return;
    toast('Mahalle sınırı ve sokaklar yükleniyor...');
    try {
      const res = await api('/api/neighborhoods', { method: 'POST', body: JSON.stringify({ query: q }) });
      await loadNeighborhood(res.id);
      document.getElementById('neighborhoodInput').value = '';
      closeModal('menuModalOverlay');
      toast(`${res.street_count != null ? res.street_count : ''} sokak yüklendi`.trim());
    } catch (e) { toast(e.message); }
  });
  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await api('/api/logout', { method: 'POST' });
    window.location.href = '/login';
  });

  document.getElementById('voiceToggleBtn').addEventListener('click', () => {
    state.voiceOn = !state.voiceOn;
    document.getElementById('voiceToggleBtn').classList.toggle('active', state.voiceOn);
    document.getElementById('voiceToggleBtn').textContent = state.voiceOn ? '🔊' : '🔇';
    if (state.voiceOn) speak('Sesli yönlendirme açık');
  });
  document.getElementById('voiceToggleBtn').classList.add('active');

  // ── Girilmeyen sokaklar / rota paneli ────────────────────
  document.getElementById('routeBtn').addEventListener('click', () => {
    const panel = document.getElementById('sidePanel');
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) renderRoutePanel();
  });

  function renderRoutePanel() {
    const list = document.getElementById('streetList');
    const pos = state.lastPos;
    let unvisited = state.streets.filter((s) => !s.visited);
    if (pos) {
      unvisited = unvisited.map((s) => ({ s, d: nearestPointOnStreet(s, pos.lat, pos.lng) }))
        .sort((a, b) => a.d - b.d).map((x) => x.s);
    }
    if (!unvisited.length) {
      list.innerHTML = '<div style="color:#1a7a3c;">Tüm sokaklar gezildi 🎉</div>';
      return;
    }
    list.innerHTML = unvisited.map((s) =>
      `<div class="streetRow"><span>${escapeHtml(s.name)}</span><button data-fly="${s.id}">Git</button></div>`
    ).join('');
    list.querySelectorAll('[data-fly]').forEach((btn) => {
      btn.onclick = () => {
        const street = state.streets.find((s) => s.id === Number(btn.dataset.fly));
        if (!street) return;
        map.fitBounds(L.latLngBounds(street.geometry), { padding: [40, 40] });
        speak(`${street.name} yönüne gidin`);
        document.getElementById('sidePanel').classList.remove('open');
      };
    });
    if (unvisited[0]) speak(`En yakın gezilmemiş sokak: ${unvisited[0].name}`);
  }

  // ── Bitti ────────────────────────────────────────────────
  document.getElementById('finishBtn').addEventListener('click', async () => {
    if (!state.neighborhoodId) { toast('Önce bir mahalle seçin'); return; }
    const remaining = state.streets.filter((s) => !s.visited).length;
    if (remaining > 0) {
      if (!window.confirm(`${remaining} sokak henüz işaretlenmedi. Yine de bitirilsin mi?`)) return;
    }
    try {
      const res = await api(`/api/neighborhoods/${state.neighborhoodId}/finish`, { method: 'POST' });
      toast(`Tamamlandı: ${res.visited}/${res.total} sokak. Yetkiliye bildirim gönderildi.`, 5000);
      speak('Tarama tamamlandı olarak bildirildi');
    } catch (e) { toast(e.message); }
  });

  // ── Konum takibi + sesli yönlendirme ─────────────────────
  function onPosition(pos) {
    const { latitude: lat, longitude: lon } = pos.coords;
    state.lastPos = { lat, lng: lon };
    if (!state.meMarker) {
      state.meMarker = L.circleMarker([lat, lon], { radius: 8, color: '#2b7fd6', fillColor: '#2b7fd6', fillOpacity: 0.9 }).addTo(map);
    } else {
      state.meMarker.setLatLng([lat, lon]);
    }

    // Yakındaki çözülmemiş notları sesli oku
    state.points.forEach((p) => {
      if (p.resolved || !p.note || state.announcedPoints.has(p.id)) return;
      if (haversine(lat, lon, p.lat, p.lon) <= 40) {
        state.announcedPoints.add(p.id);
        speak(p.note);
        toast(`Yakında not: ${p.note}`);
      }
    });

    // En yakın gezilmemiş sokağa girildiyse hatırlat
    let nearest = null, nearestDist = Infinity;
    state.streets.forEach((s) => {
      if (s.visited) return;
      const d = nearestPointOnStreet(s, lat, lon);
      if (d < nearestDist) { nearestDist = d; nearest = s; }
    });
    if (nearest && nearestDist <= 25 && state.lastAnnouncedStreetId !== nearest.id) {
      state.lastAnnouncedStreetId = nearest.id;
      speak(`${nearest.name} — henüz işaretlenmedi`);
    }
  }

  if ('geolocation' in navigator) {
    navigator.geolocation.watchPosition(onPosition, () => {}, {
      enableHighAccuracy: true, maximumAge: 5000, timeout: 20000,
    });
  }

  // ── Servis çalışanı (PWA) ────────────────────────────────
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js').catch(() => {});
  }

  // ── Başlangıç: son seçilen mahalleyi yükle ───────────────
  const lastId = localStorage.getItem('lastNeighborhoodId');
  if (lastId) loadNeighborhood(Number(lastId)).catch(() => {});
})();
