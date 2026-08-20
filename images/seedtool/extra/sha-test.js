// Test diferencial del SHA-256 del shim contra node:crypto.
const fs=require("fs"), crypto=require("crypto"), vm=require("vm");
const src=fs.readFileSync("/home/ubuntu/proyectos/umbrel/images/seedtool/extra/compat.js","utf8");
const ctx={console, TextEncoder, ArrayBuffer, Uint8Array, Uint32Array, Math, Promise, Object, String, TypeError, Error};
ctx.window={crypto:{}}; ctx.navigator={clipboard:{}}; ctx.document={};
vm.createContext(ctx); vm.runInContext(src, ctx);
const digest=ctx.window.crypto.subtle.digest;
const hex=b=>Buffer.from(b).toString("hex");
(async()=>{
  let fails=0, n=0;
  const lens=[0,1,2,3,55,56,57,63,64,65,119,120,121,127,128,129,255,256,1000,4096];
  for(const L of lens){
    const buf=crypto.randomBytes(L);
    const got=hex(await digest("SHA-256", new Uint8Array(buf)));
    const exp=crypto.createHash("sha256").update(buf).digest("hex");
    n++; if(got!==exp){fails++; console.log("FALLA len",L,got,exp);}
  }
  for(let i=0;i<3000;i++){
    const L=Math.floor(Math.random()*600);
    const buf=crypto.randomBytes(L);
    const got=hex(await digest({name:"SHA-256"}, new Uint8Array(buf)));
    const exp=crypto.createHash("sha256").update(buf).digest("hex");
    n++; if(got!==exp){fails++; if(fails<4) console.log("FALLA len",L);}
  }
  // vectores conocidos
  const vec=[["abc","ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"],
             ["","e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
             ["abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq","248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"]];
  for(const [s,e] of vec){
    const got=hex(await digest("SHA-256", new TextEncoder().encode(s)));
    n++; if(got!==e){fails++; console.log("FALLA vector",JSON.stringify(s));}
  }
  // ArrayBuffer y vistas con offset
  const ab=crypto.randomBytes(100); const view=new Uint8Array(ab.buffer, ab.byteOffset+10, 50);
  const g1=hex(await digest("SHA-256", view));
  const e1=crypto.createHash("sha256").update(Buffer.from(ab.subarray(10,60))).digest("hex");
  n++; if(g1!==e1){fails++; console.log("FALLA vista con offset");}
  const g2=hex(await digest("SHA-256", new Uint8Array(ab).buffer));
  const e2=crypto.createHash("sha256").update(ab).digest("hex");
  n++; if(g2!==e2){fails++; console.log("FALLA ArrayBuffer");}
  // algoritmo no soportado
  let rejected=false;
  try { await digest("SHA-512", new Uint8Array(3)); } catch(e){ rejected=true; }
  n++; if(!rejected){fails++; console.log("FALLA: SHA-512 no fue rechazado");}
  console.log(fails===0 ? `OK ${n} casos, sin diferencias contra node:crypto` : `${fails} FALLAS de ${n}`);
})();
