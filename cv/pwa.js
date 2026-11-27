(function () {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/cv/sw.js').catch(function () {});
  }
  var standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone;
  var btn = document.getElementById('installBtn');
  var deferred = null;
  window.addEventListener('beforeinstallprompt', function (e) { e.preventDefault(); deferred = e; });
  window.addEventListener('appinstalled', function () { if (btn) btn.style.display = 'none'; });
  if (standalone) { if (btn) btn.style.display = 'none'; return; }
  function help() {
    var ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    var m = document.getElementById('installHelp');
    if (!m) {
      m = document.createElement('div');
      m.id = 'installHelp';
      m.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:50;background:#fff;color:#1b2430;padding:18px 18px 22px;border-radius:16px 16px 0 0;box-shadow:0 -4px 20px rgba(0,0,0,.25);font:15px/1.5 system-ui,sans-serif';
      m.innerHTML = '<b style="font-size:16px">Ana ekrana ekle</b><p style="margin:8px 0 12px" id="installTxt"></p><button style="padding:9px 16px;border:0;border-radius:9px;background:#0f6a8e;color:#fff;font-weight:600;font-size:14px" onclick="this.parentNode.remove()">Tamam</button>';
      document.body.appendChild(m);
    }
    document.getElementById('installTxt').textContent = ios
      ? 'Safari\'de alttaki Paylaş (□↑) düğmesine dokun, sonra "Ana Ekrana Ekle"yi seç.'
      : 'Tarayıcı menüsünü (⋮) aç ve "Ana ekrana ekle" ya da "Uygulamayı yükle"yi seç.';
  }
  if (btn) btn.addEventListener('click', function () {
    if (deferred) {
      deferred.prompt();
      deferred.userChoice.then(function () { deferred = null; });
    } else { help(); }
  });
  // Açılışta bir kez hatırlat
  try {
    if (!localStorage.getItem('pwaHint')) {
      localStorage.setItem('pwaHint', '1');
      setTimeout(function () { if (deferred) { deferred.prompt(); } else { help(); } }, 2500);
    }
  } catch (e) {}
})();
