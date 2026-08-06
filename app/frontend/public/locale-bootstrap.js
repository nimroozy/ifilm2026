/**
 * Synchronous locale bootstrap — no browser-language default, no Persian flash.
 * Kept as an external script so production CSP (script-src 'self') can execute it.
 */
(function () {
  try {
    var path = location.pathname || '';
    if (path === '/admin' || path.indexOf('/admin/') === 0) {
      document.documentElement.setAttribute('lang', 'en');
      document.documentElement.setAttribute('dir', 'ltr');
      return;
    }
    var saved = null;
    try {
      saved = localStorage.getItem('ifilm.locale');
    } catch (e) {}
    if (saved !== 'en' && saved !== 'fa' && saved !== 'ps') {
      var match = document.cookie.match(/(?:^|; )ifilm\.locale=([^;]*)/);
      saved = match ? decodeURIComponent(match[1]) : null;
    }
    var locale = saved === 'en' || saved === 'fa' || saved === 'ps' ? saved : 'en';
    document.documentElement.setAttribute('lang', locale);
    document.documentElement.setAttribute('dir', locale === 'en' ? 'ltr' : 'rtl');
  } catch (e) {}
})();
