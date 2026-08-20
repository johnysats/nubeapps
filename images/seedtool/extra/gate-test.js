// Simula un origen no seguro y comprueba que el chequeo de upstream pasa con el shim puesto.
const fs=require("fs"), {JSDOM}=require("/tmp/i18ntest/node_modules/jsdom");
const E="/home/ubuntu/proyectos/umbrel/images/seedtool/extra/";
const dom=new JSDOM("<body></body>",{runScripts:"outside-only"});
const w=dom.window;
delete w.crypto.subtle; Object.defineProperty(w.crypto,"subtle",{value:undefined,configurable:true});
Object.defineProperty(w.navigator,"clipboard",{value:undefined,configurable:true});
const gate=()=>!w.crypto||!w.crypto.getRandomValues||!w.crypto.subtle||!w.navigator.clipboard||
  !("content" in w.document.createElement("template"))||!w.TextEncoder||!w.String.prototype.normalize;
console.log("antes del shim, la pagina se bloquea:", gate());
const rngBefore=w.crypto.getRandomValues;
w.eval(fs.readFileSync(E+"compat.js","utf8"));
console.log("despues del shim, la pagina se bloquea:", gate());
w.crypto.subtle.digest("SHA-256", new w.TextEncoder().encode("abc")).then(h=>{
  console.log("digest('abc'):", Buffer.from(h).toString("hex").slice(0,16)+"…",
              "| getRandomValues intacto:", w.crypto.getRandomValues===rngBefore);
});
