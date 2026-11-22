/* PIXELATE Studio worker — renders off the main thread. */
/* global importScripts, PixelateEngine */
importScripts("data.js", "engine.js");

let source = null;

function reply(id, res) {
  const img = res.image;
  const indices = Int32Array.from(res.indices);
  const alpha = res.alpha ? Uint8Array.from(res.alpha) : null;
  const transfer = [img.data.buffer, indices.buffer];
  if (alpha) transfer.push(alpha.buffer);
  self.postMessage(
    {
      type: "result",
      id,
      image: { width: img.width, height: img.height, data: img.data },
      indices,
      alpha,
      palette: res.palette,
      logicalWidth: res.logicalWidth,
      logicalHeight: res.logicalHeight,
      stats: res.stats,
    },
    transfer
  );
}

self.onmessage = (event) => {
  const msg = event.data;
  try {
    if (msg.type === "source") {
      source = msg.image;
      return;
    }
    const src = msg.type === "frame" ? msg.image : source;
    if (!src) return;
    reply(msg.id, PixelateEngine.render(msg.params, src));
  } catch (err) {
    self.postMessage({ type: "error", id: msg.id, message: String((err && err.message) || err) });
  }
};
