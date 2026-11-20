// ZeroCloudGravity — Sovereign Node Control Plane & Public Passport Island (ES2024, 0 innerHTML)
(() => {
  window.ZCGIslands = window.ZCGIslands || {};

  function codeLine(text, { linkHref = '', linkText = '' } = {}) {
    const code = document.createElement('code');
    code.className = 'zcg-code-line';
    code.textContent = String(text ?? '');
    if (linkHref && linkText) {
      const anchor = document.createElement('a');
      anchor.href = linkHref;
      anchor.textContent = linkText;
      code.appendChild(anchor);
    }
    return code;
  }

  function badgeEl(text, { title = '', extraClass = '', dataState = '' } = {}) {
    const span = document.createElement('span');
    span.className = extraClass ? `zcg-badge ${extraClass}` : 'zcg-badge';
    span.textContent = text;
    if (title) span.title = title;
    if (dataState) span.dataset.healthState = dataState;
    return span;
  }

  function copyBtnEl(cmd) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'zcg-btn zcg-btn--secondary zcg-btn--sm';
    btn.dataset.zcgCopy = String(cmd ?? '');
    btn.textContent = 'Copy';
    return btn;
  }

  const HEALTH_DIMENSIONS = [
    ['security_posture', 'Security Posture', 'Run local posture audit:', 'make workstation-audit'],
    ['skill_trust', 'Skill Trust', 'Inspect SKILL.md findings:', 'zcg lint-skills .'],
    ['sync_safety', 'Git Sync Safety', 'Inspect dirty/ahead/behind state:', 'git status --short'],
    ['operational_drift', 'Template & Makefile Sync', 'Synchronize node templates:', 'make sync'],
  ];

  function renderHealthBreakdown(container, nodeHealth) {
    if (!container) return;
    if (!nodeHealth || typeof nodeHealth !== 'object') {
      container.replaceChildren();
      return;
    }
    const overall = String(nodeHealth.overall_state || 'OPTIMAL').toUpperCase();
    const head = document.createElement('div');
    head.className = 'zcg-health-head';
    const headLbl = document.createElement('strong');
    headLbl.textContent = '4-Dimension Node Health Breakdown';
    head.append(
      headLbl,
      badgeEl(overall, {
        extraClass: `zcg-health-pill zcg-health-pill--${overall.toLowerCase()}`,
        dataState: overall,
      }),
    );
    const dims = nodeHealth.dimensions || {};
    const grid = document.createElement('div');
    grid.className = 'zcg-grid';
    for (const [key, label, fixHint, fixCmd] of HEALTH_DIMENSIONS) {
      const d = dims[key] || {};
      const st = String(d.state || 'UNCONFIGURED').toUpperCase();
      const card = document.createElement('div');
      card.className = 'zcg-kanban-card';
      card.dataset.healthDimension = key;
      const top = document.createElement('div');
      top.className = 'zcg-kanban-col__head';
      const titleEl = document.createElement('strong');
      titleEl.textContent = label;
      top.append(
        titleEl,
        badgeEl(st, {
          extraClass: `zcg-health-pill zcg-health-pill--${st.toLowerCase()}`,
          dataState: st,
        }),
      );
      const noteEl = document.createElement('p');
      noteEl.className = 'zcg-muted-note';
      noteEl.textContent = String(d.note || st);
      card.append(top, noteEl);
      if (st === 'ATTENTION' || st === 'CRITICAL') {
        const fixRow = document.createElement('div');
        fixRow.className = 'zcg-health-fix';
        const hintEl = document.createElement('small');
        hintEl.textContent = fixHint;
        const cmdEl = document.createElement('code');
        cmdEl.textContent = fixCmd;
        fixRow.append(hintEl, cmdEl, copyBtnEl(fixCmd));
        card.append(fixRow);
      }
      grid.append(card);
    }
    container.replaceChildren(head, grid);
  }

  window.ZCGIslands['cockpit-passport'] = (rootEl, _props, bus) => {
    const dataNode = document.getElementById('cockpit-data');
    if (!dataNode || !dataNode.textContent) return;
    const eventBus = bus || window.IslandBus;
    const data = JSON.parse(dataNode.textContent);
    const topo = data.intranet_topology || {};
    const rep = data.data_scopes?.node?.representation_context || {};
    const ledger = data.data_scopes?.node?.own_node_ledger || {};
    const gates = data.data_scopes?.network?.environment_gates || {};
    const netLinks = data.data_scopes?.network?.network_representation_links || {};
    const fleet = data.data_scopes?.federation?.fleet_plugin_inventory || [];
    const deployTarget = data.data_scopes?.federation?.deployment_target || {};
    const byId = (id) => document.getElementById(id);

    function renderLineageCrumb(env) {
      const crumbEl = byId('lineage_crumb');
      if (!crumbEl) return;
      const parent = netLinks.parent_home_node;
      const selfSpan = document.createElement('strong');
      selfSpan.textContent = `● ${data.layer_id}`;
      const roleSpan = document.createElement('span');
      roleSpan.className = 'zcg-crumb-role';
      roleSpan.textContent = `(${data.human_role || data.layer_role || 'node'})`;
      if (parent && parent.node_id) {
        let parentEl;
        if (parent.online === false) {
          parentEl = document.createElement('span');
          parentEl.className = 'zcg-crumb-offline';
          parentEl.setAttribute('aria-disabled', 'true');
          parentEl.textContent = `⚪ ↑ ${parent.node_id} (Offline)`;
        } else {
          parentEl = document.createElement('a');
          parentEl.href = parent.cockpit_url ? `${parent.cockpit_url}/?env=${env}` : '/';
          parentEl.textContent = `↑ ${parent.node_id}`;
        }
        const sep = document.createElement('span');
        sep.textContent = '›';
        crumbEl.replaceChildren(parentEl, sep, selfSpan, roleSpan);
      } else {
        crumbEl.replaceChildren(badgeEl('★ Root 0'), selfSpan, roleSpan);
      }
    }

    function renderEnvironment(env) {
      const isPublicPro = topo.visibility === 'public' && env === 'pro';
      const scopeFile =
        env === 'dev' ? 'node_scope.json' : env === 'pro' ? 'federation_scope.json' : 'network_scope.json';
      const secPosture = rep.security_posture;
      const skillTrust = rep.skill_trust;
      const nodeHealth = rep.node_health;
      const isPersonalProfile = data.layer_role === 'workstation' && rep.workstation_config;
      const modeLabel = isPublicPro
        ? 'External Sovereign Passport'
        : isPersonalProfile
          ? 'Node Admin — Personal Hub (Root 0)'
          : 'Node Admin';

      renderLineageCrumb(env);

      const subEl = byId('sub');
      if (subEl) {
        const regime = rep.runtime_telemetry?.regime || 'OPTIMAL';
        subEl.textContent = `${modeLabel} · ${rep.view_archetype} · Health: ${regime} · Scope: surfaces/data/${scopeFile}`;
      }

      const sprintHdr = byId('s_hdr');
      if (sprintHdr) {
        sprintHdr.textContent = isPublicPro
          ? `Public Governance Attestation (${scopeFile})`
          : 'Repository Work Summary';
      }
      const z4Hdr = byId('z4_hdr');
      if (z4Hdr) {
        z4Hdr.textContent = isPublicPro
          ? 'External Peer Verification & Link Commands'
          : 'Operator CLI Quick Reference';
      }

      const canSwitchEnv = data.can_switch_env !== false;
      document.documentElement.dataset.zcgEnv = canSwitchEnv ? env : 'pro';
      renderHealthBreakdown(byId('health_breakdown'), nodeHealth);

      const workEl = byId('work');
      if (workEl) {
        if (isPublicPro) {
          const p = document.createElement('p');
          p.textContent =
            'Public Twin Status: CERTIFIED (pro) · Internal sprint items sanitized on public passport.';
          workEl.replaceChildren(p);
        } else {
          const summary = document.createElement('p');
          summary.textContent =
            `Open: ${ledger.total_open_items ?? 0} · ` +
            `In Progress: ${ledger.total_in_progress_items ?? 0} · ` +
            `Completed: ${ledger.total_completed_items ?? 0}`;
          workEl.replaceChildren(
            summary,
            ...(ledger.active_node_tasks || []).map((t) => codeLine(t)),
          );
        }
      }

      byId('iac')?.replaceChildren(
        ...(nodeHealth
          ? [codeLine(
              `Node Health: ${nodeHealth.overall_state} ` +
              `(Unconfigured/N-A: ${(nodeHealth.unconfigured_dimensions || []).join(', ') || 'none'})`,
            )]
          : []),
        ...(secPosture
          ? [codeLine(`Security Posture: ${secPosture.score}/100 (${secPosture.grade})`)]
          : []),
        ...(skillTrust
          ? [codeLine(
              `Skill Trust (zcg-skill-auditor): ${skillTrust.score}/100 ` +
              `(${skillTrust.grade} · ${skillTrust.scanned_skill_count} skills · ${skillTrust.finding_count} findings)`,
            )]
          : []),
        ...fleet.map((p) =>
          codeLine(`[Plugin] ${p.workspace_id}: ${p.plugin_id} (${p.status} · ${p.environment})`),
        ),
        codeLine(
          `Deployment Target: ${deployTarget.provider || ''} (${deployTarget.stage || ''}) -> ${deployTarget.iac_manifest || ''}`,
        ),
        ...((topo.promotion_pipeline === 'staged' || topo.visibility === 'public')
          ? Object.entries(gates).map(([k, v]) =>
              codeLine(`Gate [${k.toUpperCase()}]: ${v.allowed ? 'READY' : 'BLOCKED'}`),
            )
          : []),
      );

      byId('cmds')?.replaceChildren(
        ...(data.remote_session_commands || []).map((c) => {
          const row = document.createElement('div');
          row.className = 'zcg-cmd-row';
          row.append(codeLine(c), copyBtnEl(c));
          return row;
        }),
      );
      eventBus?.emit('env:change', { env, scope: scopeFile });
    }

    function activateAdminTab(rawTabId) {
      const tabs = Array.from(rootEl.querySelectorAll('[data-admin-tab]'));
      if (!tabs.length) return;
      const aliases = {
        modules: 'capabilities', telemetry: 'health', mesh: 'network', inbox: 'exposure',
      };
      const normId = aliases[rawTabId] || rawTabId;
      const activeBtn = tabs.find((b) => b.dataset.adminTab === normId) || tabs[0];
      const tabId = activeBtn.dataset.adminTab;
      const tabTitle = activeBtn.dataset.adminTitle || tabId;
      for (const btn of tabs) {
        const isSel = btn === activeBtn;
        btn.classList.toggle('is-active', isSel);
        btn.setAttribute('aria-selected', String(isSel));
      }
      const indicator = document.querySelector('[data-zcg-view-indicator]');
      if (indicator) indicator.textContent = tabTitle;
      if (window.history?.replaceState) {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.set('tab', tabId);
        window.history.replaceState(null, '', nextUrl);
      }
      for (const panel of rootEl.querySelectorAll('[data-admin-panel]')) {
        const pKind = panel.dataset.adminPanel;
        const show =
          (tabId === 'health' && pKind === 'health') ||
          (tabId === 'brand' && pKind === 'brand') ||
          (tabId !== 'health' && tabId !== 'brand' && pKind === 'remote');
        panel.hidden = !show;
      }
      byId('zcg-capability-stage')?.replaceChildren();
      if (tabId === 'health') {
        window.ZCGSwap?.swapFetch('/api/modules/telemetry', {
          method: 'GET',
          targetSel: '#admin-telemetry-slot',
        });
      } else if (tabId !== 'brand' && activeBtn.dataset.adminFetch) {
        window.ZCGSwap?.swapFetch(activeBtn.dataset.adminFetch, {
          method: 'GET',
          targetSel: '#zcg-capability-stage',
        });
      }
    }

    document.addEventListener('click', (ev) => {
      const tabBtn = ev.target.closest('[data-admin-tab]');
      if (tabBtn && rootEl.contains(tabBtn)) {
        ev.preventDefault();
        activateAdminTab(tabBtn.dataset.adminTab);
      }
    });

    const params = new URLSearchParams(window.location.search);
    const initialEnv = params.get('env') || data.plugin_state?.environment || 'dev';
    renderEnvironment(initialEnv);
    activateAdminTab(params.get('tab') || 'health');
    rootEl.dataset.cockpitReady = '1';
  };
})();
