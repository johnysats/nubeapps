// Requiere SEEDTOOL_URL apuntando al preview de la app.
// Junta el texto visible que la app genera desde JS (no esta en el HTML) y no cubre es.json.
const { chromium } = require("playwright");
const fs = require("fs");
const dict = JSON.parse(fs.readFileSync(require("path").join(__dirname, "es.json"), "utf8"));
const URL = process.env.SEEDTOOL_URL;
const SKIP = /^(SCRIPT|STYLE|TEXTAREA|CODE|PRE|SVG|CANVAS)$/;

const grab = () => `(() => {
  const SKIP = ${SKIP.toString()};
  const out = new Set();
  const skip = (n) => { for (let e = n.parentNode; e && e.nodeType === 1; e = e.parentNode) {
      if (SKIP.test(e.tagName) || e.hasAttribute('data-no-i18n')) return true;
      const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return true; } return false; };
  const it = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while ((n = it.nextNode())) { if (skip(n)) continue;
    const t = n.nodeValue.trim().replace(/\\s+/g, ' '); if (t) out.add(t); }
  document.querySelectorAll('[placeholder],[title],[aria-label]').forEach(e => {
    if (e.hasAttribute('data-no-i18n')) return;
    ['placeholder','title','aria-label'].forEach(a => { const v = e.getAttribute(a);
      if (v) out.add(v.trim().replace(/\\s+/g, ' ')); }); });
  return [...out];
})()`;

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1400, height: 1000 }, locale: "en-US" });
  await ctx.addInitScript(() => { try { localStorage.setItem("seedtool:lang", "en"); } catch (e) {} });
  const p = await ctx.newPage();
  const seen = new Set();
  const collect = async (label) => {
    const list = await p.evaluate(grab());
    list.forEach(t => seen.add(t));
    console.error(label, list.length);
  };
  await p.goto(URL, { waitUntil: "load" });
  await p.waitForTimeout(4000);
  await collect("home");

  // recorrer las tarjetas de la portada y cada herramienta que se abra
  const links = await p.$$eval("a[href^='#/']", as => [...new Set(as.map(a => a.getAttribute("href")))]);
  for (const href of links.slice(0, 40)) {
    await p.goto(URL + href, { waitUntil: "load" }).catch(() => {});
    await p.waitForTimeout(1200);
    await collect(href);
  }
  // con una seed cargada se despliega mucha UI mas
  await p.goto(URL + "#/", { waitUntil: "load" });
  await p.waitForTimeout(2500);
  const gen = await p.$("text=Generate test seed");
  if (gen) { await gen.click().catch(() => {}); await p.waitForTimeout(2500); await collect("con seed"); }

  const missing = [...seen].filter(t => !(t in dict));
  console.error("visibles:", seen.size, "| sin traducir:", missing.length);
  fs.writeFileSync("/tmp/missing-runtime.json", JSON.stringify(missing.sort(), null, 0));
  await b.close();
})();
