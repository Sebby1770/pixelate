/* PIXELATE Studio — UI controller. Engine: engine.js (worker when possible). */
/* global PixelateEngine, PIXELATE_DATA */
(function () {
  "use strict";

  const E = PixelateEngine;
  const DATA = PIXELATE_DATA;
  E.setData(DATA);

  const MAX_SOURCE = 2048;
  const WEB_DEFAULTS = Object.assign(E.defaults(), {
    palette: "pico8",
    saturation: 1.2,
    posterize: 0,
    seed: 0,
    hardware: "",
    customPalette: null,
    outlineColor: null,
  });

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const els = {
    palette: $("#palette"),
    dither: $("#dither"),
    ditherHint: $("#ditherHint"),
    hardware: $("#hardware"),
    hardwareHint: $("#hardwareHint"),
    customPalette: $("#customPalette"),
    outlineColor: $("#outlineColor"),
    outlineCustom: $("#outlineCustom"),
    presets: $("#presets"),
    out: $("#out"),
    before: $("#before"),
    wrap: $("#canvasWrap"),
    viewport: $("#viewport"),
    splitLine: $("#splitLine"),
    split: $("#split"),
    splitLabel: $("#splitLabel"),
    compare: $("#compare"),
    status: $("#status"),
    swatches: $("#swatches"),
    busy: $("#busy"),
    file: $("#file"),
    webcam: $("#webcam"),
    share: $("#share"),
    help: $("#help"),
    helpDialog: $("#helpDialog"),
    reset: $("#reset"),
    video: $("#video"),
    version: $("#version"),
  };

  let state = Object.assign({}, WEB_DEFAULTS);
  let source = null; // {width, height, data}
  let sourceName = "pixelate";
  let last = null; // last render result
  let activePreset = null;
  let zoom = "fit";
  let comparing = false;
  let splitPct = 50;
  let renderTimer = 0;
  let jobId = 0;
  let pendingId = 0;
  let worker = null;
  let camStream = null;
  let camBusy = false;

  // ------------------------------------------------------------ populate
  function populate() {
    els.version.textContent = "v" + DATA.version;
    const groups = { "4 colors or fewer": [], "5–16 colors": [], "17+ colors": [] };
    Object.entries(DATA.palettes).forEach(([name, colors]) => {
      const n = colors.length;
      const g = n <= 4 ? "4 colors or fewer" : n <= 16 ? "5–16 colors" : "17+ colors";
      groups[g].push([name, n]);
    });
    const auto = new Option("auto — extract from image", "auto");
    els.palette.append(auto);
    Object.entries(groups).forEach(([label, list]) => {
      const og = document.createElement("optgroup");
      og.label = label;
      list.sort((a, b) => a[0].localeCompare(b[0])).forEach(([name, n]) => og.append(new Option(`${name} (${n})`, name)));
      els.palette.append(og);
    });
    Object.entries(DATA.dithers).forEach(([name]) => els.dither.append(new Option(name, name)));
    Object.entries(DATA.hardware).forEach(([name, m]) => els.hardware.append(new Option(`${m.title}`, name)));
    Object.entries(DATA.presets).forEach(([name, p]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = name;
      b.title = p.description;
      b.dataset.preset = name;
      b.setAttribute("aria-pressed", "false");
      els.presets.append(b);
    });
  }

  // ------------------------------------------------------- state <-> UI
  function controlValue(el) {
    if (el.type === "checkbox") return el.checked;
    if (el.type === "range" || el.type === "number") return el.value === "" ? null : Number(el.value);
    if (el.dataset.key === "bayerSize") return Number(el.value);
    return el.value;
  }
  function formatOut(key, v) {
    if (key === "posterize") return v ? String(v) : "off";
    if (key === "chromatic" || key === "outline") return v ? `${v}px` : "off";
    if (key === "colorBleed" || key === "curvature") return v ? Number(v).toFixed(2) : "off";
    if (key === "upscale") return `${v}×`;
    if (key === "pixelSize") return `${v}px`;
    if (typeof v === "number" && !Number.isInteger(v)) return v.toFixed(2);
    return String(v);
  }
  function syncUI() {
    $$("[data-key]").forEach((el) => {
      const key = el.dataset.key;
      let v = state[key];
      if (key === "hardware") v = v || "";
      if (key === "cleanup") v = !!v;
      if (el.type === "checkbox") el.checked = !!v;
      else if (v == null) el.value = "";
      else el.value = String(v);
      const out = $(`output[data-for="${key}"]`);
      if (out) out.textContent = formatOut(key, v);
    });
    els.customPalette.value = state.customPalette ? state.customPalette.join(" ") : "";
    els.outlineCustom.checked = !!state.outlineColor;
    if (state.outlineColor) els.outlineColor.value = state.outlineColor;
    const hw = state.hardware ? DATA.hardware[state.hardware] : null;
    els.palette.disabled = !!hw || !!state.customPalette;
    els.hardwareHint.textContent = hw
      ? `${hw.notes} · ${hw.cell[0]}×${hw.cell[1]} cells · native ${hw.native[0]}×${hw.native[1]}`
      : "Restrict each attribute cell to the colors the real machine allowed.";
    els.ditherHint.textContent = DATA.dithers[state.dither] || "";
    $$(".auto-only").forEach((el) => el.classList.toggle("is-hidden", state.palette !== "auto" || !!hw));
    $$(".bayer-only").forEach((el) => el.classList.toggle("is-hidden", state.dither !== "bayer"));
    $$(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.preset === activePreset)));
  }
  function onControl(e) {
    const el = e.target.closest("[data-key]");
    if (!el) return;
    const key = el.dataset.key;
    let v = controlValue(el);
    if (key === "cleanup") v = v ? 1 : 0;
    if (key === "hardware") {
      v = v || "";
      if (v) state.pixelSize = Math.max(...DATA.hardware[v].native);
    }
    state[key] = v;
    activePreset = null;
    syncUI();
    schedule();
  }

  // -------------------------------------------------------------- params
  function params() {
    const p = Object.assign({}, state);
    p.hardware = state.hardware || null;
    p.posterize = state.posterize ? Number(state.posterize) : null;
    p.seed = state.seed == null ? null : Number(state.seed);
    p.outlineColor = state.outlineColor || null;
    return p;
  }
  function parseHexList(text) {
    const list = (text.match(/#?[0-9a-fA-F]{6}\b/g) || []).map((h) => "#" + h.replace("#", "").toLowerCase());
    return list.length >= 2 ? Array.from(new Set(list)).slice(0, 256) : null;
  }

  // ---------------------------------------------------------- rendering
  function setBusy(on) {
    els.busy.classList.toggle("on", on);
  }
  function schedule(delay = 90) {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(renderNow, delay);
    writeHash();
  }
  function renderNow() {
    if (!source) return;
    const id = ++jobId;
    pendingId = id;
    setBusy(true);
    if (worker) {
      worker.postMessage({ type: "render", id, params: params() });
    } else {
      setTimeout(() => {
        try {
          const res = E.render(params(), source);
          handleResult(Object.assign({ id }, res, { image: res.image }));
        } catch (err) {
          handleError(id, err);
        }
      }, 0);
    }
  }
  function handleError(id, err) {
    if (id !== pendingId) return;
    setBusy(false);
    camBusy = false;
    els.status.textContent = "Render failed: " + ((err && err.message) || err);
  }
  function handleResult(res) {
    if (res.id !== pendingId) return; // stale
    setBusy(false);
    camBusy = false;
    last = res;
    const img = res.image;
    els.out.width = img.width;
    els.out.height = img.height;
    const ctx = els.out.getContext("2d");
    ctx.putImageData(new ImageData(new Uint8ClampedArray(img.data.buffer || img.data), img.width, img.height), 0, 0);
    drawBefore();
    applyZoom();
    renderSwatches(res);
    const s = res.stats;
    let text = `${img.width}×${img.height} · art ${res.logicalWidth}×${res.logicalHeight} · ${s.colorsUsed}/${s.paletteSize} colors · ${s.ms} ms`;
    if (s.clash) text += ` · ${s.clash.mode}: ${s.clash.cells} cells, ${s.clash.distinctCellSets} cell sets`;
    if (camStream) text = "● live · " + text;
    els.status.textContent = text;
  }
  function drawBefore() {
    if (!source) return;
    els.before.width = els.out.width;
    els.before.height = els.out.height;
    const tmp = document.createElement("canvas");
    tmp.width = source.width;
    tmp.height = source.height;
    tmp.getContext("2d").putImageData(new ImageData(source.data, source.width, source.height), 0, 0);
    const ctx = els.before.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(tmp, 0, 0, els.before.width, els.before.height);
    updateSplit();
  }
  function renderSwatches(res) {
    const counts = new Map();
    for (let i = 0; i < res.indices.length; i++) counts.set(res.indices[i], (counts.get(res.indices[i]) || 0) + 1);
    els.swatches.textContent = "";
    res.palette.forEach((c, i) => {
      if (!counts.get(i)) return;
      const hex = E.rgbToHex(c);
      const b = document.createElement("button");
      b.type = "button";
      b.className = "swatch";
      b.style.background = hex;
      const pct = ((100 * counts.get(i)) / res.indices.length).toFixed(1);
      b.title = `${hex} · ${pct}% — click to copy`;
      b.setAttribute("aria-label", `${hex}, ${pct} percent. Copy hex`);
      b.dataset.hex = hex;
      els.swatches.append(b);
    });
  }

  // --------------------------------------------------------------- zoom
  function applyZoom() {
    const fit = zoom === "fit";
    els.viewport.classList.toggle("fit", fit);
    els.viewport.classList.toggle("zoomed", !fit);
    if (fit) {
      els.out.style.width = "";
      els.out.style.height = "";
    } else {
      const z = Number(zoom);
      els.out.style.width = `${els.out.width * z}px`;
      els.out.style.height = `${els.out.height * z}px`;
      els.out.style.maxWidth = "none";
      els.out.style.maxHeight = "none";
    }
    if (fit) {
      els.out.style.maxWidth = "";
      els.out.style.maxHeight = "";
    }
    $$("[data-zoom]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.zoom === String(zoom))));
  }
  const ZOOMS = ["fit", "1", "2", "4", "8"];
  function stepZoom(dir) {
    const i = ZOOMS.indexOf(String(zoom));
    zoom = ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, i + dir))];
    applyZoom();
  }

  // ------------------------------------------------------------ compare
  function setCompare(on) {
    comparing = on;
    document.body.classList.toggle("comparing", on);
    els.compare.setAttribute("aria-pressed", String(on));
    els.splitLabel.hidden = !on;
    updateSplit();
  }
  function updateSplit() {
    els.before.style.clipPath = `inset(0 ${100 - splitPct}% 0 0)`;
    els.splitLine.style.left = `calc(${splitPct}% - 1px)`;
    els.split.value = String(Math.round(splitPct));
  }

  // ------------------------------------------------------------- source
  function imageToSource(drawable, w, h, name) {
    const scale = Math.min(1, MAX_SOURCE / Math.max(w, h));
    const cw = Math.max(1, Math.round(w * scale));
    const ch = Math.max(1, Math.round(h * scale));
    const c = document.createElement("canvas");
    c.width = cw;
    c.height = ch;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(drawable, 0, 0, cw, ch);
    const id = ctx.getImageData(0, 0, cw, ch);
    return { width: cw, height: ch, data: id.data, name };
  }
  function setSource(src) {
    source = { width: src.width, height: src.height, data: src.data };
    sourceName = (src.name || "pixelate").replace(/\.[^.]+$/, "");
    if (worker) worker.postMessage({ type: "source", image: { width: source.width, height: source.height, data: source.data } });
    schedule(0);
  }
  function loadFile(file) {
    if (!file || !/^image\//.test(file.type)) {
      toast("That file is not an image");
      return;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      setSource(imageToSource(img, img.naturalWidth, img.naturalHeight, file.name));
      URL.revokeObjectURL(url);
      els.status.textContent = `Loaded ${file.name} (${img.naturalWidth}×${img.naturalHeight})`;
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      toast("Could not decode that image");
    };
    img.src = url;
  }
  function demoScene() {
    const w = 480, h = 320;
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    const g = c.getContext("2d");
    const sky = g.createLinearGradient(0, 0, 0, h * 0.7);
    sky.addColorStop(0, "#1b1446");
    sky.addColorStop(0.45, "#c2306b");
    sky.addColorStop(0.75, "#ff9a4d");
    sky.addColorStop(1, "#ffe08a");
    g.fillStyle = sky;
    g.fillRect(0, 0, w, h);
    for (let i = 0; i < 70; i++) {
      g.fillStyle = `rgba(255,255,255,${0.35 + ((i * 37) % 60) / 100})`;
      g.fillRect((i * 97) % w, (i * 53) % (h * 0.35), 2, 2);
    }
    const sun = g.createRadialGradient(330, 175, 10, 330, 175, 70);
    sun.addColorStop(0, "#fff7c2");
    sun.addColorStop(0.6, "#ffd34d");
    sun.addColorStop(1, "rgba(255,160,60,0)");
    g.fillStyle = sun;
    g.beginPath();
    g.arc(330, 175, 70, 0, Math.PI * 2);
    g.fill();
    const ridge = (base, amp, freq, color, phase) => {
      g.fillStyle = color;
      g.beginPath();
      g.moveTo(0, h);
      for (let x = 0; x <= w; x += 4) g.lineTo(x, base + Math.sin(x * freq + phase) * amp + Math.sin(x * freq * 2.7) * amp * 0.35);
      g.lineTo(w, h);
      g.fill();
    };
    ridge(210, 22, 0.018, "#6b2f73", 0.5);
    ridge(240, 28, 0.012, "#3a1f4d", 2.1);
    ridge(275, 18, 0.025, "#161026", 4.0);
    g.fillStyle = "#0d0a18";
    g.fillRect(0, 292, w, 28);
    g.strokeStyle = "rgba(82,255,143,0.55)";
    for (let i = 0; i < 9; i++) {
      g.beginPath();
      g.moveTo(w / 2, 292);
      g.lineTo((i - 4) * 120 + w / 2, h);
      g.stroke();
    }
    return imageToSource(c, w, h, "demo");
  }

  // ------------------------------------------------------------- webcam
  async function toggleWebcam() {
    if (camStream) return stopWebcam();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast("Webcam is not available in this browser");
      return;
    }
    try {
      camStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
    } catch (err) {
      camStream = null;
      toast(err && err.name === "NotAllowedError" ? "Camera permission was denied" : "Could not start the camera");
      return;
    }
    els.video.srcObject = camStream;
    await els.video.play().catch(() => {});
    els.webcam.setAttribute("aria-pressed", "true");
    els.webcam.textContent = "Stop webcam";
    sourceName = "webcam";
    requestAnimationFrame(camLoop);
  }
  function stopWebcam() {
    if (camStream) camStream.getTracks().forEach((t) => t.stop());
    camStream = null;
    els.webcam.setAttribute("aria-pressed", "false");
    els.webcam.textContent = "Webcam";
    if (source && worker) worker.postMessage({ type: "source", image: { width: source.width, height: source.height, data: source.data } });
  }
  function camLoop() {
    if (!camStream) return;
    const v = els.video;
    if (!camBusy && v.videoWidth) {
      const frame = imageToSource(v, v.videoWidth, v.videoHeight, "webcam");
      camBusy = true;
      source = { width: frame.width, height: frame.height, data: frame.data };
      const id = ++jobId;
      pendingId = id;
      if (worker) worker.postMessage({ type: "frame", id, params: params(), image: { width: frame.width, height: frame.height, data: frame.data } });
      else {
        try {
          handleResult(Object.assign({ id }, E.render(params(), source)));
        } catch (err) {
          handleError(id, err);
        }
      }
    }
    requestAnimationFrame(camLoop);
  }

  // ------------------------------------------------------------- export
  function download(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function exportAs(kind) {
    if (!last) return;
    const base = `${sourceName}_pixel`;
    const pal = last.palette;
    if (kind === "png") {
      els.out.toBlob((b) => b && download(b, base + ".png"), "image/png");
    } else if (kind === "svg") {
      download(new Blob([E.toSVG(last.indices, last.logicalWidth, last.logicalHeight, pal, last.alpha)], { type: "image/svg+xml" }), base + ".svg");
    } else if (kind === "json") {
      download(new Blob([E.toJSON(last.indices, last.logicalWidth, last.logicalHeight, pal)], { type: "application/json" }), base + ".json");
    } else if (kind === "gpl") {
      download(new Blob([E.toGPL(pal, base)], { type: "text/plain" }), base + ".gpl");
    } else if (kind === "hex") {
      download(new Blob([E.toHEX(pal)], { type: "text/plain" }), base + ".hex");
    }
  }

  // --------------------------------------------------------- share hash
  const HASH_KEYS = Object.keys(WEB_DEFAULTS);
  function writeHash() {
    const q = new URLSearchParams();
    HASH_KEYS.forEach((k) => {
      const v = state[k];
      const d = WEB_DEFAULTS[k];
      if (k === "customPalette") {
        if (v && v.length) q.set(k, v.map((h) => h.replace("#", "")).join("-"));
        return;
      }
      if (v !== d && !(v == null && d == null) && String(v) !== String(d)) q.set(k, String(v));
    });
    if (activePreset) q.set("preset", activePreset);
    const hash = q.toString();
    history.replaceState(null, "", hash ? `#${hash}` : location.pathname + location.search);
  }
  function readHash() {
    if (!location.hash) return;
    const q = new URLSearchParams(location.hash.slice(1));
    const preset = q.get("preset");
    if (preset && DATA.presets[preset]) presetState(preset); // base, then overrides
    q.forEach((v, k) => {
      if (k === "preset") return;
      if (!(k in WEB_DEFAULTS)) return;
      const d = WEB_DEFAULTS[k];
      if (k === "customPalette") state[k] = v.split("-").filter((h) => /^[0-9a-f]{6}$/i.test(h)).map((h) => "#" + h.toLowerCase());
      else if (typeof d === "boolean") state[k] = v === "true";
      else if (typeof d === "number") state[k] = Number(v);
      else if (v === "null") state[k] = null;
      else state[k] = v;
    });
    if (state.palette !== "auto" && !DATA.palettes[state.palette] && !DATA.paletteAliases[state.palette]) state.palette = WEB_DEFAULTS.palette;
    if (state.hardware && !DATA.hardware[state.hardware]) state.hardware = "";
    if (!DATA.dithers[state.dither]) state.dither = WEB_DEFAULTS.dither;
  }

  // ------------------------------------------------------------ presets
  function applyPreset(name) {
    presetState(name);
    syncUI();
    schedule(0);
    toast(`${name}: ${DATA.presets[name].description}`);
  }
  function presetState(name) {
    const p = E.presetParams(name);
    state = Object.assign({}, WEB_DEFAULTS, p, {
      hardware: p.hardware || "",
      posterize: p.posterize || 0,
      seed: p.seed == null ? 0 : p.seed,
      customPalette: null,
      outlineColor: p.outlineColor || null,
    });
    if (state.hardware && !("pixel_size" in DATA.presets[name].options)) state.pixelSize = Math.max(...DATA.hardware[state.hardware].native);
    activePreset = name;
  }

  // --------------------------------------------------------------- misc
  let toastTimer = 0;
  function toast(msg) {
    let t = $(".toast");
    if (!t) {
      t = document.createElement("div");
      t.className = "toast";
      t.setAttribute("role", "status");
      document.body.append(t);
    }
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), 2200);
  }
  async function copyText(text, label) {
    try {
      await navigator.clipboard.writeText(text);
      toast(`Copied ${label}`);
    } catch (_) {
      window.prompt("Copy this:", text);
    }
  }

  // ------------------------------------------------------------- worker
  function startWorker() {
    if (typeof Worker === "undefined" || location.protocol === "file:") return null;
    try {
      const w = new Worker("worker.js");
      w.onmessage = (e) => {
        const m = e.data;
        if (m.type === "result") handleResult(m);
        else if (m.type === "error") handleError(m.id, m.message);
      };
      w.onerror = (e) => {
        e.preventDefault();
        worker = null; // fall back to the main thread
        if (source) schedule(0);
      };
      return w;
    } catch (_) {
      return null;
    }
  }

  // -------------------------------------------------------------- wire
  function wire() {
    document.addEventListener("input", (e) => {
      if (e.target.matches("[data-key]")) onControl(e);
    });
    document.addEventListener("change", (e) => {
      if (e.target.matches("select[data-key], input[type=checkbox][data-key]")) onControl(e);
    });
    els.customPalette.addEventListener("input", () => {
      state.customPalette = parseHexList(els.customPalette.value);
      activePreset = null;
      els.palette.disabled = !!state.customPalette || !!state.hardware;
      schedule(200);
    });
    const outlineInk = () => {
      state.outlineColor = els.outlineCustom.checked ? els.outlineColor.value : null;
      schedule();
    };
    els.outlineColor.addEventListener("input", outlineInk);
    els.outlineCustom.addEventListener("change", outlineInk);
    els.presets.addEventListener("click", (e) => {
      const b = e.target.closest("[data-preset]");
      if (b) applyPreset(b.dataset.preset);
    });
    $$("[data-zoom]").forEach((b) =>
      b.addEventListener("click", () => {
        zoom = b.dataset.zoom;
        applyZoom();
      })
    );
    els.compare.addEventListener("click", () => setCompare(!comparing));
    els.split.addEventListener("input", () => {
      splitPct = Number(els.split.value);
      updateSplit();
    });
    $$("[data-export]").forEach((b) => b.addEventListener("click", () => exportAs(b.dataset.export)));
    els.swatches.addEventListener("click", (e) => {
      const b = e.target.closest(".swatch");
      if (b) copyText(b.dataset.hex, b.dataset.hex);
    });
    els.file.addEventListener("change", () => els.file.files[0] && loadFile(els.file.files[0]));
    els.webcam.addEventListener("click", toggleWebcam);
    els.share.addEventListener("click", () => {
      writeHash();
      copyText(location.href, "share link");
    });
    els.help.addEventListener("click", () => els.helpDialog.showModal());
    els.reset.addEventListener("click", () => {
      state = Object.assign({}, WEB_DEFAULTS);
      activePreset = null;
      syncUI();
      schedule(0);
    });

    // drag & drop / paste
    let dragDepth = 0;
    window.addEventListener("dragenter", (e) => {
      if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes("Files")) return;
      dragDepth++;
      document.body.classList.add("dropping");
    });
    window.addEventListener("dragleave", () => {
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) document.body.classList.remove("dropping");
    });
    window.addEventListener("dragover", (e) => e.preventDefault());
    window.addEventListener("drop", (e) => {
      e.preventDefault();
      dragDepth = 0;
      document.body.classList.remove("dropping");
      const f = e.dataTransfer && e.dataTransfer.files[0];
      if (f) loadFile(f);
    });
    window.addEventListener("paste", (e) => {
      const item = Array.from((e.clipboardData && e.clipboardData.items) || []).find((i) => i.type.startsWith("image/"));
      if (item) {
        e.preventDefault();
        loadFile(item.getAsFile());
      }
    });

    // split drag + pan
    let drag = null;
    els.viewport.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      if (comparing) {
        drag = { mode: "split" };
        moveSplit(e);
      } else if (zoom !== "fit") {
        drag = { mode: "pan", x: e.clientX, y: e.clientY, sl: els.viewport.scrollLeft, st: els.viewport.scrollTop };
        els.viewport.classList.add("dragging");
      }
      if (drag) els.viewport.setPointerCapture(e.pointerId);
    });
    els.viewport.addEventListener("pointermove", (e) => {
      if (!drag) return;
      if (drag.mode === "split") moveSplit(e);
      else {
        els.viewport.scrollLeft = drag.sl - (e.clientX - drag.x);
        els.viewport.scrollTop = drag.st - (e.clientY - drag.y);
      }
    });
    const endDrag = () => {
      drag = null;
      els.viewport.classList.remove("dragging");
    };
    els.viewport.addEventListener("pointerup", endDrag);
    els.viewport.addEventListener("pointercancel", endDrag);
    function moveSplit(e) {
      const r = els.out.getBoundingClientRect();
      splitPct = Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100));
      updateSplit();
    }

    // share links pasted into an open tab
    window.addEventListener("hashchange", () => {
      state = Object.assign({}, WEB_DEFAULTS);
      activePreset = null;
      readHash();
      syncUI();
      schedule(0);
    });

    // keyboard
    document.addEventListener("keydown", (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.target.closest("input, select, textarea, [contenteditable]") || els.helpDialog.open) return;
      const k = e.key;
      if (k === "c" || k === "C") setCompare(!comparing);
      else if (k === "g" || k === "G") {
        state.grid = !state.grid;
        syncUI();
        schedule(0);
      } else if (k === "+" || k === "=") stepZoom(1);
      else if (k === "-" || k === "_") stepZoom(-1);
      else if (k === "0") {
        zoom = "fit";
        applyZoom();
      } else if (k === "d" || k === "D") exportAs("png");
      else if (k === "r" || k === "R") {
        const names = Object.keys(DATA.presets).filter((n) => n !== activePreset);
        applyPreset(names[Math.floor(Math.random() * names.length)]);
      } else if (k === "?") els.helpDialog.showModal();
      else return;
      e.preventDefault();
    });
  }

  // --------------------------------------------------------------- boot
  populate();
  readHash();
  syncUI();
  wire();
  worker = startWorker();
  setSource(demoScene());
  els.status.textContent = "Demo scene loaded — open, drop or paste an image to convert it.";
})();
