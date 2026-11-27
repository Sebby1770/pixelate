/*
 * PIXELATE Studio engine — a DOM-free port of the Python pipeline.
 *
 * Works as a <script> (self.PixelateEngine), inside a Web Worker via
 * importScripts, and in Node (module.exports). Images are plain
 * {width, height, data: Uint8ClampedArray RGBA} objects.
 *
 * Mirrors pixelate/core.py: preprocess → box downscale → palette →
 * quantize to indices (LUT diffusion, Bayer, Knoll pattern family, or
 * hardware attribute cells) → cleanup / outline → upscale → effects.
 * Threshold maps, kernels, palettes, presets and hardware specs come from
 * data.json (generated from Python) so both engines agree.
 *
 * Known, intentional deviations from Python: the auto palette uses a
 * JS PRNG (same algorithm, different random stream); hardware modes with a
 * shared background try the 6 most-used colours instead of all 16; CRT bloom
 * uses a 3-pass box blur instead of PIL's Gaussian; ciede2000 matching falls
 * back to CIE76 Lab.
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.PixelateEngine = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  var D65 = [0.95047, 1.0, 1.08883];
  var DELTA = 6 / 29;
  var DELTA3 = DELTA * DELTA * DELTA;
  var BITS = 6;
  var SHIFT = 8 - BITS;
  var CELLS = 1 << (3 * BITS);
  var LUMA = [0.299, 0.587, 0.114];

  var DATA = null;
  function setData(data) {
    DATA = data;
    thresholdCache = {};
  }
  function data() {
    if (!DATA) {
      var g = typeof self !== "undefined" ? self : globalThis;
      if (g.PIXELATE_DATA) DATA = g.PIXELATE_DATA;
      else throw new Error("PixelateEngine: call setData(data.json) first");
    }
    return DATA;
  }

  // ------------------------------------------------------------------ math
  function clamp255(v) {
    return v < 0 ? 0 : v > 255 ? 255 : v;
  }
  // Python's round(): half to even.
  function pyRound(x) {
    var r = Math.round(x);
    if (Math.abs(x % 1) === 0.5 && r % 2 !== 0) r -= 1;
    return r;
  }
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ----------------------------------------------------------------- color
  function hexToRgb(hex) {
    var h = String(hex).replace("#", "").trim();
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  function rgbToHex(c) {
    return "#" + c.map(function (v) { return (v | 0).toString(16).padStart(2, "0"); }).join("");
  }
  function linear(c) {
    c = clamp255(c) / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }
  function fLab(t) {
    return t > DELTA3 ? Math.cbrt(t) : t / (3 * DELTA * DELTA) + 4 / 29;
  }
  function srgbToLab(r, g, b) {
    var R = linear(r), G = linear(g), B = linear(b);
    var x = (0.4124564 * R + 0.3575761 * G + 0.1804375 * B) / D65[0];
    var y = (0.2126729 * R + 0.7151522 * G + 0.072175 * B) / D65[1];
    var z = (0.0193339 * R + 0.119192 * G + 0.9503041 * B) / D65[2];
    var fx = fLab(x), fy = fLab(y), fz = fLab(z);
    return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
  }
  function luma(c) {
    return LUMA[0] * c[0] + LUMA[1] * c[1] + LUMA[2] * c[2];
  }

  // ------------------------------------------------------------------- LUT
  var gridLab = null;
  function getGridLab() {
    if (gridLab) return gridLab;
    var n = 1 << BITS, step = 256 >> BITS, half = (step - 1) / 2;
    gridLab = new Float64Array(CELLS * 3);
    var i = 0;
    for (var r = 0; r < n; r++)
      for (var g = 0; g < n; g++)
        for (var b = 0; b < n; b++) {
          var lab = srgbToLab(r * step + half, g * step + half, b * step + half);
          gridLab[i++] = lab[0]; gridLab[i++] = lab[1]; gridLab[i++] = lab[2];
        }
    return gridLab;
  }
  function metricSpace(space) {
    return space === "rgb" ? "rgb" : "lab";
  }
  var lutCache = new Map();
  function getLut(pal, space) {
    space = metricSpace(space);
    var key = space + "|" + pal.map(function (c) { return c.join(","); }).join(";");
    var hit = lutCache.get(key);
    if (hit) return hit;
    var table = new Uint8Array(CELLS);
    var P = pal.length;
    var pts = space === "lab" ? pal.map(function (c) { return srgbToLab(c[0], c[1], c[2]); }) : pal;
    var n = 1 << BITS, step = 256 >> BITS, half = (step - 1) / 2;
    var grid = space === "lab" ? getGridLab() : null;
    var cell = 0;
    for (var r = 0; r < n; r++)
      for (var g = 0; g < n; g++)
        for (var b = 0; b < n; b++, cell++) {
          var p0, p1, p2;
          if (grid) { p0 = grid[cell * 3]; p1 = grid[cell * 3 + 1]; p2 = grid[cell * 3 + 2]; }
          else { p0 = r * step + half; p1 = g * step + half; p2 = b * step + half; }
          var best = 0, bestD = Infinity;
          for (var k = 0; k < P; k++) {
            var q = pts[k], d0 = p0 - q[0], d1 = p1 - q[1], d2 = p2 - q[2];
            var d = d0 * d0 + d1 * d1 + d2 * d2;
            if (d < bestD) { bestD = d; best = k; }
          }
          table[cell] = best;
        }
    if (lutCache.size > 24) lutCache.delete(lutCache.keys().next().value);
    lutCache.set(key, table);
    return table;
  }
  function lutKey(r, g, b) {
    var ri = r <= 0 ? 0 : r >= 255 ? 255 : r | 0;
    var gi = g <= 0 ? 0 : g >= 255 ? 255 : g | 0;
    var bi = b <= 0 ? 0 : b >= 255 ? 255 : b | 0;
    return ((ri >> SHIFT) << (2 * BITS)) | ((gi >> SHIFT) << BITS) | (bi >> SHIFT);
  }

  // Exact nearest (used by "none" / "bayer", like nearest_palette_indices).
  function exactNearest(pal, palPts, space, r, g, b) {
    var p = space === "lab" ? srgbToLab(r, g, b) : [clamp255(r), clamp255(g), clamp255(b)];
    var best = 0, bestD = Infinity;
    for (var k = 0; k < pal.length; k++) {
      var q = palPts[k], d0 = p[0] - q[0], d1 = p[1] - q[1], d2 = p[2] - q[2];
      var d = d0 * d0 + d1 * d1 + d2 * d2;
      if (d < bestD) { bestD = d; best = k; }
    }
    return best;
  }

  // ------------------------------------------------------------ thresholds
  var thresholdCache = {};
  function bayerMatrix(size) {
    var m = [[0, 2], [3, 1]];
    while (m.length < size) {
      var n = m.length, out = [];
      for (var y = 0; y < n * 2; y++) {
        out.push([]);
        for (var x = 0; x < n * 2; x++) {
          var v = 4 * m[y % n][x % n];
          var add = y < n ? (x < n ? 0 : 2) : x < n ? 3 : 1;
          out[y].push(v + add);
        }
      }
      m = out;
    }
    var flat = new Float64Array(size * size);
    for (var i = 0; i < size; i++) for (var j = 0; j < size; j++) flat[i * size + j] = m[i][j] / (size * size);
    return { size: size, values: flat };
  }
  function threshold(name) {
    if (thresholdCache[name]) return thresholdCache[name];
    var t = data().thresholds[name];
    var n = t.size * t.size;
    var values = new Float64Array(n);
    for (var i = 0; i < n; i++) values[i] = t.ranks[i] / n;
    thresholdCache[name] = { size: t.size, values: values };
    return thresholdCache[name];
  }

  // ----------------------------------------------------------- image utils
  function makeImage(w, h) {
    return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) };
  }
  function toFloatRGB(img) {
    var n = img.width * img.height, out = new Float64Array(n * 3), d = img.data;
    for (var i = 0; i < n; i++) { out[i * 3] = d[i * 4]; out[i * 3 + 1] = d[i * 4 + 1]; out[i * 3 + 2] = d[i * 4 + 2]; }
    return out;
  }
  function hasAlpha(img) {
    var d = img.data;
    for (var i = 3; i < d.length; i += 4) if (d[i] < 255) return true;
    return false;
  }

  // Separable area-average (PIL BOX) resample of a float RGB(A) buffer.
  function boxResample(src, w, h, ch, tw, th) {
    function axis(n, tn) {
      var scale = n / tn, spans = [];
      for (var o = 0; o < tn; o++) {
        var a = o * scale, b = (o + 1) * scale, taps = [];
        for (var s = Math.floor(a); s < Math.ceil(b); s++) {
          var wgt = Math.min(b, s + 1) - Math.max(a, s);
          if (wgt > 1e-9) taps.push(s, wgt / scale);
        }
        spans.push(taps);
      }
      return spans;
    }
    var xs = axis(w, tw), ys = axis(h, th);
    var mid = new Float64Array(tw * h * ch);
    for (var y = 0; y < h; y++)
      for (var x = 0; x < tw; x++) {
        var taps = xs[x];
        for (var c = 0; c < ch; c++) {
          var acc = 0;
          for (var t = 0; t < taps.length; t += 2) acc += src[(y * w + taps[t]) * ch + c] * taps[t + 1];
          mid[(y * tw + x) * ch + c] = acc;
        }
      }
    var out = new Float64Array(tw * th * ch);
    for (var yy = 0; yy < th; yy++) {
      var tp = ys[yy];
      for (var xx = 0; xx < tw; xx++)
        for (var cc = 0; cc < ch; cc++) {
          var sum = 0;
          for (var k = 0; k < tp.length; k += 2) sum += mid[(tp[k] * tw + xx) * ch + cc] * tp[k + 1];
          out[(yy * tw + xx) * ch + cc] = sum;
        }
    }
    return out;
  }
  function nearestResample(src, w, h, ch, tw, th) {
    var out = new Float64Array(tw * th * ch);
    for (var y = 0; y < th; y++) {
      var sy = Math.min(h - 1, Math.floor((y + 0.5) * h / th));
      for (var x = 0; x < tw; x++) {
        var sx = Math.min(w - 1, Math.floor((x + 0.5) * w / tw));
        for (var c = 0; c < ch; c++) out[(y * tw + x) * ch + c] = src[(sy * w + sx) * ch + c];
      }
    }
    return out;
  }
  function targetSize(w, h, maxDim) {
    if (Math.max(w, h) <= maxDim) return [w, h];
    if (w >= h) return [maxDim, Math.max(1, pyRound(h * (maxDim / w)))];
    return [Math.max(1, pyRound(w * (maxDim / h))), maxDim];
  }

  // PIL ImageEnhance-style adjustments on a float RGB buffer (in place).
  function enhance(rgb, n, opts) {
    var i;
    if (opts.invert) for (i = 0; i < n * 3; i++) rgb[i] = 255 - rgb[i];
    if (opts.contrast !== 1) {
      var sum = 0;
      for (i = 0; i < n; i++) sum += (rgb[i * 3] * 19595 + rgb[i * 3 + 1] * 38470 + rgb[i * 3 + 2] * 7471 + 0x8000) / 65536;
      var mean = Math.floor(sum / n + 0.5);
      for (i = 0; i < n * 3; i++) rgb[i] = clamp255(mean + (rgb[i] - mean) * opts.contrast);
    }
    if (opts.saturation !== 1) {
      for (i = 0; i < n; i++) {
        var L = (rgb[i * 3] * 19595 + rgb[i * 3 + 1] * 38470 + rgb[i * 3 + 2] * 7471 + 0x8000) / 65536;
        for (var c = 0; c < 3; c++) rgb[i * 3 + c] = clamp255(L + (rgb[i * 3 + c] - L) * opts.saturation);
      }
    }
    if (opts.invert || opts.contrast !== 1 || opts.saturation !== 1) for (i = 0; i < n * 3; i++) rgb[i] = Math.round(rgb[i]);
  }
  function posterize(rgb, levels) {
    for (var i = 0; i < rgb.length; i++) {
      var q = Math.round(rgb[i] * (levels - 1) / 255);
      rgb[i] = clamp255(Math.round(q * (255 / (levels - 1))));
    }
  }

  // ------------------------------------------------------------- dithering
  function diffuse(rgb, w, h, pal, space, kernel, serpentine) {
    var table = getLut(pal, space);
    var PAD = 2, pw = w + 2 * PAD, stride = pw * 3;
    var buf = new Float64Array((h + PAD) * stride);
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++)
        for (var c = 0; c < 3; c++) buf[y * stride + (x + PAD) * 3 + c] = rgb[(y * w + x) * 3 + c];
    var fwd = [], rev = [];
    kernel.forEach(function (k) { fwd.push(k[0] * stride + k[1] * 3, k[2]); rev.push(k[0] * stride - k[1] * 3, k[2]); });
    var out = new Uint8Array(w * h);
    for (var yy = 0; yy < h; yy++) {
      var reverse = serpentine && (yy & 1) === 1;
      var taps = reverse ? rev : fwd;
      var row = yy * stride + PAD * 3;
      for (var s = 0; s < w; s++) {
        var xx = reverse ? w - 1 - s : s;
        var i = row + xx * 3;
        var r = buf[i], g = buf[i + 1], b = buf[i + 2];
        var k = table[lutKey(r, g, b)];
        out[yy * w + xx] = k;
        var er = r - pal[k][0], eg = g - pal[k][1], eb = b - pal[k][2];
        for (var t = 0; t < taps.length; t += 2) {
          var j = i + taps[t], wt = taps[t + 1];
          buf[j] += er * wt; buf[j + 1] += eg * wt; buf[j + 2] += eb * wt;
        }
      }
    }
    return out;
  }

  function patternDither(rgb, w, h, pal, space, thr) {
    var table = getLut(pal, space);
    var cfg = data().pattern, N = cfg.candidates, mult = cfg.multiplier;
    var lum = pal.map(luma), out = new Uint8Array(w * h);
    var picks = new Array(N), keys = new Array(N);
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++) {
        var p = (y * w + x) * 3, sr = clamp255(rgb[p]), sg = clamp255(rgb[p + 1]), sb = clamp255(rgb[p + 2]);
        var er = 0, eg = 0, eb = 0;
        for (var c = 0; c < N; c++) {
          var k = table[lutKey(sr + er * mult, sg + eg * mult, sb + eb * mult)];
          picks[c] = k; keys[c] = lum[k];
          er += sr - pal[k][0]; eg += sg - pal[k][1]; eb += sb - pal[k][2];
        }
        // stable insertion sort by luminance
        for (var a = 1; a < N; a++) {
          var pk = picks[a], kk = keys[a], z = a - 1;
          while (z >= 0 && keys[z] > kk) { picks[z + 1] = picks[z]; keys[z + 1] = keys[z]; z--; }
          picks[z + 1] = pk; keys[z + 1] = kk;
        }
        var t = thr.values[(y % thr.size) * thr.size + (x % thr.size)];
        out[y * w + x] = picks[Math.min(N - 1, Math.floor(t * N))];
      }
    return out;
  }

  function quantize(rgb, w, h, pal, space, offsetFn) {
    var pts = space === "lab" ? pal.map(function (c) { return srgbToLab(c[0], c[1], c[2]); }) : pal;
    var out = new Uint8Array(w * h);
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++) {
        var p = (y * w + x) * 3, off = offsetFn ? offsetFn(x, y) : 0;
        out[y * w + x] = exactNearest(pal, pts, space,
          clamp255(rgb[p] + off), clamp255(rgb[p + 1] + off), clamp255(rgb[p + 2] + off));
      }
    return out;
  }

  function ditherIndices(rgb, w, h, pal, opts) {
    var name = opts.dither, space = metricSpace(opts.colorspace);
    var kernels = data().kernels;
    if (name === "sierra_lite") name = "sierra-lite";
    if (kernels[name]) return diffuse(rgb, w, h, pal, space, kernels[name], opts.serpentine);
    if (name === "pattern" || name === "bluenoise" || name === "halftone")
      return patternDither(rgb, w, h, pal, space, threshold(name));
    if (name === "bayer") {
      var bm = bayerMatrix(opts.bayerSize || 4);
      return quantize(rgb, w, h, pal, space, function (x, y) {
        return (bm.values[(y % bm.size) * bm.size + (x % bm.size)] - 0.5) * 32;
      });
    }
    return quantize(rgb, w, h, pal, space, null);
  }

  // ----------------------------------------------------------- auto palette
  function extractPalette(rgb, n, count, seed) {
    var uniq = new Map();
    for (var i = 0; i < n; i++) {
      var key = (rgb[i * 3] << 16) | (rgb[i * 3 + 1] << 8) | rgb[i * 3 + 2];
      if (!uniq.has(key)) uniq.set(key, [rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]]);
    }
    var colors = Array.from(uniq.values());
    if (colors.length <= count) return colors.sort(function (a, b) { return luma(a) - luma(b); });
    var rand = mulberry32(seed == null ? 42 : seed);
    var sample = [];
    var step = Math.max(1, Math.floor(n / 10000));
    for (var s = 0; s < n; s += step) sample.push(srgbToLab(rgb[s * 3], rgb[s * 3 + 1], rgb[s * 3 + 2]));
    var m = sample.length, k = Math.min(count, m);
    var centers = [sample[Math.floor(rand() * m)]];
    var closest = new Float64Array(m);
    function d2(a, b) { var x = a[0] - b[0], y = a[1] - b[1], z = a[2] - b[2]; return x * x + y * y + z * z; }
    for (var j = 0; j < m; j++) closest[j] = d2(sample[j], centers[0]);
    while (centers.length < k) {
      var total = 0;
      for (j = 0; j < m; j++) total += closest[j];
      var target = rand() * total, pick = m - 1;
      for (j = 0; j < m; j++) { target -= closest[j]; if (target <= 0) { pick = j; break; } }
      var c = sample[pick];
      centers.push(c);
      for (j = 0; j < m; j++) closest[j] = Math.min(closest[j], d2(sample[j], c));
    }
    var labels = new Int32Array(m);
    for (var iter = 0; iter < 20; iter++) {
      for (j = 0; j < m; j++) {
        var best = 0, bd = Infinity;
        for (var q = 0; q < k; q++) { var dd = d2(sample[j], centers[q]); if (dd < bd) { bd = dd; best = q; } }
        labels[j] = best;
      }
      var sums = centers.map(function () { return [0, 0, 0, 0]; });
      for (j = 0; j < m; j++) { var sm = sums[labels[j]]; sm[0] += sample[j][0]; sm[1] += sample[j][1]; sm[2] += sample[j][2]; sm[3]++; }
      var moved = 0;
      centers = centers.map(function (cc, q) {
        var sm2 = sums[q];
        if (!sm2[3]) return sample[Math.floor(rand() * m)];
        var nc = [sm2[0] / sm2[3], sm2[1] / sm2[3], sm2[2] / sm2[3]];
        moved = Math.max(moved, Math.abs(nc[0] - cc[0]), Math.abs(nc[1] - cc[1]), Math.abs(nc[2] - cc[2]));
        return nc;
      });
      if (moved < 0.5) break;
    }
    var out = [], seen = new Set();
    centers.map(labToSrgb).sort(function (a, b) { return luma(a) - luma(b); }).forEach(function (c2) {
      var key2 = c2.join(",");
      if (!seen.has(key2)) { seen.add(key2); out.push(c2); }
    });
    return out;
  }
  function labToSrgb(lab) {
    var fy = (lab[0] + 16) / 116, fx = fy + lab[1] / 500, fz = fy - lab[2] / 200;
    function inv(f) { return f > DELTA ? f * f * f : 3 * DELTA * DELTA * (f - 4 / 29); }
    var x = inv(fx) * D65[0], y = inv(fy) * D65[1], z = inv(fz) * D65[2];
    var R = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z;
    var G = -0.969266 * x + 1.8760108 * y + 0.041556 * z;
    var B = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z;
    function enc(c) { c = Math.max(0, c); return clamp255(Math.round(255 * (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055))); }
    return [enc(R), enc(G), enc(B)];
  }

  // -------------------------------------------------------------- hardware
  function combos(mode, exclude) {
    var P = mode.palette.length;
    var banks = mode.groups && mode.groups.length ? mode.groups : [Array.from({ length: P }, function (_, i) { return i; })];
    var out = [], seen = new Set();
    banks.forEach(function (bank) {
      var pool = bank.filter(function (i) { return exclude.indexOf(i) < 0; });
      var k = Math.min(mode.perCell, pool.length);
      (function rec(start, acc) {
        if (acc.length === k) {
          var key = acc.map(function (i) { return String(mode.palette[i]).toLowerCase(); }).sort().filter(function (v, j, arr) { return j === 0 || arr[j - 1] !== v; }).join("|");
          if (!seen.has(key)) { seen.add(key); out.push(acc.slice()); }
          return;
        }
        for (var i = start; i < pool.length; i++) { acc.push(pool[i]); rec(i + 1, acc); acc.pop(); }
      })(0, []);
    });
    return out;
  }
  function facilityLocation(E, nCells, nCombos, m) {
    m = Math.min(m, nCombos);
    var chosen = [], current = new Float64Array(nCells).fill(Infinity), c, n;
    for (var r = 0; r < m; r++) {
      var bestC = -1, bestT = Infinity;
      for (c = 0; c < nCombos; c++) {
        if (chosen.indexOf(c) >= 0) continue;
        var t = 0;
        for (n = 0; n < nCells; n++) t += Math.min(current[n], E[n * nCombos + c]);
        if (t < bestT) { bestT = t; bestC = c; }
      }
      chosen.push(bestC);
      for (n = 0; n < nCells; n++) current[n] = Math.min(current[n], E[n * nCombos + bestC]);
    }
    function total(set) {
      var s = 0;
      for (var nn = 0; nn < nCells; nn++) { var b = Infinity; for (var q = 0; q < set.length; q++) b = Math.min(b, E[nn * nCombos + set[q]]); s += b; }
      return s;
    }
    var improved = true, bestTotal = total(chosen);
    while (improved) {
      improved = false;
      for (var slot = 0; slot < chosen.length; slot++) {
        for (c = 0; c < nCombos; c++) {
          if (chosen.indexOf(c) >= 0) continue;
          var trial = chosen.slice(); trial[slot] = c;
          var tt = total(trial);
          if (tt < bestTotal - 1e-9) { chosen = trial; bestTotal = tt; improved = true; }
        }
      }
    }
    return chosen;
  }
  function chooseCellColors(rgb, w, h, mode, space) {
    var pal = mode.palette.map(hexToRgb), P = pal.length;
    var lab = space === "lab";
    var palPts = lab ? pal.map(function (c) { return srgbToLab(c[0], c[1], c[2]); }) : pal;
    var cw = mode.cell[0], ch = mode.cell[1], cols = w / cw, rows = h / ch, N = cols * rows, npx = cw * ch;
    var dist = new Float64Array(N * npx * P);
    var usage = new Float64Array(P);
    for (var cy = 0; cy < rows; cy++)
      for (var cx = 0; cx < cols; cx++) {
        var n = cy * cols + cx;
        for (var py = 0; py < ch; py++)
          for (var px = 0; px < cw; px++) {
            var x = cx * cw + px, y = cy * ch + py, o = (y * w + x) * 3;
            var p = lab ? srgbToLab(rgb[o], rgb[o + 1], rgb[o + 2]) : [rgb[o], rgb[o + 1], rgb[o + 2]];
            var base = (n * npx + py * cw + px) * P, best = 0, bd = Infinity;
            for (var k = 0; k < P; k++) {
              var q = palPts[k], d0 = p[0] - q[0], d1 = p[1] - q[1], d2 = p[2] - q[2];
              var d = d0 * d0 + d1 * d1 + d2 * d2;
              dist[base + k] = d;
              if (d < bd) { bd = d; best = k; }
            }
            usage[best]++;
          }
      }
    var bgs = [null];
    if (mode.shared) {
      bgs = Array.from({ length: P }, function (_, i) { return i; })
        .sort(function (a, b) { return usage[b] - usage[a] || a - b; }).slice(0, 6);
    }
    var bestRun = null;
    bgs.forEach(function (bg) {
      var cs = combos(mode, bg == null ? [] : [bg]), C = cs.length;
      var E = new Float64Array(N * C);
      for (var nn = 0; nn < N; nn++)
        for (var c = 0; c < C; c++) {
          var combo = cs[c], sum = 0;
          for (var i = 0; i < npx; i++) {
            var b0 = (nn * npx + i) * P, m = bg == null ? Infinity : dist[b0 + bg];
            for (var j = 0; j < combo.length; j++) { var dv = dist[b0 + combo[j]]; if (dv < m) m = dv; }
            sum += m;
          }
          E[nn * C + c] = sum;
        }
      var assign = new Int32Array(N);
      var allowed = mode.maxSets ? facilityLocation(E, N, C, mode.maxSets) : null;
      var tot = 0;
      for (nn = 0; nn < N; nn++) {
        var bc = -1, be = Infinity, list = allowed || null;
        var lim = list ? list.length : C;
        for (var a = 0; a < lim; a++) { var cc = list ? list[a] : a; if (E[nn * C + cc] < be) { be = E[nn * C + cc]; bc = cc; } }
        assign[nn] = bc; tot += be;
      }
      if (!bestRun || tot < bestRun.total) bestRun = { total: tot, bg: bg, combos: cs, assign: assign };
    });
    var K = mode.perCell + mode.shared;
    var sets = new Int32Array(N * K);
    for (var q = 0; q < N; q++) {
      var s = (bestRun.bg == null ? [] : [bestRun.bg]).concat(bestRun.combos[bestRun.assign[q]]);
      while (s.length < K) s.push(s[s.length - 1]);
      for (var z = 0; z < K; z++) sets[q * K + z] = s[z];
    }
    return { sets: sets, K: K, cols: cols, rows: rows, shared: bestRun.bg == null ? [] : [bestRun.bg] };
  }
  // ---------------------------------------- generated palettes (tiled, HAM)
  function snapDepth(v, bits) {
    var lv = (1 << bits) - 1;
    return Math.round(Math.round(clamp255(v) * lv / 255) * 255 / lv);
  }
  function groupPalette(ints, n, count, bits, seed) {
    var out = [], seen = new Set();
    extractPalette(ints, n, count, seed).forEach(function (c) {
      var s = c.map(function (v) { return snapDepth(v, bits); }), key = s.join(",");
      if (!seen.has(key)) { seen.add(key); out.push(s); }
    });
    return out;
  }
  function kmeansRows(feats, k) {
    var n = feats.length, dim = feats[0].length, rand = mulberry32(0);
    k = Math.max(1, Math.min(k, n));
    function d2(a, b) { var s = 0; for (var i = 0; i < dim; i++) s += (a[i] - b[i]) * (a[i] - b[i]); return s; }
    var centers = [feats[Math.floor(rand() * n)].slice()];
    var close = feats.map(function (f) { return d2(f, centers[0]); });
    while (centers.length < k) {
      var tot = close.reduce(function (a, b) { return a + b; }, 0), pick = Math.floor(rand() * n);
      if (tot > 0) { var r = rand() * tot; for (var i = 0; i < n; i++) { r -= close[i]; if (r <= 0) { pick = i; break; } } }
      centers.push(feats[pick].slice());
      for (var j = 0; j < n; j++) close[j] = Math.min(close[j], d2(feats[j], feats[pick]));
    }
    var labels = new Int32Array(n);
    for (var it = 0; it < 15; it++) {
      var changed = false;
      for (var q = 0; q < n; q++) {
        var best = 0, bd = Infinity;
        for (var c = 0; c < k; c++) { var dd = d2(feats[q], centers[c]); if (dd < bd) { bd = dd; best = c; } }
        if (labels[q] !== best) { labels[q] = best; changed = true; }
      }
      if (!changed && it > 0) break;
      for (var c2 = 0; c2 < k; c2++) {
        var sum = new Array(dim).fill(0), cnt = 0;
        for (var q2 = 0; q2 < n; q2++) if (labels[q2] === c2) { cnt++; for (var e = 0; e < dim; e++) sum[e] += feats[q2][e]; }
        if (cnt) centers[c2] = sum.map(function (v) { return v / cnt; });
      }
    }
    return labels;
  }
  function chooseTilePalettes(rgb, w, h, mode, space) {
    var lab = space === "lab", cw = mode.cell[0], ch = mode.cell[1], cols = w / cw, rows = h / ch, N = cols * rows, npx = cw * ch;
    var px = new Float64Array(N * npx * 3), pm = new Float64Array(N * npx * 3), feats = [];
    for (var n = 0; n < N; n++) {
      var ty = Math.floor(n / cols) * ch, tx = (n % cols) * cw, mean = [0, 0, 0, 0, 0, 0], labs = [];
      for (var p = 0; p < npx; p++) {
        var o = ((ty + Math.floor(p / cw)) * w + tx + (p % cw)) * 3, q = (n * npx + p) * 3;
        px[q] = rgb[o]; px[q + 1] = rgb[o + 1]; px[q + 2] = rgb[o + 2];
        var L = srgbToLab(rgb[o], rgb[o + 1], rgb[o + 2]); labs.push(L);
        var m = lab ? L : [rgb[o], rgb[o + 1], rgb[o + 2]];
        pm[q] = m[0]; pm[q + 1] = m[1]; pm[q + 2] = m[2];
        for (var c = 0; c < 3; c++) mean[c] += L[c] / npx;
      }
      labs.forEach(function (L2) { for (var c3 = 0; c3 < 3; c3++) mean[3 + c3] += (L2[c3] - mean[c3]) * (L2[c3] - mean[c3]) / npx; });
      for (var s = 3; s < 6; s++) mean[s] = Math.sqrt(mean[s]);
      feats.push(mean);
    }
    var groups = Math.min(mode.subPalettes, N), labels = kmeansRows(feats, groups), shared = [];
    if (mode.shared) {
      var counts = new Map(), bestKey = 0, bestCount = -1;
      for (var i = 0; i < N * npx; i++) {
        var key = (snapDepth(px[i * 3], mode.bits) << 16) | (snapDepth(px[i * 3 + 1], mode.bits) << 8) | snapDepth(px[i * 3 + 2], mode.bits);
        var c4 = (counts.get(key) || 0) + 1; counts.set(key, c4);
        if (c4 > bestCount || (c4 === bestCount && key < bestKey)) { bestCount = c4; bestKey = key; }
      }
      shared = [[(bestKey >> 16) & 255, (bestKey >> 8) & 255, bestKey & 255]];
    }
    var sharedKeys = shared.map(function (c5) { return c5.join(","); });
    var palettes = [];
    for (var round = 0; round <= 2; round++) {
      for (var g = 0; g < groups; g++) {
        var members = [];
        for (var t = 0; t < N; t++) if (labels[t] === g) members.push(t);
        if (members.length) {
          var ints = new Uint8Array(members.length * npx * 3);
          members.forEach(function (tt, mi) { for (var z = 0; z < npx * 3; z++) ints[mi * npx * 3 + z] = Math.round(clamp255(px[tt * npx * 3 + z])); });
          var own = groupPalette(ints, members.length * npx, mode.perCell, mode.bits, g)
            .filter(function (c6) { return sharedKeys.indexOf(c6.join(",")) < 0; }).slice(0, mode.perCell);
          palettes[g] = shared.concat(own);
        }
        if (!palettes[g] || !palettes[g].length) palettes[g] = shared.length ? shared.slice() : [[0, 0, 0]];
      }
      if (round === 2) break;
      var pmPal = palettes.map(function (pl) { return pl.map(function (c7) { return lab ? srgbToLab(c7[0], c7[1], c7[2]) : c7; }); });
      for (var n2 = 0; n2 < N; n2++) {
        var bestG = labels[n2], bestE = Infinity;
        for (var g2 = 0; g2 < groups; g2++) {
          var err = 0, cand = pmPal[g2];
          for (var p2 = 0; p2 < npx; p2++) {
            var q2 = (n2 * npx + p2) * 3, md = Infinity;
            for (var k = 0; k < cand.length; k++) {
              var d0 = pm[q2] - cand[k][0], d1 = pm[q2 + 1] - cand[k][1], dz = pm[q2 + 2] - cand[k][2], dd = d0 * d0 + d1 * d1 + dz * dz;
              if (dd < md) md = dd;
            }
            err += md;
          }
          if (err < bestE) { bestE = err; bestG = g2; }
        }
        labels[n2] = bestG;
      }
    }
    var palette = [], index = new Map(), groupIdx = palettes.map(function (pl) {
      return pl.map(function (c8) { var key2 = c8.join(","); if (!index.has(key2)) { index.set(key2, palette.length); palette.push(c8); } return index.get(key2); });
    });
    var K = mode.perCell + mode.shared, sets = new Int32Array(N * K);
    for (var n3 = 0; n3 < N; n3++) {
      var ids = groupIdx[labels[n3]];
      for (var z2 = 0; z2 < K; z2++) sets[n3 * K + z2] = ids[Math.min(z2, ids.length - 1)];
    }
    return { palette: palette, sets: sets, K: K, cols: cols, rows: rows, shared: sharedKeys.map(function (kk) { return index.get(kk); }) };
  }
  function applyHam(rgb, w, h, mode, opts) {
    var lab = metricSpace(opts.colorspace) === "lab", bits = mode.bits, lv = (1 << bits) - 1, step = 255 / lv, side = lv + 1;
    var ints = new Uint8Array(rgb.length);
    for (var i = 0; i < rgb.length; i++) ints[i] = Math.round(clamp255(rgb[i]));
    var base = groupPalette(ints, w * h, 16, bits, 0).sort(function (a, b) { return luma(a) - luma(b); });
    var baseLv = base.map(function (c) { return c.map(function (v) { return Math.round(v / step); }); }), nb = baseLv.length;
    var table = new Float64Array(side * side * side * 3);
    for (var r = 0; r < side; r++) for (var g = 0; g < side; g++) for (var b = 0; b < side; b++) {
      var k = ((r * side + g) * side + b) * 3, p = lab ? srgbToLab(r * step, g * step, b * step) : [r * step, g * step, b * step];
      table[k] = p[0]; table[k + 1] = p[1]; table[k + 2] = p[2];
    }
    var name = opts.dither === "sierra_lite" ? "sierra-lite" : opts.dither;
    var thr = name === "bayer" ? bayerMatrix(opts.bayerSize || 4) : name === "pattern" || name === "bluenoise" || name === "halftone" ? threshold(name) : null;
    var diffuse = !!data().kernels[name], modified = 0, out = new Int32Array(w * h * 3), st = { bd: 0, r: 0, g: 0, b: 0, mod: false };
    function consider(tp, rr, gg, bb, mod) {
      var kk = ((rr * side + gg) * side + bb) * 3, d0 = table[kk] - tp[0], d1 = table[kk + 1] - tp[1], d2 = table[kk + 2] - tp[2];
      var dd = d0 * d0 + d1 * d1 + d2 * d2;
      if (dd < st.bd) { st.bd = dd; st.r = rr; st.g = gg; st.b = bb; st.mod = mod; }
    }
    for (var y = 0; y < h; y++) {
      var pr = baseLv[0][0], pg = baseLv[0][1], pb = baseLv[0][2], cr = 0, cg = 0, cb = 0;
      for (var x = 0; x < w; x++) {
        var o = (y * w + x) * 3, off = thr ? (thr.values[(y % thr.size) * thr.size + (x % thr.size)] - 0.5) * 32 : 0;
        var tr = clamp255(clamp255(rgb[o] + off) + cr), tg = clamp255(clamp255(rgb[o + 1] + off) + cg), tb = clamp255(clamp255(rgb[o + 2] + off) + cb);
        var tp = lab ? srgbToLab(tr, tg, tb) : [tr, tg, tb];
        st.bd = Infinity;
        for (var q = 0; q < nb; q++) consider(tp, baseLv[q][0], baseLv[q][1], baseLv[q][2], false);
        for (var l = 0; l < side; l++) consider(tp, l, pg, pb, true);
        for (l = 0; l < side; l++) consider(tp, pr, l, pb, true);
        for (l = 0; l < side; l++) consider(tp, pr, pg, l, true);
        pr = st.r; pg = st.g; pb = st.b;
        if (st.mod) modified++;
        out[o] = pr; out[o + 1] = pg; out[o + 2] = pb;
        if (diffuse) { cr = (tr - pr * step) * 0.5; cg = (tg - pg * step) * 0.5; cb = (tb - pb * step) * 0.5; }
      }
    }
    var palette = [], index = new Map(), indices = new Int32Array(w * h);
    for (var n = 0; n < w * h; n++) {
      var c = [Math.round(out[n * 3] * step), Math.round(out[n * 3 + 1] * step), Math.round(out[n * 3 + 2] * step)], key = c.join(",");
      if (!index.has(key)) { index.set(key, palette.length); palette.push(c); }
      indices[n] = index.get(key);
    }
    return {
      indices: indices, palette: palette, cellSets: new Int32Array(0), K: 0, cols: 0, rows: 0,
      report: { mode: mode.title, cells: 1, distinctCellSets: 1, colorsUsed: palette.length, shared: [], baseColors: nb, modifiedPixels: Math.round(1000 * modified / Math.max(1, w * h)) / 10 },
    };
  }

  function restrictedNearest(p, cand, K, palPts) {
    var best = cand[0], bd = Infinity;
    for (var i = 0; i < K; i++) {
      var q = palPts[cand[i]], d0 = p[0] - q[0], d1 = p[1] - q[1], d2 = p[2] - q[2];
      var d = d0 * d0 + d1 * d1 + d2 * d2;
      if (d < bd) { bd = d; best = cand[i]; }
    }
    return best;
  }
  function applyHardware(rgb, w, h, mode, opts) {
    var space = metricSpace(opts.colorspace), lab = space === "lab";
    if (mode.kind === "ham") return applyHam(rgb, w, h, mode, opts);
    var cw = mode.cell[0], ch = mode.cell[1];
    var pw = Math.ceil(w / cw) * cw, ph = Math.ceil(h / ch) * ch;
    var pad = new Float64Array(pw * ph * 3);
    for (var y = 0; y < ph; y++)
      for (var x = 0; x < pw; x++) {
        var sx = Math.min(x, w - 1), sy = Math.min(y, h - 1);
        for (var c = 0; c < 3; c++) pad[(y * pw + x) * 3 + c] = rgb[(sy * w + sx) * 3 + c];
      }
    var cells, pal;
    if (mode.kind === "tiled") {
      cells = chooseTilePalettes(pad, pw, ph, mode, space);
      pal = cells.palette;
    } else {
      pal = mode.palette.map(hexToRgb);
      cells = chooseCellColors(pad, pw, ph, mode, space);
    }
    var palPts = lab ? pal.map(function (cc) { return srgbToLab(cc[0], cc[1], cc[2]); }) : pal;
    var K = cells.K;
    function candAt(xx, yy) {
      var n = Math.floor(yy / ch) * cells.cols + Math.floor(xx / cw);
      return cells.sets.subarray(n * K, n * K + K);
    }
    function pt(r, g, b) { return lab ? srgbToLab(r, g, b) : [clamp255(r), clamp255(g), clamp255(b)]; }
    var idx = new Int32Array(pw * ph), name = opts.dither === "sierra_lite" ? "sierra-lite" : opts.dither;
    var kernels = data().kernels;
    if (kernels[name]) {
      var grid = getGridLab(), kernel = kernels[name], PAD = 2, bw = pw + 2 * PAD, stride = bw * 3;
      var buf = new Float64Array((ph + PAD) * stride);
      for (y = 0; y < ph; y++) for (x = 0; x < pw; x++) for (c = 0; c < 3; c++) buf[y * stride + (x + PAD) * 3 + c] = pad[(y * pw + x) * 3 + c];
      var fwd = [], rev = [];
      kernel.forEach(function (k) { fwd.push(k[0] * stride + k[1] * 3, k[2]); rev.push(k[0] * stride - k[1] * 3, k[2]); });
      for (y = 0; y < ph; y++) {
        var reverse = opts.serpentine && (y & 1) === 1, taps = reverse ? rev : fwd, row = y * stride + PAD * 3;
        for (var s = 0; s < pw; s++) {
          x = reverse ? pw - 1 - s : s;
          var i = row + x * 3, r = buf[i], g = buf[i + 1], b = buf[i + 2], p;
          if (lab) { var key = lutKey(r, g, b) * 3; p = [grid[key], grid[key + 1], grid[key + 2]]; }
          else p = [r, g, b];
          var k2 = restrictedNearest(p, candAt(x, y), K, palPts);
          idx[y * pw + x] = k2;
          var er = r - pal[k2][0], eg = g - pal[k2][1], eb = b - pal[k2][2];
          for (var t = 0; t < taps.length; t += 2) { var j = i + taps[t], wt = taps[t + 1]; buf[j] += er * wt; buf[j + 1] += eg * wt; buf[j + 2] += eb * wt; }
        }
      }
    } else if (name === "pattern" || name === "bluenoise" || name === "halftone") {
      var thr = threshold(name), cfg = data().pattern, N = cfg.candidates, mult = cfg.multiplier;
      var lum = pal.map(luma), picks = new Array(N), keys = new Array(N);
      for (y = 0; y < ph; y++)
        for (x = 0; x < pw; x++) {
          var o = (y * pw + x) * 3, sr = clamp255(pad[o]), sg = clamp255(pad[o + 1]), sb = clamp255(pad[o + 2]);
          var cand = candAt(x, y), e0 = 0, e1 = 0, e2 = 0;
          for (var q = 0; q < N; q++) {
            var kk = restrictedNearest(pt(sr + e0 * mult, sg + e1 * mult, sb + e2 * mult), cand, K, palPts);
            picks[q] = kk; keys[q] = lum[kk];
            e0 += sr - pal[kk][0]; e1 += sg - pal[kk][1]; e2 += sb - pal[kk][2];
          }
          for (var a = 1; a < N; a++) {
            var pk = picks[a], ky = keys[a], z = a - 1;
            while (z >= 0 && keys[z] > ky) { picks[z + 1] = picks[z]; keys[z + 1] = keys[z]; z--; }
            picks[z + 1] = pk; keys[z + 1] = ky;
          }
          idx[y * pw + x] = picks[Math.min(N - 1, Math.floor(thr.values[(y % thr.size) * thr.size + (x % thr.size)] * N))];
        }
    } else {
      var bm = name === "bayer" ? bayerMatrix(opts.bayerSize || 4) : null;
      for (y = 0; y < ph; y++)
        for (x = 0; x < pw; x++) {
          var off = bm ? (bm.values[(y % bm.size) * bm.size + (x % bm.size)] - 0.5) * 32 : 0, oo = (y * pw + x) * 3;
          idx[y * pw + x] = restrictedNearest(pt(clamp255(pad[oo] + off), clamp255(pad[oo + 1] + off), clamp255(pad[oo + 2] + off)), candAt(x, y), K, palPts);
        }
    }
    var out = new Int32Array(w * h);
    for (y = 0; y < h; y++) for (x = 0; x < w; x++) out[y * w + x] = idx[y * pw + x];
    var distinct = new Set(), used = new Set();
    for (var n2 = 0; n2 < cells.cols * cells.rows; n2++) {
      distinct.add(Array.from(new Set(cells.sets.subarray(n2 * K, n2 * K + K))).sort(function (a2, b2) { return a2 - b2; }).join(","));
    }
    for (var u = 0; u < out.length; u++) used.add(out[u]);
    return {
      indices: out, palette: pal, cellSets: cells.sets, K: K, cols: cells.cols, rows: cells.rows,
      report: { mode: mode.title, cells: cells.cols * cells.rows, distinctCellSets: distinct.size, colorsUsed: used.size, subPalettes: mode.kind === "tiled" ? distinct.size : undefined, shared: cells.shared.map(function (i2) { return pal[i2]; }) },
    };
  }

  // ------------------------------------------------------------ post (art)
  function cleanupOrphans(idx, w, h, passes) {
    var out = Int32Array.from(idx);
    for (var p = 0; p < passes; p++) {
      var next = Int32Array.from(out), changed = false;
      for (var y = 0; y < h; y++)
        for (var x = 0; x < w; x++) {
          var up = out[Math.max(0, y - 1) * w + x], dn = out[Math.min(h - 1, y + 1) * w + x];
          var lf = out[y * w + Math.max(0, x - 1)], rt = out[y * w + Math.min(w - 1, x + 1)];
          if (up === dn && up === lf && up === rt && up !== out[y * w + x]) { next[y * w + x] = up; changed = true; }
        }
      out = next;
      if (!changed) break;
    }
    return out;
  }
  function dilate(mask, w, h, steps) {
    var cur = Uint8Array.from(mask);
    for (var s = 0; s < steps; s++) {
      var nx = Uint8Array.from(cur);
      for (var y = 0; y < h; y++)
        for (var x = 0; x < w; x++) {
          if (cur[y * w + x]) continue;
          if ((y > 0 && cur[(y - 1) * w + x]) || (y < h - 1 && cur[(y + 1) * w + x]) ||
              (x > 0 && cur[y * w + x - 1]) || (x < w - 1 && cur[y * w + x + 1])) nx[y * w + x] = 1;
        }
      cur = nx;
    }
    return cur;
  }
  function outline(idx, w, h, pal, thickness, color, alphaMask) {
    var fg = new Uint8Array(w * h), i;
    if (alphaMask) for (i = 0; i < w * h; i++) fg[i] = alphaMask[i] > 127 ? 1 : 0;
    else {
      var counts = new Map(), bump = function (v) { counts.set(v, (counts.get(v) || 0) + 1); };
      for (var x = 0; x < w; x++) { bump(idx[x]); bump(idx[(h - 1) * w + x]); }
      for (var y = 0; y < h; y++) { bump(idx[y * w]); bump(idx[y * w + w - 1]); }
      var bg = -1, bc = -1;
      counts.forEach(function (c, v) { if (c > bc || (c === bc && v < bg)) { bc = c; bg = v; } });
      for (i = 0; i < w * h; i++) fg[i] = idx[i] !== bg ? 1 : 0;
    }
    var ring = dilate(fg, w, h, thickness), ink;
    pal = pal.slice();
    if (color) {
      ink = pal.findIndex(function (c) { return c[0] === color[0] && c[1] === color[1] && c[2] === color[2]; });
      if (ink < 0) { pal.push(color); ink = pal.length - 1; }
    } else {
      ink = 0;
      for (i = 1; i < pal.length; i++) if (luma(pal[i]) < luma(pal[ink])) ink = i;
    }
    var out = Int32Array.from(idx);
    for (i = 0; i < w * h; i++) if (ring[i] && !fg[i]) out[i] = ink;
    return { indices: out, palette: pal };
  }

  // -------------------------------------------------------------- upscale
  function packed(img) { return new Uint32Array(img.data.buffer.slice(0)); }
  function scale2xPacked(src, w, h) {
    var out = new Uint32Array(w * h * 4), W = w * 2;
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++) {
        var e = src[y * w + x];
        var b = src[Math.max(0, y - 1) * w + x], hh = src[Math.min(h - 1, y + 1) * w + x];
        var d = src[y * w + Math.max(0, x - 1)], f = src[y * w + Math.min(w - 1, x + 1)];
        var e0 = e, e1 = e, e2 = e, e3 = e;
        if (b !== hh && d !== f) {
          if (d === b) e0 = d;
          if (b === f) e1 = f;
          if (d === hh) e2 = d;
          if (hh === f) e3 = f;
        }
        var o = (y * 2) * W + x * 2;
        out[o] = e0; out[o + 1] = e1; out[o + W] = e2; out[o + W + 1] = e3;
      }
    return out;
  }
  function scale3xPacked(src, w, h) {
    var W = w * 3, out = new Uint32Array(w * h * 9);
    function at(x, y) { return src[Math.min(h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x))]; }
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++) {
        var a = at(x - 1, y - 1), b = at(x, y - 1), c = at(x + 1, y - 1);
        var d = at(x - 1, y), e = at(x, y), f = at(x + 1, y);
        var g = at(x - 1, y + 1), hh = at(x, y + 1), i = at(x + 1, y + 1);
        var blk = [e, e, e, e, e, e, e, e, e];
        if (b !== hh && d !== f) {
          var db = d === b, bf = b === f, dh = d === hh, hf = hh === f;
          if (db) blk[0] = d;
          if ((db && e !== c) || (bf && e !== a)) blk[1] = b;
          if (bf) blk[2] = f;
          if ((db && e !== g) || (dh && e !== a)) blk[3] = d;
          if ((bf && e !== i) || (hf && e !== c)) blk[5] = f;
          if (dh) blk[6] = d;
          if ((dh && e !== i) || (hf && e !== g)) blk[7] = hh;
          if (hf) blk[8] = f;
        }
        for (var r = 0; r < 3; r++) for (var q = 0; q < 3; q++) out[(y * 3 + r) * W + x * 3 + q] = blk[r * 3 + q];
      }
    return out;
  }
  function fromPacked(arr, w, h) {
    return { width: w, height: h, data: new Uint8ClampedArray(arr.buffer) };
  }
  function nearestScale(img, f) {
    if (f <= 1) return img;
    var w = img.width, h = img.height, src = packed(img), out = new Uint32Array(w * f * h * f), W = w * f;
    for (var y = 0; y < h * f; y++) {
      var sy = (y / f) | 0;
      for (var x = 0; x < W; x++) out[y * W + x] = src[sy * w + ((x / f) | 0)];
    }
    return fromPacked(out, W, h * f);
  }
  function upscaleImage(img, factor, method) {
    if (factor <= 1) return img;
    if (method === "nearest" || !method) return nearestScale(img, factor);
    var w = img.width, h = img.height, arr = packed(img), rem = factor;
    if (method === "scale3x" && rem % 3 === 0) { arr = scale3xPacked(arr, w, h); w *= 3; h *= 3; rem /= 3; }
    while (rem % 2 === 0) { arr = scale2xPacked(arr, w, h); w *= 2; h *= 2; rem /= 2; }
    if (method === "scale3x" && rem % 3 === 0) { arr = scale3xPacked(arr, w, h); w *= 3; h *= 3; rem /= 3; }
    return nearestScale(fromPacked(arr, w, h), rem);
  }

  // -------------------------------------------------------------- effects
  function boxBlurRGB(src, w, h, radius) {
    var tmp = new Float64Array(src.length), out = new Float64Array(src.length), y, x, c, k;
    for (y = 0; y < h; y++)
      for (c = 0; c < 3; c++) {
        var acc = 0;
        for (k = -radius; k <= radius; k++) acc += src[(y * w + Math.min(w - 1, Math.max(0, k))) * 3 + c];
        for (x = 0; x < w; x++) {
          tmp[(y * w + x) * 3 + c] = acc / (2 * radius + 1);
          acc += src[(y * w + Math.min(w - 1, x + radius + 1)) * 3 + c] - src[(y * w + Math.max(0, x - radius)) * 3 + c];
        }
      }
    for (x = 0; x < w; x++)
      for (c = 0; c < 3; c++) {
        var acc2 = 0;
        for (k = -radius; k <= radius; k++) acc2 += tmp[(Math.min(h - 1, Math.max(0, k)) * w + x) * 3 + c];
        for (y = 0; y < h; y++) {
          out[(y * w + x) * 3 + c] = acc2 / (2 * radius + 1);
          acc2 += tmp[(Math.min(h - 1, y + radius + 1) * w + x) * 3 + c] - tmp[(Math.max(0, y - radius) * w + x) * 3 + c];
        }
      }
    return out;
  }
  function imgToRGB(img) { return toFloatRGB(img); }
  function rgbIntoImg(rgb, img) {
    var n = img.width * img.height;
    for (var i = 0; i < n; i++) for (var c = 0; c < 3; c++) img.data[i * 4 + c] = clamp255(rgb[i * 3 + c]) | 0;
    return img;
  }
  function applyGrid(img, cell) {
    if (cell < 2) return img;
    var w = img.width, h = img.height, d = img.data, op = 0.35;
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++)
        if ((y > 0 && y % cell === 0) || (x > 0 && x % cell === 0))
          for (var c = 0; c < 3; c++) d[(y * w + x) * 4 + c] = d[(y * w + x) * 4 + c] * (1 - op) | 0;
    return img;
  }
  function applyCrt(img) {
    var w = img.width, h = img.height, base = imgToRGB(img);
    var blur = boxBlurRGB(boxBlurRGB(boxBlurRGB(base, w, h, 2), w, h, 2), w, h, 2);
    var cy = (h - 1) / 2 || 1, cx = (w - 1) / 2 || 1;
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++) {
        var dist = Math.sqrt(Math.pow((x - cx) / cx, 2) + Math.pow((y - cy) / cy, 2));
        var fall = Math.min(1, Math.max(0, 1 - 0.4 * dist));
        for (var c = 0; c < 3; c++) {
          var i = (y * w + x) * 3 + c;
          base[i] = clamp255(base[i] + 0.5 * (blur[i] - base[i]) * 0.6) * fall;
        }
      }
    return rgbIntoImg(base, img);
  }
  function applyColorBleed(img, strength) {
    var w = img.width, h = img.height, rgb = imgToRGB(img), n = w * h, width = 3, pad = 1;
    var Y = new Float64Array(n), I = new Float64Array(n), Q = new Float64Array(n), i;
    for (i = 0; i < n; i++) {
      var r = rgb[i * 3] / 255, g = rgb[i * 3 + 1] / 255, b = rgb[i * 3 + 2] / 255;
      Y[i] = 0.299 * r + 0.587 * g + 0.114 * b;
      I[i] = 0.596 * r - 0.274 * g - 0.322 * b;
      Q[i] = 0.211 * r - 0.523 * g + 0.312 * b;
    }
    function blur(ch) {
      var out = new Float64Array(n);
      for (var y = 0; y < h; y++)
        for (var x = 0; x < w; x++) {
          var s = 0;
          for (var k = 0; k < width; k++) s += ch[y * w + Math.min(w - 1, Math.max(0, x - pad + k))];
          out[y * w + x] = ch[y * w + x] * (1 - strength) + (s / width) * strength;
        }
      return out;
    }
    I = blur(I); Q = blur(Q);
    for (i = 0; i < n; i++) {
      rgb[i * 3] = 255 * (Y[i] + 0.9563 * I[i] + 0.621 * Q[i]);
      rgb[i * 3 + 1] = 255 * (Y[i] - 0.2721 * I[i] - 0.6474 * Q[i]);
      rgb[i * 3 + 2] = 255 * (Y[i] - 1.107 * I[i] + 1.7046 * Q[i]);
    }
    return rgbIntoImg(rgb, img);
  }
  function applyChromatic(img, shift) {
    var w = img.width, h = img.height, src = Uint8ClampedArray.from(img.data), d = img.data;
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++) {
        d[(y * w + x) * 4] = src[(y * w + Math.max(0, x - shift)) * 4];
        d[(y * w + x) * 4 + 2] = src[(y * w + Math.min(w - 1, x + shift)) * 4 + 2];
      }
    return img;
  }
  function applyPhosphor(img) {
    var w = img.width, h = img.height, d = img.data, fade = 0.65;
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++) {
        var keep = x % 3;
        for (var c = 0; c < 3; c++) if (c !== keep) d[(y * w + x) * 4 + c] = d[(y * w + x) * 4 + c] * fade | 0;
      }
    return img;
  }
  function applyScanlines(img) {
    var w = img.width, h = img.height, d = img.data;
    for (var y = 0; y < h; y += 2) for (var x = 0; x < w; x++) for (var c = 0; c < 3; c++) d[(y * w + x) * 4 + c] = d[(y * w + x) * 4 + c] * 0.65 | 0;
    return img;
  }
  function applyCurvature(img, amount) {
    if (amount <= 0) return img;
    var w = img.width, h = img.height, src = new Uint32Array(img.data.buffer.slice(0)), out = new Uint32Array(w * h);
    var black = new Uint32Array(new Uint8ClampedArray([0, 0, 0, 255]).buffer)[0];
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++) {
        var nx = (x + 0.5) / w * 2 - 1, ny = (y + 0.5) / h * 2 - 1, f = 1 + amount * (nx * nx + ny * ny);
        var sx = Math.round((nx * f + 1) / 2 * w - 0.5), sy = Math.round((ny * f + 1) / 2 * h - 0.5);
        out[y * w + x] = sx >= 0 && sx < w && sy >= 0 && sy < h ? src[sy * w + sx] : black;
      }
    return fromPacked(out, w, h);
  }

  // --------------------------------------------------------------- render
  function defaults() {
    var d = data().defaults;
    return {
      palette: d.palette, pixelSize: d.pixel_size, dither: d.dither, upscale: d.upscale,
      saturation: d.saturation, contrast: d.contrast, invert: d.invert, posterize: d.posterize,
      colors: d.colors, seed: d.seed, downscale: d.downscale, colorspace: d.colorspace,
      serpentine: d.serpentine, bayerSize: d.bayer_size, hardware: d.hardware, upscaler: d.upscaler,
      outline: d.outline, outlineColor: d.outline_color, grid: d.grid, chromatic: d.chromatic,
      colorBleed: d.color_bleed, curvature: d.curvature, cleanup: d.cleanup, crt: d.crt,
      phosphor: d.phosphor, scanlines: d.scanlines, scale: d.scale, customPalette: null,
    };
  }
  var SNAKE = { pixel_size: "pixelSize", bayer_size: "bayerSize", color_bleed: "colorBleed", outline_color: "outlineColor" };
  function fromPythonOptions(opts) {
    var out = {};
    Object.keys(opts).forEach(function (k) { out[SNAKE[k] || k] = opts[k]; });
    return out;
  }
  function presetParams(name) {
    var p = data().presets[name];
    if (!p) throw new Error("Unknown preset " + name);
    return Object.assign(defaults(), fromPythonOptions(p.options));
  }
  function resolvePalette(name) {
    var d = data(), key = String(name).toLowerCase();
    key = d.paletteAliases[key] || key;
    var pal = d.palettes[key];
    if (!pal) throw new Error("Unknown palette " + name);
    return pal.map(hexToRgb);
  }

  function render(params, src) {
    var t0 = Date.now();
    var o = Object.assign(defaults(), params || {});
    var mode = o.hardware ? data().hardware[o.hardware] : null;
    if (o.hardware && !mode) throw new Error("Unknown hardware mode " + o.hardware);
    var pixelSize = o.pixelSize;
    if (mode && params && params.pixelSize == null) pixelSize = Math.max(mode.native[0], mode.native[1]);
    var w = src.width, h = src.height, n = w * h;
    var rgb = toFloatRGB(src);
    var alpha = hasAlpha(src) ? src.data : null;
    enhance(rgb, n, { invert: !!o.invert, contrast: +o.contrast, saturation: +o.saturation });
    var ts = targetSize(w, h, pixelSize), tw = ts[0], th = ts[1];
    if (tw !== w || th !== h) rgb = (o.downscale === "nearest" ? nearestResample : boxResample)(rgb, w, h, 3, tw, th);
    if (mode && mode.pixelWidth > 1) {
      var narrow = Math.max(1, pyRound(tw / mode.pixelWidth));
      rgb = boxResample(rgb, tw, th, 3, narrow, th); tw = narrow;
    }
    if (o.posterize) posterize(rgb, +o.posterize);
    for (var i = 0; i < rgb.length; i++) rgb[i] = clamp255(rgb[i]);

    var pal, idx, report = null;
    if (mode) {
      var hw = applyHardware(rgb, tw, th, mode, o);
      pal = hw.palette; idx = hw.indices; report = hw.report;
    } else {
      if (o.customPalette && o.customPalette.length) pal = o.customPalette.map(function (c) { return typeof c === "string" ? hexToRgb(c) : c; });
      else if (o.palette === "auto") {
        var ints = new Uint8Array(rgb.length);
        for (i = 0; i < rgb.length; i++) ints[i] = Math.round(rgb[i]);
        pal = extractPalette(ints, tw * th, +o.colors || 16, o.seed);
      } else pal = resolvePalette(o.palette);
      idx = Int32Array.from(ditherIndices(rgb, tw, th, pal, o));
    }
    if (o.cleanup) idx = cleanupOrphans(idx, tw, th, +o.cleanup);
    if (mode && mode.pixelWidth > 1) {
      var wide = new Int32Array(tw * mode.pixelWidth * th);
      for (var y = 0; y < th; y++) for (var x = 0; x < tw * mode.pixelWidth; x++) wide[y * tw * mode.pixelWidth + x] = idx[y * tw + ((x / mode.pixelWidth) | 0)];
      idx = wide; tw *= mode.pixelWidth;
    }
    var artAlpha = null;
    if (alpha) {
      artAlpha = new Uint8Array(tw * th);
      for (y = 0; y < th; y++) for (x = 0; x < tw; x++) {
        var sx = Math.min(w - 1, Math.floor((x + 0.5) * w / tw)), sy = Math.min(h - 1, Math.floor((y + 0.5) * h / th));
        artAlpha[y * tw + x] = alpha[(sy * w + sx) * 4 + 3];
      }
    }
    if (o.outline) {
      var col = o.outlineColor ? (typeof o.outlineColor === "string" ? hexToRgb(o.outlineColor) : o.outlineColor) : null;
      var ol = outline(idx, tw, th, pal, +o.outline, col, artAlpha);
      idx = ol.indices; pal = ol.palette;
    }

    var art = makeImage(tw, th);
    for (i = 0; i < tw * th; i++) {
      var c = pal[idx[i]];
      art.data[i * 4] = c[0]; art.data[i * 4 + 1] = c[1]; art.data[i * 4 + 2] = c[2];
      art.data[i * 4 + 3] = artAlpha ? artAlpha[i] : 255;
    }
    var up = Math.max(1, o.upscale | 0);
    var out = upscaleImage(art, up, o.upscaler);
    if (o.grid && up > 1) applyGrid(out, up);
    if (o.crt) applyCrt(out);
    if (+o.colorBleed) applyColorBleed(out, +o.colorBleed);
    if (+o.chromatic) applyChromatic(out, o.chromatic | 0);
    if (o.phosphor) applyPhosphor(out);
    if (o.scanlines) applyScanlines(out);
    if (+o.curvature) out = applyCurvature(out, +o.curvature);
    if ((o.scale | 0) > 1) out = nearestScale(out, o.scale | 0);
    if (artAlpha) {
      for (y = 0; y < out.height; y++) for (x = 0; x < out.width; x++) {
        out.data[(y * out.width + x) * 4 + 3] = artAlpha[Math.min(th - 1, Math.floor(y * th / out.height)) * tw + Math.min(tw - 1, Math.floor(x * tw / out.width))];
      }
    }
    var used = new Set();
    for (i = 0; i < idx.length; i++) used.add(idx[i]);
    return {
      image: out, indices: idx, palette: pal, logicalWidth: tw, logicalHeight: th, alpha: artAlpha,
      stats: { ms: Date.now() - t0, colorsUsed: used.size, paletteSize: pal.length, clash: report },
    };
  }

  // -------------------------------------------------------------- exports
  function toSVG(idx, w, h, pal, alpha) {
    var runs = new Map();
    for (var y = 0; y < h; y++) {
      var x = 0;
      while (x < w) {
        var v = idx[y * w + x], start = x, transparent = alpha ? alpha[y * w + x] < 128 : false;
        while (x < w && idx[y * w + x] === v && (alpha ? alpha[y * w + x] < 128 : false) === transparent) x++;
        if (transparent) continue;
        if (!runs.has(v)) runs.set(v, []);
        runs.get(v).push('<rect x="' + start + '" y="' + y + '" width="' + (x - start) + '" height="1"/>');
      }
    }
    var parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h + '" shape-rendering="crispEdges">'];
    Array.from(runs.keys()).sort(function (a, b) { return a - b; }).forEach(function (v2) {
      parts.push('<g fill="' + rgbToHex(pal[v2]) + '">');
      parts.push.apply(parts, runs.get(v2));
      parts.push("</g>");
    });
    parts.push("</svg>");
    return parts.join("\n") + "\n";
  }
  function toJSON(idx, w, h, pal) {
    var rows = [];
    for (var y = 0; y < h; y++) rows.push(Array.from(idx.subarray ? idx.subarray(y * w, y * w + w) : idx.slice(y * w, y * w + w)));
    return JSON.stringify({ format: "pixelate-indexed", version: 1, width: w, height: h, palette: pal.map(rgbToHex), pixels: rows }) + "\n";
  }
  function toGPL(pal, name) {
    var lines = ["GIMP Palette", "Name: " + (name || "pixelate"), "Columns: " + Math.min(16, pal.length), "#"];
    pal.forEach(function (c) { lines.push(String(c[0]).padStart(3) + " " + String(c[1]).padStart(3) + " " + String(c[2]).padStart(3) + "\t" + rgbToHex(c)); });
    return lines.join("\n") + "\n";
  }
  function toHEX(pal) {
    return pal.map(function (c) { return rgbToHex(c).slice(1); }).join("\n") + "\n";
  }

  return {
    version: function () { return data().version; },
    setData: setData,
    defaults: defaults,
    presetParams: presetParams,
    fromPythonOptions: fromPythonOptions,
    resolvePalette: resolvePalette,
    render: render,
    srgbToLab: srgbToLab,
    labToSrgb: labToSrgb,
    hexToRgb: hexToRgb,
    rgbToHex: rgbToHex,
    getLut: getLut,
    lutKey: lutKey,
    bayerMatrix: bayerMatrix,
    threshold: threshold,
    ditherIndices: ditherIndices,
    extractPalette: extractPalette,
    applyHardware: applyHardware,
    cleanupOrphans: cleanupOrphans,
    upscaleImage: upscaleImage,
    targetSize: targetSize,
    toSVG: toSVG,
    toJSON: toJSON,
    toGPL: toGPL,
    toHEX: toHEX,
  };
});
