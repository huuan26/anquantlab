/**
 * Shared HiDPI Canvas utilities: muted theme palettes, touch/mouse pointer normalization, safe text truncation.
 */

export function snapPx(v) {
  return Math.floor(v) + 0.5;
}

export function readChartPalette() {
  const light = document.documentElement.getAttribute("data-theme") === "light";
  if (light) {
    return {
      bg: "#FAF9F5",
      pane: "#F3F1EA",
      elev: "#EAE7DE",
      grid: "rgba(24, 28, 36, 0.045)",
      border: "rgba(24, 28, 36, 0.09)",
      borderStrong: "rgba(24, 28, 36, 0.22)",
      text: "#1A1D24",
      sub: "#525866",
      muted: "#767C8A",
      axisText: "#767C8A",
      crosshair: "rgba(26, 29, 36, 0.30)",
      tagBg: "rgba(26, 29, 36, 0.88)",
      tagText: "#FAF9F5",
      blue: "#2F5696",
      blueTop: "rgba(47, 86, 150, 0.08)",
      blueBot: "rgba(47, 86, 150, 0.00)",
      blueSoft: "rgba(47, 86, 150, 0.14)",
      blueBar: "rgba(47, 86, 150, 0.58)",
      blueBarSoft: "rgba(47, 86, 150, 0.32)",
      up: "#1F6E5C",
      upSoft: "rgba(31, 110, 92, 0.58)",
      upVol: "rgba(31, 110, 92, 0.13)",
      down: "#A93F48",
      downSoft: "rgba(169, 63, 72, 0.58)",
      downVol: "rgba(169, 63, 72, 0.13)",
      downTop: "rgba(169, 63, 72, 0.01)",
      downBot: "rgba(169, 63, 72, 0.09)",
      warn: "#B4691E",
      warnSoft: "rgba(180, 105, 30, 0.65)",
      oosTint: "rgba(180, 105, 30, 0.045)",
      gross: "rgba(82, 88, 102, 0.58)",
      bench: "rgba(118, 124, 138, 0.45)",
      fanOuter: "rgba(47, 86, 150, 0.05)",
      fanInner: "rgba(47, 86, 150, 0.10)",
    };
  }
  return {
    bg: "#0E1117",
    pane: "#141821",
    elev: "#1B202C",
    grid: "rgba(255, 255, 255, 0.035)",
    border: "rgba(255, 255, 255, 0.065)",
    borderStrong: "rgba(255, 255, 255, 0.14)",
    text: "#D8DEE9",
    sub: "#8F98A8",
    muted: "#687182",
    axisText: "#687182",
    crosshair: "rgba(216, 222, 233, 0.28)",
    tagBg: "rgba(35, 41, 56, 0.92)",
    tagText: "#D8DEE9",
    blue: "#5A8DEE",
    blueTop: "rgba(90, 141, 238, 0.09)",
    blueBot: "rgba(90, 141, 238, 0.00)",
    blueSoft: "rgba(90, 141, 238, 0.15)",
    blueBar: "rgba(90, 141, 238, 0.52)",
    blueBarSoft: "rgba(90, 141, 238, 0.28)",
    up: "#2E9E84",
    upSoft: "rgba(46, 158, 132, 0.56)",
    upVol: "rgba(46, 158, 132, 0.12)",
    down: "#C85A62",
    downSoft: "rgba(200, 90, 98, 0.56)",
    downVol: "rgba(200, 90, 98, 0.12)",
    downTop: "rgba(200, 90, 98, 0.01)",
    downBot: "rgba(200, 90, 98, 0.09)",
    warn: "#D48A3B",
    warnSoft: "rgba(212, 138, 59, 0.65)",
    oosTint: "rgba(212, 138, 59, 0.045)",
    gross: "rgba(143, 152, 168, 0.55)",
    bench: "rgba(104, 113, 130, 0.45)",
    fanOuter: "rgba(90, 141, 238, 0.055)",
    fanInner: "rgba(90, 141, 238, 0.105)",
  };
}

export function fillVerticalFade(ctx, topY, botY, topColor, botColor) {
  const grad = ctx.createLinearGradient(0, topY, 0, Math.max(topY + 1, botY));
  grad.addColorStop(0, topColor);
  grad.addColorStop(1, botColor);
  return grad;
}

export function attachCanvasPointerEvents(canvas, onPoint, onLeave) {
  const toLocal = (clientX, clientY) => {
    const rect = canvas.getBoundingClientRect();
    return { x: clientX - rect.left, y: clientY - rect.top, width: rect.width };
  };

  canvas.addEventListener("mousemove", (ev) => {
    onPoint(toLocal(ev.clientX, ev.clientY));
  });
  canvas.addEventListener("mouseleave", () => {
    onLeave();
  });
  canvas.addEventListener(
    "touchstart",
    (ev) => {
      if (ev.touches.length === 1) {
        const t = ev.touches[0];
        onPoint(toLocal(t.clientX, t.clientY));
      }
    },
    { passive: true }
  );
  canvas.addEventListener(
    "touchmove",
    (ev) => {
      if (ev.touches.length === 1) {
        const t = ev.touches[0];
        onPoint(toLocal(t.clientX, t.clientY));
      }
    },
    { passive: true }
  );
  canvas.addEventListener("touchend", () => onLeave(), { passive: true });
}

export function fitCanvasText(ctx, text, maxWidth) {
  const raw = String(text ?? "");
  if (maxWidth <= 8) return "";
  if (ctx.measureText(raw).width <= maxWidth) return raw;
  const ellipsis = "...";
  const ellW = ctx.measureText(ellipsis).width;
  if (maxWidth <= ellW) return "";
  let lo = 0;
  let hi = raw.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (ctx.measureText(raw.slice(0, mid)).width + ellW <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  return raw.slice(0, lo) + ellipsis;
}

export function drawQuadrantHeader(ctx, x, y, w, title, rightMeta, pal, baseline = 15) {
  const padX = 12;
  const usableW = Math.max(20, w - padX * 2);
  let metaW = 0;
  if (rightMeta) {
    ctx.font = "400 10px 'JetBrains Mono', monospace";
    const clippedMeta = fitCanvasText(ctx, rightMeta, Math.floor(usableW * 0.48));
    metaW = ctx.measureText(clippedMeta).width;
    ctx.fillStyle = pal.muted;
    ctx.textAlign = "right";
    ctx.fillText(clippedMeta, x + w - padX, y + baseline);
  }
  ctx.font = "500 11px Inter, sans-serif";
  ctx.fillStyle = pal.sub;
  ctx.textAlign = "left";
  const titleMaxW = metaW > 0 ? Math.max(24, usableW - metaW - 10) : usableW;
  ctx.fillText(fitCanvasText(ctx, title, titleMaxW), x + padX, y + baseline);
}

export function renderFourPanels(ctx, w, h, pal, snap, leftFrac, drawFns) {
  const stacked = w < 700;
  let boxes;
  ctx.strokeStyle = pal.border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  if (stacked) {
    const qh = Math.floor(h * 0.25);
    boxes = [
      [0, 0, w, qh],
      [0, qh, w, qh],
      [0, qh * 2, w, qh],
      [0, qh * 3, w, h - qh * 3],
    ];
    for (let i = 1; i <= 3; i++) {
      ctx.moveTo(0, snap(qh * i));
      ctx.lineTo(w, snap(qh * i));
    }
  } else {
    const midX = Math.floor(w * leftFrac);
    const midY = Math.floor(h * 0.5);
    boxes = [
      [0, 0, midX, midY],
      [midX, 0, w - midX, midY],
      [0, midY, midX, h - midY],
      [midX, midY, w - midX, h - midY],
    ];
    ctx.moveTo(snap(midX), 0);
    ctx.lineTo(snap(midX), h);
    ctx.moveTo(0, snap(midY));
    ctx.lineTo(w, snap(midY));
  }
  ctx.stroke();
  boxes.forEach(([qx, qy, qw, qh], idx) => {
    ctx.save();
    ctx.beginPath();
    ctx.rect(qx, qy, qw, qh);
    ctx.clip();
    drawFns[idx](qx, qy, qw, qh);
    ctx.restore();
  });
}
