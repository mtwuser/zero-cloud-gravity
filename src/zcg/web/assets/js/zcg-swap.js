// ZeroCloudGravity — Progressive Partial Swap, HTTP 286 Polling & SSE Bridge (ES2024)
(() => {
  const readCookieValue = (name) => {
    const prefix = `${name}=`;
    const part = (document.cookie || '')
      .split(';')
      .map((s) => s.trim())
      .find((s) => s.startsWith(prefix));
    return part ? decodeURIComponent(part.slice(prefix.length)) : '';
  };

  const readCsrfToken = () =>
    document.querySelector('meta[name="zcg-csrf-token"]')?.content ||
    readCookieValue('zcg_csrf');

  const activeWorkspaceScope = () =>
    document.querySelector('[data-zcg-ws-scope]')?.dataset.zcgWsScope || '';

  const TRANSVERSAL_VIEWS = {
    docs: ['/api/modules/docs-reader', 'Docs & Knowledge'],
  };

  async function swapFetch(
    url,
    { method = 'GET', body = null, targetSel = null } = {},
  ) {
    const headers = { 'hx-request': 'true' };
    if (targetSel) {
      headers['hx-target'] = targetSel;
    }
    const csrfToken = readCsrfToken();
    if (method !== 'GET' && csrfToken) {
      headers['x-zcg-csrf-token'] = csrfToken;
    }

    let reqUrl = String(url);
    const wsScope =
      method === 'GET' && document.querySelector('[data-zcg-plane="workspace"]')
        ? activeWorkspaceScope()
        : '';
    if (wsScope && !reqUrl.includes('ws_scope=')) {
      const sep = reqUrl.includes('?') ? '&' : '?';
      reqUrl = `${reqUrl}${sep}ws_scope=${encodeURIComponent(wsScope)}`;
    }

    const res = await fetch(reqUrl, { method, headers, body });
    if (res.ok && res.headers.get('hx-refresh') === 'true') {
      window.location.reload();
      return res;
    }
    const html = await res.text();
    const effectiveSelector = res.headers.get('hx-retarget') || targetSel;
    const swapMode = res.headers.get('hx-reswap') || 'innerHTML';
    const targetEl = effectiveSelector
      ? document.querySelector(effectiveSelector)
      : null;

    if (targetEl) {
      if (swapMode === 'outerHTML') {
        targetEl.outerHTML = html;
      } else {
        targetEl.innerHTML = html;
      }
      bindPolling(document);
      window.ZCGHydrator?.hydrateAll(document);
    }

    const triggerTopic = res.headers.get('hx-trigger');
    if (triggerTopic === 'appearanceUpdated' && targetEl) {
      const box = targetEl.querySelector('[data-apply-contrast],[data-apply-theme]');
      const root = document.documentElement;
      const curPlane =
        document.querySelector('[data-zcg-appearance-plane]')?.dataset.zcgAppearancePlane;
      const scopeOk =
        !box?.dataset.applyScope ||
        box.dataset.applyScope === 'all' ||
        box.dataset.applyScope === curPlane;
      if (box?.dataset.applyContrast) root.dataset.zcgContrast = box.dataset.applyContrast;
      if (box?.dataset.applyScale) root.dataset.zcgScale = box.dataset.applyScale;
      if (box?.dataset.applyMotion) root.dataset.zcgMotion = box.dataset.applyMotion;
      if (scopeOk && box?.dataset.applyTheme) root.dataset.zcgTheme = box.dataset.applyTheme;
      if (scopeOk && box?.dataset.applyAccent) root.dataset.zcgAccent = box.dataset.applyAccent;
      if (scopeOk && box?.dataset.applyLogo) {
        document.querySelectorAll('.zcg-brand-logo').forEach((img) => {
          img.src = box.dataset.applyLogo;
        });
      }
    }
    if (triggerTopic) {
      window.IslandBus?.emit(triggerTopic, { status: res.status });
    }
    return res;
  }

  function activateTransversalView(viewKey) {
    const entry = TRANSVERSAL_VIEWS[viewKey];
    const isWorkspace = Boolean(document.querySelector('[data-zcg-plane="workspace"]'));
    const stage = document.getElementById('zcg-capability-stage');
    if (!entry || !isWorkspace || !stage) {
      return false;
    }
    const [endpoint, titleText] = entry;
    document.querySelectorAll('.zcg-sidebar [role="tab"]').forEach((tabEl) => {
      const isMatch = tabEl.dataset.tabId === viewKey;
      tabEl.classList.toggle('is-active', isMatch);
      tabEl.setAttribute('aria-selected', String(isMatch));
    });
    const indicator = document.querySelector('[data-zcg-view-indicator]');
    if (indicator) {
      indicator.textContent = titleText;
    }
    if (window.history?.replaceState) {
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.set('view', viewKey);
      nextUrl.searchParams.delete('tab');
      window.history.replaceState(null, '', nextUrl);
    }
    document.querySelectorAll('details.zcg-burger[open]').forEach((d) => {
      d.open = false;
    });
    swapFetch(endpoint, { method: 'GET', targetSel: '#zcg-capability-stage' });
    return true;
  }

  document.addEventListener('click', (ev) => {
    document.querySelectorAll('details.zcg-burger[open]').forEach((det) => {
      if (!det.contains(ev.target)) {
        det.open = false;
      }
    });

    const navViewLink = ev.target.closest('a[data-zcg-nav-view]');
    if (navViewLink && activateTransversalView(navViewLink.dataset.zcgNavView)) {
      ev.preventDefault();
      return;
    }

    const openBtn = ev.target.closest('[data-zcg-modal-open]');
    if (openBtn) {
      document.getElementById(openBtn.dataset.zcgModalOpen)?.showModal();
      return;
    }

    const closeBtn = ev.target.closest('[data-zcg-modal-close]');
    if (closeBtn) {
      document.getElementById(closeBtn.dataset.zcgModalClose)?.close();
      return;
    }

    const copyBtn = ev.target.closest('[data-zcg-copy]');
    if (copyBtn) {
      ev.preventDefault();
      navigator.clipboard?.writeText(copyBtn.dataset.zcgCopy || '');
      copyBtn.textContent = 'Copied ✓';
      return;
    }

    const scopeBtn = ev.target.closest('[data-ws-scope]');
    if (scopeBtn) {
      ev.preventDefault();
      const nextScope = scopeBtn.dataset.wsScope || 'all';
      const group = scopeBtn.closest('[data-zcg-ws-scope]');
      if (group) {
        group.dataset.zcgWsScope = nextScope;
        group.querySelectorAll('[data-ws-scope]').forEach((btn) => {
          const active = btn === scopeBtn;
          btn.classList.toggle('is-active', active);
          btn.setAttribute('aria-pressed', String(active));
        });
      }
      if (window.history?.replaceState) {
        const nextUrl = new URL(window.location.href);
        if (nextScope === 'all') {
          nextUrl.searchParams.delete('ws_scope');
        } else {
          nextUrl.searchParams.set('ws_scope', nextScope);
        }
        window.history.replaceState(null, '', nextUrl);
      }
      const activeUrl =
        document.querySelector('.zcg-sidebar [role="tab"].is-active')?.dataset.zcgGet ||
        '/api/modules/work-ledger?section=dashboard';
      swapFetch(activeUrl, { method: 'GET', targetSel: '#zcg-capability-stage' });
      return;
    }

    const triggerEl = ev.target.closest(
      'button[data-zcg-get],a[data-zcg-get],[data-zcg-delete]',
    );
    if (!triggerEl) {
      return;
    }
    ev.preventDefault();

    if (triggerEl.getAttribute('role') === 'tab') {
      const tabScope = triggerEl.closest('.zcg-sidebar') || triggerEl.parentElement;
      tabScope?.querySelectorAll('[role="tab"]').forEach((tabEl) => {
        const isActive = tabEl === triggerEl;
        tabEl.classList.toggle('is-active', isActive);
        tabEl.setAttribute('aria-selected', String(isActive));
      });
      const indicator = document.querySelector('[data-zcg-view-indicator]');
      if (indicator) {
        indicator.textContent = (
          triggerEl.dataset.viewTitle ||
          triggerEl.textContent ||
          ''
        ).trim();
      }
      if (triggerEl.dataset.tabId && window.history?.replaceState) {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.set('view', triggerEl.dataset.tabId);
        nextUrl.searchParams.delete('tab');
        window.history.replaceState(null, '', nextUrl);
      }
    }

    const method = triggerEl.dataset.zcgDelete ? 'DELETE' : 'GET';
    const url = triggerEl.dataset.zcgDelete || triggerEl.dataset.zcgGet;
    swapFetch(url, { method, targetSel: triggerEl.dataset.zcgTarget });
  });

  document.addEventListener('submit', (ev) => {
    const form = ev.target.closest('form[data-zcg-get],form[data-zcg-post]');
    if (!form) {
      return;
    }
    ev.preventDefault();

    const formData = new FormData(form);
    if (form.dataset.zcgGet) {
      const query = new URLSearchParams(formData).toString();
      const base = form.dataset.zcgGet;
      const sep = base.includes('?') ? '&' : '?';
      const url = query ? `${base}${sep}${query}` : base;
      swapFetch(url, { method: 'GET', targetSel: form.dataset.zcgTarget });
    } else {
      const isMultipart = (form.enctype || '').includes('multipart/form-data');
      const body = isMultipart ? formData : new URLSearchParams(formData);
      swapFetch(form.dataset.zcgPost, {
        method: 'POST',
        body,
        targetSel: form.dataset.zcgTarget,
      });
    }
  });

  function bindPolling(root) {
    root.querySelectorAll('[data-zcg-poll]').forEach((node) => {
      if (node.dataset.zcgPollActive) {
        return;
      }
      node.dataset.zcgPollActive = '1';
      const intervalMs = Math.max(250, Number(node.dataset.zcgInterval || 1000));
      const timer = setInterval(async () => {
        if (!document.body.contains(node)) {
          clearInterval(timer);
          return;
        }
        const res = await fetch(node.dataset.zcgPoll, {
          headers: { 'hx-request': 'true' },
        });
        node.outerHTML = await res.text();
        window.ZCGHydrator?.hydrateAll(document);
        if (res.status === 286) {
          clearInterval(timer);
        }
      }, intervalMs);
    });
  }

  function bindSSE(root) {
    root.querySelectorAll('[data-zcg-sse]').forEach((node) => {
      const eventSource = new EventSource(node.dataset.zcgSse);
      eventSource.onmessage = (ev) =>
        window.IslandBus?.emit('sse.message', ev.data);
    });
  }

  window.ZCGSwap = { swapFetch, bindPolling, bindSSE };
  document.addEventListener('DOMContentLoaded', () => {
    bindPolling(document);
    bindSSE(document);
    const params = new URLSearchParams(window.location.search);
    const initialView = params.get('view') || params.get('tab');
    if (initialView && TRANSVERSAL_VIEWS[initialView]) {
      if (activateTransversalView(initialView)) {
        return;
      }
    }
    const ssrViews = new Set(['overview', 'dashboard', 'backlog', 'roadmaps', 'validations', 'metrics']);
    if (initialView && !ssrViews.has(initialView)) {
      const savedTab = Array.from(document.querySelectorAll('[role="tab"][data-tab-id]')).find(
        (el) => el.dataset.tabId === initialView,
      );
      savedTab?.click();
    }
  });
})();
