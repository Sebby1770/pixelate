/* PIXELATE web lab — local-only pixel art (no upload). */

const PALETTES = {
  gameboy: [
    [15, 56, 15], [48, 98, 48], [139, 172, 15], [155, 188, 15],
  ],
  nes: [
    [0, 0, 0], [124, 124, 124], [188, 188, 188], [252, 252, 252],
    [124, 0, 0], [228, 0, 88], [248, 56, 0], [252, 160, 68],
    [172, 124, 0], [0, 88, 0], [0, 168, 0], [88, 248, 152],
    [0, 64, 88], [0, 120, 248], [104, 136, 252], [216, 168, 248],
  ],
  pico8: [
    [0, 0, 0], [29, 43, 83], [126, 37, 83], [0, 135, 81],
    [171, 82, 54], [95, 87, 79], [194, 195, 199], [255, 241, 232],
    [255, 0, 77], [255, 163, 0], [255, 236, 39], [0, 228, 54],
    [41, 173, 255], [131, 118, 156], [255, 119, 168], [255, 204, 170],
  ],
  c64: [
    [0, 0, 0], [255, 255, 255], [136, 0, 0], [170, 255, 238],
    [204, 68, 204], [0, 204, 85], [0, 0, 170], [238, 238, 119],
    [221, 136, 85], [102, 68, 0], [255, 119, 119], [51, 51, 51],
    [119, 119, 119], [170, 255, 102], [0, 136, 255], [187, 187, 187],
  ],
  sweetie16: [
    [26, 28, 44], [93, 39, 93], [177, 62, 83], [239, 125, 87],
    [255, 205, 117], [167, 240, 112], [56, 183, 100], [37, 113, 121],
    [41, 54, 111], [59, 93, 201], [65, 166, 246], [115, 239, 247],
    [244, 244, 244], [148, 176, 194], [86, 108, 134], [51, 60, 87],
  ],
  vaporwave: [
    [15, 12, 33], [45, 24, 72], [90, 40, 120], [255, 113, 206],
    [1, 205, 254], [5, 255, 161], [185, 103, 255], [255, 251, 150],
    [255, 110, 199], [148, 198, 255], [36, 23, 52], [255, 255, 255],
  ],
  macintosh: [
    [255, 255, 255], [252, 243, 5], [255, 100, 2], [221, 8, 6],
    [242, 8, 132], [70, 0, 165], [0, 0, 212], [2, 171, 234],
    [31, 183, 20], [0, 100, 17], [86, 44, 5], [144, 113, 58],
    [192, 192, 192], [128, 128, 128], [64, 64, 64], [0, 0, 0],
  ],
  grayscale: [0, 32, 64, 96, 128, 160, 192, 224, 255].map((v) => [v, v, v]),
};

const KERNELS = {
  floyd: [
    [0, 1, 7 / 16], [1, -1, 3 / 16], [1, 0, 5 / 16], [1, 1, 1 / 16],
  ],
  jjn: [
    [0, 1, 7 / 48], [0, 2, 5 / 48],
    [1, -2, 3 / 48], [1, -1, 5 / 48], [1, 0, 7 / 48], [1, 1, 5 / 48], [1, 2, 3 / 48],
    [2, -2, 1 / 48], [2, -1, 3 / 48], [2, 0, 5 / 48], [2, 1, 3 / 48], [2, 2, 1 / 48],
  ],
  sierra3: [
    [0, 1, 5 / 32], [0, 2, 3 / 32],
    [1, -2, 2 / 32], [1, -1, 4 / 32], [1, 0, 5 / 32], [1, 1, 4 / 32], [1, 2, 2 / 32],
    [2, -1, 2 / 32], [2, 0, 3 / 32], [2, 1, 2 / 32],
  ],
  sierraLite: [
    [0, 1, 2 / 4], [1, -1, 1 / 4], [1, 0, 1 / 4],
  ],
};

const BAYER4 = [
  [0, 8, 2, 10],
  [12, 4, 14, 6],
  [3, 11, 1, 9],
  [15, 7, 13, 5],
];

const els = {
  file: document.getElementById("file"),
  palette: document.getElementById("palette"),
  paletteB: document.getElementById("paletteB"),
  dither: document.getElementById("dither"),
  downscale: document.getElementById("downscale"),
  pixelSize: document.getElementById("pixelSize"),
  pixelSizeVal: document.getElementById("pixelSizeVal"),
  upscale: document.getElementById("upscale"),
  upscaleVal: document.getElementById("upscaleVal"),
  crt: document.getElementById("crt"),
  scanlines: document.getElementById("scanlines"),
  serpentine: document.getElementById("serpentine"),
  phosphor: document.getElementById("phosphor"),
  posterize: document.getElementById("posterize"),
  posterizeVal: document.getElementById("posterizeVal"),
  compare: document.getElementById("compare"),
  download: document.getElementById("download"),
  srcCanvas: document.getElementById("srcCanvas"),
  outCanvas: document.getElementById("outCanvas"),
  outFrame: document.getElementById("outFrame"),
  status: document.getElementById("status"),
  swatches: document.getElementById("swatches"),
};

const appEl = document.querySelector(".app");

let sourceImage = null;
let renderTimer = 0;
let compareOn = false;

function clamp(v) {
  return v < 0 ? 0 : v > 255 ? 255 : v;
}

function srgbToLab(r, g, b) {
  const lin = (c) => {
    c /= 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const R = lin(clamp(r));
  const G = lin(clamp(g));
  const B = lin(clamp(b));
  const x = (0.4124564 * R + 0.3575761 * G + 0.1804375 * B) / 0.95047;
  const y = 0.2126729 * R + 0.7151522 * G + 0.0721750 * B;
  const z = (0.0193339 * R + 0.1191920 * G + 0.9503041 * B) / 1.08883;
  const f = (t) => {
    const d = 6 / 29;
    return t > d ** 3 ? Math.cbrt(t) : t / (3 * d * d) + 4 / 29;
  };
  const fx = f(x);
  const fy = f(y);
  const fz = f(z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function paletteLab(palette) {
  return palette.map((c) => srgbToLab(c[0], c[1], c[2]));
}

function nearestIndex(r, g, b, palette, labPal) {
  const lab = srgbToLab(r, g, b);
  let best = 0;
  let bestD = Infinity;
  for (let i = 0; i < labPal.length; i++) {
    const dL = lab[0] - labPal[i][0];
    const da = lab[1] - labPal[i][1];
    const db = lab[2] - labPal[i][2];
    const d = dL * dL + da * da + db * db;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

function errorDiffuse(data, w, h, palette, labPal, kernel, serpentine) {
  const buf = new Float32Array(data.length);
  for (let i = 0; i < data.length; i++) buf[i] = data[i];
  for (let y = 0; y < h; y++) {
    const reverse = serpentine && y % 2 === 1;
    const start = reverse ? w - 1 : 0;
    const end = reverse ? -1 : w;
    const step = reverse ? -1 : 1;
    for (let x = start; x !== end; x += step) {
      const i = (y * w + x) * 4;
      const r = buf[i];
      const g = buf[i + 1];
      const b = buf[i + 2];
      const idx = nearestIndex(r, g, b, palette, labPal);
      const nr = palette[idx][0];
      const ng = palette[idx][1];
      const nb = palette[idx][2];
      const er = r - nr;
      const eg = g - ng;
      const eb = b - nb;
      buf[i] = nr;
      buf[i + 1] = ng;
      buf[i + 2] = nb;
      for (let k = 0; k < kernel.length; k++) {
        let dy = kernel[k][0];
        let dx = kernel[k][1];
        const wt = kernel[k][2];
        if (reverse) dx = -dx;
        const nx = x + dx;
        const ny = y + dy;
        if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
          const j = (ny * w + nx) * 4;
          buf[j] += er * wt;
          buf[j + 1] += eg * wt;
          buf[j + 2] += eb * wt;
        }
      }
    }
  }
  for (let i = 0; i < data.length; i += 4) {
    data[i] = clamp(buf[i]);
    data[i + 1] = clamp(buf[i + 1]);
    data[i + 2] = clamp(buf[i + 2]);
  }
}

function atkinson(data, w, h, palette, labPal, serpentine) {
  const offsets = [[0, 1], [0, 2], [1, -1], [1, 0], [1, 1], [2, 0]];
  const buf = new Float32Array(data.length);
  for (let i = 0; i < data.length; i++) buf[i] = data[i];
  for (let y = 0; y < h; y++) {
    const reverse = serpentine && y % 2 === 1;
    const start = reverse ? w - 1 : 0;
    const end = reverse ? -1 : w;
    const step = reverse ? -1 : 1;
    for (let x = start; x !== end; x += step) {
      const i = (y * w + x) * 4;
      const r = buf[i];
      const g = buf[i + 1];
      const b = buf[i + 2];
      const idx = nearestIndex(r, g, b, palette, labPal);
      const nr = palette[idx][0];
      const ng = palette[idx][1];
      const nb = palette[idx][2];
      const er = (r - nr) / 8;
      const eg = (g - ng) / 8;
      const eb = (b - nb) / 8;
      buf[i] = nr;
      buf[i + 1] = ng;
      buf[i + 2] = nb;
      for (let k = 0; k < offsets.length; k++) {
        let dy = offsets[k][0];
        let dx = offsets[k][1];
        if (reverse) dx = -dx;
        const nx = x + dx;
        const ny = y + dy;
        if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
          const j = (ny * w + nx) * 4;
          buf[j] += er;
          buf[j + 1] += eg;
          buf[j + 2] += eb;
        }
      }
    }
  }
  for (let i = 0; i < data.length; i += 4) {
    data[i] = clamp(buf[i]);
    data[i + 1] = clamp(buf[i + 1]);
    data[i + 2] = clamp(buf[i + 2]);
  }
}

function quantize(data, w, h, palette, labPal) {
  for (let i = 0; i < data.length; i += 4) {
    const idx = nearestIndex(data[i], data[i + 1], data[i + 2], palette, labPal);
    data[i] = palette[idx][0];
    data[i + 1] = palette[idx][1];
    data[i + 2] = palette[idx][2];
  }
}

function bayer(data, w, h, palette, labPal) {
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      const t = (BAYER4[y & 3][x & 3] / 16 - 0.5) * 32;
      const idx = nearestIndex(data[i] + t, data[i + 1] + t, data[i + 2] + t, palette, labPal);
      data[i] = palette[idx][0];
      data[i + 1] = palette[idx][1];
      data[i + 2] = palette[idx][2];
    }
  }
}

function posterizeLevels() {
  if (!els.posterize) return 0;
  let n = Number(els.posterize.value);
  if (n === 1) {
    els.posterize.value = "0";
    n = 0;
  }
  if (!n || n < 2) return 0;
  return Math.min(8, n);
}

function posterizeData(data, levels) {
  if (!levels || levels < 2) return;
  const n = levels - 1;
  for (let i = 0; i < data.length; i += 4) {
    for (let c = 0; c < 3; c++) {
      const q = Math.round((data[i + c] * n) / 255);
      data[i + c] = Math.round(q * (255 / n));
    }
  }
}

function applyPhosphorCanvas(canvas, ctx, strength) {
  const s = strength == null ? 0.35 : strength;
  const fade = 1 - s;
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const data = imageData.data;
  const w = canvas.width;
  const h = canvas.height;
  for (let x = 0; x < w; x++) {
    const lane = x % 3;
    for (let y = 0; y < h; y++) {
      const i = (y * w + x) * 4;
      if (lane !== 0) data[i] *= fade;
      if (lane !== 1) data[i + 1] *= fade;
      if (lane !== 2) data[i + 2] *= fade;
    }
  }
  ctx.putImageData(imageData, 0, 0);
}

function dither(imageData, name, palette, serpentine) {
  const { data, width, height } = imageData;
  const labPal = paletteLab(palette);
  const serp = serpentine !== false;
  if (name === "none") quantize(data, width, height, palette, labPal);
  else if (name === "bayer") bayer(data, width, height, palette, labPal);
  else if (name === "atkinson") atkinson(data, width, height, palette, labPal, serp);
  else if (name === "jjn") errorDiffuse(data, width, height, palette, labPal, KERNELS.jjn, serp);
  else if (name === "sierra3") errorDiffuse(data, width, height, palette, labPal, KERNELS.sierra3, serp);
  else if (name === "sierra-lite" || name === "sierra_lite") {
    errorDiffuse(data, width, height, palette, labPal, KERNELS.sierraLite, serp);
  } else errorDiffuse(data, width, height, palette, labPal, KERNELS.floyd, serp);
}

function fitSize(w, h, maxDim) {
  if (Math.max(w, h) <= maxDim) return { w, h };
  if (w >= h) return { w: maxDim, h: Math.max(1, Math.round(h * (maxDim / w))) };
  return { h: maxDim, w: Math.max(1, Math.round(w * (maxDim / h))) };
}

function paintSource(img) {
  const c = els.srcCanvas;
  const ctx = c.getContext("2d");
  const max = 360;
  const s = fitSize(img.width, img.height, max);
  c.width = s.w;
  c.height = s.h;
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(img, 0, 0, s.w, s.h);
}

function boxDownscale(img, dw, dh) {
  const sw = img.width;
  const sh = img.height;
  const src = document.createElement("canvas");
  src.width = sw;
  src.height = sh;
  const sctx = src.getContext("2d", { willReadFrequently: true });
  sctx.drawImage(img, 0, 0);
  const srcData = sctx.getImageData(0, 0, sw, sh).data;
  const out = sctx.createImageData(dw, dh);
  const dst = out.data;
  for (let y = 0; y < dh; y++) {
    const y0 = Math.floor((y * sh) / dh);
    const y1 = Math.max(y0 + 1, Math.floor(((y + 1) * sh) / dh));
    for (let x = 0; x < dw; x++) {
      const x0 = Math.floor((x * sw) / dw);
      const x1 = Math.max(x0 + 1, Math.floor(((x + 1) * sw) / dw));
      let r = 0;
      let g = 0;
      let b = 0;
      let a = 0;
      let n = 0;
      for (let yy = y0; yy < y1; yy++) {
        let i = (yy * sw + x0) * 4;
        for (let xx = x0; xx < x1; xx++) {
          r += srcData[i];
          g += srcData[i + 1];
          b += srcData[i + 2];
          a += srcData[i + 3];
          n++;
          i += 4;
        }
      }
      const j = (y * dw + x) * 4;
      dst[j] = r / n;
      dst[j + 1] = g / n;
      dst[j + 2] = b / n;
      dst[j + 3] = a / n;
    }
  }
  return out;
}

function downscaleTo(img, dw, dh, mode) {
  const small = document.createElement("canvas");
  small.width = dw;
  small.height = dh;
  const sctx = small.getContext("2d", { willReadFrequently: true });
  const filter = mode || "box";
  if (filter === "nearest") {
    sctx.imageSmoothingEnabled = false;
    sctx.drawImage(img, 0, 0, dw, dh);
  } else if (filter === "lanczos") {
    sctx.imageSmoothingEnabled = true;
    if ("imageSmoothingQuality" in sctx) sctx.imageSmoothingQuality = "high";
    sctx.drawImage(img, 0, 0, dw, dh);
  } else {
    sctx.putImageData(boxDownscale(img, dw, dh), 0, 0);
  }
  return small;
}

function pixelateBuffer(palette) {
  const pixelSize = Number(els.pixelSize.value);
  const ditherName = els.dither.value;
  const serpentine = !els.serpentine || els.serpentine.checked;
  const dim = fitSize(sourceImage.width, sourceImage.height, pixelSize);
  const filter = els.downscale ? els.downscale.value : "box";
  const small = downscaleTo(sourceImage, dim.w, dim.h, filter);
  const sctx = small.getContext("2d", { willReadFrequently: true });
  const imageData = sctx.getImageData(0, 0, dim.w, dim.h);
  const levels = posterizeLevels();
  if (levels >= 2) posterizeData(imageData.data, levels);
  dither(imageData, ditherName, palette, serpentine);
  sctx.putImageData(imageData, 0, 0);
  return { small, dim };
}

function render() {
  if (!sourceImage) return;
  const palette = PALETTES[els.palette.value];
  const upscale = Number(els.upscale.value);
  const ditherName = els.dither.value;
  const t0 = performance.now();

  const a = pixelateBuffer(palette);
  const dim = a.dim;

  const out = els.outCanvas;
  out.width = dim.w * upscale;
  out.height = dim.h * upscale;
  const octx = out.getContext("2d", { willReadFrequently: true });
  octx.imageSmoothingEnabled = false;

  if (compareOn && els.paletteB) {
    const bPal = PALETTES[els.paletteB.value] || palette;
    const b = pixelateBuffer(bPal);
    const mid = Math.floor(out.width / 2);
    const srcMid = Math.floor(dim.w / 2);
    octx.drawImage(a.small, 0, 0, srcMid, dim.h, 0, 0, mid, out.height);
    octx.drawImage(b.small, srcMid, 0, dim.w - srcMid, dim.h, mid, 0, out.width - mid, out.height);
    octx.fillStyle = "rgba(60,255,122,0.85)";
    octx.fillRect(Math.max(0, mid - 1), 0, 2, out.height);
  } else {
    octx.drawImage(a.small, 0, 0, out.width, out.height);
  }

  if (els.phosphor && els.phosphor.checked) {
    applyPhosphorCanvas(out, octx);
  }

  els.outFrame.classList.toggle("crt-on", els.crt.checked);
  els.outFrame.classList.toggle("scan-on", els.scanlines.checked);

  const ms = (performance.now() - t0).toFixed(0);
  const cmp = compareOn
    ? `  ·  ${els.palette.value}|${els.paletteB.value}`
    : "";
  els.status.textContent =
    `${dim.w}×${dim.h} → ${out.width}×${out.height}  ·  ${ditherName}  ·  ${ms}ms  ·  drop zone${cmp}`;
}

function paintSwatches(name) {
  const pal = PALETTES[name];
  els.swatches.innerHTML = pal
    .map((c) => `<i style="background:rgb(${c[0]},${c[1]},${c[2]})"></i>`)
    .join("");
}

function makeDemo() {
  const c = document.createElement("canvas");
  c.width = 320;
  c.height = 200;
  const ctx = c.getContext("2d");
  const g = ctx.createLinearGradient(0, 0, 320, 200);
  g.addColorStop(0, "#1a1033");
  g.addColorStop(0.45, "#c13b5e");
  g.addColorStop(1, "#f4c56e");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 320, 200);
  ctx.fillStyle = "#2ce8f5";
  ctx.beginPath();
  ctx.arc(70, 55, 28, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#0b1a12";
  ctx.fillRect(0, 148, 320, 52);
  ctx.fillStyle = "#3e8948";
  for (let x = 0; x < 320; x += 18) {
    ctx.fillRect(x, 130, 12, 40);
  }
  const img = new Image();
  img.onload = () => {
    sourceImage = img;
    paintSource(img);
    render();
  };
  img.src = c.toDataURL("image/png");
}

function populatePalettes() {
  const keys = ["gameboy", "nes", "pico8", "c64", "sweetie16", "vaporwave", "macintosh", "grayscale"];
  keys.forEach((k) => {
    const o = document.createElement("option");
    o.value = k;
    o.textContent = k;
    els.palette.appendChild(o);
    if (els.paletteB) {
      const o2 = document.createElement("option");
      o2.value = k;
      o2.textContent = k;
      els.paletteB.appendChild(o2);
    }
  });
  els.palette.value = "pico8";
  if (els.paletteB) els.paletteB.value = "gameboy";
  paintSwatches(els.palette.value);
}

function scheduleRender() {
  els.pixelSizeVal.textContent = els.pixelSize.value;
  els.upscaleVal.textContent = els.upscale.value;
  if (els.posterizeVal && els.posterize) {
    const n = posterizeLevels();
    els.posterizeVal.textContent = n < 2 ? "off" : String(n);
  }
  clearTimeout(renderTimer);
  renderTimer = setTimeout(render, 40);
}

populatePalettes();
makeDemo();

function loadImageFile(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const img = new Image();
    img.onload = () => {
      sourceImage = img;
      paintSource(img);
      render();
      els.status.textContent = `loaded ${file.name} (${img.width}×${img.height}) · drop zone`;
    };
    img.src = reader.result;
  };
  reader.readAsDataURL(file);
}

function firstImageFile(fileList) {
  if (!fileList || !fileList.length) return null;
  for (let i = 0; i < fileList.length; i++) {
    if (fileList[i].type && fileList[i].type.startsWith("image/")) return fileList[i];
  }
  return fileList[0];
}

function setDropTarget(on) {
  document.body.classList.toggle("drop-target", on);
  if (appEl) appEl.classList.toggle("drop-target", on);
}

function blockDrag(e) {
  e.preventDefault();
  e.stopPropagation();
}

["dragenter", "dragover"].forEach((name) => {
  document.body.addEventListener(name, (e) => {
    blockDrag(e);
    setDropTarget(true);
  });
  if (appEl) {
    appEl.addEventListener(name, (e) => {
      blockDrag(e);
      setDropTarget(true);
    });
  }
});

document.body.addEventListener("dragleave", (e) => {
  if (e.target === document.body) setDropTarget(false);
});
if (appEl) {
  appEl.addEventListener("dragleave", (e) => {
    if (e.target === appEl) setDropTarget(false);
  });
}

function onDrop(e) {
  blockDrag(e);
  setDropTarget(false);
  const file = firstImageFile(e.dataTransfer && e.dataTransfer.files);
  if (file) loadImageFile(file);
}

document.body.addEventListener("drop", onDrop);
if (appEl) appEl.addEventListener("drop", onDrop);

els.file.addEventListener("change", (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  loadImageFile(file);
});

["palette", "paletteB", "dither", "downscale", "pixelSize", "upscale", "crt", "scanlines", "serpentine", "phosphor", "posterize"].forEach((id) => {
  if (!els[id]) return;
  els[id].addEventListener("input", () => {
    if (id === "palette") paintSwatches(els.palette.value);
    scheduleRender();
  });
  els[id].addEventListener("change", () => {
    if (id === "palette") paintSwatches(els.palette.value);
    scheduleRender();
  });
});

if (els.compare) {
  els.compare.addEventListener("click", () => {
    compareOn = !compareOn;
    els.compare.setAttribute("aria-pressed", compareOn ? "true" : "false");
    scheduleRender();
  });
}

els.download.addEventListener("click", () => {
  const a = document.createElement("a");
  a.download = "pixelate.png";
  a.href = els.outCanvas.toDataURL("image/png");
  a.click();
});
