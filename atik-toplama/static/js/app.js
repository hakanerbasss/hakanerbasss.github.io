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
  activeNb: null,
  streets: [],
  myStreets: [],
  completedIds: new Set(),
  notifications: [],
  map: null,
  streetLayers: {},
  assignSelected: new Set(),
  meMarker: null,
  lastPos: null,
  voiceOn: true,
  announcedNotifs: new Set(),
  mode: 'normal',
  closingStreetId: null,
  photoFile: null,
  _notifStreet: null,
  _resolvingNotif: null,
  _resolvePhotoFile: null,
  _refreshTimer: null,
  heading: null,
  _needsOrientationPermission: false,
  routeLayer: null,
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

// ── Sesli giriş (SpeechRecognition) ──────────────────────────────────────────
function startVoice(inputEl, btnEl) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast('Sesli giriş bu tarayıcıda desteklenmiyor', 'error', 4000); return; }
  const recognition = new SR();
  recognition.lang = 'tr-TR';
  recognition.continuous = false;
  recognition.interimResults = false;
  const origLabel = btnEl ? btnEl.textContent : '';
  if (btnEl) { btnEl.textContent = '🔴 Dinleniyor…'; btnEl.classList.add('recording'); btnEl.disabled = true; }
  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    inputEl.value = (inputEl.value.trim() ? inputEl.value.trim() + ' ' : '') + text;
    inputEl.dispatchEvent(new Event('input'));
    const preview = text.length > 40 ? text.slice(0, 40) + '…' : text;
    toast(`🎤 "${preview}"`, 'success', 3500);
  };
  recognition.onerror = (e) => {
    if (e.error !== 'aborted' && e.error !== 'no-speech') toast('Ses alınamadı — ' + e.error, 'error');
  };
  recognition.onend = () => {
    if (btnEl) { btnEl.textContent = origLabel; btnEl.classList.remove('recording'); btnEl.disabled = false; }
  };
  try { recognition.start(); } catch(e) {}
}

function haversine(la1, lo1, la2, lo2) {
  const R = 6371000, r = Math.PI/180;
  const dLa = (la2-la1)*r, dLo = (lo2-lo1)*r;
  const a = Math.sin(dLa/2)**2 + Math.cos(la1*r)*Math.cos(la2*r)*Math.sin(dLo/2)**2;
  return 2*R*Math.asin(Math.sqrt(a));
}

function streetMidpoint(geom) {
  return geom[Math.floor(geom.length/2)];
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

// ── Çevrimdışı kuyruk ─────────────────────────────────────────────────────────
const OQ_KEY = 'atik_offline_queue';
function _getOQ() { try { return JSON.parse(localStorage.getItem(OQ_KEY) || '[]'); } catch { return []; } }
function _saveOQ(q) { try { localStorage.setItem(OQ_KEY, JSON.stringify(q)); } catch {} }
function _addToOQ(item) { const q = _getOQ(); q.push({...item, queued_at: Date.now()}); _saveOQ(q); }

async function syncOfflineQueue() {
  const q = _getOQ();
  if (!q.length) return;
  const remaining = [];
  let synced = 0;
  for (const item of q) {
    try {
      if (item.type === 'complete_street') {
        const fd = new FormData();
        fd.append('work_date', item.work_date);
        fd.append('neighborhood_id', item.neighborhood_id);
        if (item.note) fd.append('note', item.note);
        const res = await fetch(`/api/streets/${item.street_id}/complete`, {method:'POST', body:fd});
        if (res.ok || res.status === 401) { synced++; continue; }
      }
    } catch {}
    remaining.push(item);
  }
  _saveOQ(remaining);
  if (synced > 0) {
    toast(`${synced} çevrimdışı kayıt senkronize edildi ✅`, 'success', 4000);
    if (S.activeNb) loadNeighborhood(S.activeNb);
  }
}

window.addEventListener('online', () => {
  toast('İnternet bağlantısı geri geldi', 'success', 3000);
  syncOfflineQueue();
});
window.addEventListener('offline', () => toast('İnternet bağlantısı kesildi — çevrimdışı mod aktif', '', 5000));

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
  Object.values(S.streetLayers).forEach(lr => {
    S.map.removeLayer(lr.vis);
    S.map.removeLayer(lr.hit);
  });
  S.streetLayers = {};

  streets.forEach(street => {
    const vis = L.polyline(street.geometry, {...streetColor(street), interactive:false});
    const hit = L.polyline(street.geometry, {weight:20, opacity:0, interactive:true});
    hit.on('click', () => onStreetClick(street));
    vis.bindTooltip(street.name, {direction:'top', sticky:false, opacity:.9});
    vis.addTo(S.map);
    hit.addTo(S.map);
    S.streetLayers[street.id] = {vis, hit};
  });
}

function refreshStreetColor(streetId) {
  const street = S.myStreets.find(s => s.id === streetId) || S.streets.find(s => s.id === streetId);
  const lr = S.streetLayers[streetId];
  if (!street || !lr) return;
  lr.vis.setStyle(streetColor(street));
}

// ── Mahalle yükleme ─────────────────────────────────────────────────────────────
async function loadNeighborhood(nb) {
  clearRoute();
  S.activeNb = nb;
  el('nbTitle').textContent = nb.name;
  el('progressLabel').textContent = 'Yükleniyor…';

  const allStreets = await api(`/api/neighborhoods/${nb.id}/streets`);
  S.streets = allStreets;

  try {
    S.notifications = await api(`/api/notifications?neighborhood_id=${nb.id}&status=open`);
  } catch(e) { S.notifications = []; }

  if (SUPERVISOR_ROLES.has(S.user.role)) {
    await loadSupervisorView();
    _startAutoRefresh();
  } else {
    await loadSweeperView();
    _stopAutoRefresh();
  }
  renderNotifMarkers(S.notifications);
  fitMapToStreets(S.streets.length ? S.streets : []);
  localStorage.setItem('lastNbId', String(nb.id));
  updateNotifBadge();
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

// ── Yetkili otomatik yenileme (60 saniyede bir) ────────────────────────────────
function _startAutoRefresh() {
  _stopAutoRefresh();
  S._refreshTimer = setInterval(async () => {
    if (!S.activeNb || document.hidden || S.mode !== 'normal') return;
    try { await loadSupervisorView(); } catch {}
  }, 60000);
}
function _stopAutoRefresh() {
  if (S._refreshTimer) { clearInterval(S._refreshTimer); S._refreshTimer = null; }
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden && S.user && SUPERVISOR_ROLES.has(S.user.role) && S.activeNb) {
    loadSupervisorView().catch(()=>{});
  }
});

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
    const lr = S.streetLayers[street.id];
    if (lr) lr.vis.setStyle(streetColor(street));
    _updateAssignCount();
    return;
  }
  const lr = S.streetLayers[street.id];
  if (lr) {
    lr.vis.setStyle({color:'#1f6feb', weight:8, opacity:1});
    setTimeout(() => refreshStreetColor(street.id), 1800);
  }
  // Süpürgeci modunda tıklanan sokağa otomatik rota çiz
  if (S.user && !SUPERVISOR_ROLES.has(S.user.role) && S.lastPos && street.geometry && street.geometry.length) {
    const mid = streetMidpoint(street.geometry);
    drawRouteTo(mid[0], mid[1], street.name);
  }
  openStreetDetail(street);
}

function _updateAssignCount() {
  el('assignBarCount').textContent = S.assignSelected.size;
  document.querySelectorAll('[data-assign-street]').forEach(cb => {
    cb.checked = S.assignSelected.has(+cb.dataset.assignStreet);
  });
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
    d.notifications.forEach(n => {
      html += `<div style="border-bottom:1px solid var(--border);padding:8px 0">
        <div style="display:flex;align-items:center;gap:6px;font-size:13px;flex-wrap:wrap">
          <span>${NOTIF_ICONS[n.type]||'📝'}</span>
          <b>${NOTIF_LABELS[n.type]||n.type}</b>
          <span class="sd-muted">${esc(n.creator_name)}</span>
        </div>
        ${n.note ? `<div style="font-size:12px;color:var(--muted);margin-top:3px">${esc(n.note)}</div>` : ''}
        <div style="display:flex;gap:6px;margin-top:7px">
          <button class="sd-notif-resolve" data-nid="${n.id}" data-lat="${n.lat}" data-lon="${n.lon}" data-sid="${n.street_id||0}"
            style="font-size:11px;padding:5px 10px;border-radius:6px;border:1px solid var(--green);background:var(--green);color:#fff;font-weight:600;cursor:pointer">✅ Çöz</button>
          <button class="sd-notif-comment" data-nid="${n.id}"
            style="font-size:11px;padding:5px 10px;border-radius:6px;border:1px solid var(--border);background:var(--panel2);color:var(--text);font-weight:600;cursor:pointer">💬 Yorum</button>
        </div>
        <div class="comment-section" id="cs-${n.id}" style="display:none"></div>
      </div>`;
    });
    html += `</div>`;
  }

  el('sdBody').innerHTML = html;

  el('sdBody').querySelectorAll('.sd-notif-resolve').forEach(btn => {
    btn.onclick = () => {
      const nid = +btn.dataset.nid;
      const sid = +btn.dataset.sid || null;
      const lat = +btn.dataset.lat, lon = +btn.dataset.lon;
      let notif = S.notifications.find(n => n.id === nid);
      if (!notif) {
        const nd = d.notifications.find(n => n.id === nid);
        if (nd) { notif = {...nd, street_name: street.name, status: 'open'}; S.notifications.push(notif); }
      }
      closeModal('streetDetailModal');
      flyToNotif(sid, lat, lon);
      if (notif) openResolveModal(notif);
    };
  });
  el('sdBody').querySelectorAll('.sd-notif-comment').forEach(btn => {
    btn.onclick = () => toggleComments(+btn.dataset.nid);
  });

  const actions = el('sdActions');

  if (S.lastPos && street.geometry && street.geometry.length) {
    const routeBtn = document.createElement('button');
    routeBtn.textContent = '🧭 Rota';
    routeBtn.style.cssText = 'background:var(--blue);border-color:var(--blue);color:#fff';
    routeBtn.onclick = () => {
      const mid = streetMidpoint(street.geometry);
      closeModal('streetDetailModal');
      drawRouteTo(mid[0], mid[1], street.name);
    };
    actions.appendChild(routeBtn);
  }

  const notifBtn = document.createElement('button');
  notifBtn.textContent = '⚠️ Bildirim Ekle';
  notifBtn.onclick = () => { closeModal('streetDetailModal'); openNotifModal(street); };
  actions.appendChild(notifBtn);

  if (SUPERVISOR_ROLES.has(S.user.role) && d.completions && d.completions.length) {
    const undoBtn = document.createElement('button');
    undoBtn.textContent = '↩️ Geri Al';
    undoBtn.style.cssText = 'background:var(--red);border-color:var(--red);color:#fff';
    undoBtn.onclick = async () => {
      if (!confirm(`${street.name} tamamlamasını geri al?`)) return;
      try {
        await api(`/api/streets/${street.id}/complete?date=${todayStr()}&neighborhood_id=${S.activeNb?.id||''}`, {method:'DELETE'});
        closeModal('streetDetailModal');
        toast('Tamamlama geri alındı', 'success');
        if (S.activeNb) loadNeighborhood(S.activeNb);
      } catch(e) { toast(e.message, 'error'); }
    };
    actions.appendChild(undoBtn);
  }

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
  el('csSaveBtn').disabled = false;
  el('csSaveBtn').textContent = '✅ Kapat & Gönder';
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
  if (!S.closingStreetId || !S.activeNb) return;
  el('csSaveBtn').disabled = true;
  el('csSaveBtn').textContent = 'Gönderiliyor…';

  const fd = new FormData();
  if (S.photoFile) fd.append('photo', S.photoFile, 'photo.jpg');
  fd.append('work_date', todayStr());
  fd.append('neighborhood_id', S.activeNb.id);

  const myS = S.myStreets.find(s => s.id === S.closingStreetId);
  if (myS && myS.assignment_id) fd.append('assignment_id', myS.assignment_id);

  const note = el('csNote').value.trim();
  if (note) fd.append('note', note);

  const streetName = myS ? myS.name : 'Sokak';

  try {
    const res = await fetch(`/api/streets/${S.closingStreetId}/complete`, {method:'POST', body:fd});
    if (res.status === 401) { location.href = '/login'; return; }
    const d = await res.json();
    if (!res.ok) throw Error(d.error || 'Hata');

    S.completedIds.add(S.closingStreetId);
    if (myS) myS.completed = true;
    refreshStreetColor(S.closingStreetId);
    updateProgress(S.completedIds.size, S.myStreets.length);
    closeModal('closeStreetModal');

    toast(`${streetName} tamamlandı ✅` + (d.photo_sent ? ' — Telegram\'a gönderildi' : ''), 'success', 4000);
    speak(`${streetName} süpürüldü`);

    // Sıradaki en yakın sokağa otomatik git
    setTimeout(() => _navigateToNextStreet(), 1200);

  } catch(e) {
    if (!navigator.onLine) {
      // Çevrimdışı kuyruğa ekle, yerel olarak işaretle
      _addToOQ({
        type: 'complete_street',
        street_id: S.closingStreetId,
        work_date: todayStr(),
        neighborhood_id: S.activeNb.id,
        note: el('csNote').value.trim(),
      });
      S.completedIds.add(S.closingStreetId);
      if (myS) myS.completed = true;
      refreshStreetColor(S.closingStreetId);
      updateProgress(S.completedIds.size, S.myStreets.length);
      closeModal('closeStreetModal');
      toast(`${streetName} çevrimdışı kaydedildi — internet gelince senkronize edilir`, 'success', 5000);
      speak(`${streetName} kaydedildi`);
      setTimeout(() => _navigateToNextStreet(), 1200);
    } else {
      toast(e.message, 'error');
      el('csSaveBtn').disabled = false;
      el('csSaveBtn').textContent = '✅ Kapat & Gönder';
    }
  }
});

function _navigateToNextStreet() {
  const unvisited = S.myStreets.filter(s => !S.completedIds.has(s.id));
  if (!unvisited.length) {
    toast('🎉 Tüm sokaklar tamamlandı!', 'success', 5000);
    speak('Tebrikler! Tüm sokaklar tamamlandı.');
    return;
  }
  if (!S.lastPos) return;
  let nearest = unvisited[0], nearestD = Infinity;
  for (const s of unvisited) {
    const d = nearestStreetDist(s);
    if (d < nearestD) { nearestD = d; nearest = s; }
  }
  const [la, lo] = nearest.geometry[Math.floor(nearest.geometry.length / 2)];
  S.map.flyTo([la, lo], 17, {animate:true, duration:.8});
  speak(`Sıradaki: ${nearest.name}, yaklaşık ${Math.round(nearestD)} metre`);
  toast(`�� Sıradaki: ${nearest.name} — ${Math.round(nearestD)}m`, '', 5000);
}

// ── Rota çizme (OSRM yürüyüş) ────────────────────────────────────────────────
async function drawRouteTo(destLat, destLon, destName) {
  clearRoute();
  if (!S.lastPos) { toast('GPS konumu alınamadı', 'error'); return; }
  const {lat, lng} = S.lastPos;
  el('clearRouteBtn').style.display = 'flex';
  try {
    const url = `https://router.project-osrm.org/route/v1/foot/${lng.toFixed(6)},${lat.toFixed(6)};${destLon.toFixed(6)},${destLat.toFixed(6)}?overview=full&geometries=geojson`;
    const ctrl = new AbortController();
    const tmo = setTimeout(() => ctrl.abort(), 8000);
    const res = await fetch(url, {signal: ctrl.signal});
    clearTimeout(tmo);
    const data = await res.json();
    if (!data.routes || !data.routes.length) throw new Error('rota_yok');
    const coords = data.routes[0].geometry.coordinates.map(([lo, la]) => [la, lo]);
    const dist = data.routes[0].distance;
    const dur = Math.round(data.routes[0].duration / 60);
    S.routeLayer = L.polyline(coords, {
      color: '#1f6feb', weight: 5, opacity: 0.85, dashArray: '10,6', lineCap: 'round'
    }).addTo(S.map);
    S.map.fitBounds(S.routeLayer.getBounds(), {padding: [50, 50]});
    const distStr = dist > 999 ? (dist / 1000).toFixed(1) + ' km' : Math.round(dist) + ' m';
    toast(`🧭 ${esc(destName)} — ${distStr}, ~${dur} dk`, '', 6000);
    speak(`${destName}. ${Math.round(dist) < 1000 ? Math.round(dist) + ' metre' : (dist/1000).toFixed(1) + ' kilometre'}, yaklaşık ${dur} dakika`);
  } catch(e) {
    // OSRM erişilemezse düz hat fallback
    const dist = Math.round(haversine(lat, lng, destLat, destLon));
    S.routeLayer = L.polyline([[lat, lng], [destLat, destLon]], {
      color: '#1f6feb', weight: 4, opacity: 0.65, dashArray: '8,8',
    }).addTo(S.map);
    S.map.fitBounds(S.routeLayer.getBounds(), {padding: [50, 50]});
    toast(`🧭 ${esc(destName)} — ~${dist} m`, '', 5000);
  }
}

function clearRoute() {
  if (S.routeLayer) { S.map.removeLayer(S.routeLayer); S.routeLayer = null; }
  const btn = el('clearRouteBtn');
  if (btn) btn.style.display = 'none';
}

el('clearRouteBtn').addEventListener('click', clearRoute);

// ── En yakın sokak butonu ──────────────────────────────────────────────────────
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

// ── Konum markeri (yön oku) ────────────────────────────────────────────────
function _meDivIcon(heading) {
  const hasH = heading != null && isFinite(heading);
  const rot = hasH ? heading : 0;
  return L.divIcon({
    className: '',
    iconSize: [44, 44],
    iconAnchor: [22, 22],
    html: `<div style="width:44px;height:44px;position:relative">
      ${hasH ? `<div style="position:absolute;inset:0;transform:rotate(${rot}deg);transform-origin:22px 22px">
        <svg width="44" height="44" viewBox="0 0 44 44"><polygon points="22,2 15,24 22,19 29,24" fill="#1f6feb" opacity="0.88"/></svg>
      </div>` : ''}
      <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:18px;height:18px;border-radius:50%;background:#1f6feb;border:2.5px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.5)"></div>
    </div>`,
  });
}

function _updateMeMarker(lat, lng) {
  if (!S.meMarker) {
    S.meMarker = L.marker([lat, lng], {icon: _meDivIcon(S.heading), zIndexOffset: 1000}).addTo(S.map);
  } else {
    S.meMarker.setLatLng([lat, lng]);
    S.meMarker.setIcon(_meDivIcon(S.heading));
  }
}

function _onOrientationEvent(e) {
  let deg = null;
  if (e.webkitCompassHeading != null && isFinite(e.webkitCompassHeading)) {
    // iOS: manyetik kuzey bazlı, saat yönü (0=K, 90=D, 180=G, 270=B)
    deg = e.webkitCompassHeading;
  } else if ((e.absolute === true || e.type === 'deviceorientationabsolute') && e.alpha != null && isFinite(e.alpha)) {
    // Android mutlak: alpha saat-yönü tersine, çevir
    deg = (360 - e.alpha) % 360;
  }
  if (deg != null) {
    S.heading = deg;
    if (S.lastPos) _updateMeMarker(S.lastPos.lat, S.lastPos.lng);
  }
}

function _setupDeviceOrientation() {
  if (typeof DeviceOrientationEvent === 'undefined') return;
  if (typeof DeviceOrientationEvent.requestPermission === 'function') {
    // iOS 13+: ilk kullanıcı etkileşiminde izin isteyeceğiz
    S._needsOrientationPermission = true;
  } else {
    window.addEventListener('deviceorientationabsolute', _onOrientationEvent, {passive: true});
    window.addEventListener('deviceorientation', _onOrientationEvent, {passive: true});
  }
}

// ── GPS ───────────────────────────────────────────────────────────────────────
el('locateBtn').addEventListener('click', () => {
  if (S._needsOrientationPermission) {
    S._needsOrientationPermission = false;
    DeviceOrientationEvent.requestPermission().then(state => {
      if (state === 'granted') {
        window.addEventListener('deviceorientationabsolute', _onOrientationEvent, {passive: true});
        window.addEventListener('deviceorientation', _onOrientationEvent, {passive: true});
        toast('Pusula izni verildi ✅', 'success', 2500);
      }
    }).catch(() => {});
  }
  if (S.lastPos) S.map.setView([S.lastPos.lat, S.lastPos.lng], 17);
  else toast('Konum alınamadı');
});

function onGpsPosition(pos) {
  const {latitude:lat, longitude:lng, heading} = pos.coords;
  S.lastPos = {lat, lng};
  // GPS heading sadece hareket halindeyken geçerli; pusula yoksa kullan
  if (S.heading == null && heading != null && isFinite(heading) && heading >= 0) {
    S.heading = heading;
  }
  _updateMeMarker(lat, lng);

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

// ── Bildirim rozeti ───────────────────────────────────────────────────────────
function updateNotifBadge() {
  const openCount = S.notifications.filter(n => n.status === 'open').length;
  el('notifPoolBtn').textContent = openCount > 0 ? `📋 Havuz (${openCount})` : '📋 Havuz';
}

// ── Bildirim ekle ─────────────────────────────────────────────────────────────
function openNotifModal(street) {
  if (!S.activeNb) { toast('Önce bir mahalle seçin'); return; }
  el('notifNote').value = '';
  S._notifStreet = street || null;

  if (street) {
    S._pendingNotifLatLng = null;
    el('notifLocInfo').textContent = `🛣 ${street.name}`;
  } else {
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
  }
  openModal('addNotifModal');
}

el('addNotifBtn').addEventListener('click', () => openNotifModal());

el('notifCancelBtn').addEventListener('click', () => { S._notifStreet = null; closeModal('addNotifModal'); });

el('notifSaveBtn').addEventListener('click', async () => {
  if (!S._notifStreet && !S._pendingNotifLatLng) {
    toast('Konum veya sokak seçilmedi', 'error'); return;
  }
  const type = el('notifType').value;
  const note = el('notifNote').value.trim();
  const payload = { neighborhood_id: S.activeNb.id, type, note };

  if (S._notifStreet) {
    payload.street_id = S._notifStreet.id;
    const geom = S._notifStreet.geometry;
    if (geom && geom.length) {
      const mid = geom[Math.floor(geom.length / 2)];
      payload.lat = mid[0];
      payload.lon = mid[1];
    }
  } else {
    payload.lat = S._pendingNotifLatLng.lat;
    payload.lon = S._pendingNotifLatLng.lng;
  }

  try {
    const n = await api('/api/notifications', {method:'POST', body:JSON.stringify(payload)});
    S.notifications.push(n);
    renderNotifMarkers(S.notifications);
    updateNotifBadge();
    S._notifStreet = null;
    closeModal('addNotifModal');
    toast('Bildirim gönderildi ✅', 'success');
  } catch(e) { toast(e.message, 'error'); }
});

// ── Sokak listesi paneli ───────────────────────────────────────────────────────
el('streetListBtn').addEventListener('click', () => openSidePanel('Sokaklar', renderStreetList));
el('notifPoolBtn').addEventListener('click', async () => {
  el('sidePanelTitle').textContent = 'Bildirim Havuzu';
  el('sidePanelBody').innerHTML = '<p style="padding:12px;color:var(--muted)">Yükleniyor…</p>';
  el('sidePanel').classList.add('open');
  if (S.activeNb) {
    try {
      const fresh = await api(`/api/notifications?neighborhood_id=${S.activeNb.id}&status=open`);
      const localNonOpen = S.notifications.filter(n => n.status !== 'open');
      S.notifications = [...fresh, ...localNonOpen];
      renderNotifMarkers(S.notifications.filter(n => n.status === 'open'));
      updateNotifBadge();
    } catch(e) {}
  }
  renderNotifPool();
});

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

  const sorted = [...pool].map(s => ({...s, completed: S.completedIds.has(s.id)}))
    .sort((a,b) => a.completed - b.completed || a.name.localeCompare(b.name, 'tr'));

  const done = sorted.filter(s => s.completed).length;
  body.innerHTML = `
    <div style="padding:8px 8px 4px">
      <input id="streetSearch" type="text" placeholder="Sokak ara…"
        style="width:100%;padding:8px 10px;border-radius:var(--radius-sm);border:1px solid var(--border);
        background:var(--bg);color:var(--text);font-size:14px;font-family:inherit">
      <div style="font-size:11px;color:var(--muted);margin-top:4px;padding:0 2px">${done}/${sorted.length} tamamlandı</div>
    </div>
  ` + sorted.map(s => `
    <div class="street-row" data-street-id="${s.id}">
      <span class="sname">${esc(s.name)}</span>
      <span class="badge ${s.completed ? 'done' : ''}">${s.completed ? '✅ Tamam' : '⬛ Bekliyor'}</span>
      <button data-fly="${s.id}">Git</button>
    </div>
  `).join('');

  const searchEl = body.querySelector('#streetSearch');
  if (searchEl) {
    searchEl.addEventListener('input', () => {
      const q = searchEl.value.toLowerCase();
      body.querySelectorAll('[data-street-id]').forEach(row => {
        row.style.display = row.querySelector('.sname').textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }

  body.querySelectorAll('[data-fly]').forEach(btn => {
    btn.onclick = () => {
      const street = pool.find(s => s.id === Number(btn.dataset.fly));
      if (!street || !street.geometry.length) return;
      const mid = street.geometry[Math.floor(street.geometry.length / 2)];
      S.map.flyTo(mid, 17, {animate:true, duration:.7});
      speak(street.name);
      el('sidePanel').classList.remove('open');
    };
  });
}

// ── Bildirim havuzu renderı ────────────────────────────────────────────────────
function renderNotifPool() {
  const body = el('sidePanelBody');
  if (!S.activeNb) { body.innerHTML = '<p style="padding:12px;color:var(--muted)">Mahalle seçin</p>'; return; }
  const items = S.notifications;
  if (!items.length) { body.innerHTML = '<p style="padding:12px;color:var(--green)">Açık olumsuzluk yok 🎉</p>'; return; }

  body.innerHTML = items.map(n => {
    const isOpen = n.status === 'open';
    const statusBadge = isOpen
      ? `<span class="status-open" style="margin-left:auto;font-size:11px">Açık</span>`
      : n.status === 'resolved'
        ? `<span class="status-resolved" style="margin-left:auto;font-size:11px">Giderildi ✅</span>`
        : `<span style="margin-left:auto;font-size:11px;color:var(--muted)">İptal</span>`;
    const actionBtns = isOpen
      ? `<button data-fly-notif="${n.id}" data-lat="${n.lat}" data-lon="${n.lon}" data-street-id="${n.street_id||''}">📍 Git</button>
         <button class="primary" data-resolve-notif="${n.id}" data-lat="${n.lat}" data-lon="${n.lon}" data-street-id="${n.street_id||''}">✅ Çöz</button>
         ${SUPERVISOR_ROLES.has(S.user.role) ? `<button data-cancel-notif="${n.id}" style="background:var(--red-light);border-color:var(--red);color:#fff">İptal</button>` : ''}
         <button data-comment-toggle="${n.id}" style="flex:0;padding:7px 10px">💬</button>`
      : `<button data-fly-notif="${n.id}" data-lat="${n.lat}" data-lon="${n.lon}" data-street-id="${n.street_id||''}">📍 Git</button>
         <button data-comment-toggle="${n.id}">💬 Yorumlar</button>`;
    return `
      <div class="notif-card">
        <div class="ntop">
          <span>${NOTIF_ICONS[n.type]||'📝'}</span>
          <span class="nlabel">${NOTIF_LABELS[n.type]||n.type}</span>
          ${statusBadge}
        </div>
        ${n.street_name ? `<div style="font-size:12px;color:var(--text);margin:2px 0">🛣 ${esc(n.street_name)}</div>` : ''}
        ${n.note ? `<div style="margin:2px 0 4px;font-size:12px">${esc(n.note)}</div>` : ''}
        <div class="ninfo">👤 ${esc(n.creator_name||'')} — ${timeAgo(n.created_at)}</div>
        <div class="nbtn-row">${actionBtns}</div>
        <div class="comment-section" id="cs-${n.id}" style="display:none"></div>
      </div>`;
  }).join('');

  body.querySelectorAll('[data-fly-notif]').forEach(btn => {
    btn.onclick = () => flyToNotif(+btn.dataset.streetId || null, +btn.dataset.lat, +btn.dataset.lon);
  });
  body.querySelectorAll('[data-resolve-notif]').forEach(btn => {
    btn.onclick = () => {
      const nid = +btn.dataset.resolveNotif;
      flyToNotif(+btn.dataset.streetId || null, +btn.dataset.lat, +btn.dataset.lon);
      const notif = S.notifications.find(n => n.id === nid);
      if (notif) openResolveModal(notif);
    };
  });
  body.querySelectorAll('[data-cancel-notif]').forEach(btn => {
    btn.onclick = async () => {
      if (!confirm('Bildirimi iptal et?')) return;
      const nid = +btn.dataset.cancelNotif;
      try {
        await api(`/api/notifications/${nid}/cancel`, {method:'POST'});
        const idx = S.notifications.findIndex(n => n.id === nid);
        if (idx !== -1) S.notifications[idx] = {...S.notifications[idx], status: 'cancelled'};
        renderNotifMarkers(S.notifications.filter(n => n.status === 'open'));
        updateNotifBadge();
        renderNotifPool();
      } catch(e) { toast(e.message, 'error'); }
    };
  });
  body.querySelectorAll('[data-comment-toggle]').forEach(btn => {
    btn.onclick = () => toggleComments(+btn.dataset.commentToggle);
  });
}

function flyToNotif(streetId, lat, lon) {
  el('sidePanel').classList.remove('open');
  if (streetId) {
    const street = S.streets.find(s => s.id === streetId);
    if (street && street.geometry && street.geometry.length) {
      const mid = street.geometry[Math.floor(street.geometry.length / 2)];
      S.map.flyTo(mid, 17, {animate:true, duration:.7});
      const lr = S.streetLayers[streetId];
      if (lr) {
        lr.vis.setStyle({color:'#d29922', weight:8, opacity:1});
        setTimeout(() => refreshStreetColor(streetId), 3000);
      }
      return;
    }
  }
  if (lat && lon) S.map.flyTo([lat, lon], 17, {animate:true, duration:.8});
}

function openResolveModal(notif) {
  S._resolvingNotif = notif;
  S._resolvePhotoFile = null;
  el('resolveNotifTitle').textContent = `✅ Gider: ${NOTIF_LABELS[notif.type]||notif.type}`;
  const street = notif.street_name;
  el('resolveNotifStreet').textContent = street ? `🛣 ${street}` : '';
  el('resolveNotifNote').value = '';
  el('resolvePhotoPreview').style.display = 'none';
  el('resolvePhotoInput').value = '';
  el('resolvePhotoBtn').className = 'photo-btn';
  el('resolvePhotoBtn').textContent = '📷 Fotoğraf Çek / Seç (isteğe bağlı)';
  openModal('resolveNotifModal');
}

el('resolvePhotoBtn').addEventListener('click', () => el('resolvePhotoInput').click());

el('resolvePhotoInput').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  S._resolvePhotoFile = file;
  el('resolvePhotoPreview').src = URL.createObjectURL(file);
  el('resolvePhotoPreview').style.display = 'block';
  el('resolvePhotoBtn').className = 'photo-btn has-photo';
  el('resolvePhotoBtn').textContent = '✅ Fotoğraf seçildi — değiştirmek için dokun';
});

el('resolveNotifCancelBtn').addEventListener('click', () => {
  S._resolvingNotif = null; S._resolvePhotoFile = null;
  closeModal('resolveNotifModal');
});

el('csNoteVoice').addEventListener('click', () => startVoice(el('csNote'), el('csNoteVoice')));
el('notifNoteVoice').addEventListener('click', () => startVoice(el('notifNote'), el('notifNoteVoice')));
el('resolveNoteVoice').addEventListener('click', () => startVoice(el('resolveNotifNote'), el('resolveNoteVoice')));

el('resolveNotifSaveBtn').addEventListener('click', async () => {
  const notif = S._resolvingNotif;
  if (!notif) return;
  el('resolveNotifSaveBtn').disabled = true;
  el('resolveNotifSaveBtn').textContent = 'Kaydediliyor…';

  const fd = new FormData();
  const note = el('resolveNotifNote').value.trim();
  if (note) fd.append('note', note);
  if (S._resolvePhotoFile) fd.append('photo', S._resolvePhotoFile, 'photo.jpg');

  try {
    const res = await fetch(`/api/notifications/${notif.id}/resolve`, {method:'POST', body:fd});
    if (res.status === 401) { location.href = '/login'; return; }
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw Error(d.error || 'Hata');

    const idx = S.notifications.findIndex(n => n.id === notif.id);
    if (idx !== -1) S.notifications[idx] = {...S.notifications[idx], status: 'resolved'};
    renderNotifMarkers(S.notifications.filter(n => n.status === 'open'));
    updateNotifBadge();

    S._resolvingNotif = null; S._resolvePhotoFile = null;
    closeModal('resolveNotifModal');
    toast('Bildirim giderildi ✅', 'success');

    if (el('sidePanel').classList.contains('open') && el('sidePanelTitle').textContent === 'Bildirim Havuzu') {
      renderNotifPool();
    }
  } catch(e) { toast(e.message, 'error'); }

  el('resolveNotifSaveBtn').disabled = false;
  el('resolveNotifSaveBtn').textContent = '✅ Giderildi Kaydet';
});

// ── Bildirim yorumları ────────────────────────────────────────────────────────
async function toggleComments(nid) {
  const section = el(`cs-${nid}`);
  if (!section) return;
  if (section.style.display !== 'none') { section.style.display = 'none'; return; }
  section.style.display = 'block';
  section.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:4px 0">Yükleniyor…</div>';
  try {
    const comments = await api(`/api/notifications/${nid}/comments`);
    let html = comments.length
      ? comments.map(c => `
          <div class="comment-row">
            <span class="cuser">${esc(c.user_name)}</span>
            <span style="flex:1">${esc(c.text)}</span>
            <span class="ctime">${timeAgo(c.created_at)}</span>
          </div>`).join('')
      : '<div style="color:var(--muted);font-size:12px;padding:4px 0">Henüz yorum yok</div>';
    html += `<div class="comment-add">
      <button class="cmt-voice" title="Sesli yorum">🎤</button>
      <input type="text" class="cmt-input" placeholder="Yorum ekle…" maxlength="300">
      <button class="cmt-send">Gönder</button>
    </div>`;
    section.innerHTML = html;

    const input = section.querySelector('.cmt-input');
    const send = section.querySelector('.cmt-send');
    const voiceBtn = section.querySelector('.cmt-voice');
    if (voiceBtn) voiceBtn.onclick = () => startVoice(input, voiceBtn);
    const doSend = async () => {
      const text = input.value.trim(); if (!text) return;
      send.disabled = true;
      try {
        await api(`/api/notifications/${nid}/comments`, {method:'POST', body:JSON.stringify({text})});
        input.value = '';
        section.style.display = 'none';
        toggleComments(nid);
      } catch(e) { toast(e.message, 'error'); }
      send.disabled = false;
    };
    send.onclick = doSend;
    input.addEventListener('keydown', e => { if (e.key === 'Enter') doSend(); });
  } catch(e) {
    section.innerHTML = `<div style="color:var(--red);font-size:12px">${e.message}</div>`;
  }
}

// ── Bildirim markerları ────────────────────────────────────────────────────────
const _notifMarkersByStreet = {};
const _notifMarkersById    = {};

function _clearNotifMarkers() {
  Object.values(_notifMarkersByStreet).forEach(m => S.map.removeLayer(m));
  Object.values(_notifMarkersById).forEach(m => S.map.removeLayer(m));
  Object.keys(_notifMarkersByStreet).forEach(k => delete _notifMarkersByStreet[k]);
  Object.keys(_notifMarkersById).forEach(k => delete _notifMarkersById[k]);
}

function renderNotifMarkers(notifications) {
  _clearNotifMarkers();

  const byStreet = {};
  for (const n of notifications) {
    if (n.street_id) {
      (byStreet[n.street_id] = byStreet[n.street_id] || []).push(n);
    } else {
      if (_notifMarkersById[n.id]) return;
      const icon = L.divIcon({
        html:`<div style="font-size:22px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))">⚠️</div>`,
        className:'',iconSize:[24,24],iconAnchor:[12,12]
      });
      const m = L.marker([n.lat, n.lon], {icon, zIndexOffset:500});
      m.bindPopup(`<b>${NOTIF_LABELS[n.type]||n.type}</b>${n.note?'<br>'+esc(n.note):''}`);
      m.addTo(S.map);
      _notifMarkersById[n.id] = m;
    }
  }

  for (const [streetId, notifs] of Object.entries(byStreet)) {
    const street = S.streets.find(s => s.id === Number(streetId));
    if (!street || !street.geometry || !street.geometry.length) continue;
    const mid = street.geometry[Math.floor(street.geometry.length / 2)];
    const cnt = notifs.length;
    const badge = cnt > 1
      ? `<span style="position:absolute;top:-5px;right:-8px;font-size:10px;background:#b91c1c;color:#fff;border-radius:8px;padding:0 4px">${cnt}</span>`
      : '';
    const icon = L.divIcon({
      html: `<div style="position:relative;font-size:22px;line-height:1;filter:drop-shadow(0 1px 3px rgba(0,0,0,.6))">⚠️${badge}</div>`,
      className: '', iconSize: [30, 30], iconAnchor: [15, 15]
    });
    const m = L.marker(mid, {icon, zIndexOffset: 600});
    m.on('click', () => {
      const s = S.streets.find(x => x.id === Number(streetId));
      if (s) openStreetDetail(s);
    });
    m.addTo(S.map);
    _notifMarkersByStreet[streetId] = m;
  }
}

// ── Yetkili: Personel İlerlemesi paneli ───────────────────────────────────────
async function openWorkersPanel() {
  if (!S.activeNb) { toast('Önce mahalle seçin'); return; }
  el('sidePanelTitle').textContent = '👥 Personel İlerlemesi';
  el('sidePanelBody').innerHTML = '<p style="padding:12px;color:var(--muted)">Yükleniyor…</p>';
  el('sidePanel').classList.add('open');

  try {
    const workers = await api(`/api/neighborhoods/${S.activeNb.id}/workers?date=${todayStr()}`);
    if (!workers.length) {
      el('sidePanelBody').innerHTML = '<p style="padding:12px;color:var(--muted)">Bugün atanmış sahada personel yok</p>';
      return;
    }

    // Son yenileme zamanı
    const now = new Date().toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit'});
    el('sidePanelBody').innerHTML = `
      <div style="padding:6px 8px 2px;font-size:11px;color:var(--muted);text-align:right">Son güncelleme: ${now}</div>
    ` + workers.map(w => `
      <div class="personnel-row" style="flex-direction:column;align-items:stretch;gap:6px;padding:12px 8px">
        <div style="display:flex;align-items:center;gap:8px">
          <div style="flex:1;min-width:0">
            <div class="pname">${esc(w.display_name)}</div>
            <div class="prole">${ROLE_NAMES[w.role]||w.role} — ${w.completed}/${w.assigned} sokak</div>
          </div>
          <span style="font-size:14px;font-weight:700;color:${w.pct===100?'var(--green)':w.pct>50?'var(--yellow)':'var(--red)'};">${w.pct}%</span>
          <button data-track-uid="${w.id}" data-track-name="${esc(w.display_name)}"
            style="font-size:11px;padding:6px 10px;border-radius:6px;border:1px solid var(--blue);background:var(--blue);color:#fff;flex-shrink:0">📍 Gör</button>
        </div>
        <div style="height:8px;background:var(--bg);border-radius:4px;overflow:hidden;border:1px solid var(--border)">
          <div style="height:100%;width:${w.pct}%;background:${w.pct===100?'var(--green)':w.pct>50?'var(--yellow)':'var(--red)'};transition:width .4s;border-radius:4px"></div>
        </div>
      </div>
    `).join('');

    el('sidePanelBody').querySelectorAll('[data-track-uid]').forEach(btn => {
      btn.onclick = () => {
        el('sidePanel').classList.remove('open');
        viewWorkerStreets(Number(btn.dataset.trackUid), btn.dataset.trackName);
      };
    });
  } catch(e) {
    el('sidePanelBody').innerHTML = `<p style="color:var(--red);padding:12px">${e.message}</p>`;
  }
}

// ── Yetkili: Günlük özet paneli ───────────────────────────────────────────────
async function openDailySummary() {
  if (!S.activeNb) { toast('Önce mahalle seçin'); return; }
  const dateStr = todayStr();
  el('sidePanelTitle').textContent = `📊 Günlük Özet`;
  el('sidePanelBody').innerHTML = '<p style="padding:12px;color:var(--muted)">Yükleniyor…</p>';
  el('sidePanel').classList.add('open');

  try {
    const summary = await api(`/api/neighborhoods/${S.activeNb.id}/summary?date=${dateStr}`);
    let html = `
      <div style="padding:12px;border-bottom:1px solid var(--border)">
        <div style="font-size:11px;color:var(--muted);margin-bottom:2px">${S.activeNb.name} — ${dateStr}</div>
        <div style="display:flex;gap:16px;margin-top:8px">
          <div style="text-align:center;flex:1">
            <div style="font-size:24px;font-weight:700">${summary.total_streets}</div>
            <div style="font-size:11px;color:var(--muted)">Toplam sokak</div>
          </div>
          <div style="text-align:center;flex:1">
            <div style="font-size:24px;font-weight:700;color:var(--green)">${summary.completed_by_worker.reduce((s,w)=>s+w.cnt,0)}</div>
            <div style="font-size:11px;color:var(--muted)">Tamamlanan</div>
          </div>
          <div style="text-align:center;flex:1">
            <div style="font-size:24px;font-weight:700;color:${summary.open_notifications>0?'var(--red)':'var(--green)'}">${summary.open_notifications}</div>
            <div style="font-size:11px;color:var(--muted)">Açık bildirim</div>
          </div>
        </div>
      </div>
    `;

    if (summary.assigned_by_type.length) {
      html += `<div style="padding:12px;border-bottom:1px solid var(--border)">
        <div class="sd-label" style="margin-bottom:8px">Ekip Atamaları</div>`;
      summary.assigned_by_type.forEach(a => {
        html += `<div style="display:flex;justify-content:space-between;font-size:13px;padding:4px 0;border-bottom:1px solid rgba(48,54,61,.4)">
          <span>${ROLE_NAMES[a.team_type]||a.team_type}</span>
          <b>${a.cnt} sokak</b>
        </div>`;
      });
      html += `</div>`;
    }

    if (summary.completed_by_worker.length) {
      html += `<div style="padding:12px">
        <div class="sd-label" style="margin-bottom:8px">Bugün Tamamlayanlar</div>`;
      summary.completed_by_worker.forEach(w => {
        html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid rgba(48,54,61,.4)">
          <div>
            <div style="font-size:13px;font-weight:700">${esc(w.display_name)}</div>
            <div style="font-size:11px;color:var(--muted)">${ROLE_NAMES[w.role]||w.role}</div>
          </div>
          <div style="text-align:right">
            <div style="font-size:16px;font-weight:700;color:var(--green)">${w.cnt} sokak</div>
            <div style="font-size:11px;color:var(--muted)">son: ${timeAgo(w.last_at)}</div>
          </div>
        </div>`;
      });
      html += `</div>`;
    } else {
      html += `<div style="padding:12px;color:var(--muted);font-size:13px;text-align:center">Bugün henüz tamamlanan sokak yok</div>`;
    }

    el('sidePanelBody').innerHTML = html;
  } catch(e) {
    el('sidePanelBody').innerHTML = `<p style="color:var(--red);padding:12px">${e.message}</p>`;
  }
}

// ── Menü ──────────────────────────────────────────────────────────────────────
el('menuBtn').addEventListener('click', async () => {
  const sel = el('nbSelect');
  sel.innerHTML = '<option value="">— Mahalle seç —</option>';
  for (const nb of S.neighborhoods) {
    const opt = document.createElement('option');
    opt.value = nb.id; opt.textContent = nb.name;
    if (S.activeNb && nb.id === S.activeNb.id) opt.selected = true;
    sel.appendChild(opt);
  }

  const section = el('menuRoleSection');
  if (!SUPERVISOR_ROLES.has(S.user.role)) {
    section.innerHTML = S.neighborhoods.length
      ? `<p style="font-size:12px;color:var(--muted);margin-top:10px">📍 Görev mahalleniz amiriniz tarafından atanır. Listedeki mahalle(ler) bugünkü atamalarınızı gösterir.</p>`
      : `<p style="font-size:12px;color:var(--red);margin-top:10px">⚠️ Bugün atanmış güzergah yok. Amirinizle iletişime geçin.</p>`;
  } else {
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
      <button id="openAssignBtn" style="width:100%;padding:10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--panel2);color:var(--text);font-size:13px;font-weight:600;margin-bottom:6px">📋 Güzergah Ata</button>
      <button id="openPersonnelBtn" style="width:100%;padding:10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--panel2);color:var(--text);font-size:13px;font-weight:600;margin-bottom:6px">👥 Personel Yönetimi</button>
      <button id="openWorkersBtn" style="width:100%;padding:10px;border-radius:var(--radius-sm);border:1px solid var(--blue);background:var(--blue);color:#fff;font-size:13px;font-weight:600;margin-bottom:6px">📍 Personel İlerlemesi</button>
      <button id="openSummaryBtn" style="width:100%;padding:10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--panel2);color:var(--text);font-size:13px;font-weight:600">📊 Günlük Özet</button>`;

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
        if (res.street_fetch_error) {
          toast(res.street_fetch_error, 'error', 8000);
        } else {
          toast(`${mahalle} eklendi — ${res.street_count || 0} sokak ✅`, 'success', 5000);
        }
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
        if (!S.activeNb) {
          const newNb = S.neighborhoods.find(n => n.name === res.name || n.id === res.id);
          if (newNb) { closeModal('menuModal'); loadNeighborhood(newNb); return; }
        }
      } catch(e) { toast(e.message, 'error'); }
      el('addNbBtn').disabled = false;
      el('addNbBtn').textContent = '+ Mahalle Ekle';
    };

    el('openAssignBtn').onclick = () => { closeModal('menuModal'); openAssignPanel(); };
    el('openPersonnelBtn').onclick = () => { closeModal('menuModal'); openPersonnelPanel(); };
    el('openWorkersBtn').onclick = () => { closeModal('menuModal'); openWorkersPanel(); };
    el('openSummaryBtn').onclick = () => { closeModal('menuModal'); openDailySummary(); };
  }

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
  el('assignBarCount').textContent = '0';

  el('assignPermanent').checked = false;
  el('assignDateSection').style.display = '';

  el('assignPermanent').onchange = () => {
    el('assignDateSection').style.display = el('assignPermanent').checked ? 'none' : '';
  };

  el('assignDate').value = todayStr();

  try {
    const shifts = await api(`/api/shifts?district_id=${S.user.district_id}`);
    const sel = el('assignShift');
    sel.innerHTML = '<option value="">— Tüm gün —</option>';
    shifts.forEach(sh => {
      const o = document.createElement('option'); o.value = sh.id; o.textContent = sh.display_name; sel.appendChild(o);
    });
  } catch(e) {}

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

  renderStreets(S.streets.map(s => ({...s, completed: false})));
  openModal('assignModal');
}

el('assignCancelBtn').addEventListener('click', () => { _exitAssignMode(); });
el('assignMapBtn').addEventListener('click', () => { _enterAssignSelectMode('map'); });
el('assignListBtn').addEventListener('click', () => { _enterAssignSelectMode('list'); });

// ── Atama çubuğu ─────────────────────────────────────────────────────────────
function _enterAssignSelectMode(mode) {
  S._assignConfig = {
    permanent: el('assignPermanent').checked,
    work_date: el('assignDate').value || todayStr(),
    team_type: el('assignTeamType').value,
    shift_id: el('assignShift').value || null,
    assigned_user_id: el('assignUser').value || null,
  };
  closeModal('assignModal');
  el('bottombar').style.display = 'none';
  el('assignBar').style.display = 'flex';
  const roleLabels = {'supurgeci':'Yaya Süpürgeci','aracli_supurge':'Araçlı Süpürge','cop_araci':'Çöp Aracı','ring_araci':'Ring Aracı','kaba_atik':'Kaba Atık','konteyner_yikama':'Kont. Yıkama'};
  el('assignBarTeam').textContent = roleLabels[S._assignConfig.team_type] || S._assignConfig.team_type;
  _updateAssignCount();
  if (mode === 'list') _openAssignList();
}

function _exitAssignMode() {
  S.mode = 'normal'; S.assignSelected.clear();
  el('assignBar').style.display = 'none';
  el('bottombar').style.display = 'flex';
  el('sidePanel').classList.remove('open');
  closeModal('assignModal');
  loadNeighborhood(S.activeNb);
}

function _openAssignList(filter) {
  el('sidePanelTitle').textContent = 'Sokak Seçimi';
  const body = el('sidePanelBody');
  const q = (filter || '').toLowerCase();
  const sorted = [...S.streets].sort((a,b) => a.name.localeCompare(b.name, 'tr'));
  const filtered = q ? sorted.filter(s => s.name.toLowerCase().includes(q)) : sorted;

  body.innerHTML = `
    <div style="padding:8px 8px 4px">
      <input id="assignSearch" type="text" placeholder="Sokak ara…" value="${esc(filter||'')}"
        style="width:100%;padding:8px 10px;border-radius:var(--radius-sm);border:1px solid var(--border);
        background:var(--bg);color:var(--text);font-size:14px;font-family:inherit">
    </div>
  ` + filtered.map(s => `
    <label class="street-row" style="cursor:pointer;gap:10px">
      <input type="checkbox" data-assign-street="${s.id}" ${S.assignSelected.has(s.id) ? 'checked' : ''}
        style="width:18px;height:18px;accent-color:var(--blue);flex-shrink:0">
      <span class="sname">${esc(s.name)}</span>
    </label>
  `).join('');

  const searchEl = body.querySelector('#assignSearch');
  if (searchEl) {
    searchEl.addEventListener('input', () => _openAssignList(searchEl.value));
    if (filter) searchEl.focus();
  }

  body.querySelectorAll('[data-assign-street]').forEach(cb => {
    cb.onchange = () => {
      const sid = +cb.dataset.assignStreet;
      if (cb.checked) S.assignSelected.add(sid);
      else S.assignSelected.delete(sid);
      const lr = S.streetLayers[sid];
      if (lr) lr.vis.setStyle(streetColor(S.streets.find(s => s.id === sid) || {id:sid}));
      _updateAssignCount();
    };
  });
  el('sidePanel').classList.add('open');
}

el('assignBarBackBtn').addEventListener('click', () => {
  el('sidePanel').classList.remove('open');
  el('assignBar').style.display = 'none';
  el('bottombar').style.display = 'flex';
  openModal('assignModal');
});

el('assignBarListBtn').addEventListener('click', () => {
  if (el('sidePanel').classList.contains('open') && el('sidePanelTitle').textContent === 'Sokak Seçimi') {
    el('sidePanel').classList.remove('open');
  } else {
    _openAssignList();
  }
});

el('assignBarAllBtn').addEventListener('click', () => {
  S.streets.forEach(s => { S.assignSelected.add(s.id); const lr = S.streetLayers[s.id]; if (lr) lr.vis.setStyle(streetColor(s)); });
  _updateAssignCount();
});

el('assignBarClearBtn').addEventListener('click', () => {
  S.assignSelected.clear();
  S.streets.forEach(s => { const lr = S.streetLayers[s.id]; if (lr) lr.vis.setStyle(streetColor(s)); });
  _updateAssignCount();
});

el('assignBarSaveBtn').addEventListener('click', async () => {
  if (!S.assignSelected.size) { toast('Hiç sokak seçilmedi', 'error'); return; }
  const cfg = S._assignConfig || {};
  const payload = {
    neighborhood_id: S.activeNb.id,
    team_type: cfg.team_type,
    shift_id: cfg.shift_id,
    permanent: cfg.permanent,
    work_date: cfg.permanent ? null : cfg.work_date,
    street_ids: [...S.assignSelected],
    assigned_user_id: cfg.assigned_user_id,
  };
  el('assignBarSaveBtn').disabled = true;
  el('assignBarSaveBtn').textContent = 'Kaydediliyor…';
  try {
    const res = await api('/api/assignments', {method:'POST', body:JSON.stringify(payload)});
    toast(`${res.street_count} sokak atandı ✅`, 'success');
    _exitAssignMode();
  } catch(e) {
    toast(e.message, 'error');
    el('assignBarSaveBtn').disabled = false;
    el('assignBarSaveBtn').textContent = '✅ Kaydet';
  }
});

// ── Personel yönetimi ─────────────────────────────────────────────────────────
async function viewWorkerStreets(uid, name) {
  if (!S.activeNb) { toast('Önce mahalle seçin', 'error'); return; }
  toast(`${name} sokakları yükleniyor…`);
  try {
    const data = await api(`/api/workers/${uid}/streets?neighborhood_id=${S.activeNb.id}&date=${todayStr()}`);
    if (!data.streets.length) { toast(`${name} için bugün atanmış sokak yok`, '', 4000); return; }
    renderStreets(data.streets);
    fitMapToStreets(data.streets);
    el('nbTitle').textContent = `👁 ${name}`;
    const done = data.streets.filter(s=>s.completed).length;
    el('progressLabel').textContent = `${done} / ${data.streets.length} tamamlandı`;
    toast(`${name} — ${data.streets.length} sokak gösteriliyor`, 'success', 3000);
  } catch(e) { toast(e.message, 'error'); }
}

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
        ${!SUPERVISOR_ROLES.has(u.role) ? `<button data-track-uid="${u.id}" data-track-name="${esc(u.display_name)}" style="background:var(--blue);border-color:var(--blue);color:#fff">📍</button>` : ''}
        <button data-edit-uid="${u.id}">Düzenle</button>
      </div>
    `).join('');
    list.querySelectorAll('[data-edit-uid]').forEach(btn => {
      const uid = Number(btn.dataset.editUid);
      const u = users.find(x => x.id === uid);
      btn.onclick = () => openEditPersonnel(u);
    });
    list.querySelectorAll('[data-track-uid]').forEach(btn => {
      btn.onclick = () => {
        closeModal('personnelModal');
        viewWorkerStreets(Number(btn.dataset.trackUid), btn.dataset.trackName);
      };
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
  const isSup = user ? SUPERVISOR_ROLES.has(user.role) : false;
  el('epNotifSweepRow').style.display = isSup ? '' : 'none';
  el('epNotifSweep').checked = user ? (user.notify_sweep !== 0 && user.notify_sweep !== '0') : true;
  el('epRole').onchange = () => {
    el('epNotifSweepRow').style.display = SUPERVISOR_ROLES.has(el('epRole').value) ? '' : 'none';
  };

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
    notify_sweep: SUPERVISOR_ROLES.has(el('epRole').value) ? (el('epNotifSweep').checked ? 1 : 0) : 1,
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

document.querySelectorAll('.modal-overlay').forEach(ov => {
  ov.addEventListener('click', e => { if (e.target === ov) closeModal(ov.id); });
});

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
  try {
    initMap();
  } catch(e) {
    await new Promise(r => setTimeout(r, 200));
    try { initMap(); } catch(e2) { toast('Harita yüklenemedi. Sayfayı yenileyin.', 'error'); return; }
  }
  setTimeout(() => S.map && S.map.invalidateSize(), 300);
  _setupDeviceOrientation();

  // Çevrimdışı kuyruğu kontrol et
  if (navigator.onLine) syncOfflineQueue().catch(()=>{});

  try {
    const data = await api('/api/me');
    S.user = data.user;
    S.neighborhoods = data.neighborhoods;

    const lastId = localStorage.getItem('lastNbId');
    const nb = lastId && S.neighborhoods.find(n => n.id === Number(lastId))
                || S.neighborhoods[0];
    if (nb) await loadNeighborhood(nb);
    else if (SUPERVISOR_ROLES.has(S.user.role)) toast('Menüden mahalle seçin ☰');
    else toast('Bugün atanmış güzergah yok. Amirle iletişime geçin.', 'error', 7000);

    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(()=>{});
  } catch(e) {
    if (e.message !== 'giris gerekli') toast(e.message, 'error');
  }
}

document.addEventListener('DOMContentLoaded', init);
})();
