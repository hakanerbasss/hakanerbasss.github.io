let currentDocId = null;

function toast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast' + (type ? ' ' + type : '');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

async function api(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) { location.href = '/admin/login'; throw new Error('giris_gerekli'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Hata');
  return data;
}

function esc(s) {
  return (s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleString('tr-TR');
}

// ── Ayarlar ──
async function loadSettings() {
  try {
    const d = await api('/api/admin/settings');
    document.getElementById('keyStatus').textContent = d.deepseek_api_key_set
      ? `(kayıtlı: ${d.deepseek_api_key_masked})` : '(henüz girilmedi)';
    document.getElementById('modelName').value = d.deepseek_model || 'deepseek-chat';
  } catch (e) {}
}

document.getElementById('saveSettingsBtn').addEventListener('click', async () => {
  const apiKey = document.getElementById('apiKey').value.trim();
  const modelName = document.getElementById('modelName').value.trim();
  try {
    await api('/api/admin/settings', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({deepseek_api_key: apiKey, deepseek_model: modelName})
    });
    document.getElementById('apiKey').value = '';
    toast('Ayarlar kaydedildi ✅', 'success');
    loadSettings();
  } catch (e) { toast(e.message, 'error'); }
});

// ── Belgeler ──
async function loadDocuments() {
  const list = document.getElementById('docList');
  try {
    const docs = await api('/api/admin/documents');
    if (!docs.length) {
      list.innerHTML = '<p style="color:var(--muted);font-size:13px">Henüz belge yüklenmedi.</p>';
      return;
    }
    list.innerHTML = docs.map(d => `
      <div class="doc-row">
        <div style="flex:1">
          <div class="dtitle">${esc(d.title)} ${d.is_active ? '⭐' : ''}</div>
          <div class="dmeta">${d.page_count} sayfa · ${fmtDate(d.created_at)}</div>
        </div>
        <span class="status-badge ${d.status}">${
          d.status === 'ready' ? 'Hazır' : d.status === 'processing' ? 'İşleniyor' : 'Hata'
        }</span>
        <button class="btn" onclick="viewPages(${d.id}, '${esc(d.title).replace(/'/g, "\\'")}')">Sayfalar</button>
        ${d.status === 'ready' && !d.is_active
          ? `<button class="btn primary" onclick="activateDoc(${d.id})">Aktif Yap</button>` : ''}
        <button class="btn danger" onclick="deleteDoc(${d.id})">Sil</button>
      </div>
    `).join('');

    if (docs.some(d => d.status === 'processing')) {
      setTimeout(loadDocuments, 3000);
    }
  } catch (e) {
    list.innerHTML = `<p style="color:var(--red);font-size:13px">${e.message}</p>`;
  }
}

async function activateDoc(id) {
  try {
    await api(`/api/admin/documents/${id}/activate`, {method: 'POST'});
    toast('Belge aktif edildi ✅', 'success');
    loadDocuments();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteDoc(id) {
  if (!confirm('Bu belgeyi ve tüm sayfalarını silmek istediğinize emin misiniz?')) return;
  try {
    await api(`/api/admin/documents/${id}`, {method: 'DELETE'});
    toast('Belge silindi', 'success');
    if (currentDocId === id) document.getElementById('pagesSection').style.display = 'none';
    loadDocuments();
  } catch (e) { toast(e.message, 'error'); }
}

document.getElementById('uploadBtn').addEventListener('click', async () => {
  const title = document.getElementById('uploadTitle').value.trim();
  const file = document.getElementById('uploadFile').files[0];
  const status = document.getElementById('uploadStatus');
  if (!file) { toast('PDF dosyası seçin', 'error'); return; }

  const fd = new FormData();
  fd.append('title', title);
  fd.append('file', file);

  document.getElementById('uploadBtn').disabled = true;
  status.textContent = 'Yükleniyor ve OCR ile işleniyor… bu birkaç dakika sürebilir.';
  try {
    await api('/api/admin/documents', {method: 'POST', body: fd});
    status.textContent = 'Yüklendi — arka planda işleniyor, aşağıdaki listeden takip edin.';
    document.getElementById('uploadTitle').value = '';
    document.getElementById('uploadFile').value = '';
    loadDocuments();
  } catch (e) {
    status.textContent = '';
    toast(e.message, 'error');
  }
  document.getElementById('uploadBtn').disabled = false;
});

// ── Sayfalar ──
async function viewPages(id, title) {
  currentDocId = id;
  document.getElementById('pagesSection').style.display = 'block';
  document.getElementById('pagesDocTitle').textContent = title;
  document.getElementById('pagesSection').scrollIntoView({behavior: 'smooth'});
  await renderPages();
}

async function renderPages() {
  const container = document.getElementById('pagesList');
  container.innerHTML = '<p style="color:var(--muted);font-size:13px">Yükleniyor…</p>';
  try {
    const d = await api(`/api/admin/documents/${currentDocId}`);
    if (!d.pages.length) {
      container.innerHTML = '<p style="color:var(--muted);font-size:13px">Henüz sayfa yok.</p>';
      return;
    }
    container.innerHTML = d.pages.map(p => `
      <div class="page-edit" data-page-id="${p.id}">
        <div class="prow">
          <span>Sayfa ${p.page_number}</span>
          <button class="btn danger" style="padding:4px 9px;font-size:11px" onclick="deletePage(${p.id})">Sil</button>
        </div>
        <textarea data-page-id="${p.id}">${esc(p.text || '')}</textarea>
        <button class="btn" style="margin-top:6px" onclick="savePage(${p.id})">Metni Kaydet</button>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = `<p style="color:var(--red);font-size:13px">${e.message}</p>`;
  }
}

async function savePage(pageId) {
  const textarea = document.querySelector(`textarea[data-page-id="${pageId}"]`);
  try {
    await api(`/api/admin/pages/${pageId}`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: textarea.value})
    });
    toast('Sayfa metni kaydedildi ✅', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

async function deletePage(pageId) {
  if (!confirm('Bu sayfayı silmek istediğinize emin misiniz?')) return;
  try {
    await api(`/api/admin/pages/${pageId}`, {method: 'DELETE'});
    toast('Sayfa silindi', 'success');
    renderPages();
    loadDocuments();
  } catch (e) { toast(e.message, 'error'); }
}

document.getElementById('addPageBtn').addEventListener('click', async () => {
  const file = document.getElementById('addPageFile').files[0];
  if (!file || !currentDocId) { toast('Görsel seçin', 'error'); return; }
  const fd = new FormData();
  fd.append('file', file);
  try {
    await api(`/api/admin/documents/${currentDocId}/pages`, {method: 'POST', body: fd});
    document.getElementById('addPageFile').value = '';
    toast('Sayfa eklendi ✅', 'success');
    renderPages();
    loadDocuments();
  } catch (e) { toast(e.message, 'error'); }
});

document.getElementById('logoutBtn').addEventListener('click', async () => {
  await fetch('/api/admin/logout', {method: 'POST'});
  location.href = '/admin/login';
});

loadSettings();
loadDocuments();
