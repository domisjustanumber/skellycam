// Deterministic, collision-free label placement (same algorithm as scripts/overlays/label_layout.py).
//
// placeLabels(items, measure, bounds, opts)
//   items:   [{id, x, y, text}]  anchors in image px; processed in ascending id order (deterministic)
//   measure: text -> {w, h}
//   bounds:  {w, h}
//   opts:    {markerR: 6, gap: 3, rings: 3, laneW: 0 (auto)}
// For each anchor try 8 directions x `rings` radii (E, NE, SE, N, S, W, NW, SW); accept the first box that is
// inside the bounds and does not intersect any already-placed label box or any marker box. If none fits, put
// the label into the nearest side lane (left or right edge column), at the free slot closest to the anchor's y,
// with a leader line. If both lanes are full the label is hidden and counted.
// Returns {placed: [{id, x, y, w, h, lane, leader}], hidden: [ids]}  (x, y = top-left of the text box).
(function (root) {
  function inter(a, b) { return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h; }
  function placeLabels(items, measure, bounds, opts) {
    opts = Object.assign({ markerR: 6, gap: 3, rings: 3 }, opts || {});
    const sorted = items.slice().sort((a, b) => a.id - b.id);
    const markers = sorted.map(it => ({ x: it.x - opts.markerR, y: it.y - opts.markerR, w: 2 * opts.markerR, h: 2 * opts.markerR }));
    const placed = []; const boxes = []; const hidden = [];
    const dirs = [[1, 0], [1, -1], [1, 1], [0, -1], [0, 1], [-1, 0], [-1, -1], [-1, 1]];
    let maxW = 0; for (const it of sorted) maxW = Math.max(maxW, measure(it.text).w);
    const laneW = opts.laneW || maxW + 4;
    const lanes = { L: [], R: [] }; // occupied y-intervals
    for (const it of sorted) {
      const { w, h } = measure(it.text);
      let best = null;
      for (let ring = 1; ring <= opts.rings && !best; ring++) {
        const d = opts.markerR + opts.gap + (ring - 1) * (h + opts.gap);
        for (const [dx, dy] of dirs) {
          const cx = it.x + dx * d; const cy = it.y + dy * d;
          const bx = dx > 0 ? cx : dx < 0 ? cx - w : cx - w / 2;
          const by = dy > 0 ? cy : dy < 0 ? cy - h : cy - h / 2;
          const b = { x: bx, y: by, w, h };
          if (b.x < 0 || b.y < 0 || b.x + w > bounds.w || b.y + h > bounds.h) continue;
          if (boxes.some(o => inter(o, b))) continue;
          if (markers.some(m => inter(m, b))) continue;
          best = b; break;
        }
      }
      if (best) { boxes.push(best); placed.push({ id: it.id, ...best, lane: null, leader: null }); continue; }
      // lane fallback
      const order = it.x > bounds.w / 2 ? ['R', 'L'] : ['L', 'R'];
      let done = false;
      for (const side of order) {
        const lx = side === 'L' ? 2 : bounds.w - laneW - 2;
        const slots = [];
        for (let y = 2; y + h <= bounds.h - 2; y += h + 1) slots.push(y);
        slots.sort((a, b) => Math.abs(a + h / 2 - it.y) - Math.abs(b + h / 2 - it.y) || a - b);
        for (const y of slots) {
          const b = { x: lx, y, w, h };
          if (lanes[side].some(o => inter(o, b)) || boxes.some(o => inter(o, b))) continue;
          lanes[side].push(b); boxes.push(b);
          placed.push({ id: it.id, ...b, lane: side, leader: [it.x, it.y, side === 'L' ? lx + w : lx, y + h / 2] });
          done = true; break;
        }
        if (done) break;
      }
      if (!done) hidden.push(it.id);
    }
    return { placed, hidden };
  }
  function countOverlaps(boxes, markers) {
    let ll = 0, lm = 0;
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) if (inter(boxes[i], boxes[j])) ll++;
      for (const m of markers) if (inter(boxes[i], m)) lm++;
    }
    return { labelLabel: ll, labelMarker: lm };
  }
  root.placeLabels = placeLabels; root.countOverlaps = countOverlaps; root.boxInter = inter;
})(typeof window !== 'undefined' ? window : globalThis);
