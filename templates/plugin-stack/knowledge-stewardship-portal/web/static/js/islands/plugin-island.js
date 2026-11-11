(() => {
  window.ZCGIslands = window.ZCGIslands || {};
  window.ZCGIslands['plugin-status'] = (el, _props, bus) => {
    const badge = el.querySelector('[data-role="island-badge"]');
    const detail = el.querySelector('[data-role="island-detail"]');
    if (badge) badge.textContent = 'Hydrated · knowledge-stewardship-portal';
    bus?.on('sse.message', (raw) => {
      if (detail) detail.textContent = `Live SSE snapshot received (${String(raw).slice(0, 72)})`;
    });
  };
})();
