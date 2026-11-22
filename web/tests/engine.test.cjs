/* node --test web/tests/ — parity + invariants for web/engine.js */
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

const DATA = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "data.json"), "utf8"));
const FX = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures.json"), "utf8"));
const E = require(path.join(__dirname, "..", "engine.js"));
E.setData(DATA);

function gradient(w, h) {
  const rgb = new Float64Array(w * h * 3);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 3;
      rgb[i] = (x * 255) / (w - 1);
      rgb[i + 1] = (y * 255) / (h - 1);
      rgb[i + 2] = 255 - (x * 255) / (w - 1);
    }
  return rgb;
}
function rgbaImage(w, h, fn) {
  const data = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const c = fn(x, y);
      data.set([c[0], c[1], c[2], c[3] == null ? 255 : c[3]], (y * w + x) * 4);
    }
  return { width: w, height: h, data };
}
const PICO8 = E.resolvePalette("pico8");
const DEFAULT_OPTS = { colorspace: "lab", serpentine: true, bayerSize: 4 };
const agreement = (a, b) => a.reduce((n, v, i) => n + (v === b[i] ? 1 : 0), 0) / a.length;

test("Lab conversion matches Python", () => {
  for (const [hex, ref] of Object.entries(FX.lab)) {
    const [r, g, b] = E.hexToRgb(hex);
    E.srgbToLab(r, g, b).forEach((v, i) => assert.ok(Math.abs(v - ref[i]) < 1e-4, `${hex}[${i}] ${v} vs ${ref[i]}`));
  }
});

test("LUT agrees with brute-force Lab search at cell centers", () => {
  const table = E.getLut(PICO8, "lab");
  const labs = PICO8.map((c) => E.srgbToLab(...c));
  let checked = 0;
  for (let r = 1.5; r < 256; r += 4 * 7)
    for (let g = 1.5; g < 256; g += 4 * 5)
      for (let b = 1.5; b < 256; b += 4 * 3) {
        const p = E.srgbToLab(r, g, b);
        let best = 0, bd = Infinity;
        labs.forEach((q, k) => { const d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2; if (d < bd) { bd = d; best = k; } });
        assert.equal(table[E.lutKey(r, g, b)], best);
        checked++;
      }
  assert.ok(checked > 500);
});

test("dither indices match Python on the reference gradient", () => {
  const { w, h } = FX.gradient;
  const rgb = gradient(w, h);
  const decode = (s) => Array.from(s, (ch) => parseInt(ch, 16));
  for (const name of ["floyd", "atkinson", "pattern", "bluenoise", "halftone", "bayer", "none"]) {
    const js = Array.from(E.ditherIndices(rgb, w, h, PICO8, { ...DEFAULT_OPTS, dither: name }));
    const score = agreement(js, decode(FX[name]));
    assert.ok(score >= 0.97, `${name}: only ${(score * 100).toFixed(1)}% of pixels match Python`);
  }
});

test("threshold maps are permutations shared with Python", () => {
  for (const name of ["pattern", "halftone", "bluenoise"]) {
    const t = E.threshold(name);
    const ranks = Array.from(t.values, (v) => Math.round(v * t.size * t.size)).sort((a, b) => a - b);
    ranks.forEach((v, i) => assert.equal(v, i));
  }
  const bayer8 = E.bayerMatrix(8);
  const fromData = E.threshold("pattern");
  assert.deepEqual(Array.from(bayer8.values), Array.from(fromData.values));
});

test("every dither stays inside the palette", () => {
  const rgb = gradient(24, 16);
  const allowed = new Set(PICO8.map((_, i) => i));
  for (const name of Object.keys(DATA.dithers)) {
    for (const v of E.ditherIndices(rgb, 24, 16, PICO8, { ...DEFAULT_OPTS, dither: name })) assert.ok(allowed.has(v), name);
  }
});

test("pattern dithers track mean gray", () => {
  const gray = E.resolvePalette("grayscale");
  for (const name of ["pattern", "bluenoise", "halftone"]) {
    for (const level of [40, 128, 200]) {
      const rgb = new Float64Array(32 * 32 * 3).fill(level);
      const idx = E.ditherIndices(rgb, 32, 32, gray, { ...DEFAULT_OPTS, dither: name });
      const mean = Array.from(idx).reduce((s, k) => s + gray[k][0], 0) / idx.length;
      assert.ok(Math.abs(mean - level) < 12, `${name} @${level}: ${mean}`);
    }
  }
});

function cellColors(indices, w, h, cw, ch) {
  const cells = [];
  for (let cy = 0; cy < h; cy += ch)
    for (let cx = 0; cx < w; cx += cw) {
      const s = new Set();
      for (let y = cy; y < Math.min(h, cy + ch); y++) for (let x = cx; x < Math.min(w, cx + cw); x++) s.add(indices[y * w + x]);
      cells.push(s);
    }
  return cells;
}

test("ZX mode: 2 colors per 8x8 cell from one BRIGHT bank; matches Python", () => {
  const { w, h } = FX.gradient;
  const res = E.applyHardware(gradient(w, h), w, h, DATA.hardware.zx, { ...DEFAULT_OPTS, dither: "none" });
  const pal = res.palette;
  for (const cell of cellColors(res.indices, w, h, 8, 8)) {
    assert.ok(cell.size <= 2);
    const banks = new Set([...cell].filter((i) => pal[i].some((v) => v > 0)).map((i) => (i < 8 ? "n" : "b")));
    assert.ok(banks.size <= 1);
  }
  assert.ok(agreement(Array.from(res.indices), FX.zx_none) >= 0.97);
  for (const dither of ["floyd", "pattern", "bayer"]) {
    const r2 = E.applyHardware(gradient(w, h), w, h, DATA.hardware.zx, { ...DEFAULT_OPTS, dither });
    for (const cell of cellColors(r2.indices, w, h, 8, 8)) assert.ok(cell.size <= 2, dither);
  }
});

test("C64 multicolor and NES obey their attribute rules", () => {
  const w = 40, h = 32, rgb = gradient(w, h);
  const c64 = E.applyHardware(rgb, w, h, DATA.hardware["c64-multi"], { ...DEFAULT_OPTS, dither: "floyd" });
  const bg = c64.report.shared.length;
  assert.equal(bg, 1);
  for (const cell of cellColors(c64.indices, w, h, 4, 8)) assert.ok(cell.size <= 4);
  const nes = E.applyHardware(rgb, w, h, DATA.hardware.nes, { ...DEFAULT_OPTS, dither: "none" });
  assert.ok(nes.report.distinctCellSets <= 4);
  for (const cell of cellColors(nes.indices, w, h, 16, 16)) assert.ok(cell.size <= 4);
  const msx = E.applyHardware(rgb, w, h, DATA.hardware.msx, { ...DEFAULT_OPTS, dither: "bluenoise" });
  for (const cell of cellColors(msx.indices, w, h, 8, 1)) assert.ok(cell.size <= 2);
});

test("scale2x / scale3x match Python on a diagonal", () => {
  const img = rgbaImage(4, 4, (x, y) => (x === y ? [255, 255, 255] : [0, 0, 0]));
  for (const [method, f, ref] of [["scale2x", 2, FX.scale2x_diag], ["scale3x", 3, FX.scale3x_diag]]) {
    const out = E.upscaleImage(img, f, method);
    const bits = [];
    for (let y = 0; y < out.height; y++) {
      const row = [];
      for (let x = 0; x < out.width; x++) row.push(out.data[(y * out.width + x) * 4] ? 1 : 0);
      bits.push(row);
    }
    assert.deepEqual(bits, ref, method);
  }
  for (const [f, m] of [[4, "scale3x"], [6, "scale3x"], [3, "scale2x"], [8, "scale4x"]]) {
    const out = E.upscaleImage(img, f, m);
    assert.equal(out.width, 4 * f);
  }
});

test("render: every preset and hardware mode", () => {
  const src = rgbaImage(64, 48, (x, y) => [x * 4, y * 5, 255 - x * 3]);
  for (const name of Object.keys(DATA.presets)) {
    const res = E.render({ ...E.presetParams(name), pixelSize: 32 }, src);
    assert.ok(res.image.width > 0 && res.stats.colorsUsed > 0, name);
  }
  for (const mode of Object.keys(DATA.hardware)) {
    const res = E.render({ hardware: mode, pixelSize: 48, upscale: 1 }, src);
    assert.ok(res.stats.clash && res.stats.clash.cells > 0, mode);
  }
});

test("render keeps the palette locked and sizes right", () => {
  const src = rgbaImage(80, 40, (x, y) => [x * 3, y * 6, 90]);
  const res = E.render({ palette: "gameboy", pixelSize: 20, upscale: 3, dither: "floyd" }, src);
  assert.equal(res.logicalWidth, 20);
  assert.equal(res.logicalHeight, 10);
  assert.equal(res.image.width, 60);
  const allowed = new Set(E.resolvePalette("gameboy").map((c) => c.join(",")));
  for (let i = 0; i < res.image.data.length; i += 4) assert.ok(allowed.has(`${res.image.data[i]},${res.image.data[i + 1]},${res.image.data[i + 2]}`));
});

test("outline uses the darkest color and alpha, cleanup removes orphans", () => {
  const src = rgbaImage(16, 16, (x, y) => (x > 4 && x < 11 && y > 4 && y < 11 ? [255, 255, 255, 255] : [0, 0, 0, 0]));
  const res = E.render({ palette: "pico8", pixelSize: 16, upscale: 1, dither: "none", outline: 1 }, src);
  const ink = res.palette.reduce((best, c, i, arr) => (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] < 0.299 * arr[best][0] + 0.587 * arr[best][1] + 0.114 * arr[best][2] ? i : best), 0);
  assert.equal(res.indices[4 * 16 + 7], ink);
  const idx = Int32Array.from({ length: 9 }, (_, i) => (i === 4 ? 2 : 1));
  assert.equal(E.cleanupOrphans(idx, 3, 3, 1)[4], 1);
});

test("auto palette and exporters", () => {
  const src = rgbaImage(40, 30, (x, y) => [x * 6, y * 8, (x + y) * 3]);
  const res = E.render({ palette: "auto", colors: 6, pixelSize: 20, upscale: 1, seed: 1 }, src);
  assert.ok(res.palette.length <= 6 && res.palette.length >= 2);
  const svg = E.toSVG(res.indices, res.logicalWidth, res.logicalHeight, res.palette, null);
  assert.match(svg, /^<svg[^>]+crispEdges/);
  const doc = JSON.parse(E.toJSON(res.indices, res.logicalWidth, res.logicalHeight, res.palette));
  assert.equal(doc.format, "pixelate-indexed");
  assert.equal(doc.pixels.length, res.logicalHeight);
  assert.match(E.toGPL(res.palette, "x"), /^GIMP Palette/);
  assert.equal(E.toHEX(res.palette).trim().split("\n").length, res.palette.length);
});
