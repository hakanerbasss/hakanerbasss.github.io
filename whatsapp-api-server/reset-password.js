#!/usr/bin/env node
// reset-password.js — Admin şifresini sıfırla (veriler silinmez)
const path = require('path');
const readline = require('readline');
const bcrypt = require('bcryptjs');

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const q = (question) => new Promise(resolve => rl.question(question, resolve));

async function main() {
  console.log('\n🔑 Admin Şifre Sıfırlama\n');

  // Veritabanını başlat
  const db = require('./src/database');
  await db.initDb();

  if (!db.adminExists()) {
    console.log('❌ Henüz admin hesabı yok. node src/index.js ile kurulum yapın.');
    process.exit(1);
  }

  const newPass = await q('Yeni şifre: ');
  const newPass2 = await q('Yeni şifre tekrar: ');

  if (!newPass || newPass.length < 4) {
    console.log('❌ Şifre en az 4 karakter olmalı');
    process.exit(1);
  }

  if (newPass !== newPass2) {
    console.log('❌ Şifreler eşleşmiyor');
    process.exit(1);
  }

  const hash = bcrypt.hashSync(newPass, 10);
  const d = db.getDb();
  d.run('UPDATE admins SET password = ? WHERE id = 1', [hash]);
  db.saveDb();

  console.log('\n✅ Şifre güncellendi! Tekrar giriş yapabilirsiniz.\n');
  rl.close();
  process.exit(0);
}

main().catch(e => { console.error('Hata:', e.message); process.exit(1); });
