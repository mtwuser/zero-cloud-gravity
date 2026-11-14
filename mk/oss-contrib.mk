# ZeroCloudGravity — Isolated Open-Source Engine Contribution Targets
OSS_REMOTE_URL ?= git@github.com:mtwuser/zero-cloud-gravity.git
RELEASE_VERSION ?= $(shell tr -d '[:space:]' < VERSION)

.PHONY: oss-push-branch oss-promote-master oss-publish

oss-push-branch:
	@$(ZCG) $(if $(filter 1,$(DRY_RUN)),--dry-run,) oss push-branch . $(if $(filter 1,$(VERIFY)),--verify,)

oss-promote-master:
	@$(ZCG) $(if $(filter 1,$(DRY_RUN)),--dry-run,) oss promote-master .

oss-publish: $(if $(filter 0,$(VERIFY)),,verify)
	@$(ZCG) $(if $(filter 1,$(DRY_RUN)),--dry-run,) oss publish . --remote-url "$(OSS_REMOTE_URL)" --release-version "$(RELEASE_VERSION)" $(if $(CONTRIB_BRANCH),--contrib-branch "$(CONTRIB_BRANCH)",) $(if $(filter 1,$(CREATE_PR)),--create-pr,)
