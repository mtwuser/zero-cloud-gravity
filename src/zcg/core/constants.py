"""Nominal constants, contracts, and orthogonal taxonomies for ZeroCloudGravity.

Specification: docs/architecture/01_core_and_node_manifest.md
"""

from __future__ import annotations

import stat
from pathlib import Path

REPO_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
NODE_MANIFEST_REL_PATH: str = "system/zcg-node.json"
NODE_MANIFEST_CONTRACT_REV: str = "zcg-node-v1"
TEMPLATE_MANIFEST_CONTRACT_REV: str = "zcg-template-v1"
SKILLS_MANIFEST_CONTRACT_REV: str = "zcg-skills-v1"
PERMISSIONS_MANIFEST_CONTRACT_REV: str = "zcg-agy-permissions-v1"
SIDECAR_MANIFEST_CONTRACT_REV: str = "zcg-sidecar-v1"
SKILLS_MANIFEST_REL_PATH: str = ".agents/skills.json"
PLUGINS_MANIFEST_REL_PATH: str = ".agents/plugins.json"
ANTIGRAVITY_PERMISSIONS_REL_PATH: str = ".agents/antigravity-permissions.json"
SIDECAR_MANIFEST_REL_PATH: str = ".agents/sidecar.json"
TOOL_RUNTIME_REL_DIR: str = ".zcg/tools"
PROJECT_ZCG_MK_REL_PATH: str = ".agents/zcg.mk"
MCP_JSONRPC_PROTOCOL_REV: str = "2024-11-05"
MISSING_VERSION_SENTINEL: str = "unversioned"

OSS_WORKSTATION_IDS: tuple[str, ...] = (
    "root", "zero-cloud-gravity", "zero-cloud-gravity-workstation",
    "zcg-workstation-root", "mtwuser/zero-cloud-gravity",
)  # fmt: skip
VALID_LAYER_ROLES: tuple[str, ...] = (
    "corporate", "department", "domain-policy", "ephemeral-bot", "knowledge",
    "project", "squad", "service-node", "environment-cluster", "workstation",
)  # fmt: skip
TOPOLOGICAL_ROLE_CLASSES: dict[str, str] = {
    "corporate": "governance-layer", "domain-policy": "governance-layer",
    "department": "governance-layer", "squad": "governance-layer",
    "knowledge": "knowledge", "workstation": "runtime-node",
    "service-node": "runtime-node", "environment-cluster": "runtime-node",
    "ephemeral-bot": "ephemeral-sandbox", "project": "consumer-workspace",
}  # fmt: skip
LAYER_ORIGIN_ROLES: tuple[str, ...] = (
    "root", "workstation", "corporate", "domain-policy", "department", "squad", "knowledge",
)  # fmt: skip
MCP_OPERATING_MODES: dict[str, str] = {
    "oss-readonly-appliance": "workstation-baseline-provider",
    "oss-dev": "self-test-and-dev-only", "individual-root": "personal-root-hub",
    "corporate-root": "enterprise-governance-hub", "domain-policy": "departmental-policy-hub",
    "department": "departmental-policy-hub", "squad": "squad-execution-hub",
    "knowledge": "knowledge-corpus-provider", "service-node": "infrastructure-node-provider",
    "environment-cluster": "infrastructure-node-provider",
    "ephemeral-bot": "scoped-ephemeral-sandbox", "project": "project-consumer-only",
}  # fmt: skip
ROLE_DEFAULT_PRECEDENCE: dict[str, int] = {
    "domain-policy": 5, "corporate": 10, "workstation": 10, "ephemeral-bot": 15,
    "bridge": 20, "knowledge": 20, "department": 30, "squad": 50,
    "service-node": 60, "environment-cluster": 70, "project": 80,
}  # fmt: skip
INDIVIDUAL_MIN_PRECEDENCE, PUBLIC_GOV_MAX_ROOT_PRECEDENCE, PUBLIC_GOV_MAX_PRECEDENCE = 85, 2, 4
PUBLIC_GOV_PREFIXES: tuple[str, ...] = ("gov-", "geo-")
VALID_ENTITY_KINDS: tuple[str, ...] = (
    "public-government", "enterprise", "individual", "open-source",
)  # fmt: skip
VALID_VISIBILITY_MODES, VALID_PROMOTION_PIPELINES = ("private", "public"), ("direct", "staged")
VALID_ENVIRONMENTS: tuple[str, ...] = ("dev", "tst", "pre", "pro")
VALID_NODE_DATA_SCOPES: tuple[str, ...] = ("node", "network", "federation")
VALID_NODE_LINK_RELATIONS: tuple[str, ...] = (
    "lateral-peer", "co-sovereign-union", "spinout-project",
    "hr-process", "b2b-collaboration", "knowledge-feed",
)  # fmt: skip
VALID_PLUGIN_SERVICE_ACTIONS: tuple[str, ...] = (
    "install", "uninstall", "activate", "deactivate", "switch-env", "provision",
    "deploy", "restart", "healthcheck", "teardown", "enable-autostart", "disable-autostart",
)  # fmt: skip
DEFAULT_PLUGIN_BASE_PORT: int = 8700
CANONICAL_STACK_GROUP_DIRS: tuple[str, ...] = (
    "human-stack", "context-stack", "tool-stack", "plugin-stack",
)  # fmt: skip
TEMPLATE_STACK_GROUP_DIRS: tuple[str, ...] = CANONICAL_STACK_GROUP_DIRS
VALID_TEMPLATE_KINDS: tuple[str, ...] = TEMPLATE_STACK_GROUP_DIRS
CANONICAL_STARTER_TEMPLATES: tuple[str, ...] = (
    "universal-base", "academic-base", "science-base", "business-base",
    "academic-curriculum", "scientific-methodology", "software-engineering", "corporate-operations",
    "spatial-simulation", "nist-csf-security", "self-hosted-container", "google-cloud-iac",
    "workstation-control-tower", "corporate-root-hub", "node-work-cockpit", "tutor-study-cockpit",
    "secops-mcp-guardian", "knowledge-stewardship-portal", "sovereign-wallet-cockpit",
)  # fmt: skip
BUILTIN_COCKPIT_PLUGINS: tuple[str, ...] = (
    "workstation-control-tower", "corporate-root-hub", "node-work-cockpit",
    "tutor-study-cockpit", "secops-mcp-guardian", "knowledge-stewardship-portal",
    "sovereign-wallet-cockpit",
)  # fmt: skip
ROLE_DEFAULT_COCKPIT_PLUGIN: dict[str, str] = {
    "workstation": "workstation-control-tower", "corporate": "corporate-root-hub",
    "knowledge": "knowledge-stewardship-portal", "academic": "tutor-study-cockpit",
    "default": "node-work-cockpit",
}  # fmt: skip
BASE_SKILL_TAXONOMY: dict[str, tuple[str, ...]] = {
    "universal-base": ("sopen", "continue", "sclose", "review", "enrich"),
    "academic-base": (), "business-base": ("governance",),
    "science-base": ("architecture", "audit"),
}  # fmt: skip

DEFAULT_INTERACTION_LANGUAGE: str = "en"
INTERACTION_LANGUAGE_LABELS: dict[str, str] = {
    "en": "English (en)", "es": "Spanish (es)", "it": "Italian (it)",
    "fr": "French (fr)", "de": "German (de)", "pt": "Portuguese (pt)",
}  # fmt: skip
VALID_INTERACTION_LANGUAGES: tuple[str, ...] = tuple(INTERACTION_LANGUAGE_LABELS)
VALID_HUMAN_MASTERY_LEVELS: tuple[str, ...] = ("M1", "M2", "M3", "M4")
VALID_HUMAN_STACK_FACETS: tuple[str, ...] = ("domain-", "bridge-", "soft-", "hat-")
HUMAN_STACK_BLUEPRINT_HINT: str = (
    "[Optional: leave blank for default, or compose Human-Stack facets: "
    "domain-<area>:M1..M4 | bridge-* | soft-* | hat-*]"
)
VALID_EPISTEMIC_GRADES: tuple[str, ...] = ("E3", "E2", "E1", "E0")
EPISTEMIC_GRADE_RANK: dict[str, int] = {"E3": 3, "E2": 2, "E1": 1, "E0": 0}
EPISTEMIC_GRADE_LABELS: dict[str, str] = {
    "E3": "inviolable-axiom-or-law", "E2": "canonical-contract-or-standard",
    "E1": "contextual-guideline-or-theory", "E0": "provisional-hypothesis-or-draft",
}  # fmt: skip

VALID_KNOWLEDGE_PREFIXES: tuple[str, ...] = ("gov-", "sci-", "geo-", "org-")
VALID_KNOWLEDGE_STEWARDSHIP_STAGES: tuple[str, ...] = (
    "private-incubation", "public-community", "sovereign-authority",
)  # fmt: skip
KNOWLEDGE_DOMAIN_TAXONOMY: dict[str, dict[str, str]] = {
    "gov-": {"knowledge_domain": "jurisdictional-normative", "default_epistemic_grade": "E3",
        "default_entity_kind": "public-government",
        "default_templates": "business-base,corporate-operations,science-base"},
    "sci-": {"knowledge_domain": "scientific-epistemic", "default_epistemic_grade": "E2",
        "default_entity_kind": "enterprise",
        "default_templates": "science-base,scientific-methodology"},
    "geo-": {"knowledge_domain": "territorial-empirical", "default_epistemic_grade": "E3",
        "default_entity_kind": "public-government",
        "default_templates": "science-base,scientific-methodology"},
    "org-": {"knowledge_domain": "organizational-operational", "default_epistemic_grade": "E2",
        "default_entity_kind": "enterprise",
        "default_templates": "business-base,corporate-operations"},
}  # fmt: skip
CANONICAL_SCIENCE_TRUNKS: dict[str, tuple[str, ...]] = {
    "formal": ("math", "maths", "mathematics", "logic", "statistics", "cs-theory"),
    "nature": ("physics", "chemistry", "earth", "biology", "biochemistry",
        "microbiology", "botany", "genetics", "astronomy", "ecology"),
    "health": ("health-sciences", "pharmacology", "nursing", "public-health", "nutrition",
        "psychology", "veterinary"),
    "engineering": ("civil", "industrial", "mechanical", "electrical", "telecom", "aerospace",
        "chemical", "materials", "metallurgy", "bioprocess", "mechatronics", "control",
        "software", "security"),
    "social": (
        "economic", "economics", "sociology", "demographics",
        "education", "pedagogy", "jurisprudence",
    ),
    "humanities": ("philosophy", "ethics", "history", "linguistics", "arts"),
}  # fmt: skip
_GH_PUB: str = "https://github.com/mtwuser"
_SCI_AUTH: str = "https://github.com/consortium-sci"
DEFAULT_PUBLIC_KNOWLEDGE_REGISTRY: dict[str, dict[str, str]] = {
    "gov-es": {"knowledge_domain": "jurisdictional-normative",
        "stewardship_stage": "public-community", "public_url": f"{_GH_PUB}/gov-es.git",
        "canonical_authority_url": "https://github.com/administracion-gob-es/gov-es.git"},
    "geo-es": {"knowledge_domain": "territorial-empirical",
        "stewardship_stage": "public-community", "public_url": f"{_GH_PUB}/geo-es.git",
        "canonical_authority_url": "https://github.com/ign-cnig-es/geo-es.git"},
    "sci-maths": {"knowledge_domain": "scientific-epistemic", "canonical_trunk": "formal",
        "stewardship_stage": "public-community", "public_url": f"{_GH_PUB}/sci-maths.git",
        "canonical_authority_url": f"{_SCI_AUTH}/sci-maths.git"},
    "sci-physics": {"knowledge_domain": "scientific-epistemic", "canonical_trunk": "nature",
        "stewardship_stage": "public-community", "public_url": f"{_GH_PUB}/sci-physics.git",
        "canonical_authority_url": f"{_SCI_AUTH}/sci-physics.git"},
    "sci-biology": {"knowledge_domain": "scientific-epistemic", "canonical_trunk": "nature",
        "stewardship_stage": "public-community", "public_url": f"{_GH_PUB}/sci-biology.git",
        "canonical_authority_url": f"{_SCI_AUTH}/sci-biology.git"},
    "sci-engineering": {"knowledge_domain": "scientific-epistemic",
        "canonical_trunk": "engineering", "stewardship_stage": "public-community",
        "public_url": f"{_GH_PUB}/sci-engineering.git",
        "canonical_authority_url": f"{_SCI_AUTH}/sci-engineering.git"},
    "sci-economic": {"knowledge_domain": "scientific-epistemic", "canonical_trunk": "social",
        "stewardship_stage": "public-community", "public_url": f"{_GH_PUB}/sci-economic.git",
        "canonical_authority_url": f"{_SCI_AUTH}/sci-economic.git"},
}  # fmt: skip

VALID_ROSTER_ROLES: tuple[str, ...] = ("owner", "maintainer", "validator", "member")
ROLE_ENVIRONMENT_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": ("dev", "tst", "pre", "pro"), "maintainer": ("dev", "tst", "pre"),
    "validator": ("dev", "tst", "pre"), "member": ("dev", "tst"), "consumer": (),
}  # fmt: skip
VALID_TRACKER_FILES: tuple[str, ...] = (
    "WORKTASK.md", "BACKLOG.md", "WORKROAD.md", "ROADMAP.md", "WORKVALI.md",
)  # fmt: skip
WORK_ORCHESTRATION_TRACKERS: tuple[str, ...] = (
    "WORKROAD.md", "WORKTASK.md", "WORKVALI.md", "BACKLOG.md",
)  # fmt: skip
MAKEFILE_ROLE_HEADER_PREFIX: str = "# Zero-Cloud Node Makefile"
MAKEFILE_PROJECT_HEADER_PREFIX: str = "# Zero-Cloud Project Makefile"
MAKEFILE_CUSTOM_TARGETS_MARKER: str = "# --- Custom Targets ---"
MAKEFILE_COMPOSABLE_BLOCKS: dict[str, tuple[str, ...]] = {
    "base": ("status", "sync", "diff", "task", "complete", "consult", "link", "unlink",
        "apply-template", "mcp-test"),
    "hierarchy": ("horizon", "upstream-diff", "delegate", "promote", "authority", "roster",
        "decision", "env-gate"),
    "plugin_ops": ("install-plugin", "uninstall-plugin", "activate-plugin", "deactivate-plugin",
        "switch-env", "deploy-plugin", "plugin"),
    "workstation_host_ops": ("workstation-sync", "workstation-backup", "workstation-audit",
        "workstation-restore", "workstation-update-agy"),
}  # fmt: skip
PROJECT_ZCG_MK_TARGETS: tuple[str, ...] = (
    "zcg-help", "zcg-status", "zcg-sync", "zcg-diff",
    "zcg-task", "zcg-complete", "zcg-consult", "zcg-promote",
)  # fmt: skip
MAKEFILE_DOMAIN_TAXONOMY: dict[str, tuple[str, ...]] = {
    "universal_base_local": ("status", "task", "complete", "sync", "diff"),
    "business_inter_layer": ("consult", "promote", "link", "unlink", "env-gate", "authority"),
    "layer_hierarchy_governance": ("horizon", "delegate", "decision", "roster", "upstream-diff"),
    "technical_and_plugin_ops": ("apply-template", "mcp-test",
        *MAKEFILE_COMPOSABLE_BLOCKS["plugin_ops"]),
    "workstation_host_ops": MAKEFILE_COMPOSABLE_BLOCKS["workstation_host_ops"],
}  # fmt: skip
_NODE_GOV_TARGETS: tuple[str, ...] = (
    *MAKEFILE_COMPOSABLE_BLOCKS["base"], *MAKEFILE_COMPOSABLE_BLOCKS["hierarchy"],
    *MAKEFILE_COMPOSABLE_BLOCKS["plugin_ops"],
)  # fmt: skip
LAYER_ROLE_MAKEFILE_TARGETS: dict[str, tuple[str, ...]] = {
    "workstation": (*_NODE_GOV_TARGETS, *MAKEFILE_COMPOSABLE_BLOCKS["workstation_host_ops"]),
    "corporate": tuple(t for t in _NODE_GOV_TARGETS if t != "complete"),
    "domain-policy": _NODE_GOV_TARGETS, "department": _NODE_GOV_TARGETS,
    "squad": _NODE_GOV_TARGETS, "knowledge": _NODE_GOV_TARGETS,
    "project": (*(t for t in MAKEFILE_COMPOSABLE_BLOCKS["base"] if t != "mcp-test"),
        "promote", "authority", "env-gate"),
}  # fmt: skip

_ZCG_RUN, _PF = "\t@$(ZCG_BIN)", "$(CURDIR) $(PARENT_FLAG)"
_PLUGIN_SVC: str = (
    f"{_ZCG_RUN} apply-project {_PF} $(if $(PLUGIN),--template $(PLUGIN),) "
    "$(if $(ENV),--env $(ENV),) $(if $(EMAIL),--email $(EMAIL),) --service-action"
)
LAYER_MAKEFILE_RECIPES: dict[str, str] = {
    "status": f"{_ZCG_RUN} status {_PF}", "horizon": f"{_ZCG_RUN} inspect-horizon {_PF}",
    "diff": f"{_ZCG_RUN} diff-project {_PF}", "mcp-test": f"{_ZCG_RUN} list-templates $(CURDIR)",
    "unlink": f"{_ZCG_RUN} unlink $(CURDIR) --target $(TARGET)",
    "apply-template": (f"{_ZCG_RUN} apply-project $(CURDIR) "
        "--template $(if $(TEMPLATE),$(TEMPLATE),software-engineering) --include-defaults"),
    "task": f'{_ZCG_RUN} start-task $(CURDIR) --task "$(TASK)" $(if $(TICKET),--ticket $(TICKET),)',
    "complete": (f"{_ZCG_RUN} complete-task $(CURDIR) "
        "$(if $(PARENT_SYNC),--parent-dir $(PARENT_DIR),$(PARENT_FLAG)) "
        '--task "$(TASK)" $(if $(DELIVERABLE),--deliverable "$(DELIVERABLE)",) '
        '$(if $(SUMMARY),--summary "$(SUMMARY)",) $(if $(CREATE_PR),--create-pr,)'),
    "consult": (f'{_ZCG_RUN} consult-layer {_PF} --layer $(if $(LAYER),$(LAYER),self) '
        '--query "$(QUERY)" $(if $(PATH_TARGET),--path $(PATH_TARGET),) '
        "$(if $(TIER),--tier $(TIER),)"),
    "link": (f"{_ZCG_RUN} link $(CURDIR) $(if $(FROM),--from $(FROM),--target $(TARGET)) "
        "$(if $(REL),--relation $(REL),) $(if $(REF),--ref $(REF),) "
        "$(if $(URL),--url $(URL),) $(if $(PACKS),--packs $(PACKS),)"),
    "sync": (f"{_ZCG_RUN} sync-layer {_PF} $(if $(TEMPLATE),--templates $(TEMPLATE),) "
        "$(if $(STRATEGY),--strategy $(STRATEGY),)"),
    "upstream-diff": (f"{_ZCG_RUN} compare-upstream {_PF} $(if $(TEMPLATE),--template $(TEMPLATE),)"
        " $(if $(APPLY_SAFE),--apply-safe,)"),
    "authority": (f"{_ZCG_RUN} check-authority {_PF} --op $(if $(OP),$(OP),release) "
        "$(if $(EMAIL),--email $(EMAIL),)"),
    "roster": (f"{_ZCG_RUN} manage-roster $(CURDIR) $(if $(ADD),--add $(ADD),) "
        "$(if $(REMOVE),--remove $(REMOVE),) $(if $(ROLE),--role $(ROLE),)"),
    "env-gate": (f"{_ZCG_RUN} check-env-promotion {_PF} --to-env $(if $(ENV),$(ENV),tst) "
        "$(if $(FILES),--files $(FILES),) $(if $(EMAIL),--email $(EMAIL),)"),
    "decision": (f'{_ZCG_RUN} record-decision $(CURDIR) --item "$(ITEM)" '
        '--decision $(DEC) --reason "$(REASON)"'),
    "promote": (f"{_ZCG_RUN} promote-from-project $(CURDIR) --source $(SOURCE) "
        "$(if $(TARGET_REPO),--upstream-dir $(TARGET_REPO),"
        "$(if $(PARENT_DIR),--upstream-dir $(PARENT_DIR),)) "
        "$(if $(LAYER),--to-layer $(LAYER),) $(if $(TEMPLATE),--to-template $(TEMPLATE),) "
        "$(PR_FLAGS)"),
    "delegate": (f'{_ZCG_RUN} delegate-to-child $(CURDIR) --to-child $(CHILD) --task "$(TASK)" '
        "$(if $(TICKET),--ticket $(TICKET),) $(if $(PRIORITY),--priority $(PRIORITY),) "
        "$(if $(SURFACE),--surface $(SURFACE),) $(if $(SOURCE),--source $(SOURCE),) "
        "$(if $(CREATE_PR),--create-pr,)"),
    "install-plugin": f"{_PLUGIN_SVC} install", "uninstall-plugin": f"{_PLUGIN_SVC} uninstall",
    "activate-plugin": f"{_PLUGIN_SVC} activate", "deactivate-plugin": f"{_PLUGIN_SVC} deactivate",
    "switch-env": f"{_PLUGIN_SVC} switch-env", "deploy-plugin": f"{_PLUGIN_SVC} deploy",
    "plugin": f"{_PLUGIN_SVC} $(if $(ACTION),$(ACTION),healthcheck)",
    "workstation-update-agy": (f"{_ZCG_RUN} install-antigravity $(if $(MODE),$(MODE),--agents) "
        "$(if $(FORCE),--force,)"),
    "workstation-sync": (f"{_ZCG_RUN} workstation-sync $(if $(MODE),$(MODE),sync) "
        "$(if $(PROFILE),--profile $(PROFILE),) $(if $(LANG),--lang $(LANG),)"),
    "workstation-backup": f"{_ZCG_RUN} workstation-backup $(CURDIR)",
    "workstation-audit": f"{_ZCG_RUN} workstation-audit $(CURDIR) $(if $(CLEAN),--clean,)",
    "workstation-restore": f"{_ZCG_RUN} workstation-restore $(CURDIR) $(if $(MODE),$(MODE),)",
}  # fmt: skip

DEFAULT_SQUAD_ONBOARDING_SPEC: tuple[str, str, str, str] = (
    "Level 3 — Squad, Case & Operational Unit Node",
    "[Fill: Operational unit/squad mission, bounded contexts, and verification gates]",
    "[Fill: Target consumer project or service repositories for zcg apply-project]",
    "apply-project commands for our target consumer project or service repositories",
)  # fmt: skip
ROLE_ONBOARDING_SPECS: dict[str, tuple[str, str, str, str]] = {
    "workstation": ("Level 0 — Personal Root 0 Workstation Hub",
        "[Fill: Personal workstation habits, host manifests, and 1-hop personal pillar topology]",
        "[Fill: Planned 1-hop pillars (<persona>-tutor, <persona>-work, <persona>-wallet)]",
        "bootstrap commands to initialize our 1-hop personal pillars"),
    "corporate": ("Level 1 — Root 0 (Corporate & Organizational Governance Hub)",
        "[Fill: Organization mission, core business domain, and compliance/IP/SLA non-negotiables]",
        "[Fill: Planned child Departments (--role department / --role domain-policy)]",
        "bootstrap commands to initialize our planned child Departments"),
    "department": ("Level 2 — Department & Cross-Cutting Domain Node",
        "[Fill: Department mission, domain invariants, and target file surface globs]",
        "[Fill: Planned child Units, Cases, or Squads (--role squad)]",
        "bootstrap commands to initialize our child Units, Cases, or Squads"),
    "domain-policy": ("Level 2 — Cross-Cutting Domain Policy & SecOps Node",
        "[Fill: Cross-cutting policy domain (Legal/IP/Security), invariants, and surface globs]",
        "[Fill: Consumer Departments, Units, or Squads mounting this policy layer]",
        "register-subtree and bootstrap commands for consumer layers"),
    "squad": DEFAULT_SQUAD_ONBOARDING_SPEC,
    "knowledge": ("Epistemic Knowledge Atlas Node (gov-*, sci-*, geo-*, org-*)",
        "[Fill: Epistemic domain, E3..E0 credibility invariants, and citation_receipt scope]",
        "[Fill: Consumer nodes mounting this knowledge corpus]",
        "register-subtree commands for consumer nodes mounting this knowledge corpus"),
}  # fmt: skip
GIT_CMD_TIMEOUT_SECONDS, MAX_SKILL_FRONTMATTER_LINES, SKILL_MD_MAX_LINES = 5, 30, 464
STATUS_EXCERPT_MAX_LINES, CAPSULE_DIGEST_HEX_LEN, CAPSULE_HMAC_HEX_LEN = 12, 16, 24
OWNER_WRITABLE_MODE_BIT, OWNER_DIR_RWX_BITS = stat.S_IWUSR, stat.S_IRWXU
AGENTS_MD_WARN_BYTES, AGENTS_MD_MAX_BYTES = 16000, 18000
VALID_RUNTIME_PERSISTENCE_MODES: tuple[str, ...] = ("static", "dynamic")
VALID_DYNAMIC_RESOLUTION_POLICIES: tuple[str, ...] = (
    "standing", "ttl-expired", "goal-resolved", "surface-matched", "no-utility-pruned",
)  # fmt: skip
VALID_SYNC_STRATEGIES: tuple[str, ...] = ("reconcile", "accept-upstream", "merge", "keep-local")
VALID_GOVERNANCE_DECISIONS: tuple[str, ...] = ("approve", "reject", "defer", "blocked")
VALID_AGENT_TIERS: tuple[str, ...] = ("flash_lite", "flash", "inherit", "pro")
VALID_DELEGATION_DIRS: tuple[str, ...] = ("corporate", "docs", "roadmaps")
VALID_DELEGATION_SURFACES: tuple[str, ...] = (*VALID_TRACKER_FILES, "rules", *VALID_DELEGATION_DIRS)
CONSUMER_ALLOWED_OPS: tuple[str, ...] = (
    "status", "list-templates", "diff-project", "lint-arch", "lint-skills", "check-handoff",
    "apply-project", "scaffold-web-app", "check-authority", "inspect-horizon",
    "compare-upstream", "consult-layer",
)  # fmt: skip
MAINTAINER_ALLOWED_OPS: tuple[str, ...] = (
    "sync-layer", "scaffold-template", "scaffold-plugin-module", "delegate-to-child",
    "link", "unlink", "spinout-project", "install-plugin", "uninstall-plugin",
    "activate-plugin", "deactivate-plugin", "deploy-plugin",
)  # fmt: skip
VALIDATOR_ALLOWED_OPS: tuple[str, ...] = ("check-env-promotion", "record-decision")
OWNER_RESTRICTED_OPS: tuple[str, ...] = (
    "init-fork", "register-subtree", "set-authority",
    "manage-roster", "configure-git-policy", "release",
)  # fmt: skip
DEFAULT_PROTECTED_BRANCHES: tuple[str, ...] = ("main", "master", "env/pre", "env/pro")
DEFAULT_ENV_BRANCH_MAP: dict[str, str] = {
    "dev": "feature/*", "tst": "env/tst", "pre": "env/pre", "pro": "master",
}  # fmt: skip
DEFAULT_CONTEXT_BRANCH_PREFIXES: dict[str, str] = {
    "machine": "machine/", "hat": "hat/", "specialty": "specialty/",
    "opportunity": "opportunity/", "venture": "venture/", "engagement": "engagement/",
}  # fmt: skip
DEFAULT_PROCESS_BRANCH_PREFIXES: dict[str, str] = {
    "feature": "feature/", "directive": "directive/", "fix": "fix/",
    "chore": "chore/", "release": "release/",
}  # fmt: skip
DEFAULT_GOVERNANCE_PR_PREFIXES: dict[str, str] = {"promote": "promote/", "delegate": "delegate/"}
CAPSULE_REF_NAMESPACE: str = "refs/zcg/capsules"
COMMAND_CONSCIOUSNESS_TIERS: dict[str, tuple[str, ...]] = {
    "c1_tactical_fast": (
        "status", "task", "diff", "workstation-audit", "activate-plugin",
        "deactivate-plugin", "switch-env", "plugin",
    ),
    "c2_deliberate_audit": (
        "sync", "horizon", "upstream-diff", "consult", "link", "unlink", "apply-template",
        "mcp-test", "workstation-sync", "workstation-backup", "install-plugin",
        "uninstall-plugin", "deploy-plugin",
    ),
    "c3_sovereign_human": (
        "complete", "promote", "delegate", "decision", "roster", "authority",
        "env-gate", "workstation-update-agy", "workstation-restore",
    ),
}  # fmt: skip
