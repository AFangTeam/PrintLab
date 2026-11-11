export function trustedBambuddyOrigin(referrer, currentOrigin) {
  try {
    const parent = new URL(referrer), current = new URL(currentOrigin);
    const localParent = ['localhost', '127.0.0.1'].includes(parent.hostname);
    if (!['http:', 'https:'].includes(parent.protocol) || parent.port !== '8017') return null;
    return parent.hostname === current.hostname || localParent ? parent.origin : null;
  } catch { return null; }
}
export function estimateDuration(seconds) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return null;
  const minutes = Math.ceil(seconds / 60), hours = Math.floor(minutes / 60);
  return hours ? `${hours} 小时${minutes % 60 ? ` ${minutes % 60} 分钟` : ''}` : `${minutes} 分钟`;
}
export function estimateWeight(grams) {
  return typeof grams === 'number' && Number.isFinite(grams) && grams >= 0 ? `${Number(grams.toFixed(2))} g` : null;
}

// Display-only approximations for the eight photographed Bambu PETG spools.
// Not official RGB values or slicer material settings; stored colors take priority.
const petgDisplayColors = {
  'Basic|Purple': ['#8660A8', '紫色'],
  'Basic|Sunflower Yellow': ['#F2C62D', '向日葵黄'],
  'Basic|Hot Pink': ['#E64F91', '亮粉色'],
  'Basic|Bright Green': ['#65C64A', '亮绿色'],
  'Matte|Cyan': ['#49AFCA', '青蓝色'],
  'Matte|Turquoise': ['#54A99E', '绿松石色'],
  'Matte|Red': ['#C64A45', '红色'],
  'Matte|Caramel': ['#B78659', '焦糖色'],
};
export function materialDisplayColor(material) {
  const fallback = material.brand === 'Bambu Lab' && material.material === 'PETG'
    ? petgDisplayColors[`${material.subtype}|${material.color_name}`] : null;
  const name = fallback?.[1] || material.color_name || '颜色待记录';
  const stored = [material.rgba, material.color_hex, material.color]
    .find(value => typeof value === 'string' && /^#?[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(value));
  if (stored) return {hex: '#' + stored.replace('#', '').slice(0, 6), name, approximate: false};
  return {hex: fallback?.[0] || '#d5d5d5', name, approximate: Boolean(fallback)};
}

// Packaging labels stay in English; Chinese can be a secondary explanation.
export function materialEnglishLabel(material) {
  if (material.english_label) return material.english_label;
  const brand = material.brand || 'Brand not identified';
  const materialName = material.material || material.tray_type || 'Material not identified';
  const subtype = material.subtype;
  const family = !subtype || materialName.toLowerCase().includes(subtype.toLowerCase()) ? materialName : `${materialName} ${subtype}`;
  return `${brand} ${family} — ${material.color_name || 'Color not identified'}`;
}
export function deviceRemainingLabel(slot) {
  const value = slot.reported_remaining_percent;
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 100) return '设备余量未知';
  return `${slot.fresh ? '设备报告' : '上次设备报告'} ${value}% · 可能滞后`;
}
export function inventoryRemainingLabel(material) {
  const grams = material.estimated_remaining_weight ?? material.remaining_weight;
  const percent = material.estimated_remaining_percent ?? material.remaining_percent;
  if (typeof grams !== 'number' || !Number.isFinite(grams) || grams < 0) return '账面估算不可用';
  const pct = typeof percent === 'number' && Number.isFinite(percent) ? ` / ${Number(percent.toFixed(1))}%` : '';
  return `台账估算 ${Number(grams.toFixed(1))} g${pct}`;
}
