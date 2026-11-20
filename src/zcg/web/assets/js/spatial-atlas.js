// ZeroCloudGravity — Zone.Z4 2D/3D Spatial Atlas Dumb Renderer (ES2024, 0 innerHTML)
(() => {
  window.ZCGIslands = window.ZCGIslands || {};
  const RING_COLORS = { R0: '#38bdf8', R1: '#f59e0b', R2: '#22c55e', R3: '#a855f7' };

  function buildCell(text, { code = false } = {}) {
    const td = document.createElement('td');
    if (code) {
      const codeEl = document.createElement('code');
      codeEl.textContent = String(text ?? '');
      td.appendChild(codeEl);
    } else {
      td.textContent = String(text ?? '');
    }
    return td;
  }

  function populateSelectOptions(selectEl, nodes) {
    selectEl.replaceChildren(
      ...nodes.map((nd) => {
        const opt = document.createElement('option');
        opt.value = String(nd.node_id ?? '');
        opt.textContent = `${nd.node_id} (${nd.surface_ring})`;
        return opt;
      }),
    );
  }

  window.ZCGIslands['spatial-atlas'] = (el, props, bus) => {
    const cv = el.querySelector('[data-atlas-canvas]') || el.querySelector('canvas');
    if (!cv || !cv.getContext) return;
    const ctx = cv.getContext('2d');
    const apiPrefix = props.apiPrefix || el.dataset.apiPrefix || '/api/spatial-atlas';
    let scene = props.scene || { nodes: [], edges: [], lenses: [], core_radius: 150 };
    let mode = props.initialMode || el.dataset.renderMode || 'blueprint-3d';
    let yaw = 0.38, pitch = 0.26, zoom = 1.0, panX = 0, panY = 0, autoSpin = true;
    let buf = new Float32Array(0), nodeMap = new Map(), screenPts = [], drag = null;

    const q = (sel) => el.querySelector(sel);
    const presetSel = q('[data-atlas-preset]'), lensSel = q('[data-atlas-lens]');
    const expInput = q('[data-atlas-explosion]'), expOut = q('[data-atlas-explosion-val]');
    const postureChip = q('[data-atlas-posture]'), lensDesc = q('[data-atlas-lens-desc]');
    const spinBtn = q('[data-atlas-spin]'), tbody = q('[data-atlas-tbody]');
    const stage = q('[data-atlas-stage]'), receiptEl = q('[data-atlas-receipt]');
    const srcSel = q('[data-atlas-src]'), dstSel = q('[data-atlas-dst]');

    function syncScene(nextScene) {
      scene = nextScene || scene;
      const nodes = scene.nodes || [];
      if (buf.length !== nodes.length * 3) buf = new Float32Array(nodes.length * 3);
      nodeMap = new Map();
      nodes.forEach((nd, idx) => {
        buf[idx * 3] = Number(nd.x || 0);
        buf[idx * 3 + 1] = Number(nd.y || 0);
        buf[idx * 3 + 2] = Number(nd.z || 0);
        nodeMap.set(nd.node_id, idx);
      });
      if (postureChip) {
        postureChip.textContent = `Posture: ${scene.federation_posture || 'sovereign'}`;
      }
      if (lensDesc && scene.lens_summary) {
        lensDesc.textContent =
          `${scene.lens_summary} · Solid = Connected Core · Dashed = Discoverable Horizon`;
      }
      if (expOut && expInput) expOut.textContent = Number(expInput.value).toFixed(2);
      if (tbody) {
        tbody.replaceChildren(
          ...nodes.map((nd) => {
            const tr = document.createElement('tr');
            const xyz =
              `(${Number(nd.x).toFixed(1)}, ${Number(nd.y).toFixed(1)}, ` +
              `${Number(nd.z).toFixed(1)})`;
            tr.append(
              buildCell(nd.node_id, { code: true }),
              buildCell(nd.label),
              buildCell(nd.lens_group || nd.zone_band),
              buildCell(nd.surface_ring),
              buildCell(xyz),
              buildCell(Number(nd.jaccard_affinity || 0).toFixed(2)),
            );
            return tr;
          }),
        );
      }
      if (srcSel && dstSel && nodes.length) {
        const prevSrc = srcSel.value, prevDst = dstSel.value;
        populateSelectOptions(srcSel, nodes);
        populateSelectOptions(dstSel, nodes);
        srcSel.value = nodeMap.has(prevSrc) ? prevSrc : nodes[0].node_id;
        dstSel.value =
          nodeMap.has(prevDst) && prevDst !== srcSel.value
            ? prevDst
            : (nodes[1] || nodes[0]).node_id;
      }
    }

    function setMode(nextMode) {
      mode = nextMode;
      el.dataset.renderMode = mode;
      el.querySelectorAll('[data-atlas-mode]').forEach((btn) => {
        const active = btn.dataset.atlasMode === mode;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-pressed', String(active));
      });
      if (stage) stage.hidden = mode === 'accessible-table';
    }

    function projectIdx(idx, cx, cy) {
      const x = buf[idx * 3], y = buf[idx * 3 + 1], z = buf[idx * 3 + 2];
      const scale = 0.68 * zoom;
      if (mode === 'blueprint-2d') {
        return { sx: cx + panX + x * scale, sy: cy + panY + y * scale, z2: 0, p: 1 };
      }
      const cY = Math.cos(yaw), sY = Math.sin(yaw);
      const cP = Math.cos(pitch), sP = Math.sin(pitch);
      const x1 = x * cY - z * sY, z1 = x * sY + z * cY;
      const y1 = y * cP - z1 * sP, z2 = y * sP + z1 * cP;
      const p = 560 / Math.max(200, 560 + z2);
      return { sx: cx + panX + x1 * scale * p, sy: cy + panY + y1 * scale * p, z2, p };
    }

    async function refreshScene() {
      const pr = encodeURIComponent(presetSel ? presetSel.value : scene.preset || '');
      const ln = encodeURIComponent(lensSel ? lensSel.value : scene.lens || 'relational-affinity');
      const ex = encodeURIComponent(expInput ? expInput.value : '0.25');
      if (expOut && expInput) expOut.textContent = Number(expInput.value).toFixed(2);
      const res = await fetch(`${apiPrefix}/scene?preset=${pr}&lens=${ln}&explosion=${ex}`);
      if (!res.ok) return;
      const next = await res.json();
      syncScene(next);
      bus?.emit('spatial:scene', next);
    }

    cv.addEventListener('pointerdown', (ev) => {
      drag = { x: ev.clientX, y: ev.clientY, moved: false };
      cv.setPointerCapture?.(ev.pointerId);
    });

    cv.addEventListener('pointermove', (ev) => {
      if (!drag) return;
      const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      drag.x = ev.clientX;
      drag.y = ev.clientY;
      if (mode === 'blueprint-2d') {
        panX += dx;
        panY += dy;
        return;
      }
      autoSpin = false;
      if (spinBtn) spinBtn.textContent = 'Auto-Orbit: OFF';
      yaw += dx * 0.008;
      pitch = Math.max(-1.25, Math.min(1.25, pitch + dy * 0.008));
    });

    cv.addEventListener('pointerup', (ev) => {
      if (drag && !drag.moved && screenPts.length && srcSel && dstSel) {
        const rect = cv.getBoundingClientRect();
        const mx = (ev.clientX - rect.left) * (cv.width / Math.max(1, rect.width));
        const my = (ev.clientY - rect.top) * (cv.height / Math.max(1, rect.height));
        const hit = screenPts.find((pt) => Math.hypot(pt.sx - mx, pt.sy - my) <= pt.rad + 8);
        if (hit) {
          if (srcSel.value !== hit.id) dstSel.value = hit.id;
          if (receiptEl) receiptEl.textContent = `Focused node: ${hit.id} [${hit.ring}]`;
        }
      }
      drag = null;
    });

    cv.addEventListener(
      'wheel',
      (ev) => {
        ev.preventDefault();
        zoom = Math.max(0.45, Math.min(2.6, zoom * (ev.deltaY < 0 ? 1.1 : 0.91)));
      },
      { passive: false },
    );

    cv.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowLeft') { yaw -= 0.08; autoSpin = false; }
      else if (ev.key === 'ArrowRight') { yaw += 0.08; autoSpin = false; }
      else if (ev.key === 'ArrowUp') pitch = Math.max(-1.25, pitch - 0.07);
      else if (ev.key === 'ArrowDown') pitch = Math.min(1.25, pitch + 0.07);
      else if (ev.key === '+' || ev.key === '=') zoom = Math.min(2.6, zoom * 1.12);
      else if (ev.key === '-') zoom = Math.max(0.45, zoom * 0.89);
      else if (ev.key === '0') { yaw = 0.38; pitch = 0.26; zoom = 1.0; panX = 0; panY = 0; }
      else if (ev.key === '2') setMode('blueprint-2d');
      else if (ev.key === '3') setMode('blueprint-3d');
    });

    presetSel?.addEventListener('change', refreshScene);
    lensSel?.addEventListener('change', refreshScene);
    expInput?.addEventListener('input', refreshScene);

    el.addEventListener('click', async (ev) => {
      const mBtn = ev.target.closest('[data-atlas-mode]');
      if (mBtn) { setMode(mBtn.dataset.atlasMode); return; }
      const zBtn = ev.target.closest('[data-atlas-zoom]');
      if (zBtn) {
        const zf = zBtn.dataset.atlasZoom === 'in' ? 1.16 : 0.86;
        zoom = Math.max(0.45, Math.min(2.6, zoom * zf));
        return;
      }
      if (ev.target.closest('[data-atlas-reset]')) {
        yaw = 0.38; pitch = 0.26; zoom = 1.0; panX = 0; panY = 0;
        return;
      }
      if (ev.target.closest('[data-atlas-spin]')) {
        autoSpin = !autoSpin;
        if (spinBtn) spinBtn.textContent = `Auto-Orbit: ${autoSpin ? 'ON' : 'OFF'}`;
        return;
      }
      const actBtn = ev.target.closest('[data-atlas-act]');
      if (actBtn && srcSel && dstSel) {
        const csrf = document.querySelector('meta[name="zcg-csrf-token"]')?.content || '';
        const body = JSON.stringify({
          action: actBtn.dataset.atlasAct,
          source_id: srcSel.value,
          target_id: dstSel.value,
        });
        const res = await fetch(`${apiPrefix}/action`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-zcg-csrf-token': csrf },
          body,
        });
        const data = await res.json().catch(() => ({}));
        if (receiptEl) {
          receiptEl.textContent = res.ok
            ? `${data.action} ${data.intent}: ${data.source_id} -> ${data.target_id}`
            : data.message || 'Select two distinct nodes';
        }
        bus?.emit('spatial:action', data);
      }
    });

    function draw() {
      if (!document.body.contains(el)) return;
      if (mode !== 'accessible-table') {
        const w = cv.width, h = cv.height, cx = w / 2, cy = h / 2;
        ctx.fillStyle = '#0b1220';
        ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
        ctx.lineWidth = 1;
        for (let gx = 40; gx < w; gx += 40) {
          ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, h); ctx.stroke();
        }
        for (let gy = 40; gy < h; gy += 40) {
          ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke();
        }
        const coreR = Number(scene.core_radius || 150) * 0.64 * zoom;
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.30)';
        ctx.beginPath(); ctx.arc(cx + panX, cy + panY, coreR, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([6, 5]);
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.25)';
        ctx.beginPath(); ctx.arc(cx + panX, cy + panY, coreR * 1.48, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]);

        const nodes = scene.nodes || [];
        const pts = nodes.map((nd, idx) => ({ nd, idx, ...projectIdx(idx, cx, cy) }));
        for (const lens of scene.lenses || []) {
          const ia = nodeMap.get(lens.source_id || lens.node_a);
          const ib = nodeMap.get(lens.target_id || lens.node_b);
          if (ia === undefined || ib === undefined) continue;
          const pa = pts[ia], pb = pts[ib];
          ctx.strokeStyle = 'rgba(34, 197, 94, 0.42)';
          ctx.lineWidth = 3;
          ctx.beginPath(); ctx.moveTo(pa.sx, pa.sy); ctx.lineTo(pb.sx, pb.sy); ctx.stroke();
          ctx.fillStyle = 'rgba(34, 197, 94, 0.20)';
          ctx.beginPath();
          ctx.arc((pa.sx + pb.sx) / 2, (pa.sy + pb.sy) / 2, 9 * zoom, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.lineWidth = 1.4;
        for (const ed of scene.edges || []) {
          const isrc = nodeMap.get(ed.source_id), idst = nodeMap.get(ed.target_id);
          if (isrc === undefined || idst === undefined) continue;
          const ps = pts[isrc], pd = pts[idst];
          ctx.strokeStyle = 'rgba(56, 189, 248, 0.48)';
          ctx.beginPath(); ctx.moveTo(ps.sx, ps.sy); ctx.lineTo(pd.sx, pd.sy); ctx.stroke();
        }
        const ordered = [...pts].sort((a, b) => b.z2 - a.z2);
        screenPts = [];
        ctx.font = '12px system-ui, sans-serif';
        for (const { nd, sx, sy, p } of ordered) {
          const col = RING_COLORS[nd.surface_ring] || '#38bdf8';
          const rad = Math.max(8, Number(nd.membrane_radius || 28) * 0.36 * zoom * p);
          screenPts.push({ id: nd.node_id, ring: nd.surface_ring, sx, sy, rad });
          if (nd.zone_band !== 'connected-core') ctx.setLineDash([4, 3]);
          const isCore = nd.zone_band === 'connected-core';
          ctx.fillStyle = isCore ? 'rgba(56,189,248,0.2)' : 'rgba(148,163,184,0.14)';
          ctx.strokeStyle = col;
          ctx.lineWidth = 1.8;
          ctx.beginPath(); ctx.arc(sx, sy, rad, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = col;
          ctx.beginPath(); ctx.arc(sx, sy, 4.2, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = '#f8fafc';
          ctx.fillText(`${nd.node_id} [${nd.surface_ring}]`, sx + rad + 5, sy + 4);
        }
        ctx.fillStyle = '#94a3b8';
        const modeLabel = mode === 'blueprint-2d' ? '2D BLUEPRINT' : '3D ORBIT';
        const activeLens = scene.lens || 'relational-affinity';
        const hud = `${modeLabel} · Lens: ${activeLens} · Nodes: ${nodes.length} · Edges: ${(scene.edges || []).length}`;
        ctx.fillText(`${hud} · Zoom: ${zoom.toFixed(2)}x`, 14, 22);
        const reducedMotion =
          document.documentElement.dataset.zcgMotion === 'reduced' ||
          Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches);
        if (mode === 'blueprint-3d' && autoSpin && !drag && !reducedMotion) yaw += 0.0045;
      }
      requestAnimationFrame(draw);
    }

    syncScene(scene);
    setMode(mode);
    requestAnimationFrame(draw);
  };
})();
