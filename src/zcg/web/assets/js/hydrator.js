// ZeroCloudGravity — Progressive Island Hydrator (eager | idle | visible, ES2024)
(() => {
  window.ZCGIslands = window.ZCGIslands || {};

  async function mount(el) {
    if (el.dataset.hydrated) {
      return;
    }
    el.dataset.hydrated = '1';
    const props = JSON.parse(el.dataset.props || '{}');
    if (el.dataset.module) {
      const mod = await import(el.dataset.module);
      mod.mount?.(el, props, window.IslandBus);
    } else {
      window.ZCGIslands[el.dataset.island]?.(el, props, window.IslandBus);
    }
  }

  function hydrateAll(root = document) {
    root.querySelectorAll('[data-island]').forEach((el) => {
      const mode = el.dataset.hydrate || 'visible';
      if (mode === 'eager') {
        queueMicrotask(() => mount(el));
      } else if (mode === 'idle') {
        const scheduleIdle =
          window.requestIdleCallback || ((cb) => setTimeout(cb, 50));
        scheduleIdle(() => mount(el));
      } else if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
          if (entries.some((entry) => entry.isIntersecting)) {
            observer.disconnect();
            mount(el);
          }
        });
        observer.observe(el);
      } else {
        mount(el);
      }
    });
  }

  window.ZCGIslands['portal-channels'] = (el) => {
    const statusEl = el.querySelector('[data-channel-status]');
    el.addEventListener('click', async (ev) => {
      const copyBtn = ev.target.closest('[data-copy-phone]');
      if (!copyBtn) return;
      const phone = copyBtn.dataset.copyPhone || '';
      if (navigator.clipboard?.writeText && phone) {
        await navigator.clipboard.writeText(phone).catch(() => {});
        copyBtn.textContent = 'Phone Copied!';
        if (statusEl) statusEl.textContent = `Copied ${phone}`;
      }
    });
    el.querySelectorAll('form[data-portal-form]').forEach((form) => {
      form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const csrf = document.querySelector('meta[name="zcg-csrf-token"]')?.content || '';
        const body = new URLSearchParams(new FormData(form)).toString();
        const res = await fetch(form.action, {
          method: 'POST',
          headers: {
            'content-type': 'application/x-www-form-urlencoded',
            'x-zcg-csrf-token': csrf,
          },
          body,
        });
        const data = await res.json().catch(() => ({}));
        if (statusEl) {
          statusEl.textContent = res.ok
            ? `Queued (${data.receipt_id || data.request_id || 'OK'})`
            : data.message || 'Check input fields';
        }
        if (res.ok) form.reset();
      });
    });
  };

  window.ZCGIslands['draft-studio'] = (el, props) => {
    const inputEl = el.querySelector('[data-draft-input]');
    const statusEl = el.querySelector('[data-draft-status]');
    const linesEl = el.querySelector('[data-draft-lines]');
    const saveBtn = el.querySelector('[data-draft-save]');
    const copyBtn = el.querySelector('[data-draft-copy]');
    const resetBtn = el.querySelector('[data-draft-reset]');
    if (!inputEl) return;
    const storageKey = String(props.storageKey || 'zcg_draft_studio');
    const saveUrl = String(props.saveUrl || '');
    const resetUrl = String(props.resetUrl || '');
    const payloadField = String(props.payloadField || 'prompt');
    const draftKey = String(props.draftKey || '');
    const maxLines = Number(props.maxLines || 464);
    const resetMsg = String(
      props.resetConfirm || 'Discard your customized edits and restore the default template?'
    );
    let isDirty = false;
    let timerId = null;

    const setStatus = (msg) => {
      if (statusEl) statusEl.textContent = msg;
    };

    const updateLineCount = () => {
      if (linesEl) {
        linesEl.textContent = `${inputEl.value.split('\n').length} / ${maxLines} lines`;
      }
    };

    const clearLocalDraft = () => {
      if (timerId) {
        clearTimeout(timerId);
        timerId = null;
      }
      isDirty = false;
      try {
        window.localStorage?.removeItem(storageKey);
      } catch {
        // Ignore storage restrictions
      }
    };

    try {
      const localCached = window.localStorage?.getItem(storageKey);
      if (localCached && !props.hasServerDraft && localCached !== inputEl.value) {
        inputEl.value = localCached;
        isDirty = true;
        setStatus('● Restored unsaved browser draft — click Save Draft to sync.');
      }
    } catch {
      // Ignore private-browsing storage restrictions
    }

    updateLineCount();

    const persistToServer = async () => {
      if (timerId) {
        clearTimeout(timerId);
        timerId = null;
      }
      if (!saveUrl || !inputEl.value.trim()) return false;
      const csrf = document.querySelector('meta[name="zcg-csrf-token"]')?.content || '';
      const payload = {
        [payloadField]: inputEl.value,
        ...(draftKey ? { draft_key: draftKey } : {}),
      };
      const res = await fetch(saveUrl, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-zcg-csrf-token': csrf,
        },
        body: JSON.stringify(payload),
      }).catch(() => null);
      if (!res || !res.ok) {
        setStatus('⚠ Auto-save paused — draft kept safely in browser storage.');
        return false;
      }
      const data = await res.json().catch(() => ({}));
      isDirty = false;
      const stamp = data.updated_at ? ` · ${data.updated_at}` : '';
      setStatus(`✓ Draft saved locally (.zcg/runtime/${stamp})`);
      return true;
    };

    inputEl.addEventListener('input', () => {
      isDirty = true;
      updateLineCount();
      try {
        window.localStorage?.setItem(storageKey, inputEl.value);
      } catch {
        // Ignore storage quota errors
      }
      setStatus('● Editing — auto-saving draft...');
      if (timerId) clearTimeout(timerId);
      timerId = setTimeout(() => {
        void persistToServer();
      }, 600);
    });

    el.querySelectorAll('form').forEach((form) => {
      form.addEventListener('submit', () => {
        clearLocalDraft();
      });
    });

    el.querySelectorAll('[data-draft-discard]').forEach((btn) => {
      btn.addEventListener('click', () => {
        clearLocalDraft();
      });
    });

    window.addEventListener('beforeunload', (ev) => {
      if (isDirty) {
        ev.preventDefault();
        ev.returnValue = '';
      }
    });

    document.addEventListener('click', (ev) => {
      const link = ev.target.closest('a[href]');
      if (!link || !isDirty) return;
      const href = link.getAttribute('href') || '';
      if (!href || href.startsWith('#')) return;
      if (!window.confirm('You have unsaved edits in your setup prompt. Leave anyway?')) {
        ev.preventDefault();
      }
    });

    saveBtn?.addEventListener('click', async () => {
      await persistToServer();
    });

    copyBtn?.addEventListener('click', async () => {
      await persistToServer();
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(inputEl.value).catch(() => {});
      }
      setStatus(
        '✓ Prompt copied & saved! Open this workspace in local Antigravity and paste in a New Chat.'
      );
    });

    resetBtn?.addEventListener('click', async () => {
      if (!window.confirm(resetMsg)) return;
      if (timerId) {
        clearTimeout(timerId);
        timerId = null;
      }
      const csrf = document.querySelector('meta[name="zcg-csrf-token"]')?.content || '';
      if (resetUrl) {
        const res = await fetch(resetUrl, {
          method: 'POST',
          headers: { 'x-zcg-csrf-token': csrf },
        }).catch(() => null);
        const data = res && res.ok ? await res.json().catch(() => ({})) : {};
        if (data.active_prompt) inputEl.value = data.active_prompt;
      }
      clearLocalDraft();
      updateLineCount();
      setStatus('↺ Restored original archetype setup template.');
    });
  };

  window.ZCGHydrator = { hydrateAll, mount };
  document.addEventListener('DOMContentLoaded', () => hydrateAll(document));
})();
