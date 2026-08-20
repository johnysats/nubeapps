// Capturas de varias pantallas en espanol, para revisar el texto como lo ve el usuario.
const { chromium } = require("/tmp/pw/node_modules/playwright");
const URL = "http://100.73.0.55:18615/";
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 1400 }, locale: "es-AR" });
  await ctx.addInitScript(() => { try { localStorage.setItem("seedtool:lang", "es"); } catch (e) {} });
  const p = await ctx.newPage();
  const rutas = ["#/", "#/workspace", "#/tour", "#/guide", "#/recover", "#/split", "#/psbt", "#/multisig"];
  for (const r of rutas) {
    await p.goto(URL + r, { waitUntil: "load" });
    await p.waitForTimeout(2500);
    await p.screenshot({ path: "/tmp/es-" + r.replace(/[#/]/g, "") + ".png" });
  }
  await b.close();
})();
