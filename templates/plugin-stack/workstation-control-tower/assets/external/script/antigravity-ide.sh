# shellcheck shell=bash disable=SC2034
# Antigravity IDE — AI-powered code editor
NAME="Antigravity IDE"
DESCRIPTION="Google Antigravity IDE"
INSTALL_CMD="${ZCG_ENGINE_DIR:-${HOME}/zero-cloud-gravity}/scripts/install-antigravity.sh --ide"
CHECK_CMD="test -x /opt/antigravity-ide/antigravity-ide"
