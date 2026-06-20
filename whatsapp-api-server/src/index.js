// src/index.js
require('dotenv').config();
const express = require('express');
const cors = require('cors');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');
const path = require('path');
const db = require('./database');
const wa = require('./whatsapp');

const app = express();
const PORT = process.env.PORT || 3000;
const JWT_SECRET = process.env.JWT_SECRET || 'whatsapp-api-secret-2024';

app.use(cors());
app.use(express.json());

// ── HTTP BASIC AUTH ───────────────────────────────────────────────
// Panel şifresi .env'den veya varsayılan
const PANEL_USER = process.env.PANEL_USER || 'admin';
const PANEL_PASS = process.env.PANEL_PASS || null; // Şifre yoksa devre dışı

app.use((req, res, next) => {
  // API isteklerini atla (token ile korunuyor)
  if (req.path.startsWith('/api/')) return next();
  // Müşteri sayfalarını atla
  if (req.path === '/kayit' || req.path === '/musteri') return next();
  // Panel şifresi ayarlanmamışsa atla
  if (!PANEL_PASS) return next();

  const auth = req.headers.authorization;
  if (!auth || !auth.startsWith('Basic ')) {
    res.set('WWW-Authenticate', 'Basic realm="WhatsApp API Panel"');
    return res.status(401).send('Erişim için şifre gerekli');
  }
  const [user, pass] = Buffer.from(auth.slice(6), 'base64').toString().split(':');
  if (user !== PANEL_USER || pass !== PANEL_PASS) {
    res.set('WWW-Authenticate', 'Basic realm="WhatsApp API Panel"');
    return res.status(401).send('Kullanıcı adı veya şifre hatalı');
  }
  next();
});

app.use(express.static(path.join(__dirname, '../panel')));

// ── RATE LIMIT ────────────────────────────────────────────────────
// Token başına: saniyede max 2 istek
const tokenRateMap = {};
// Sunucu geneli: saniyede max 10 istek (IP koruması)
const serverRateLog = [];

function rateLimit(req, res, next) {
  const now = Date.now();

  // 1. Sunucu geneli kontrol
  const recentServer = serverRateLog.filter(t => now - t < 1000);
  serverRateLog.length = 0;
  recentServer.forEach(t => serverRateLog.push(t));
  if (serverRateLog.length >= 10) {
    return res.status(429).json({
      error: 'Sunucu yoğun, lütfen biraz bekleyin.',
      retry_after: 1
    });
  }
  serverRateLog.push(now);

  // 2. Token başına kontrol
  if (req.customer) {
    const id = req.customer.id;
    if (!tokenRateMap[id]) tokenRateMap[id] = [];
    tokenRateMap[id] = tokenRateMap[id].filter(t => now - t < 3000);
    if (tokenRateMap[id].length >= 1) {
      return res.status(429).json({
        error: 'Çok hızlı istek. Her 3 saniyede maksimum 1 mesaj gönderebilirsiniz.',
        retry_after: 3
      });
    }
    tokenRateMap[id].push(now);
  }

  next();
}

// ── MIDDLEWARE ────────────────────────────────────────────────────
function adminAuth(req, res, next) {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) return res.status(401).json({ error: 'Token gerekli' });
  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    if (decoded.role !== 'admin') throw new Error();
    req.admin = decoded;
    next();
  } catch(e) {
    res.status(401).json({ error: 'Geçersiz token' });
  }
}

function customerAuth(req, res, next) {
  const token = req.headers['x-api-token'] || req.query.token;
  if (!token) return res.status(401).json({ error: 'API token gerekli' });
  const customer = db.getCustomerByToken(token);
  if (!customer) return res.status(401).json({ error: 'Geçersiz token' });
  if (customer.status !== 'active') return res.status(403).json({ error: 'Hesabınız askıya alınmış' });
  if (customer.expires_at && new Date(customer.expires_at) < new Date()) {
    return res.status(403).json({ error: 'Aboneliğiniz sona erdi' });
  }
  req.customer = customer;
  next();
}

// Dashboard için — süresi dolsa da giriş izni verir
function customerAuthDashboard(req, res, next) {
  const token = req.headers['x-api-token'] || req.query.token;
  if (!token) return res.status(401).json({ error: 'API token gerekli' });
  const customer = db.getCustomerByToken(token);
  if (!customer) return res.status(401).json({ error: 'Geçersiz token' });
  req.customer = customer;
  next();
}

// ═══════════════════════════════════════════════════════════════
// ADMIN API
// ═══════════════════════════════════════════════════════════════

// Setup — ilk kurulum
app.post('/api/setup', async (req, res) => {
  if (db.adminExists()) return res.status(400).json({ error: 'Kurulum zaten tamamlandı' });
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: 'Kullanıcı adı ve şifre gerekli' });
  db.createAdmin(username, password);
  res.json({ ok: true, message: 'Admin hesabı oluşturuldu' });
});

// Admin login
app.post('/api/admin/login', (req, res) => {
  const { username, password } = req.body;
  const admin = db.getAdmin(username);
  if (!admin || !bcrypt.compareSync(password, admin.password)) {
    return res.status(401).json({ error: 'Kullanıcı adı veya şifre hatalı' });
  }
  const token = jwt.sign({ id: admin.id, username, role: 'admin' }, JWT_SECRET, { expiresIn: '7d' });
  res.json({ ok: true, token });
});

// Dashboard istatistikleri
app.get('/api/admin/stats', adminAuth, (req, res) => {
  res.json(db.getStats());
});

// Müşteri listesi
app.get('/api/admin/customers', adminAuth, (req, res) => {
  res.json(db.getCustomers());
});

// Müşteri ekle
app.post('/api/admin/customers', adminAuth, (req, res) => {
  const customer = db.createCustomer(req.body);
  res.json({ ok: true, customer });
});

// Müşteri güncelle
app.put('/api/admin/customers/:id', adminAuth, (req, res) => {
  db.updateCustomer(req.params.id, req.body);
  res.json({ ok: true });
});

// Müşteri sil
app.delete('/api/admin/customers/:id', adminAuth, async (req, res) => {
  await wa.disconnectCustomer(req.params.id).catch(() => {});
  db.deleteCustomer(req.params.id);
  res.json({ ok: true });
});

// Müşteri dondur/aktifleştir
app.post('/api/admin/customers/:id/toggle', adminAuth, (req, res) => {
  const customer = db.getCustomerById(req.params.id);
  const newStatus = customer.status === 'active' ? 'suspended' : 'active';
  db.toggleCustomer(req.params.id, newStatus);
  res.json({ ok: true, status: newStatus });
});

// Token yenile
app.post('/api/admin/customers/:id/reset-token', adminAuth, (req, res) => {
  const { v4: uuidv4 } = require('uuid');
  const newToken = uuidv4().replace(/-/g, '');
  db.updateCustomer(req.params.id, { token: newToken });
  res.json({ ok: true, token: newToken });
});

// Admin — WhatsApp bağlantı başlat
app.post('/api/admin/customers/:id/connect', adminAuth, async (req, res) => {
  const { method } = req.body; // qr | pairing | phone_code
  const result = await wa.startConnection(req.params.id, method || 'qr');
  res.json(result);
});

// Admin — WhatsApp bağlantı kes
app.post('/api/admin/customers/:id/disconnect', adminAuth, async (req, res) => {
  await wa.disconnectCustomer(req.params.id);
  res.json({ ok: true });
});

// Admin — bağlantı durumu
app.get('/api/admin/customers/:id/status', adminAuth, (req, res) => {
  res.json(wa.getStatus(req.params.id));
});

app.get('/api/admin/customers/:id/events', (req, res) => {
  // EventSource header gönderemez, query param kullan
  const token = req.headers.authorization?.split(' ')[1] || req.query.token;
  if (!token) return res.status(401).end();
  try { jwt.verify(token, JWT_SECRET); } catch(e) { return res.status(401).end(); }

  const customerId = parseInt(req.params.id);
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (data) => {
    res.write(`data: ${JSON.stringify(data)}\n\n`);
    if (res.flush) res.flush();
  };

  // Mevcut durumu hemen gönder
  send({ type: 'status', ...wa.getStatus(customerId) });

  const onQR      = (d) => send({ type: 'qr', ...d });
  const onStatus  = (d) => send({ type: 'status', ...d });
  const onPairing = (d) => send({ type: 'pairing', ...d });

  wa.waEvents.on(`qr_${customerId}`, onQR);
  wa.waEvents.on(`status_${customerId}`, onStatus);
  wa.waEvents.on(`pairing_${customerId}`, onPairing);

  // Keepalive ping
  const ping = setInterval(() => res.write(': ping\n\n'), 15000);

  req.on('close', () => {
    clearInterval(ping);
    wa.waEvents.off(`qr_${customerId}`, onQR);
    wa.waEvents.off(`status_${customerId}`, onStatus);
    wa.waEvents.off(`pairing_${customerId}`, onPairing);
  });
});

// ═══════════════════════════════════════════════════════════════
// PUBLIC API (auth yok)
// ═══════════════════════════════════════════════════════════════

// Paketleri herkese açık döndür — waport.wizaicorp.com buradan okur
app.get('/api/public/packages', (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  const packages = JSON.parse(db.getSetting('packages') || JSON.stringify([
    { id: 'basic',     name: 'Basic',     limit: 100,  price: '150₺/ay', desc: 'Küçük işletmeler için' },
    { id: 'pro',       name: 'Pro',       limit: 500,  price: '300₺/ay', desc: 'Büyüyen işletmeler için' },
    { id: 'unlimited', name: 'Unlimited', limit: 9999, price: '500₺/ay', desc: 'Sınırsız kullanım' },
  ]));
  res.json(packages);
});

// ═══════════════════════════════════════════════════════════════
// AYARLAR API
// ═══════════════════════════════════════════════════════════════

// Ayarları getir
app.get('/api/admin/settings', adminAuth, (req, res) => {
  res.json({
    contact_phone:   db.getSetting('contact_phone') || '',
    contact_email:   db.getSetting('contact_email') || '',
    contact_message: db.getSetting('contact_message') || 'Mesaj limitinize ulaştınız. Devam etmek için iletişime geçin.',
    packages: JSON.parse(db.getSetting('packages') || JSON.stringify([
      { id: 'basic',     name: 'Basic',     limit: 100,  price: '150₺/ay', desc: 'Küçük işletmeler için' },
      { id: 'pro',       name: 'Pro',       limit: 500,  price: '300₺/ay', desc: 'Büyüyen işletmeler için' },
      { id: 'unlimited', name: 'Unlimited', limit: 9999, price: '500₺/ay', desc: 'Sınırsız kullanım' },
    ]))
  });
});

// Ayarları kaydet
app.post('/api/admin/settings', adminAuth, (req, res) => {
  const { contact_phone, contact_email, contact_message, packages } = req.body;
  if (contact_phone   !== undefined) db.setSetting('contact_phone',   contact_phone);
  if (contact_email   !== undefined) db.setSetting('contact_email',   contact_email);
  if (contact_message !== undefined) db.setSetting('contact_message', contact_message);
  if (packages        !== undefined) db.setSetting('packages', JSON.stringify(packages));
  res.json({ ok: true });
});

// ── KARA LİSTE API ───────────────────────────────────────────────
app.get('/api/admin/blacklist', adminAuth, (req, res) => {
  const q = req.query.q;
  res.json(q ? db.searchBlacklist(q) : db.getBlacklist());
});

app.delete('/api/admin/blacklist/:id', adminAuth, (req, res) => {
  db.removeBlacklist(req.params.id);
  res.json({ ok: true });
});

app.post('/api/admin/blacklist', adminAuth, (req, res) => {
  const { phone, name, reason } = req.body;
  if (!phone) return res.status(400).json({ error: 'Telefon gerekli' });
  db.addBlacklist(phone.replace(/\D/g,''), name || '', reason || 'manual');
  res.json({ ok: true });
});
// Admin iletişim WhatsApp'ını bul
function getAdminWaConn() {
  const contactPhone = db.getSetting('contact_phone')?.replace(/\D/g, '');
  if (!contactPhone) return null;
  const customers = db.getCustomers();
  return customers.find(c => c.wa_status === 'connected' && c.wa_number === contactPhone);
}

// Kota dolduğunda admin + müşteriye bildirim gönder (günde 1 kez)
async function notifyLimitExceeded(customer) {
  try {
    if (!db.isFirstLimitExceed(customer.id)) return;
    const adminConn = getAdminWaConn();
    if (!adminConn) return;
    const contactPhone = db.getSetting('contact_phone')?.replace(/\D/g, '');
    const baseUrl = db.getSetting('base_url') || 'https://wa.wizaicorp.com';
    const isDemo = customer.plan === 'demo';
    const planLabel = isDemo ? `Demo (${customer.daily_limit} mesaj)` : `${customer.plan} (${customer.daily_limit}/gün)`;

    // Admin bildirimi
    if (contactPhone) {
      const adminMsg = `⚠️ *Kota Aşıldı*\n\nMüşteri: ${customer.name}\nPlan: ${planLabel}\nToken: ${customer.token.slice(0, 8)}...\n\nPlan yükseltmek için:\n${baseUrl}`;
      await wa.sendMessage(adminConn.id, contactPhone, adminMsg).catch(() => {});
    }

    // Müşteri bildirimi (telefonu kayıtlıysa)
    if (customer.phone) {
      const customerMsg = isDemo
        ? `⚠️ Demo süreniz doldu!\n\n${customer.daily_limit} mesaj hakkınızı kullandınız.\nDevam etmek için plan yükseltin:\n${baseUrl}/musteri?token=${customer.token}`
        : `⚠️ Günlük kotanız doldu!\n\nGünlük ${customer.daily_limit} mesaj hakkınızı kullandınız.\nYarın otomatik sıfırlanır veya planınızı yükseltin:\n${baseUrl}/musteri?token=${customer.token}`;
      await wa.sendMessage(adminConn.id, customer.phone, customerMsg).catch(() => {});
    }
  } catch(e) {
    console.error('Limit bildirim hatası:', e.message);
  }
}

// Tek müşteriye mesaj gönder
app.post('/api/admin/customers/:id/message', adminAuth, async (req, res) => {
  const { message } = req.body;
  if (!message) return res.status(400).json({ error: 'Mesaj gerekli' });
  const customer = db.getCustomerById(req.params.id);
  if (!customer) return res.status(404).json({ error: 'Müşteri bulunamadı' });
  if (!customer.phone) return res.status(400).json({ error: 'Müşterinin telefon numarası yok' });
  const adminConn = getAdminWaConn();
  if (!adminConn) return res.status(400).json({ error: 'Ayarlar\'dan iletişim telefon numaranızı ekleyin ve WhatsApp\'a bağlayın.' });
  try {
    await wa.sendMessage(adminConn.id, customer.phone, message);
    res.json({ ok: true });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

// Toplu duyuru
app.post('/api/admin/broadcast', adminAuth, async (req, res) => {
  const { message, plan_filter } = req.body;
  if (!message) return res.status(400).json({ error: 'Mesaj gerekli' });
  const adminConn = getAdminWaConn();
  if (!adminConn) return res.status(400).json({ error: 'Ayarlar\'dan iletişim telefon numaranızı ekleyin ve WhatsApp\'a bağlayın.' });
  const customers = db.getCustomers().filter(c => {
    if (c.status !== 'active') return false;
    if (!c.phone) return false;
    if (plan_filter && plan_filter !== 'all') return c.plan === plan_filter;
    return true;
  });
  const results = [];
  for (const c of customers) {
    try {
      await wa.sendMessage(adminConn.id, c.phone, message);
      results.push({ id: c.id, name: c.name, ok: true });
    } catch(e) {
      results.push({ id: c.id, name: c.name, ok: false, error: e.message });
    }
    await new Promise(r => setTimeout(r, 2000));
  }
  res.json({ ok: true, total: customers.length, results });
});

app.get('/api/admin/find/:token', adminAuth, (req, res) => {
  const customer = db.getCustomerByToken(req.params.token);
  if (!customer) return res.status(404).json({ error: 'Müşteri bulunamadı' });
  const conn = wa.getStatus(customer.id);
  const totalUsage = db.getTotalUsage(customer.id);
  res.json({ ...customer, wa_status: conn.status, wa_number: conn.phone, total_usage: totalUsage });
});

// Plan yükselt + otomatik WhatsApp mesajı
app.post('/api/admin/customers/:id/upgrade', adminAuth, async (req, res) => {
  const { plan, daily_limit, expires_at } = req.body;
  const customer = db.getCustomerById(req.params.id);
  if (!customer) return res.status(404).json({ error: 'Müşteri bulunamadı' });

  // Planı güncelle
  const updateData = { plan, daily_limit: parseInt(daily_limit), status: 'active' };
  if (expires_at) updateData.expires_at = expires_at;
  db.updateCustomer(req.params.id, updateData);

  // Paket bilgisi
  const packages = JSON.parse(db.getSetting('packages') || '[]');
  const pkg = packages.find(p => p.id === plan);
  const planName = pkg ? pkg.name : plan;

  // Otomatik WhatsApp mesajı gönder
  let waSent = false;
  if (customer.phone) {
    try {
      const customers = db.getCustomers();
      const adminConn = customers.find(c => c.wa_status === 'connected' && c.plan !== 'demo');
      if (adminConn) {
        const expStr = expires_at ? `\nBitiş tarihi: ${new Date(expires_at).toLocaleDateString('tr-TR')}` : '';
        const msg = `✅ Merhaba ${customer.name}!\n\n${planName} planınız aktifleştirildi.\n\nGünlük limit: ${daily_limit} mesaj${expStr}\n\nDashboard: ${db.getSetting('base_url') || 'http://localhost:3000'}/musteri?token=${customer.token}\n\nİyi kullanımlar! 🚀`;
        await wa.sendMessage(adminConn.id, customer.phone, msg);
        waSent = true;
      }
    } catch(e) {
      console.error('Otomatik mesaj hatası:', e.message);
    }
  }

  res.json({ ok: true, plan, daily_limit, expires_at, wa_sent: waSent });
});

// ═══════════════════════════════════════════════════════════════
// MÜŞTERİ API (Token ile)
// ═══════════════════════════════════════════════════════════════

// Durum
app.get('/api/status', customerAuth, (req, res) => {
  const conn = wa.getStatus(req.customer.id);
  res.json({
    customer: req.customer.name,
    plan: req.customer.plan,
    daily_limit: req.customer.daily_limit,
    wa_status: conn.status,
    wa_number: conn.phone,
    expires_at: req.customer.expires_at
  });
});

// Mesaj gönder
app.post('/api/send', customerAuth, rateLimit, async (req, res) => {
  const { to, message } = req.body;
  if (!to || !message) return res.status(400).json({ error: 'to ve message gerekli' });

  // Limit kontrol — demo'da toplam mesaj, diğerlerinde günlük
  const isDemoExpired = req.customer.plan === 'demo' &&
    db.getTotalUsage(req.customer.id) >= req.customer.daily_limit;
  const allowed = isDemoExpired ? false : db.checkAndIncrementUsage(req.customer.id, req.customer.daily_limit);

  if (!allowed) {
    db.logMessage(req.customer.id, to, 'text', 'limit_exceeded');
    notifyLimitExceeded(req.customer).catch(() => {});
    return res.status(429).json({
      error: db.getSetting('contact_message') || 'Günlük mesaj limitinize ulaştınız',
      contact: {
        phone: db.getSetting('contact_phone') || null,
        email: db.getSetting('contact_email') || null,
      }
    });
  }

  try {
    await wa.sendMessage(req.customer.id, to, message);
    db.logMessage(req.customer.id, to, 'text', 'sent');
    res.json({ ok: true, message: 'Mesaj gönderildi' });
  } catch(e) {
    db.logMessage(req.customer.id, to, 'text', 'failed', e.message);
    res.status(500).json({ error: e.message });
  }
});

// Resim gönder
app.post('/api/send/image', customerAuth, rateLimit, async (req, res) => {
  const { to, url, caption } = req.body;
  if (!to || !url) return res.status(400).json({ error: 'to ve url gerekli' });

  const allowed = db.checkAndIncrementUsage(req.customer.id, req.customer.daily_limit);
  if (!allowed) {
    notifyLimitExceeded(req.customer).catch(() => {});
    return res.status(429).json({ error: 'Günlük limit aşıldı' });
  }

  try {
    await wa.sendMessage(req.customer.id, to, { image: { url }, caption: caption || '' });
    db.logMessage(req.customer.id, to, 'image', 'sent');
    res.json({ ok: true });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

// Dosya gönder
app.post('/api/send/document', customerAuth, rateLimit, async (req, res) => {
  const { to, url, filename, mimetype } = req.body;
  if (!to || !url) return res.status(400).json({ error: 'to ve url gerekli' });

  const allowed = db.checkAndIncrementUsage(req.customer.id, req.customer.daily_limit);
  if (!allowed) {
    notifyLimitExceeded(req.customer).catch(() => {});
    return res.status(429).json({ error: 'Günlük limit aşıldı' });
  }

  try {
    await wa.sendMessage(req.customer.id, to, {
      document: { url },
      fileName: filename || 'dosya',
      mimetype: mimetype || 'application/octet-stream'
    });
    db.logMessage(req.customer.id, to, 'document', 'sent');
    res.json({ ok: true });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

// Numara kontrolü
app.post('/api/check', customerAuth, async (req, res) => {
  const { phones } = req.body;
  if (!phones || !Array.isArray(phones)) return res.status(400).json({ error: 'phones dizisi gerekli' });

  const conn = wa.getStatus(req.customer.id);
  if (conn.status !== 'connected') return res.status(400).json({ error: 'WhatsApp bağlı değil' });

  try {
    // Baileys onWhatsApp kontrolü
    const results = {};
    for (const phone of phones.slice(0, 10)) { // Max 10
      const jid = phone.replace(/\D/g, '') + '@s.whatsapp.net';
      results[phone] = true; // Baileys check implementasyonu
    }
    res.json({ results });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

// Toplu mesaj
app.post('/api/send/bulk', customerAuth, async (req, res) => {
  const { messages } = req.body; // [{to, message}]
  if (!messages || !Array.isArray(messages)) return res.status(400).json({ error: 'messages dizisi gerekli' });

  const results = [];
  for (const msg of messages.slice(0, 50)) { // Max 50
    const allowed = db.checkAndIncrementUsage(req.customer.id, req.customer.daily_limit);
    if (!allowed) {
      notifyLimitExceeded(req.customer).catch(() => {});
      results.push({ to: msg.to, ok: false, error: 'Limit aşıldı' });
      break;
    }
    try {
      await wa.sendMessage(req.customer.id, msg.to, msg.message);
      db.logMessage(req.customer.id, msg.to, 'text', 'sent');
      results.push({ to: msg.to, ok: true });
      await new Promise(r => setTimeout(r, 3000)); // Spam koruması
    } catch(e) {
      results.push({ to: msg.to, ok: false, error: e.message });
    }
  }
  res.json({ ok: true, results });
});

// ── MÜŞTERİ WhatsApp BAĞLANTI ─────────────────────────────────────
app.post('/api/connect', customerAuth, async (req, res) => {
  const { method, phone } = req.body;
  if (method === 'pairing' && phone) {
    db.updateCustomer(req.customer.id, { phone });
  }
  const result = await wa.startConnection(req.customer.id, method || 'qr');
  res.json(result);
});

app.get('/api/connect/status', customerAuth, (req, res) => {
  res.json(wa.getStatus(req.customer.id));
});

// Müşteri SSE
app.get('/api/connect/events', (req, res) => {
  // Header veya query param token kabul et
  const token = req.headers['x-api-token'] || req.query.token;
  if (!token) return res.status(401).end();
  const customer = db.getCustomerByToken(token);
  if (!customer || customer.status !== 'active') return res.status(401).end();
  const customerId = customer.id;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (data) => { res.write(`data: ${JSON.stringify(data)}\n\n`); if(res.flush) res.flush(); };
  send({ type: 'status', ...wa.getStatus(customerId) });

  const onQR = (d) => send({ type: 'qr', ...d });
  const onStatus = (d) => send({ type: 'status', ...d });
  const onPairing = (d) => send({ type: 'pairing', ...d });
  const ping = setInterval(() => res.write(': ping\n\n'), 15000);

  wa.waEvents.on(`qr_${customerId}`, onQR);
  wa.waEvents.on(`status_${customerId}`, onStatus);
  wa.waEvents.on(`pairing_${customerId}`, onPairing);

  req.on('close', () => {
    clearInterval(ping);
    wa.waEvents.off(`qr_${customerId}`, onQR);
    wa.waEvents.off(`status_${customerId}`, onStatus);
    wa.waEvents.off(`pairing_${customerId}`, onPairing);
  });
});

// ── DOSYA UPLOAD ─────────────────────────────────────────────────
const multer = require('multer');
const os = require('os');
const upload = multer({ 
  dest: os.tmpdir(),
  limits: { fileSize: 20 * 1024 * 1024 } // 20MB
});

app.post('/api/upload', customerAuth, upload.single('file'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'Dosya gerekli' });
  res.json({ ok: true, path: req.file.path, mimetype: req.file.mimetype, originalname: req.file.originalname });
});

// Medya buffer ile gönder
app.post('/api/send/media', customerAuth, rateLimit, upload.single('file'), async (req, res) => {
  const { to, caption, filename } = req.body;
  if (!to || !req.file) return res.status(400).json({ error: 'to ve file gerekli' });

  const allowed = db.checkAndIncrementUsage(req.customer.id, req.customer.daily_limit);
  if (!allowed) return res.status(429).json({ error: 'Günlük limit aşıldı' });

  try {
    const fs = require('fs');
    const buffer = fs.readFileSync(req.file.path);
    const mime = req.file.mimetype;
    let content;

    if (mime.startsWith('image/')) {
      content = { image: buffer, caption: caption || '' };
    } else if (mime.startsWith('video/')) {
      content = { video: buffer, caption: caption || '' };
    } else if (mime.startsWith('audio/')) {
      content = { audio: buffer };
    } else {
      content = { document: buffer, fileName: filename || req.file.originalname, mimetype: mime };
    }

    await wa.sendMessage(req.customer.id, to, content);
    db.logMessage(req.customer.id, to, mime.split('/')[0], 'sent');
    fs.unlinkSync(req.file.path); // Geçici dosyayı sil
    res.json({ ok: true });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});
// Müşteri kendi tokenını yeniler
app.post('/api/musteri/renew-token', customerAuthDashboard, (req, res) => {
  const { v4: uuidv4 } = require('uuid');
  const newToken = uuidv4().replace(/-/g, '');
  db.updateCustomer(req.customer.id, { token: newToken });
  res.json({ ok: true, token: newToken });
});

// Müşteri kendi hesabını siler
app.delete('/api/musteri/delete', customerAuthDashboard, async (req, res) => {
  const customerId = req.customer.id;
  await wa.disconnectCustomer(customerId).catch(() => {});
  db.deleteCustomer(customerId);
  res.json({ ok: true });
});

app.post('/api/demo/register', async (req, res) => {
  const { name, email, phone } = req.body;
  if (!name || !phone) return res.status(400).json({ error: 'Ad ve telefon zorunlu' });

  const cleanPhone = phone.replace(/\D/g, '');

  // Kara liste kontrolü
  if (db.isBlacklisted(cleanPhone)) {
    return res.status(403).json({
      error: 'Bu numara daha önce demo kullandı',
      blacklisted: true,
      contact: {
        phone: db.getSetting('contact_phone') || null,
        message: 'Ücretli üyelik için iletişime geçin'
      }
    });
  }

  // Aynı telefon aktif kayıt var mı?
  const existing = db.getCustomerByPhone(cleanPhone);
  if (existing) return res.status(400).json({ error: 'Bu telefon numarası zaten kayıtlı' });

  const demoLimit = parseInt(db.getSetting('demo_limit') || '50');
  const customer = db.createCustomer({
    name, email: email || null, phone: cleanPhone,
    plan: 'demo', daily_limit: demoLimit,
    notes: 'Demo kayıt - ' + new Date().toLocaleDateString('tr-TR')
  });

  // Telefonu kara listeye ekle (demo kullandı)
  db.addBlacklist(cleanPhone, name, 'demo_used');

  res.json({ ok: true, token: customer.token, name: customer.name });
});

// ── MÜŞTERİ DASHBOARD API ─────────────────────────────────────────
app.get('/api/musteri/dashboard', customerAuthDashboard, (req, res) => {
  const c = req.customer;
  const usage = db.getTodayUsage(c.id);
  const totalUsage = db.getTotalUsage(c.id);
  const conn = wa.getStatus(c.id);
  const isExpired = c.expires_at && new Date(c.expires_at) < new Date();
  const isLimitDone = c.plan === 'demo' && totalUsage >= c.daily_limit;
  res.json({
    name: c.name, plan: c.plan, status: c.status,
    daily_limit: c.daily_limit, today_usage: usage, total_usage: totalUsage,
    remaining: Math.max(0, c.daily_limit - (c.plan === 'demo' ? totalUsage : usage)),
    expires_at: c.expires_at, is_expired: isExpired, is_limit_done: isLimitDone,
    wa_status: conn.status, wa_number: conn.phone,
    packages: JSON.parse(db.getSetting('packages') || '[]'),
    contact: {
      phone: db.getSetting('contact_phone') || null,
      email: db.getSetting('contact_email') || null,
      message: db.getSetting('contact_message') || 'Planınızı yükseltmek için iletişime geçin.'
    }
  });
});

// ── PANEL ─────────────────────────────────────────────────────────
app.get('/toplu', (req, res) => {
  res.sendFile(path.join(__dirname, '../panel/toplu.html'));
});

app.get('/kayit', (req, res) => {
  res.sendFile(path.join(__dirname, '../panel/kayit.html'));
});

app.get('/musteri', (req, res) => {
  res.sendFile(path.join(__dirname, '../panel/musteri.html'));
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../panel/index.html'));
});

// ── BAŞLAT ────────────────────────────────────────────────────────
app.listen(PORT, async () => {
  console.log('\n╔════════════════════════════════════════╗');
  console.log('║     WhatsApp API Server                ║');
  console.log('╚════════════════════════════════════════╝');
  console.log(`\n✅ Sunucu çalışıyor: http://localhost:${PORT}`);

  // Veritabanını başlat
  await db.initDb();
  console.log('✅ Veritabanı hazır');

  if (!db.adminExists()) {
    console.log('\n⚠️  İlk kurulum — Admin hesabı oluşturun:');
    console.log(`   http://localhost:${PORT}`);
  }

  // Tarayıcı aç (sadece Termux/Android)
  try {
    if (process.env.PREFIX?.includes('com.termux')) {
      require('child_process').spawn('am', ['start', '-a', 'android.intent.action.VIEW', '-d', `http://localhost:${PORT}`]);
    }
  } catch(e) {}

  console.log('\n🔄 Bağlantılar yenileniyor...');
  await wa.restoreConnections();
  console.log('✅ Hazır!\n');

  // Süresi dolmuş müşterileri otomatik askıya al (her saat kontrol)
  function checkExpiredCustomers() {
    const customers = db.getCustomers();
    customers.forEach(c => {
      if (c.status === 'active' && c.expires_at && new Date(c.expires_at) < new Date()) {
        db.toggleCustomer(c.id, 'suspended');
        console.log(`⏰ Süresi doldu, askıya alındı: ${c.name}`);
      }
    });
  }
  checkExpiredCustomers();
  setInterval(checkExpiredCustomers, 60 * 60 * 1000); // Her saat
});
