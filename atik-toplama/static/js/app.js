/* Saha Yönetim — istemci tarafı ana mantık */
(function () {
'use strict';

// ── Sabitler ─────────────────────────────────────────────────────────────────
const SUPERVISOR_ROLES = new Set(['santiye_amiri', 'cavus', 'onbasi']);
const NOTIF_ICONS = {
  dolu_konteyner:'🗑️', kaba_atik:'🪑', yikanmasi_lazim:'🚿',
  suprulmesi_lazim:'🧹', park_bahce:'🌳', fen_isleri:'🔧', diger:'📝'
};
const NOTIF_LABELS = {
  dolu_konteyner:'Dolu Konteyner', kaba_atik:'Kaba Atık', yikanmasi_lazim:'Konteyner Yıkanmalı',
  suprulmesi_lazim:'Süpürülmeli', park_bahce:'Park & Bahçe', fen_isleri:'Fen İşleri', diger:'Diğer'
};

// ── Durum ─────────────────────────────────────────────────────────────────────
const S = {
  user: null,
  neighborhoods: [],
  activeNb: null,       // aktif mahalle objesi
  streets: [],          // tüm sokaklar (harita için)
  myStreets: [],        // bugün bana atanmış sokaklar (süpürgeci)
  completedIds: new Set(),
  notifications: [],
  map: null,
  streetLayers: {},     // id → polyline
  assignSelected: new Set(), // atama için seçili sokak id'leri
  meMarker: null,
  lastPos: null,
  voiceOn: true,
  announcedNotifs: new Set(),
  mode: 'normal',       // 'normal' | 'assign'
  closingStreetId: null,
  photoFile: null,
};

// ── Yardımcılar ───────────────────────────────────────────────────────────────
function el(id){ return document.getElementById(id); }

function toast(msg, type, ms) {
  const t = document.createElement('div');
  t.className = 'toast' + (type ? ' ' + type : '');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms || 3000);
}

function speak(text) {
  if (!S.voiceOn || !('speechSynthesis' in window) || !text) return;
  try { window.speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.lang = 'tr-TR'; u.rate = 1.05; window.speechSynthesis.speak(u); } catch(e){}
}

function haversine(la1, lo1, la2, lo2) {
  const R = 6371000, r = Math.PI/180;
  const dLa = (la2-la1)*r, dLo = (lo2-lo1)*r;
  const a = Math.sin(dLa/2)**2 + Math.cos(la1*r)*Math.cos(la2*r)*Math.sin(dLo/2)**2;
  return 2*R*Math.asin(Math.sqrt(a));
}

function streetMidpoint(geom) {
  const mid = geom[Math.floor(geom.length/2)];
  return mid;
}

function nearestStreetDist(street) {
  if (!S.lastPos) return Infinity;
  let best = Infinity;
  for (const [la,lo] of street.geometry)
    best = Math.min(best, haversine(S.lastPos.lat, S.lastPos.lng, la, lo));
  return best;
}

async function api(path, opts) {
  const r = await fetch(path, Object.assign({headers:{'Content-Type':'application/json'}}, opts));
  if (r.status === 401) { location.href='/login'; throw Error('giris gerekli'); }
  const d = await r.json().catch(()=>({}));
  if (!r.ok) throw Error(d.error || 'Hata');
  return d;
}

function todayStr() {
  return new Date().toISOString().slice(0,10);
}

// ── Harita kurulum ─────────────────────────────────────────────────────────────
function initMap() {
  S.map = L.map('map', {zoomControl:false}).setView([41.015, 28.979], 14);
  L.control.zoom({position:'bottomleft'}).addTo(S.map);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom:19, attribution:'© OSM'
  }).addTo(S.map);

  S.map.on('click', onMapClick);
}

// ── Sokak renk mantığı ─────────────────────────────────────────────────────────
function streetColor(street) {
  if (S.mode === 'assign') {
    if (S.assignSelected.has(street.id)) return {color:'#1f6feb', weight:6, opacity:.9};
    return {color:'#30363d', weight:4, opacity:.7};
  }
  if (street.completed) return {color:'#1a7a3c', weight:5, opacity:.85};
  return {color:'#b91c1c', weight:5, opacity:.85};
}

function renderStreets(streets) {
  // Temizle
  Object.values(S.streetLayers).forEach(l => S.map.removeLayer(l));
  S.streetLayers = {};

  streets.forEach(street => {
    const line = L.polyline(street.geometry, streetColor(street));
    line.bindTooltip(street.name, {sticky:true, className:'', opacity:.9});
    line.on('click', () => onStreetClick(street));
    line.addTo(S.map);
    S.streetLayers[street.id] = line;
  });
}

function refreshStreetColor(streetId) {
  const street = S.streets.find(s => s.id === streetId) || S.myStreets.find(s => s.id === streetId);
  if (!street || !S.streetLayers[streetId]) return;
  S.streetLayers[streetId].setStyle(streetColor(street));
}

// ── Mahalle yükleme ─────────────────────────────────────────────────────────────
async function loadNeighborhood(nb) {
  S.activeNb = nb;
  el('nbTitle').textContent = nb.name;
  el('progressLabel').textContent = 'Yükleniyor…';

  // Tüm sokaklar
  const allStreets = await api(`/api/neighborhoods/${nb.id}/streets`);
  S.streets = allStreets;

  if (SUPERVISOR_ROLES.has(S.user.role)) {
    await loadSupervisorView();
  } else {
    await loadSweeperView();
  }
  fitMapToStreets(S.streets.length ? S.streets : []);
  localStorage.setItem('lastNbId', String(nb.id));
}

async function loadSweeperView() {
  const nid = S.activeNb.id;
  const data = await api(`/api/my/streets?neighborhood_id=${nid}&date=${todayStr()}`);
  S.myStreets = data.streets;
  S.completedIds = new Set(data.completed_ids);

  if (!S.myStreets.length) {
    renderStreets(S.streets.map(s => ({...s, completed: false})));
    updateProgress(0, S.streets.length);
    toast('Bugün bu mahalle için görev atanmamış', '', 4000);
    return;
  }

  // Atanmış sokakları tamamlama durumlarıyla birlikte göster
  const displayStreets = S.myStreets.map(s => ({...s, completed: S.completedIds.has(s.id)}));
  renderStreets(displayStreets);
  updateProgress(S.completedIds.size, S.myStreets.length);
  speak(`${S.activeNb.name}. ${S.myStreets.length} sokak görevin var.`);
}

async function loadSupervisorView() {
  const nid = S.activeNb.id;
  const data = await api(`/api/neighborhoods/${nid}/progress?date=${todayStr()}`);
  const streets = data.streets.length ? data.streets : S.streets.map(s => ({...s, completed:false}));
  renderStreets(streets.map(s => ({...s, geometry: s.geometry || (S.streets.find(x=>x.id===s.id)||{}).geometry || []})));
  updateProgress(data.completed, data.total || S.streets.length);
}

function updateProgress(done, total) {
  const pct = total ? Math.round((done/total)*100) : 0;
  el('progFill').style.width = pct + '%';
  el('progressLabel').textContent = `${done} / ${total} sokak tamamlandı`;
}

function fitMapToStreets(streets) {
  const coords = streets.flatMap(s => s.geometry || []);
  if (!coords.length) return;
  try { S.map.fitBounds(L.latLngBounds(coords), {padding:[20,20]}); } catch(e){}
}

// ── Sokak tıklama ─────────────────────────────────────────────────────────────
function onStreetClick(street) {
  if (S.mode === 'assign') {
    if (S.assignSelected.has(street.id)) S.assignSelected.delete(street.id);
    else S.assignSelected.add(street.id);
    refreshStreetColor(street.id);
    el('assignStreetCount').textContent = S.assignSelected.size;
    return;
  }
  openStreetDetail(street);
}

// ── Sokak detay paneli ─────────────────────────────────────────────────────────
const ROLE_NAMES = {
  supurgeci:'Yaya Süpürgeci', aracli_supurge:'Araçlı Süpürge',
  cop_araci:'Çöp Aracı', ring_araci:'Ring Aracı',
  kaba_atik:'Kaba Atık', konteyner_yikama:'Konteyner Yıkama',
  cavus:'Çavuş', onbasi:'Onbaşı', santiye_amiri:'Şantiye Amiri',
};

async function openStreetDetail(street) {
  el('sdStreetName').textContent = street.name;
  el('sdBody').innerHTML = '<p style="padding:8px 0;color:var(--muted);font-size:13px">Yükleniyor…</p>';
  el('sdActions').innerHTML = '';
  openModal('streetDetailModal');

  const nid = S.activeNb ? S.activeNb.id : '';
  try {
    const d = await api(`/api/streets/${street.id}/details?date=${todayStr()}&neighborhood_id=${nid}`);
    renderStreetDetail(d, street);
  } catch(e) {
    el('sdBody').innerHTML = `<p style="color:var(--red);font-size:13px">${e.message}</p>`;
  }
}

function renderStreetDetail(d, street) {
  let html = '';

  if (d.supervisors && d.supervisors.length) {
    html += `<div class="sd-section"><div class="sd-label">👮 Mahalle Sorumlusu</div>`;
    d.supervisors.forEach(s => {
      html += `<div class="sd-row"><span>${ROLE_NAMES[s.role]||s.role}</span><b>${esc(s.display_name)}</b></div>`;
    });
    html += `</div>`;
  }

  html += `<div class="sd-section"><div class="sd-label">📋 Atamalar</div>`;
  if (d.assignments && d.assignments.length) {
    d.assignments.forEach(a => {
      html += `<div class="sd-row">
        <span>${ROLE_NAMES[a.team_type]||a.team_type}</span>
        <b>${esc(a.user_name || '— Tüm ekip —')}</b>
        ${a.shift_name ? `<span class="sd-muted">${esc(a.shift_name)}</span>` : ''}
        ${!a.work_date ? `<span style="font-size:10px;color:var(--green);background:rgba(26,122,60,.15);padding:2px 6px;border-radius:10px">Kalıcı</span>` : ''}
      </div>`;
    });
  } else {
    html += `<div class="sd-row sd-pending">Bu sokağa atama yok</div>`;
  }
  html += `</div>`;

  html += `<div class="sd-section"><div class="sd-label">✅ Bugün Yapılanlar</div>`;
  if (d.completions && d.completions.length) {
    d.completions.forEach(c => {
      html += `<div class="sd-row">
        <span class="sd-done">✅</span>
        <span>${ROLE_NAMES[c.role]||c.role}</span>
        <b>${esc(c.user_name)}</b>
        ${c.photo_sent ? '📷' : ''}
        <span class="sd-muted">${timeAgo(c.completed_at)}</span>
      </div>`;
      if (c.note) html += `<div style="font-size:12px;color:var(--muted);padding:2px 0 4px">${esc(c.note)}</div>`;
    });
  } else {
    html += `<div class="sd-row sd-pending">Henüz işlem yapılmamış</div>`;
  }
  html += `</div>`;

  if (d.notifications && d.notifications.length) {
    html += `<div class="sd-section"><div class="sd-label">⚠️ Açık Bildirimler (${d.notifications.length})</div>`;
    d.notifications.slice(0, 4).forEach(n => {
      html += `<div class="sd-row">${NOTIF_ICONS[n.type]||'📝'} ${NOTIF_LABELS[n.type]||n.type}
        ${n.note ? `<span style="font-size:12px;color:var(--muted)">— ${esc(n.note)}</span>` : ''}
        <span class="sd-muted">${esc(n.creator_name)}</span>
      </div>`;
    });
    html += `</div>`;
  }

  el('sdBody').innerHTML = html;

  const actions = el('sdActions');
  const notifBtn = document.createElement('button');
  notifBtn.textContent = '⚠️ Bildirim Ekle';
  notifBtn.onclick = () => { closeModal('streetDetailModal'); openNotifModal(); };
  actions.appendChild(notifBtn);

  if (!SUPERVISOR_ROLES.has(S.user.role)) {
    const myStreet = S.myStreets.find(s => s.id === street.id);
    if (myStreet && !S.completedIds.has(street.id)) {
      const closeBtn = document.createElement('button');
      closeBtn.className = 'primary';
      closeBtn.textContent = '🧹 Sokağı Kapat';
      closeBtn.onclick = () => { closeModal('streetDetailModal'); openCloseStreetModal(street); };
      actions.appendChild(closeBtn);
    }
  }
}

el('sdCloseBtn').addEventListener('click', () => closeModal('streetDetailModal'));

// ── Harita tıklama (bildirim konumu) ──────────────────────────────────────────
function onMapClick(e) {
  if (S.mode !== 'notif') return;
  S._pendingNotifLatLng = e.latlng;
  el('notifLocInfo').textContent = `📍 ${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`;
}

// ── Sokak kapat modal ─────────────────────────────────────────────────────────
function openCloseStreetModal(street) {
  S.closingStreetId = street.id;
  S.photoFile = null;
  el('csStreetName').textContent = street.name;
  el('csNote').value = '';
  el('photoPreview').style.display = 'none';
  el('photoPickBtn').className = 'photo-btn';
  el('photoPickBtn').textContent = '📷 Fotoğraf Çek / Seç';
  el('csSaveBtn').disabled = true;
  openModal('closeStreetModal');
}

el('photoPickBtn').addEventListener('click', () => el('photoInput').click());

el('photoInput').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  S.photoFile = file;
  const url = URL.createObjectURL(file);
  el('photoPreview').src = url;
  el('photoPreview').style.display = 'block';
  el('photoPickBtn').className = 'photo-btn has-photo';
  el('photoPickBtn').textContent = '✅ Fotoğraf seçildi — değiştirmek için dokun';
  el('csSaveBtn').disabled = false;
});

el('csCancelBtn').addEventListener('click', () => closeModal('closeStreetModal'));

el('csSaveBtn').addEventListener('click', async () => {
  if (!S.photoFile || !S.closingStreetId || !S.activeNb) return;
  el('csSaveBtn').disabled = true;
  el('csSaveBtn').textContent = 'Gönderiliyor…';

  const fd = new FormData();
  fd.append('photo', S.photoFile, 'photo.jpg');
  fd.append('work_date', todayStr());
  fd.append('neighborhood_id', S.activeNb.id);

  // assignment_id bul
  const myS = S.myStreets.find(s => s.id === S.closingStreetId);
  if (myS && myS.assignment_id) fd.append('assignment_id', myS.assignment_id);

  const note = el('csNote').value.trim();
  if (note) fd.append('note', note);

  try {
    const res = await fetch(`/api/streets/${S.closingStreetId}/complete`, {method:'POST', body:fd});
    if (res.status === 401) { location.href = '/login'; return; }
    const d = await res.json();
    if (!res.ok) throw Error(d.error || 'Hata');

    S.completedIds.add(S.closingStreetId);
    const street = S.myStreets.find(s => s.id === S.closingStreetId);
    if (street) street.completed = true;
    refreshStreetColor(S.closingStreetId);
    updateProgress(S.completedIds.size, S.myStreets.length);
    closeModal('closeStreetModal');

    const streetName = street ? street.name : 'Sokak';
    toast(`${streetName} tamamlandı ✅` + (d.photo_sent ? ' — Telegram\'a gönderildi' : ''), 'success', 4000);
    speak(`${streetName} süpürüldü`);
  } catch(e) {
    toast(e.message, 'error');
    el('csSaveBtn').disabled = false;
    el('csSaveBtn').textContent = '✅ Kapat & Gönder';
  }
});

// ── En yakın sokak ─────────────────────────────────────────────────────────────
el('nearestBtn').addEventListener('click', () => {
  if (!S.lastPos) {
    toast('GPS konumu henüz alınamadı — bekleyin veya uygulamaya konum izni verin', 'error', 4000);
    return;
  }
  const pool = S.myStreets.length ? S.myStreets : S.streets;
  const unvisited = pool.filter(s => !S.completedIds.has(s.id));
  if (!unvisited.length) { toast('Tüm sokaklar tamamlandı 🎉', 'success'); return; }

  let nearest = unvisited[0], nearestD = Infinity;
  for (const s of unvisited) {
    const d = nearestStreetDist(s);
    if (d < nearestD) { nearestD = d; nearest = s; }
  }
  const [la, lo] = nearest.geometry[Math.floor(nearest.geometry.length/2)];
  S.map.flyTo([la, lo], 17, {animate:true, duration:.8});
  speak(`En yakın sokak: ${nearest.name}, yaklaşık ${Math.round(nearestD)} metre`);
  toast(`🧭 ${nearest.name} — ${Math.round(nearestD)}m`);
});

// ── GPS ───────────────────────────────────────────────────────────────────────
el('locateBtn').addEventListener('click', () => {
  if (S.lastPos) S.map.setView([S.lastPos.lat, S.lastPos.lng], 17);
  else toast('Konum alınamadı');
});

function onGpsPosition(pos) {
  const {latitude:lat, longitude:lng} = pos.coords;
  S.lastPos = {lat, lng};

  if (!S.meMarker) {
    S.meMarker = L.circleMarker([lat,lng], {radius:9, color:'#1f6feb', fillColor:'#1f6feb', fillOpacity:.9, weight:2}).addTo(S.map);
  } else {
    S.meMarker.setLatLng([lat,lng]);
  }

  // Yakın notif oku
  for (const n of S.notifications) {
    if (n.status !== 'open' || S.announcedNotifs.has(n.id)) continue;
    const d = haversine(lat, lng, n.lat, n.lon);
    if (d <= 50) {
      S.announcedNotifs.add(n.id);
      const label = NOTIF_LABELS[n.type] || n.type;
      speak(`Yakında olumsuzluk: ${label}` + (n.note ? '. ' + n.note : ''));
      toast(`⚠️ ${label}${n.note ? ': '+n.note : ''}`, '', 5000);
    }
  }
}

if ('geolocation' in navigator) {
  // Hemen bir kez al (watchPosition gecikmeli başlayabiliyor)
  navigator.geolocation.getCurrentPosition(onGpsPosition, () => {}, {enableHighAccuracy:true, timeout:10000});
  navigator.geolocation.watchPosition(onGpsPosition, () => {}, {
    enableHighAccuracy: true, maximumAge: 6000, timeout: 30000
  });
}

// ── Sesli yönlendirme toggle ──────────────────────────────────────────────────
el('voiceBtn').addEventListener('click', () => {
  S.voiceOn = !S.voiceOn;
  el('voiceBtn').textContent = S.voiceOn ? '🔊' : '🔇';
  el('voiceBtn').classList.toggle('active', S.voiceOn);
  speak(S.voiceOn ? 'Sesli yönlendirme açık' : '');
});
el('voiceBtn').classList.add('active');

// ── Bildirim ekle ─────────────────────────────────────────────────────────────
function openNotifModal() {
  if (!S.activeNb) { toast('Önce bir mahalle seçin'); return; }
  el('notifNote').value = '';
  if (S.lastPos) {
    S._pendingNotifLatLng = L.latLng(S.lastPos.lat, S.lastPos.lng);
    el('notifLocInfo').textContent = `📍 ${S.lastPos.lat.toFixed(5)}, ${S.lastPos.lng.toFixed(5)} (GPS konumun)`;
  } else {
    S._pendingNotifLatLng = null;
    el('notifLocInfo').textContent = '📍 GPS bekleniyor — haritaya da dokunabilirsin';
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(pos => {
        onGpsPosition(pos);
        S._pendingNotifLatLng = L.latLng(pos.coords.latitude, pos.coords.longitude);
        el('notifLocInfo').textContent = `📍 ${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)} (GPS)`;
      }, () => {}, {enableHighAccuracy:true, timeout:8000});
    }
  }
  openModal('addNotifModal');
}

el('addNotifBtn').addEventListener('click', openNotifModal);

el('notifCancelBtn').addEventListener('click', () => closeModal('addNotifModal'));

el('notifSaveBtn').addEventListener('click', async () => {
  if (!S._pendingNotifLatLng) { toast('Konum seçilmedi — haritaya dokun', 'error'); return; }
  const type = el('notifType').value;
  const note = el('notifNote').value.trim();
  try {
    const n = await api('/api/notifications', {method:'POST', body:JSON.stringify({
      neighborhood_id: S.activeNb.id,
      lat: S._pendingNotifLatLng.lat, lon: S._pendingNotifLatLng.lng,
      type, note,
    })});
    S.notifications.push(n);
    addNotifMarker(n);
    closeModal('addNotifModal');
    toast('Bildirim gönderildi ✅', 'success');
  } catch(e) { toast(e.message, 'error'); }
});

// ── Sokak listesi paneli ───────────────────────────────────────────────────────
el('streetListBtn').addEventListener('click', () => openSidePanel('Sokaklar', renderStreetList));
el('notifPoolBtn').addEventListener('click', () => openSidePanel('Bildirim Havuzu', renderNotifPool));

function openSidePanel(title, renderFn) {
  el('sidePanelTitle').textContent = title;
  el('sidePanelBody').innerHTML = '';
  renderFn();
  el('sidePanel').classList.add('open');
}

el('sidePanelCloseBtn').addEventListener('click', () => el('sidePanel').classList.remove('open'));

function renderStreetList() {
  const body = el('sidePanelBody');
  const pool = S.myStreets.length ? S.myStreets : S.streets;
  if (!pool.length) { body.innerHTML = '<p style="padding:12px;color:var(--muted)">Sokak yok</p>'; return; }

  // Sırala: tamamlanmayanlar önce, sonra ada göre
  const sorted = [...pool].map(s => ({...s, completed: S.completedIds.has(s.id)}))
    .sort((a,b) => a.completed - b.completed || a.name.localeCompare(b.name, 'tr'));

  body.innerHTML = sorted.map(s => `
    <div class="street-row">
      <span class="sname">${esc(s.name)}</span>
      <span class="badge ${s.completed ? 'done' : ''}">${s.completed ? '✅ Tamam' : '⬛ Bekliyor'}</span>
      <button data-fly="${s.id}">Git</button>
    </div>
  `).join('');

  body.querySelectorAll('[data-fly]').forEach(btn => {
    btn.onclick = () => {
      const street = pool.find(s => s.id === Number(btn.dataset.fly));
      if (!street) return;
      const bounds = L.latLngBounds(street.geometry);
      S.map.flyToBounds(bounds, {padding:[40,40], animate:true, duration:.8});
      speak(street.name);
      el('sidePanel').classList.remove('open');
    };
  });
}

// ── Bildirim havuzu renderı ─────────────────────────────────────────────────────
async function renderNotifPool() {
  const body = el('sidePanelBody');
  if (!S.activeNb) { body.innerHTML = '<p style="padding:12px;color:var(--muted)">Mahalle seçin</p>'; return; }
  body.innerHTML = '<p style="padding:12px;color:var(--muted)">Yükleniyor…</p>';
  try {
    const items = await api(`/api/notifications?neighborhood_id=${S.activeNb.id}&status=open`);
    S.notifications = items;
    if (!items.length) { body.innerHTML = '<p style="padding:12px;color:var(--green)">Açık olumsuzluk yok 🎉</p>'; return; }
    body.innerHTML = items.map(n => `
      <div class="notif-card">
        <div class="ntop">
          <span>${NOTIF_ICONS[n.type]||'📝'}</span>
          <span class="nlabel">${NOTIF_LABELS[n.type]||n.type}</span>
          <span class="status-open" style="margin-left:auto;font-size:11px">Açık</span>
        </div>
        ${n.note ? `<div style="margin:2px 0 4px;font-size:12px">${esc(n.note)}</div>` : ''}
        <div class="ninfo">👤 ${esc(n.creator_name||'')} — ${timeAgo(n.created_at)}</div>
        <div class="nbtn-row">
          <button data-fly-notif="${n.id}" data-lat="${n.lat}" data-lon="${n.lon}">📍 Git</button>
          <button class="primary" data-resolve-notif="${n.id}" data-lat="${n.lat}" data-lon="${n.lon}">✅ Çöz</button>
          ${SUPERVISOR_ROLES.has(S.user.role) ? `<button data-cancel-notif="${n.id}" style="background:var(--red-light);border-color:var(--red);color:#fff">İptal</button>` : ''}
        </div>
      </div>
    `).join('');

    body.querySelectorAll('[data-fly-notif]').forEach(btn => {
      btn.onclick = () => { S.map.flyTo([+btn.dataset.lat, +btn.dataset.lon], 17); el('sidePanel').classList.remove('open'); };
    });
    body.querySelectorAll('[data-resolve-notif]').forEach(btn => {
      btn.onclick = () => resolveNotif(+btn.dataset.resolveNotif, +btn.dataset.lat, +btn.dataset.lon);
    });
    body.querySelectorAll('[data-cancel-notif]').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm('Bildirimi iptal et?')) return;
        await api(`/api/notifications/${btn.dataset.cancelNotif}/cancel`, {method:'POST'});
        renderNotifPool();
      };
    });
  } catch(e) { body.innerHTML = `<p style="padding:12px;color:var(--red)">${e.message}</p>`; }
}

function resolveNotif(nid, lat, lon) {
  // Önce konuma git
  if (lat && lon) {
    S.map.flyTo([lat, lon], 17, {animate: true, duration: 0.8});
    el('sidePanel').classList.remove('open');
  }
  // Fotoğraflı kapama — basit dosya seç
  const input = document.createElement('input');
  input.type = 'file'; input.accept = 'image/*'; input.capture = 'environment';
  input.onchange = async () => {
    const file = input.files[0]; if (!file) return;
    const fd = new FormData(); fd.append('photo', file, 'photo.jpg');
    try {
      await fetch(`/api/notifications/${nid}/resolve`, {method:'POST', body:fd});
      toast('Bildirim kapatıldı ✅', 'success');
      renderNotifPool();
    } catch(e) { toast(e.message, 'error'); }
  };
  input.click();
}

// ── Bildirim markerları ────────────────────────────────────────────────────────
const notifMarkers = {};
function addNotifMarker(n) {
  if (notifMarkers[n.id]) return;
  const icon = L.divIcon({html:`<div style="font-size:24px;line-height:1">${NOTIF_ICONS[n.type]||'📝'}</div>`,className:'',iconSize:[24,24],iconAnchor:[12,12]});
  const m = L.marker([n.lat,n.lon],{icon});
  m.bindPopup(`<b>${NOTIF_LABELS[n.type]||n.type}</b>${n.note?'<br>'+esc(n.note):''}`);
  m.addTo(S.map);
  notifMarkers[n.id] = m;
}

// ── Menü ──────────────────────────────────────────────────────────────────────
el('menuBtn').addEventListener('click', async () => {
  // Mahalleleri güncelle
  const sel = el('nbSelect');
  sel.innerHTML = '<option value="">— Mahalle seç —</option>';
  for (const nb of S.neighborhoods) {
    const opt = document.createElement('option');
    opt.value = nb.id; opt.textContent = nb.name;
    if (S.activeNb && nb.id === S.activeNb.id) opt.selected = true;
    sel.appendChild(opt);
  }

  // Çavuş/Şantiye amiri için ekstra menü
  const section = el('menuRoleSection');
  if (SUPERVISOR_ROLES.has(S.user.role)) {
    section.innerHTML = `
      <hr style="border-color:var(--border);margin:14px 0 10px">
      <div style="font-size:12px;color:var(--muted);margin-bottom:6px">Mahalle Ekle (OSM'den)</div>
      <select id="addNbIl" style="width:100%;padding:8px 10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:14px;margin-bottom:6px">
        <option value="">— İl seç —</option>
      </select>
      <select id="addNbIlce" disabled style="width:100%;padding:8px 10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:14px;margin-bottom:6px">
        <option value="">— Önce il seçin —</option>
      </select>
      <select id="addNbMahalle" disabled style="width:100%;padding:8px 10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:14px;margin-bottom:6px">
        <option value="">— Önce ilçe seçin —</option>
      </select>
      <button id="addNbBtn" disabled style="width:100%;padding:10px;border-radius:var(--radius-sm);border:1px solid var(--green);background:var(--green);color:#fff;font-size:13px;font-weight:600">+ Mahalle Ekle</button>
      <hr style="border-color:var(--border);margin:12px 0">
      <button id="openAssignBtn" style="width:100%;padding:10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--panel2);color:var(--text);font-size:13px;font-weight:600">📋 Güzergah Ata</button>`;

    // İl listesini yükle
    try {
      const provinces = await api('/api/osm/provinces');
      const ilSel = el('addNbIl');
      provinces.forEach(p => {
        const o = document.createElement('option');
        o.value = p; o.textContent = p;
        ilSel.appendChild(o);
      });
    } catch(e) {}

    el('addNbIl').onchange = async () => {
      const prov = el('addNbIl').value;
      const ilceSel = el('addNbIlce');
      const mahSel = el('addNbMahalle');
      mahSel.innerHTML = '<option value="">— Önce ilçe seçin —</option>';
      mahSel.disabled = true;
      el('addNbBtn').disabled = true;
      if (!prov) {
        ilceSel.innerHTML = '<option value="">— Önce il seçin —</option>';
        ilceSel.disabled = true;
        return;
      }
      ilceSel.innerHTML = '<option value="">Yükleniyor…</option>';
      ilceSel.disabled = true;
      try {
        const districts = await api(`/api/osm/districts?province=${encodeURIComponent(prov)}`);
        ilceSel.innerHTML = '<option value="">— İlçe seç —</option>';
        districts.forEach(d => {
          const o = document.createElement('option');
          o.value = d.name; o.textContent = d.name;
          ilceSel.appendChild(o);
        });
        ilceSel.disabled = false;
      } catch(e) {
        ilceSel.innerHTML = `<option value="">Hata: ${e.message}</option>`;
      }
    };

    el('addNbIlce').onchange = async () => {
      const prov = el('addNbIl').value;
      const dist = el('addNbIlce').value;
      const mahSel = el('addNbMahalle');
      el('addNbBtn').disabled = true;
      if (!dist) {
        mahSel.innerHTML = '<option value="">— Önce ilçe seçin —</option>';
        mahSel.disabled = true;
        return;
      }
      mahSel.innerHTML = '<option value="">Yükleniyor…</option>';
      mahSel.disabled = true;
      try {
        const nbs = await api(`/api/osm/neighborhoods?province=${encodeURIComponent(prov)}&district=${encodeURIComponent(dist)}`);
        mahSel.innerHTML = '<option value="">— Mahalle seç —</option>';
        nbs.forEach(n => {
          const o = document.createElement('option');
          o.value = n.name; o.textContent = n.name;
          mahSel.appendChild(o);
        });
        mahSel.disabled = false;
      } catch(e) {
        mahSel.innerHTML = `<option value="">Hata: ${e.message}</option>`;
      }
    };

    el('addNbMahalle').onchange = () => {
      el('addNbBtn').disabled = !el('addNbMahalle').value;
    };

    el('addNbBtn').onclick = async () => {
      const mahalle = el('addNbMahalle').value;
      const ilce = el('addNbIlce').value;
      const il = el('addNbIl').value;
      if (!mahalle || !S.user.district_id) return;
      el('addNbBtn').disabled = true;
      el('addNbBtn').textContent = 'Ekleniyor… (sokaklar çekiliyor)';
      try {
        const res = await api('/api/neighborhoods', {
          method: 'POST',
          body: JSON.stringify({
            query: `${mahalle}, ${ilce}, ${il}`,
            district_id: S.user.district_id,
          }),
        });
        toast(`${mahalle} eklendi — ${res.street_count || 0} sokak ✅`, 'success', 5000);
        // Mahalleleri yenile
        const me = await api('/api/me');
        S.neighborhoods = me.neighborhoods;
        const nbSel = el('nbSelect');
        nbSel.innerHTML = '<option value="">— Mahalle seç —</option>';
        S.neighborhoods.forEach(nb => {
          const o = document.createElement('option');
          o.value = nb.id; o.textContent = nb.name;
          if (S.activeNb && nb.id === S.activeNb.id) o.selected = true;
          nbSel.appendChild(o);
        });
        // Seçili mahalleye geç
        if (!S.activeNb) {
          const newNb = S.neighborhoods.find(n => n.name === res.name || n.id === res.id);
          if (newNb) { closeModal('menuModal'); loadNeighborhood(newNb); return; }
        }
      } catch(e) { toast(e.message, 'error'); }
      el('addNbBtn').disabled = false;
      el('addNbBtn').textContent = '+ Mahalle Ekle';
    };

    el('openAssignBtn').onclick = () => { closeModal('menuModal'); openAssignPanel(); };

    // Personel yönetimi butonu
    const personnelBtnHtml = `<button id="openPersonnelBtn" style="width:100%;padding:10px;margin-top:6px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--panel2);color:var(--text);font-size:13px;font-weight:600">👥 Personel Yönetimi</button>`;
    el('menuRoleSection').insertAdjacentHTML('beforeend', personnelBtnHtml);
    el('openPersonnelBtn').onclick = () => { closeModal('menuModal'); openPersonnelPanel(); };
  } else {
    section.innerHTML = '';
  }

  // Çıkış butonuna ad yaz
  const logBtn = el('logoutBtn');
  if (logBtn) logBtn.textContent = `Çıkış (${S.user.display_name})`;

  openModal('menuModal');
});

el('nbSelect').addEventListener('change', e => {
  const nid = Number(e.target.value);
  if (!nid) return;
  const nb = S.neighborhoods.find(n => n.id === nid);
  if (nb) { loadNeighborhood(nb); closeModal('menuModal'); }
});

el('menuCloseBtn').addEventListener('click', () => closeModal('menuModal'));
el('logoutBtn').addEventListener('click', async () => {
  await api('/api/logout', {method:'POST'}).catch(()=>{});
  location.href = '/login';
});

// ── Güzergah atama paneli (çavuş) ─────────────────────────────────────────────
async function openAssignPanel() {
  if (!S.activeNb) { toast('Önce mahalle seçin'); return; }
  S.mode = 'assign';
  S.assignSelected.clear();
  el('assignStreetCount').textContent = '0';

  // Kalıcı toggle sıfırla
  el('assignPermanent').checked = false;
  el('assignDateSection').style.display = '';

  el('assignPermanent').onchange = () => {
    el('assignDateSection').style.display = el('assignPermanent').checked ? 'none' : '';
  };

  // Tarih varsayılanı: bugün
  el('assignDate').value = todayStr();

  // Vardiyaları yükle
  try {
    const shifts = await api(`/api/shifts?district_id=${S.user.district_id}`);
    const sel = el('assignShift');
    sel.innerHTML = '<option value="">— Tüm gün —</option>';
    shifts.forEach(sh => {
      const o = document.createElement('option'); o.value = sh.id; o.textContent = sh.display_name; sel.appendChild(o);
    });
  } catch(e) {}

  // Ekip kullanıcılarını yükle
  try {
    const users = await api('/api/users');
    const teamType = el('assignTeamType').value;
    const sel = el('assignUser');
    sel.innerHTML = '<option value="">— Tüm ekip —</option>';
    users.filter(u => u.role === teamType).forEach(u => {
      const o = document.createElement('option'); o.value = u.id; o.textContent = u.display_name; sel.appendChild(o);
    });
  } catch(e) {}

  el('assignTeamType').onchange = async () => {
    try {
      const users = await api('/api/users');
      const sel = el('assignUser');
      sel.innerHTML = '<option value="">— Tüm ekip —</option>';
      users.filter(u => u.role === el('assignTeamType').value).forEach(u => {
        const o = document.createElement('option'); o.value = u.id; o.textContent = u.display_name; sel.appendChild(o);
      });
    } catch(e) {}
  };

  // Sokakları atama moduna al
  renderStreets(S.streets.map(s => ({...s, completed: false})));
  openModal('assignModal');
}

el('assignSelectAllBtn').addEventListener('click', () => {
  S.streets.forEach(s => { S.assignSelected.add(s.id); S.streetLayers[s.id] && S.streetLayers[s.id].setStyle(streetColor(s)); });
  el('assignStreetCount').textContent = S.assignSelected.size;
});

el('assignClearBtn').addEventListener('click', () => {
  S.assignSelected.clear();
  S.streets.forEach(s => S.streetLayers[s.id] && S.streetLayers[s.id].setStyle(streetColor(s)));
  el('assignStreetCount').textContent = '0';
});

el('assignCancelBtn').addEventListener('click', () => {
  S.mode = 'normal'; S.assignSelected.clear();
  closeModal('assignModal');
  loadNeighborhood(S.activeNb);
});

el('assignSaveBtn').addEventListener('click', async () => {
  if (!S.assignSelected.size) { toast('Hiç sokak seçilmedi', 'error'); return; }
  const permanent = el('assignPermanent').checked;
  const payload = {
    neighborhood_id: S.activeNb.id,
    team_type: el('assignTeamType').value,
    shift_id: el('assignShift').value || null,
    permanent,
    work_date: permanent ? null : (el('assignDate').value || todayStr()),
    street_ids: [...S.assignSelected],
    assigned_user_id: el('assignUser').value || null,
  };
  try {
    const res = await api('/api/assignments', {method:'POST', body:JSON.stringify(payload)});
    S.mode = 'normal'; S.assignSelected.clear();
    closeModal('assignModal');
    toast(`${res.street_count} sokak atandı ✅`, 'success');
    loadNeighborhood(S.activeNb);
  } catch(e) { toast(e.message, 'error'); }
});

// ── Personel yönetimi ─────────────────────────────────────────────────────────
async function openPersonnelPanel() {
  openModal('personnelModal');
  await refreshPersonnelList();
}

async function refreshPersonnelList() {
  const list = el('personnelList');
  list.innerHTML = '<p style="color:var(--muted);font-size:13px;padding:4px 0">Yükleniyor…</p>';
  try {
    const users = await api('/api/users');
    if (!users.length) {
      list.innerHTML = '<p style="color:var(--muted);font-size:13px">Henüz personel yok</p>';
      return;
    }
    list.innerHTML = users.map(u => `
      <div class="personnel-row">
        <div style="flex:1;min-width:0">
          <div class="pname">${esc(u.display_name)}</div>
          <div class="prole">${ROLE_NAMES[u.role]||u.role} — @${esc(u.username)}</div>
        </div>
        <span class="pbadge ${u.is_active===0||u.is_active==='0' ? 'inactive' : ''}">${u.is_active===0||u.is_active==='0' ? 'Pasif' : 'Aktif'}</span>
        <button data-edit-uid="${u.id}">Düzenle</button>
      </div>
    `).join('');
    list.querySelectorAll('[data-edit-uid]').forEach(btn => {
      const uid = Number(btn.dataset.editUid);
      const u = users.find(x => x.id === uid);
      btn.onclick = () => openEditPersonnel(u);
    });
  } catch(e) {
    list.innerHTML = `<p style="color:var(--red);font-size:13px">${e.message}</p>`;
  }
}

el('addPersonnelBtn').addEventListener('click', () => openEditPersonnel(null));
el('personnelCloseBtn').addEventListener('click', () => closeModal('personnelModal'));

async function openEditPersonnel(user) {
  const isNew = !user;
  el('editPersonnelTitle').textContent = isNew ? '👤 Personel Ekle' : '✏️ Personel Düzenle';
  el('epUserId').value = user ? user.id : '';
  el('epDisplayName').value = user ? user.display_name : '';
  el('epUsername').value = user ? user.username : '';
  el('epUsernameSection').querySelector('input').disabled = !isNew;
  el('epPassword').value = '';
  el('epPasswordHint').textContent = isNew ? '(zorunlu)' : '(değiştirmek için girin)';
  el('epRole').value = user ? user.role : 'supurgeci';
  el('epIsActive').checked = user ? (user.is_active !== 0 && user.is_active !== '0') : true;

  // Vardiyaları yükle
  const shiftSel = el('epShift');
  shiftSel.innerHTML = '<option value="">— Seçmek zorunda değilsiniz —</option>';
  if (S.user.district_id) {
    try {
      const shifts = await api(`/api/shifts?district_id=${S.user.district_id}`);
      shifts.forEach(sh => {
        const o = document.createElement('option');
        o.value = sh.id; o.textContent = sh.display_name;
        if (user && user.default_shift_id === sh.id) o.selected = true;
        shiftSel.appendChild(o);
      });
    } catch(e) {}
  }

  openModal('editPersonnelModal');
}

el('epCancelBtn').addEventListener('click', () => closeModal('editPersonnelModal'));

el('epSaveBtn').addEventListener('click', async () => {
  const uid = el('epUserId').value;
  const isNew = !uid;
  const payload = {
    display_name: el('epDisplayName').value.trim(),
    username: el('epUsername').value.trim(),
    password: el('epPassword').value.trim(),
    role: el('epRole').value,
    default_shift_id: el('epShift').value || null,
    is_active: el('epIsActive').checked ? 1 : 0,
  };

  if (!payload.display_name || !payload.role) { toast('Ad ve rol zorunludur', 'error'); return; }
  if (isNew && !payload.username) { toast('Kullanıcı adı zorunludur', 'error'); return; }
  if (isNew && !payload.password) { toast('Yeni personel için şifre zorunludur', 'error'); return; }

  el('epSaveBtn').disabled = true;
  try {
    if (isNew) {
      await api('/api/users', {method:'POST', body:JSON.stringify(payload)});
      toast(`${payload.display_name} eklendi ✅`, 'success');
    } else {
      await api(`/api/users/${uid}`, {method:'PUT', body:JSON.stringify(payload)});
      toast(`${payload.display_name} güncellendi ✅`, 'success');
    }
    closeModal('editPersonnelModal');
    await refreshPersonnelList();
  } catch(e) {
    toast(e.message, 'error');
  }
  el('epSaveBtn').disabled = false;
});

// ── Modal yardımcıları ─────────────────────────────────────────────────────────
function openModal(id) { el(id).classList.remove('hidden'); }
function closeModal(id) { el(id).classList.add('hidden'); }

// ── Zaman yardımcısı ──────────────────────────────────────────────────────────
function timeAgo(ts) {
  const d = Math.floor(Date.now()/1000 - ts);
  if (d < 60) return `${d}sn önce`;
  if (d < 3600) return `${Math.floor(d/60)}dk önce`;
  if (d < 86400) return `${Math.floor(d/3600)}sa önce`;
  return `${Math.floor(d/86400)}g önce`;
}

function esc(s) {
  const d = document.createElement('div'); d.textContent = String(s||''); return d.innerHTML;
}

// ── Uygulama başlatma ──────────────────────────────────────────────────────────
async function init() {
  initMap();
  try {
    const data = await api('/api/me');
    S.user = data.user;
    S.neighborhoods = data.neighborhoods;

    // Rol bazlı alt bar
    if (SUPERVISOR_ROLES.has(S.user.role)) {
      el('addNotifBtn').style.display = 'none'; // çavuş de bildirim ekleyebilir ama bottombar'da değil
      el('addNotifBtn').style.display = '';
    }

    // Son mahalle
    const lastId = localStorage.getItem('lastNbId');
    const nb = lastId && S.neighborhoods.find(n => n.id === Number(lastId))
                || S.neighborhoods[0];
    if (nb) await loadNeighborhood(nb);
    else toast('Menüden mahalle seçin ☰');

    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(()=>{});
  } catch(e) {
    if (e.message !== 'giris gerekli') toast(e.message, 'error');
  }
}

document.addEventListener('DOMContentLoaded', init);
})();
