export function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function fmtUsd(n) {
  const num = Number(n || 0);
  return `$${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function cloudTag(cloud) {
  const c = String(cloud || '').toLowerCase();
  if (c === 'aws') return '<span class="tag tag-aws">AWS</span>';
  if (c === 'gcp' || c === 'gcloud') return '<span class="tag tag-gcp">GCP</span>';
  if (c === 'azure' || c === 'az') return '<span class="tag tag-azure">Azure</span>';
  return `<span class="tag">${esc(cloud)}</span>`;
}

export function statusTag(status) {
  const s = String(status || '').toLowerCase();
  if (['ok', 'active', 'running', 'promoted_100', 'healthy', 'succeeded', 'live', 'simulation', 'dry_run'].includes(s)) {
    return `<span class="tag tag-ok">${esc(status)}</span>`;
  }
  if (['canary_5', 'canary_25', 'planned', 'mutating', 'warning'].includes(s)) {
    return `<span class="tag tag-warn">${esc(status)}</span>`;
  }
  if (['blocked', 'rolled_back', 'failed', 'destructive', 'destroyed'].includes(s)) {
    return `<span class="tag tag-danger">${esc(status)}</span>`;
  }
  return `<span class="tag">${esc(status)}</span>`;
}

export function prettyJson(obj) {
  if (typeof obj === 'string') return obj;
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

export async function exportOrCopy(filename, content, toast) {
  if (window.syncroDesktop?.exportFile) {
    const res = await window.syncroDesktop.exportFile(filename, content);
    if (res?.saved) {
      toast(`Saved artifact to ${res.filePath}`);
      return;
    }
  }
  try {
    await navigator.clipboard.writeText(content);
    toast(`Copied ${filename} to clipboard`);
  } catch {
    toast(`Prepared ${filename}`);
  }
}
