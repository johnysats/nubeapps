// Prueba de la pagina de donacion en un DOM real: i18n, montaje del widget y respaldo.
//
// No se copia a la imagen. Necesita jsdom (global en el server):
//   node images/donate/page-test.js
//
// Lo que importa que no se rompa: que si el widget de Blink no carga, la pagina siga
// permitiendo pagar por la direccion Lightning. Sin eso, un fallo de red = donacion perdida.
const fs = require('fs');
const path = require('path');

let JSDOM;
try {
  ({ JSDOM } = require('jsdom'));
} catch (e) {
  ({ JSDOM } = require('/usr/lib/node_modules/jsdom'));
}

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
let fails = 0;
const check = (name, cond, extra) => {
  console.log(`${cond ? 'ok  ' : 'FALLA'} ${name}${cond ? '' : '  <- ' + extra}`);
  if (!cond) fails++;
};

// El widget real se reemplaza por un stub: aca se prueba nuestra pagina, no la de Blink.
function load({ withWidget = true, lang = 'es' } = {}) {
  const stub = withWidget
    ? `<script>window.__init=[];window.BlinkPayButton={init:function(c){window.__init.push(c);
         document.getElementById(c.containerId).innerHTML='<button>Donate</button>';}};</script>`
    : '';
  const doc = html.replace('<script src="/blink-pay-button.js"></script>', stub);
  return new JSDOM(doc, {
    runScripts: 'dangerously',
    beforeParse(w) {
      Object.defineProperty(w.navigator, 'language', { value: lang, configurable: true });
    },
  });
}

// 1. Navegador en espanol.
{
  const { window: w } = load({ lang: 'es-AR' });
  check('es: el widget se monta', w.__init.length === 1, 'no se llamo a init');
  check('es: el widget queda en espanol', w.__init[0] && w.__init[0].language === 'es', w.__init[0] && w.__init[0].language);
  check('es: usuario correcto', w.__init[0] && w.__init[0].username === 'johnysats', 'username distinto');
  check('es: titulo en espanol', /Apoy/.test(w.document.querySelector('h1').textContent), w.document.querySelector('h1').textContent);
  check('es: boton ofrece English', w.document.getElementById('lang').textContent === 'English', w.document.getElementById('lang').textContent);
  check('es: el error del widget esta oculto', w.document.getElementById('widget-error').hidden, 'visible sin motivo');
}

// 2. Navegador en ingles, y la vuelta al espanol.
{
  const { window: w } = load({ lang: 'en-US' });
  const h1 = w.document.querySelector('h1').textContent;
  check('en: titulo en ingles', h1 === 'Support NubeApps', h1);
  check('en: widget en ingles', w.__init[0] && w.__init[0].language === 'en', w.__init[0] && w.__init[0].language);
  check('en: no quedo texto en espanol', !/Mantengo|Copiar/.test(w.document.body.textContent), 'quedaron textos sin traducir');

  w.document.getElementById('lang').dispatchEvent(new w.Event('click'));
  check('toggle: vuelve al espanol', /Apoy/.test(w.document.querySelector('h1').textContent), w.document.querySelector('h1').textContent);
  check('toggle: remonta el widget', w.__init.length === 2 && w.__init[1].language === 'es', 'no remonto');
  check('toggle: el contenedor no queda vacio', w.document.getElementById('blink-pay-button-container').innerHTML !== '', 'quedo vacio');
}

// 3. Sin widget (sin internet o API caida): el respaldo tiene que alcanzar para pagar.
{
  const dom = load({ withWidget: false });
  const w = dom.window;
  const addr = w.document.querySelector('.addr').textContent.trim();
  check('sin widget: la direccion Lightning esta visible', addr === 'johnysats@blink.sv', addr);
  check('sin widget: el QR esta presente', !!w.document.querySelector('.fallback img'), 'sin QR');

  // El reintento esta acotado a 5 s: pasado eso avisa, en vez de quedarse mudo para siempre.
  setTimeout(() => {
    const err = w.document.getElementById('widget-error');
    check('sin widget: avisa que no cargo', err.hidden === false, 'sigue oculto tras 6 s');
    check('sin widget: el aviso tiene texto', err.textContent.trim().length > 10, 'aviso vacio');
    dom.window.close();
    console.log(fails ? `\n${fails} fallas` : '\nTodo bien');
    process.exit(fails ? 1 : 0);
  }, 6000);
}
