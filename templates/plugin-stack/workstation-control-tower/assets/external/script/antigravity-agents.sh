# shellcheck shell=bash disable=SC2034
# Antigravity Agents — AI agent runtime
NAME="Antigravity Agents"
DESCRIPTION="Google Antigravity Agents"
INSTALL_CMD="${ZCG_ENGINE_DIR:-${HOME}/zero-cloud-gravity}/scripts/install-antigravity.sh --agents"
CHECK_CMD="test -x /opt/antigravity-agents/antigravity"
