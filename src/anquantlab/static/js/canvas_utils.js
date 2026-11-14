/**
 * Shared HiDPI Canvas utilities: touch/mouse pointer normalization and safe text truncation.
 */

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

export function drawQuadrantHeader(ctx, x, y, w, title, rightMeta, pal, baseline = 16) {
  const padX = 12;
  const usableW = Math.max(20, w - padX * 2);
  let metaW = 0;
  if (rightMeta) {
    ctx.font = "10.5px 'JetBrains Mono', monospace";
    const clippedMeta = fitCanvasText(ctx, rightMeta, Math.floor(usableW * 0.48));
    metaW = ctx.measureText(clippedMeta).width;
    ctx.fillStyle = pal.sub;
    ctx.textAlign = "right";
    ctx.fillText(clippedMeta, x + w - padX, y + baseline);
  }
  ctx.font = "600 11px Inter, sans-serif";
  ctx.fillStyle = pal.text;
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
