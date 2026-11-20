(() => {
  window.ZCGIslands = window.ZCGIslands || {};
  window.ZCGIslands['plugin-status'] = (el, _props, bus) => {
    const badge = el.querySelector('[data-role="island-badge"]');
    const detail = el.querySelector('[data-role="island-detail"]');
    const host = el.querySelector('[data-role="wallet-providers"]');
    const seen = new Set();
    const renderProviders = () => {
      if (!host) return;
      const items = Array.from(seen);
      host.textContent = items.length
        ? `Detected Read-Only Providers: ${items.join(' · ')}`
        : 'Zero-Custody Watch Mode (Phantom / Wallet Standard / EIP-6963 ready)';
    };
    window.addEventListener('eip6963:announceProvider', (ev) => {
      const name = ev?.detail?.info?.name;
      if (name) { seen.add(`${name} (EIP-6963)`); renderProviders(); }
    });
    window.dispatchEvent(new Event('eip6963:requestProvider'));
    if (navigator.wallets && typeof navigator.wallets.get === 'function') {
      for (const w of navigator.wallets.get()) {
        if (w?.name) seen.add(`${w.name} (Wallet Standard)`);
      }
    }
    if (window.phantom) seen.add('Phantom (BTC/EVM/Solana)');
    renderProviders();
    if (badge) badge.textContent = 'Hydrated · sovereign-wallet-cockpit';
    bus?.on('sse.message', (raw) => {
      if (detail) detail.textContent = `Live SSE snapshot (${String(raw).slice(0, 72)})`;
    });
  };
})();
