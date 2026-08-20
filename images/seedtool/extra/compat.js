// Compatibilidad para orígenes que no son "contexto seguro".
//
// umbrelOS publica las apps en http://umbrel.local:PUERTO, y los navegadores solo exponen
// crypto.subtle y navigator.clipboard sobre HTTPS, localhost o file://. Seed Tool chequea
// justamente esos dos en thisBrowserIsShit() y, si faltan, se niega a arrancar con un alert
// de "navegador desactualizado". Este script los repone antes de que corra ese chequeo
// (el firmware llama a setupDom en DOMContentLoaded, y nosotros vamos inyectados antes).
//
// Lo unico que la pagina le pide a crypto.subtle es digest('SHA-256') -en 5 lugares: los bits
// de checksum de BIP-39, el checksum del one-time pad y el split en 3 tarjetas-, asi que el
// shim implementa solo eso. Cualquier otro algoritmo rechaza en vez de devolver algo
// incorrecto en silencio: de ese hash sale la ultima palabra de las seeds.
//
// La entropia NO pasa por aca: crypto.getRandomValues existe igual sin contexto seguro.
(function () {
  'use strict';

  // SHA-256 (FIPS 180-4). Se compara byte a byte contra node:crypto en el test del paquete.
  var K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ];

  function sha256(bytes) {
    var h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
             0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var len = bytes.length;
    // padding: 0x80, ceros hasta 56 mod 64, y el largo en bits como uint64 big-endian
    var padded = new Uint8Array((((len + 8) >> 6) + 1) << 6);
    padded.set(bytes);
    padded[len] = 0x80;
    var bitsHi = Math.floor(len / 0x20000000);
    var bitsLo = (len << 3) >>> 0;
    var end = padded.length;
    padded[end - 8] = (bitsHi >>> 24) & 0xff;
    padded[end - 7] = (bitsHi >>> 16) & 0xff;
    padded[end - 6] = (bitsHi >>> 8) & 0xff;
    padded[end - 5] = bitsHi & 0xff;
    padded[end - 4] = (bitsLo >>> 24) & 0xff;
    padded[end - 3] = (bitsLo >>> 16) & 0xff;
    padded[end - 2] = (bitsLo >>> 8) & 0xff;
    padded[end - 1] = bitsLo & 0xff;

    var w = new Uint32Array(64);
    for (var off = 0; off < padded.length; off += 64) {
      for (var i = 0; i < 16; i++) {
        w[i] = (padded[off + i * 4] << 24) | (padded[off + i * 4 + 1] << 16) |
               (padded[off + i * 4 + 2] << 8) | padded[off + i * 4 + 3];
      }
      for (i = 16; i < 64; i++) {
        var x = w[i - 15], y = w[i - 2];
        var s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
        var s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      var a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
      for (i = 0; i < 64; i++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var ch = (e & f) ^ (~e & g);
        var t1 = (hh + S1 + ch + K[i] + w[i]) >>> 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + maj) >>> 0;
        hh = g; g = f; f = e;
        e = (d + t1) >>> 0;
        d = c; c = b; b = a;
        a = (t1 + t2) >>> 0;
      }
      h[0] = (h[0] + a) >>> 0; h[1] = (h[1] + b) >>> 0;
      h[2] = (h[2] + c) >>> 0; h[3] = (h[3] + d) >>> 0;
      h[4] = (h[4] + e) >>> 0; h[5] = (h[5] + f) >>> 0;
      h[6] = (h[6] + g) >>> 0; h[7] = (h[7] + hh) >>> 0;
    }
    var out = new Uint8Array(32);
    for (i = 0; i < 8; i++) {
      out[i * 4] = (h[i] >>> 24) & 0xff;
      out[i * 4 + 1] = (h[i] >>> 16) & 0xff;
      out[i * 4 + 2] = (h[i] >>> 8) & 0xff;
      out[i * 4 + 3] = h[i] & 0xff;
    }
    return out;
  }

  function toBytes(data) {
    if (data instanceof Uint8Array) return data;
    if (ArrayBuffer.isView(data)) return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
    if (data instanceof ArrayBuffer) return new Uint8Array(data);
    throw new TypeError('digest: se esperaba BufferSource');
  }

  function algName(algorithm) {
    var name = typeof algorithm === 'string' ? algorithm : (algorithm && algorithm.name);
    return String(name || '').toUpperCase();
  }

  if (typeof window.crypto !== 'undefined' && !window.crypto.subtle) {
    try {
      Object.defineProperty(window.crypto, 'subtle', {
        configurable: true,
        value: {
          digest: function (algorithm, data) {
            return new Promise(function (resolve, reject) {
              if (algName(algorithm) !== 'SHA-256') {
                // Upstream hoy solo usa SHA-256. Si algun dia usa otro, que falle a la vista.
                reject(new Error('crypto.subtle solo esta emulado para SHA-256 (pedido: ' +
                                 algName(algorithm) + '). Abri la app por HTTPS.'));
                return;
              }
              resolve(sha256(toBytes(data)).buffer);
            });
          }
        }
      });
      window.__seedtoolSubtleShim = true;
    } catch (e) {
      console.warn('no pude instalar el shim de crypto.subtle:', e);
    }
  }

  // navigator.clipboard tampoco existe fuera de un contexto seguro; la pagina solo usa
  // writeText para los botones de copiar.
  if (typeof navigator !== 'undefined' && !navigator.clipboard) {
    try {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText: function (text) {
            return new Promise(function (resolve, reject) {
              var ta = document.createElement('textarea');
              ta.value = text;
              ta.setAttribute('readonly', '');
              ta.style.cssText = 'position:fixed;top:-1000px;opacity:0';
              document.body.appendChild(ta);
              ta.select();
              ta.setSelectionRange(0, ta.value.length);
              var ok = false;
              try { ok = document.execCommand('copy'); } catch (e) {}
              document.body.removeChild(ta);
              ok ? resolve() : reject(new Error('no se pudo copiar al portapapeles'));
            });
          }
        }
      });
      window.__seedtoolClipboardShim = true;
    } catch (e) {
      console.warn('no pude instalar el shim de clipboard:', e);
    }
  }
})();
