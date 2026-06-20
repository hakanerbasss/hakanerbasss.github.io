// src/whatsapp.js
const { default: makeWASocket, DisconnectReason, useMultiFileAuthState, fetchLatestBaileysVersion } = require('baileys');
const { Boom } = require('@hapi/boom');
const path = require('path');
const fs = require('fs');
const QRCode = require('qrcode');
const db = require('./database');
const EventEmitter = require('events');

const SESSION_DIR = path.join(__dirname, '../data/sessions');
if (!fs.existsSync(SESSION_DIR)) fs.mkdirSync(SESSION_DIR, { recursive: true });

const connections = {};
const waEvents = new EventEmitter();
waEvents.setMaxListeners(100);

async function startConnection(customerId, method = 'qr', phoneNumber = null) {
  // Zaten bağlıysa döndür
  if (connections[customerId]?.status === 'connected') {
    return { status: 'already_connected' };
  }

  // Mevcut socket varsa kapat
  if (connections[customerId]?.socket) {
    try { connections[customerId].socket.end(); } catch(e) {}
    delete connections[customerId];
    await new Promise(r => setTimeout(r, 1000));
  }

  const sessionPath = path.join(SESSION_DIR, `customer_${customerId}`);
  if (!fs.existsSync(sessionPath)) fs.mkdirSync(sessionPath, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(sessionPath);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    logger: require('pino')({ level: 'silent' }),
    browser: ['Mac OS', 'Chrome', '14.4.1'],
    defaultQueryTimeoutMs: undefined,
    connectTimeoutMs: 60000,
    generateHighQualityLinkPreview: false,
    markOnlineOnConnect: false,
  });

  connections[customerId] = {
    socket: sock,
    status: 'connecting',
    qr_base64: null,
    pairing_code: null,
    method,
    phone: null,
    pairingRequested: false,
  };

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    // QR geldi
    if (qr) {
      try {
        const qr_base64 = await QRCode.toDataURL(qr);
        connections[customerId].qr_base64 = qr_base64;
        connections[customerId].status = 'qr_ready';
        waEvents.emit(`qr_${customerId}`, { qr_base64 });
        db.upsertConnection(customerId, { status: 'qr_ready' });
      } catch(e) {}

      // Pairing code yöntemi seçildiyse QR gelince iste
      if (method === 'pairing' && !connections[customerId].pairingRequested) {
        connections[customerId].pairingRequested = true;
        const phone = phoneNumber || db.getCustomerById(customerId)?.phone?.replace(/\D/g, '');
        if (phone) {
          try {
            const code = await sock.requestPairingCode(phone);
            connections[customerId].pairing_code = code;
            console.log(`✅ Pairing kodu: ${code} (müşteri: ${customerId})`);
            waEvents.emit(`pairing_${customerId}`, { code });
            db.upsertConnection(customerId, { status: 'pairing' });
          } catch(e) {
            console.error(`❌ Pairing code hatası (müşteri ${customerId}):`, e.message);
            waEvents.emit(`pairing_${customerId}`, { code: null, error: e.message });
          }
        }
      }
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error instanceof Boom
        ? lastDisconnect.error.output?.statusCode
        : 0;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      connections[customerId].status = 'disconnected';
      db.upsertConnection(customerId, { status: 'disconnected' });
      waEvents.emit(`status_${customerId}`, { status: 'disconnected' });

      if (shouldReconnect) {
        console.log(`🔄 Müşteri ${customerId} yeniden bağlanıyor... (kod: ${statusCode})`);
        setTimeout(() => {
          startConnection(customerId, method, phoneNumber);
        }, 3000);
      } else {
        console.log(`❌ Müşteri ${customerId} oturumu kapandı`);
        fs.rmSync(sessionPath, { recursive: true, force: true });
        delete connections[customerId];
        db.upsertConnection(customerId, { status: 'logged_out', wa_number: null });
        waEvents.emit(`status_${customerId}`, { status: 'logged_out' });
      }
    }

    if (connection === 'open') {
      const waNumber = sock.user?.id?.split(':')[0] || sock.user?.id?.split('@')[0];
      connections[customerId].status = 'connected';
      connections[customerId].phone = waNumber;
      connections[customerId].qr_base64 = null;
      connections[customerId].pairingRequested = false;

      db.upsertConnection(customerId, {
        status: 'connected',
        wa_number: waNumber,
        connected_at: new Date().toISOString(),
        last_seen: new Date().toISOString()
      });

      waEvents.emit(`status_${customerId}`, { status: 'connected', phone: waNumber });
      console.log(`✅ Müşteri ${customerId} bağlandı: ${waNumber}`);
    }
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('messages.upsert', ({ messages, type }) => {
    if (type !== 'notify') return;
    messages.forEach(msg => {
      if (!msg.key.fromMe) {
        waEvents.emit(`message_${customerId}`, {
          from: msg.key.remoteJid?.replace('@s.whatsapp.net', ''),
          message: msg.message?.conversation || msg.message?.extendedTextMessage?.text || '',
          timestamp: msg.messageTimestamp
        });
      }
    });
  });

  return { status: 'connecting' };
}

async function sendMessage(customerId, to, content) {
  const conn = connections[customerId];
  if (!conn || !conn.socket) throw new Error('WhatsApp bağlı değil');
  if (conn.status === 'disconnected' || conn.status === 'logged_out') {
    throw new Error('WhatsApp bağlantısı kesildi');
  }

  let jid = to.toString().replace(/\D/g, '');
  if (jid.startsWith('0')) jid = '90' + jid.slice(1);
  // Artık sadece rakam — @s.whatsapp.net ekle
  jid = jid + '@s.whatsapp.net';

  const msg = typeof content === 'string' ? { text: content } : content;

  // 15 saniye timeout ile gönder
  return await Promise.race([
    conn.socket.sendMessage(jid, msg),
    new Promise((_, reject) => setTimeout(() => reject(new Error('Mesaj gönderme timeout (15s)')), 15000))
  ]);
}

async function disconnectCustomer(customerId) {
  const conn = connections[customerId];
  if (conn?.socket) {
    try { await conn.socket.logout(); } catch(e) {}
    delete connections[customerId];
  }
  const sessionPath = path.join(SESSION_DIR, `customer_${customerId}`);
  fs.rmSync(sessionPath, { recursive: true, force: true });
  db.upsertConnection(customerId, { status: 'disconnected', wa_number: null });
}

function getStatus(customerId) {
  const conn = connections[customerId];
  if (!conn) return { status: 'disconnected' };
  return {
    status: conn.status,
    phone: conn.phone,
    qr_base64: conn.qr_base64,
    pairing_code: conn.pairing_code
  };
}

async function restoreConnections() {
  const customers = db.getCustomers();
  for (const c of customers) {
    if (c.status === 'active') {
      const sessionPath = path.join(SESSION_DIR, `customer_${c.id}`);
      const hasCreds = fs.existsSync(path.join(sessionPath, 'creds.json'));
      if (hasCreds) {
        console.log(`🔄 Müşteri ${c.id} (${c.name}) bağlantısı yenileniyor...`);
        await startConnection(c.id, 'qr').catch(e => console.error(`Bağlantı hatası ${c.id}:`, e.message));
        await new Promise(r => setTimeout(r, 2000));
      }
    }
  }
}

module.exports = { startConnection, sendMessage, disconnectCustomer, getStatus, waEvents, restoreConnections };
