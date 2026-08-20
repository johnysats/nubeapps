// Prueba visual del selector de idioma con Playwright contra el preview.
const { chromium } = require("/tmp/pw/node_modules/playwright");
const URL = process.env.SEEDTOOL_URL || "http://100.73.0.55:18615/";
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 860 }, locale: "es-AR" });
  const p = await ctx.newPage();
  await p.goto(URL, { waitUntil: "load" });
  await p.waitForSelector("#seedtoolLangToggle", { timeout: 15000 });
  await p.waitForTimeout(4000);

  const box = p.locator("#seedtoolLangToggle");
  console.log("visible:", await box.isVisible(), "| rect:", JSON.stringify(await box.boundingBox()));
  console.log("pista de primera visita:", await p.locator("#seedtoolLangHint").count() === 1);
  await p.locator("header.topbar").screenshot({ path: "/tmp/ui-topbar-es.png" });
  await p.screenshot({ path: "/tmp/ui-full-es.png" });

  const sample = () => p.locator("#topbarTitle").innerText();
  const heading = () => p.locator("h1, h2").first().innerText();
  console.log("ES:", JSON.stringify(await heading()));
  console.log("activo:", await p.locator('.nube-lang__opt[aria-pressed="true"]').innerText());

  await p.locator('.nube-lang__opt[data-lang="en"]').click();
  await p.waitForTimeout(400);
  console.log("EN:", JSON.stringify(await heading()));
  console.log("activo:", await p.locator('.nube-lang__opt[aria-pressed="true"]').innerText());
  console.log("pista cerrada:", await p.locator("#seedtoolLangHint").count() === 0);
  await p.locator("header.topbar").screenshot({ path: "/tmp/ui-topbar-en.png" });

  await p.locator('.nube-lang__opt[data-lang="es"]').click();
  await p.waitForTimeout(400);
  console.log("vuelta a ES:", JSON.stringify(await heading()));

  // segunda visita: la eleccion queda guardada y la pista no reaparece
  const p2 = await ctx.newPage();
  await p2.goto(URL, { waitUntil: "load" });
  await p2.waitForSelector("#seedtoolLangToggle");
  await p2.waitForTimeout(1200);
  console.log("2da visita | idioma:", await p2.evaluate(() => document.documentElement.lang),
              "| pista:", await p2.locator("#seedtoolLangHint").count());

  // movil
  const mob = await b.newContext({ viewport: { width: 390, height: 780 }, locale: "es-AR", isMobile: true, hasTouch: true });
  const pm = await mob.newPage();
  await pm.goto(URL, { waitUntil: "load" });
  await pm.waitForSelector("#seedtoolLangToggle");
  await pm.waitForTimeout(1200);
  console.log("movil | visible:", await pm.locator("#seedtoolLangToggle").isVisible(),
              "| rect:", JSON.stringify(await pm.locator("#seedtoolLangToggle").boundingBox()));
  await pm.screenshot({ path: "/tmp/ui-movil-es.png" });
  await b.close();
})();
