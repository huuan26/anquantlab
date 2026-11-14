/**
 * Typed Zero-Dependency Fetch Client for AnQuantLab REST API.
 */

async function requestJson(url, options = {}) {
  const res = await fetch(url, options);
  let payload = null;
  try {
    payload = await res.json();
  } catch {
    payload = null;
  }
  if (!res.ok) {
    const detail = payload && payload.detail ? payload.detail : `HTTP ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

export async function fetchHealth() {
  return requestJson("/api/health");
}

export async function fetchCatalog() {
  return requestJson("/api/catalog");
}

export async function fetchDatasets() {
  return requestJson("/api/datasets");
}

export async function fetchDatasetPreview(datasetId) {
  return requestJson(`/api/datasets/${encodeURIComponent(datasetId)}/preview`);
}

export async function fetchDatasetForensics(datasetId) {
  return requestJson(`/api/datasets/${encodeURIComponent(datasetId)}/forensics`);
}

export async function fetchPublicPresets() {
  return requestJson("/api/public-data/presets");
}

export async function fetchPublicDataset(presetId, forceRefresh = false) {
  return requestJson("/api/public-data/fetch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preset_id: presetId, force_refresh: forceRefresh }),
  });
}

export async function uploadDatasetFile(file) {
  const form = new FormData();
  form.append("file", file);
  return requestJson("/api/datasets/upload", {
    method: "POST",
    body: form,
  });
}

export async function previewFormula(
  datasetId,
  formula,
  { symbol = null, chartBars = 160, previewLimit = 24 } = {}
) {
  return requestJson("/api/formula/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dataset_id: datasetId,
      formula,
      symbol,
      chart_bars: chartBars,
      preview_limit: previewLimit,
    }),
  });
}

export async function runBacktest(payload) {
  return requestJson("/api/backtest/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchTrialLedger(datasetId) {
  return requestJson(`/api/trials/${encodeURIComponent(datasetId)}`);
}

export async function runXRay(payload) {
  return requestJson("/api/xray/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function runCrashTest(payload) {
  return requestJson("/api/crashtest/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
