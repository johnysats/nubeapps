// Capa de traduccion ES para Bitcoin Seed Tool.
//
// Upstream no tiene i18n: son ~1150 strings hardcodeados en el HTML y en su JS. En vez de
// forkear (lo que romperia el bump automatico de versiones y la verificacion de la firma),
// esto se inyecta con sub_filter de nginx sobre el index.html original, que queda intacto:
// el archivo que sirve /download sigue siendo byte a byte el del release firmado.
//
// Traduce por diccionario de texto completo: solo reemplaza un nodo si su texto entero
// coincide exacto con una clave. Lo que no este traducido queda en ingles.
(function () {
  'use strict';

  var STORE_KEY = 'seedtool:lang';
  var dict = null;          // en -> es
  var lang = 'en';
  var originals = new WeakMap();
  var observer = null;

  // Nada de esto se toca: contenido del usuario (seeds, xpubs, PSBTs) y codigo.
  var SKIP = /^(SCRIPT|STYLE|TEXTAREA|CODE|PRE|SVG|CANVAS)$/;
  var ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];

  function skip(node) {
    for (var el = node.parentNode; el && el.nodeType === 1; el = el.parentNode) {
      if (SKIP.test(el.tagName)) return true;
      if (el.hasAttribute('data-no-i18n')) return true;
    }
    return false;
  }

  // Traduce conservando los espacios de alrededor: en el HTML el texto suele venir con
  // saltos de linea e indentacion que hacen falta para el layout. Las claves del
  // diccionario tienen los espacios internos colapsados, porque el mismo texto puede
  // venir partido en varias lineas.
  function convert(raw) {
    var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(raw);
    var key = m[2].replace(/\s+/g, ' ');
    if (!key) return null;
    var value = dict[key];
    if (!value) return null;
    return m[1] + value + m[3];
  }

  function applyNode(node, toEs) {
    if (skip(node)) return;
    if (!originals.has(node)) {
      if (!toEs) return;                     // volviendo a EN sin haber tocado nada
      var out = convert(node.nodeValue);
      if (out === null) return;
      originals.set(node, node.nodeValue);
      node.nodeValue = out;
    } else if (!toEs) {
      node.nodeValue = originals.get(node);
      originals.delete(node);
    }
  }

  function applyAttrs(el, toEs) {
    if (SKIP.test(el.tagName)) return;
    var list = ATTRS;
    if (el.tagName === 'INPUT' && (el.type === 'button' || el.type === 'submit')) {
      list = ATTRS.concat('value');
    }
    for (var i = 0; i < list.length; i++) {
      var name = list[i];
      var raw = el.getAttribute(name);
      if (raw === null) continue;
      var saved = el.getAttribute('data-i18n-' + name);
      if (toEs) {
        if (saved !== null) continue;
        var out = convert(raw);
        if (out === null) continue;
        el.setAttribute('data-i18n-' + name, raw);
        el.setAttribute(name, out);
      } else if (saved !== null) {
        el.setAttribute(name, saved);
        el.removeAttribute('data-i18n-' + name);
      }
    }
  }

  function walk(root, toEs) {
    if (root.nodeType === 3) return applyNode(root, toEs);
    if (root.nodeType !== 1) return;
    if (SKIP.test(root.tagName)) return;
    applyAttrs(root, toEs);
    var it = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var n;
    while ((n = it.nextNode())) applyNode(n, toEs);
    var els = root.querySelectorAll('*');
    for (var i = 0; i < els.length; i++) applyAttrs(els[i], toEs);
  }

  // La herramienta reescribe el DOM todo el tiempo (resultados, tablas, modales): sin esto
  // cualquier pantalla generada despues de cargar volveria al ingles.
  function observe() {
    if (observer) return;
    observer = new MutationObserver(function (muts) {
      observer.disconnect();
      for (var i = 0; i < muts.length; i++) {
        var m = muts[i];
        if (m.type === 'characterData') applyNode(m.target, true);
        else for (var j = 0; j < m.addedNodes.length; j++) walk(m.addedNodes[j], true);
      }
      connect();
    });
    connect();
  }

  function connect() {
    observer.observe(document.body, {
      childList: true, subtree: true, characterData: true
    });
  }

  function setLang(next) {
    // El observer se corta antes de recorrer: si queda escuchando, las reescrituras de
    // este mismo walk le llegan como mutaciones y vuelve a traducir lo que acabamos de
    // devolver al ingles.
    if (observer) { observer.disconnect(); observer = null; }
    lang = next;
    var toEs = next === 'es';
    walk(document.body, toEs);
    document.documentElement.lang = next;
    if (toEs) observe();
    try { localStorage.setItem(STORE_KEY, next); } catch (e) {}
    var opts = document.querySelectorAll('.nube-lang__opt');
    for (var i = 0; i < opts.length; i++) {
      opts[i].setAttribute('aria-pressed', opts[i].dataset.lang === next ? 'true' : 'false');
    }
  }

  // Selector de idioma: dos segmentos visibles (ES | EN) en la barra superior, al lado de
  // los otros controles de la app. Un boton solo con "EN" no se lee como un selector de
  // idioma; con las dos opciones a la vista y el globo al lado, se entiende sin explicacion.
  var CSS = [
    '.nube-lang{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 4px 0 8px;',
    'border:1px solid #1e293b;border-radius:9px;background:#0b1220;position:relative}',
    '.nube-lang__globe{width:15px;height:15px;flex:none;color:#94a3b8;opacity:.9}',
    '.nube-lang__opt{appearance:none;border:0;background:transparent;cursor:pointer;',
    'font:600 12px/1 inherit;letter-spacing:.03em;color:#94a3b8;padding:5px 7px;border-radius:6px;',
    'transition:background .15s,color .15s}',
    '.nube-lang__opt:hover{color:#e2e8f0;background:#111c33}',
    '.nube-lang__opt[aria-pressed="true"]{background:#1e293b;color:#f8fafc}',
    '.nube-lang__opt:focus-visible{outline:2px solid #fbbf24;outline-offset:1px}',
    '.nube-lang__hint{position:fixed;z-index:2147483647;white-space:nowrap;',
    'background:#1e293b;color:#f8fafc;font:500 12px/1.35 inherit;padding:7px 10px;border-radius:8px;',
    'border:1px solid #334155;box-shadow:0 8px 20px rgba(0,0,0,.45)}',
    '.nube-lang__hint::before{content:"";position:absolute;top:-5px;right:14px;width:8px;height:8px;',
    'background:inherit;border-left:1px solid #334155;border-top:1px solid #334155;transform:rotate(45deg)}',
    '@media (max-width:520px){.nube-lang__globe{display:none}.nube-lang{padding:0 3px}}',
    // Este cartel no vive en el DOM sino en un ::after del CSS de upstream, asi que la
    // unica forma de traducirlo es pisar la regla.
    'html[lang="es"] .card--locked::after{content:"🔒 Cargá una seed primero"}',
    '@media (prefers-reduced-motion:no-preference){',
    '.nube-lang--new{animation:nubeLangPulse 1.6s ease-out 3}',
    '@keyframes nubeLangPulse{0%{box-shadow:0 0 0 0 rgba(251,191,36,.55)}',
    '70%{box-shadow:0 0 0 7px rgba(251,191,36,0)}100%{box-shadow:0 0 0 0 rgba(251,191,36,0)}}}'
  ].join('');

  var GLOBE = '<svg class="nube-lang__globe" viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
    ' stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/>' +
    '<path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/></svg>';

  function addToggle(firstVisit) {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    var box = document.createElement('div');
    box.className = 'nube-lang';
    box.id = 'seedtoolLangToggle';
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', 'Idioma / Language');
    box.setAttribute('data-no-i18n', '');
    box.innerHTML = GLOBE;

    ['es', 'en'].forEach(function (code) {
      var opt = document.createElement('button');
      opt.type = 'button';
      opt.className = 'nube-lang__opt';
      opt.dataset.lang = code;
      opt.textContent = code.toUpperCase();
      opt.title = code === 'es' ? 'Ver esta página en español' : 'View this page in English';
      opt.addEventListener('click', function () {
        hideHint();
        setLang(code);
      });
      box.appendChild(opt);
    });

    // La barra superior de la app: el selector va con el resto de sus controles, no flotando
    // sobre el contenido. Si upstream la renombra, cae a una posicion fija arriba a la derecha.
    var bar = document.querySelector('header.topbar');
    // Antes del ojo de "mostrar datos privados": ese es el grupo de la derecha (el indicador
    // de red va pegado a el con margin-left:auto, asi que insertar antes lo dejaria al medio).
    var eye = document.getElementById('showHide');
    if (bar && eye) bar.insertBefore(box, eye);
    else if (bar) bar.appendChild(box);
    else {
      box.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999';
      document.body.appendChild(box);
    }

    if (firstVisit) showHint(box);
  }

  // La primera visita es la unica en la que el usuario no sabe que la pagina tiene idiomas.
  function showHint(box) {
    var hint = document.createElement('div');
    hint.className = 'nube-lang__hint';
    hint.id = 'seedtoolLangHint';
    hint.setAttribute('data-no-i18n', '');
    hint.textContent = 'Español / English';
    // Va colgado del body y posicionado a mano: dentro de la topbar lo tapaba el banner de
    // "conexion detectada", que se dibuja encima.
    document.body.appendChild(hint);
    var r = box.getBoundingClientRect();
    hint.style.top = (r.bottom + 8) + 'px';
    hint.style.left = Math.max(8, r.right - hint.offsetWidth) + 'px';
    box.classList.add('nube-lang--new');
    setTimeout(hideHint, 8000);
    // El firmware hace clicks propios al arrancar (abre el panel About), asi que el cierre
    // por click recien se engancha cuando esa rafaga ya paso.
    setTimeout(function () {
      document.addEventListener('click', hideHint, { once: true });
    }, 2500);
  }

  function hideHint() {
    var hint = document.getElementById('seedtoolLangHint');
    if (hint) hint.parentNode.removeChild(hint);
    var box = document.getElementById('seedtoolLangToggle');
    if (box) box.classList.remove('nube-lang--new');
  }

  function start() {
    fetch('/extra/es.json')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        dict = data;
        var saved = null;
        try { saved = localStorage.getItem(STORE_KEY); } catch (e) {}
        addToggle(!saved);
        // Sin eleccion previa: seguimos el idioma del navegador.
        if (!saved) {
          saved = /^es\b/i.test(navigator.language || '') ? 'es' : 'en';
        }
        setLang(saved === 'es' ? 'es' : 'en');
      })
      .catch(function (e) { console.warn('i18n ES no disponible:', e); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
