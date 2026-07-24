SHELL := /bin/bash

# --- OS / architecture detection --------------------------------------------
UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)

ifeq ($(UNAME_M),x86_64)
	ARCH := amd64
else ifeq ($(UNAME_M),aarch64)
	ARCH := arm64
else ifeq ($(UNAME_M),arm64)
	ARCH := arm64
else
	ARCH := $(UNAME_M)
endif

ifeq ($(UNAME_S),Darwin)
	OS_NAME := darwin
else ifeq ($(UNAME_S),Linux)
	OS_NAME := linux
else
	$(error Unsupported OS "$(UNAME_S)" - this Makefile supports macOS and Linux)
endif

# Root doesn't need sudo (e.g. inside containers); everyone else on Linux does.
# macOS/Homebrew never needs sudo for the commands this Makefile runs.
ifeq ($(shell id -u),0)
	SUDO :=
else ifeq ($(OS_NAME),linux)
	SUDO := sudo
else
	SUDO :=
endif

# Native package manager, used where distro packages are reliable (Docker, Go).
# Tools without consistent cross-distro packaging (kind, kubectl, IPFS Kubo,
# helm) install from upstream release binaries/scripts instead, since those
# work identically across apt/dnf/pacman/apk distros without us having to
# special-case each one.
ifeq ($(OS_NAME),darwin)
	PKG_MANAGER := brew
else ifneq (,$(shell command -v apt-get 2>/dev/null))
	PKG_MANAGER := apt-get
else ifneq (,$(shell command -v dnf 2>/dev/null))
	PKG_MANAGER := dnf
else ifneq (,$(shell command -v yum 2>/dev/null))
	PKG_MANAGER := yum
else ifneq (,$(shell command -v pacman 2>/dev/null))
	PKG_MANAGER := pacman
else ifneq (,$(shell command -v apk 2>/dev/null))
	PKG_MANAGER := apk
else
	PKG_MANAGER :=
endif

# Minimum versions, kept in sync with docs/DEPS.md's ">=" floors. These are
# NOT pins: every install path below always fetches the latest release from
# upstream (Homebrew already does this; the Linux binary-download paths query
# each project's own "latest" endpoint at install time). These constants are
# used only (a) as a fallback if a live "latest" lookup fails, e.g. no network
# or a rate limit, and (b) to warn if an already-installed tool is older than
# the documented floor.
KIND_MIN_VERSION := 0.20.0
KUBECTL_MIN_VERSION := 1.27.3
TERRAFORM_MIN_VERSION := 1.15.7
IPFS_MIN_VERSION := 0.21.0
HELM_MIN_VERSION := 3.12.1
# NOTE: docs/DEPS.md lists Go as ">= v3.13.1", which isn't a real Go release
# (Go versions look like 1.21.x, 1.22.x...). Used only as a last-resort
# fallback below; the live lookup against go.dev always wins when reachable.
GO_MIN_VERSION := 1.22.5

# version_ge(actual, floor) - true if $1 >= $2, using `sort -V` (supported by
# both BSD/macOS and GNU sort on any OS/version this Makefile targets).
define version_ge
[ "$$(printf '%s\n%s\n' "$(1)" "$(2)" | sort -V | tail -n1)" = "$(1)" ]
endef

.PHONY: help deps deps-all \
	deps-docker deps-uv deps-kind deps-kubectl deps-terraform deps-go deps-ipfs deps-helm \
	deps-graphviz \
	check-pkg-manager print-versions \
	node-start node-stop node-status node-up content-store-ensure \
	execute-order diagrams

CONTENT_STORE_UTILS := data/input/structure/infrastructure/content_store_utils.py

help:
	@echo "CATs dependency installer for macOS & Linux (see docs/DEPS.md for details)"
	@echo "Detected: $(UNAME_S)/$(UNAME_M) -> os=$(OS_NAME) arch=$(ARCH) pkg_manager=$(PKG_MANAGER)"
	@echo ""
	@echo "  make deps            Install all required dependencies (Docker check, uv, kind,"
	@echo "                       kubectl, Terraform, Go, IPFS Kubo)"
	@echo "  make deps-all        Same as 'deps', plus optional helm + Graphviz"
	@echo "  make deps-docker     Verify/install Docker"
	@echo "  make deps-uv         Install uv + the pinned Python interpreter"
	@echo "  make deps-kind       Install latest kind (>= $(KIND_MIN_VERSION))"
	@echo "  make deps-kubectl    Install latest kubectl (>= $(KUBECTL_MIN_VERSION))"
	@echo "  make deps-terraform  Install latest Terraform (>= $(TERRAFORM_MIN_VERSION));"
	@echo "                       package manager first, falling back to the standalone binary"
	@echo "  make deps-go         Install latest Go (>= $(GO_MIN_VERSION))"
	@echo "  make deps-ipfs       Install latest IPFS Kubo (>= $(IPFS_MIN_VERSION))"
	@echo "  make deps-helm       Install the optional helm CLI (>= $(HELM_MIN_VERSION));"
	@echo "                       manual debugging only, not required by 'terraform apply'"
	@echo "  make deps-graphviz   Install optional Graphviz (\`dot\`) for make diagrams /"
	@echo "                       code2flow / pyreverse PNG output"
	@echo "  make print-versions  Print installed versions of all dependencies"
	@echo ""
	@echo "Node lifecycle (AQ-safe: start asserts ContentStore; ensure heals; stop = Flask only):"
	@echo "  make node-up               Convenience: content-store-ensure then node-start"
	@echo "  make content-store-ensure  InfraStructure ContentStore.ensure CLI (heal/start Kubo)"
	@echo "  make node-start            Assert bootstrap ContentStore ready, then bind Flask"
	@echo "  make node-stop             Stop Flask Node only (never host Kubo)"
	@echo "  make node-status           Flask listen + ContentStore ready"
	@echo "  make execute-order ORDER_CID=<cid>  In-process Order execute (no Flask)"
	@echo ""
	@echo "Diagramming (requires Graphviz \`dot\` on PATH; see docs/DEPS.md):"
	@echo "  make diagrams              code2flow + pyreverse PNGs under images/"

deps: deps-docker deps-uv deps-kind deps-kubectl deps-terraform deps-go deps-ipfs
	@echo ""
	@echo "Core dependencies installed. Optional extras:"
	@echo "  make deps-helm       helm CLI (manual cluster debugging)"
	@echo "  make deps-graphviz   Graphviz \`dot\` (make diagrams / PNG output)"

deps-all: deps deps-helm deps-graphviz

check-pkg-manager:
	@if [ -z "$(PKG_MANAGER)" ]; then \
		echo "No supported package manager found (looked for brew/apt-get/dnf/yum/pacman/apk)."; \
		exit 1; \
	fi

# 0. Docker (docs/DEPS.md item 0)
deps-docker:
	@if command -v docker >/dev/null; then \
		echo "docker already installed: $$(docker --version)"; \
	elif [ "$(OS_NAME)" = "darwin" ]; then \
		echo "Docker not found. Install Docker Desktop:"; \
		echo "  https://docs.docker.com/desktop/install/mac-install/"; \
		exit 1; \
	else \
		echo "Docker not found; installing via Docker's official convenience script..."; \
		curl -fsSL https://get.docker.com | $(SUDO) sh; \
		$(SUDO) usermod -aG docker "$$(whoami)" || true; \
		echo "Added $$(whoami) to the docker group - log out/in (or run 'newgrp docker') for it to take effect."; \
	fi

# 1. uv (docs/DEPS.md item 1) - upstream installer already detects OS/arch itself
# and always installs the latest uv release.
deps-uv:
	@if command -v uv >/dev/null; then \
		echo "uv already installed: $$(uv --version)"; \
	else \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	uv python install   # installs the Python version pinned in .python-version

# 2. kind (docs/DEPS.md item 2) - not reliably packaged across Linux distros,
# so Linux always fetches the latest GitHub release (falling back to the
# documented floor only if that lookup fails); macOS uses Homebrew, which
# likewise always installs latest.
deps-kind:
	@if command -v kind >/dev/null; then \
		CURRENT=$$(kind version | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' | head -1); \
		if $(call version_ge,$$CURRENT,$(KIND_MIN_VERSION)); then \
			echo "kind already installed: v$$CURRENT (>= $(KIND_MIN_VERSION) required)"; \
		else \
			echo "WARNING: installed kind v$$CURRENT is older than the required >= $(KIND_MIN_VERSION); consider upgrading."; \
		fi; \
	elif [ "$(OS_NAME)" = "darwin" ]; then \
		command -v brew >/dev/null || { echo "Homebrew is required: https://brew.sh"; exit 1; }; \
		brew install kind; \
	else \
		LATEST=$$(curl -fsSL https://api.github.com/repos/kubernetes-sigs/kind/releases/latest 2>/dev/null | grep '"tag_name"' | head -1 | cut -d'"' -f4 | sed 's/^v//'); \
		if [ -z "$$LATEST" ]; then LATEST=$(KIND_MIN_VERSION); echo "Could not detect the latest kind release; using floor v$$LATEST"; fi; \
		echo "Installing kind v$$LATEST for linux/$(ARCH)..."; \
		curl -Lo /tmp/kind "https://kind.sigs.k8s.io/dl/v$$LATEST/kind-linux-$(ARCH)"; \
		chmod +x /tmp/kind; \
		$(SUDO) mv /tmp/kind /usr/local/bin/kind; \
	fi

# 3. kubectl (docs/DEPS.md item 3) - same rationale as kind. Kubernetes
# publishes a `stable.txt` endpoint specifically for "give me the latest
# release", which the Linux path uses (mirrors docs/ubuntu2004.md's existing
# curl-based install, just no longer hardcoded to `stable.txt`'s old value).
deps-kubectl:
	@if command -v kubectl >/dev/null; then \
		CURRENT=$$(kubectl version --client 2>/dev/null | grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+' | head -1 | sed 's/^v//'); \
		if $(call version_ge,$$CURRENT,$(KUBECTL_MIN_VERSION)); then \
			echo "kubectl already installed: v$$CURRENT (>= $(KUBECTL_MIN_VERSION) required)"; \
		else \
			echo "WARNING: installed kubectl v$$CURRENT is older than the required >= $(KUBECTL_MIN_VERSION); consider upgrading."; \
		fi; \
	elif [ "$(OS_NAME)" = "darwin" ]; then \
		command -v brew >/dev/null || { echo "Homebrew is required: https://brew.sh"; exit 1; }; \
		brew install kubectl; \
	else \
		LATEST=$$(curl -fsSL https://dl.k8s.io/release/stable.txt 2>/dev/null); \
		if [ -z "$$LATEST" ]; then LATEST=v$(KUBECTL_MIN_VERSION); echo "Could not detect the latest kubectl release; using floor $$LATEST"; fi; \
		echo "Installing kubectl $$LATEST for linux/$(ARCH)..."; \
		curl -LO "https://dl.k8s.io/release/$$LATEST/bin/linux/$(ARCH)/kubectl"; \
		chmod +x kubectl; \
		$(SUDO) install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl; \
		rm -f kubectl; \
	fi

# 4. Terraform (docs/DEPS.md item 4) - try the package manager first, then
# fall back to the standalone binary, resolving "latest" via HashiCorp's
# checkpoint API (the same mechanism `terraform` itself uses for its own
# upgrade-available notices) rather than a hardcoded version.
deps-terraform:
	@if command -v terraform >/dev/null; then \
		CURRENT=$$(terraform -version | head -n1 | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+'); \
		if $(call version_ge,$$CURRENT,$(TERRAFORM_MIN_VERSION)); then \
			echo "terraform already installed: v$$CURRENT (>= $(TERRAFORM_MIN_VERSION) required)"; \
		else \
			echo "WARNING: installed terraform v$$CURRENT is older than the required >= $(TERRAFORM_MIN_VERSION); consider upgrading."; \
		fi; \
	elif [ "$(OS_NAME)" = "darwin" ] && command -v brew >/dev/null && brew install terraform; then \
		: ; \
	else \
		LATEST=$$(curl -fsSL https://checkpoint-api.hashicorp.com/v1/check/terraform 2>/dev/null | grep -o '"current_version":"[^"]*"' | cut -d'"' -f4); \
		if [ -z "$$LATEST" ]; then LATEST=$(TERRAFORM_MIN_VERSION); echo "Could not detect the latest Terraform release; using floor v$$LATEST"; fi; \
		echo "Installing Terraform v$$LATEST standalone binary for $(OS_NAME)/$(ARCH)..."; \
		curl -LO "https://releases.hashicorp.com/terraform/$$LATEST/terraform_$${LATEST}_$(OS_NAME)_$(ARCH).zip"; \
		unzip -o "terraform_$${LATEST}_$(OS_NAME)_$(ARCH).zip"; \
		mkdir -p .venv/bin; \
		mv terraform .venv/bin/; \
		rm "terraform_$${LATEST}_$(OS_NAME)_$(ARCH).zip"; \
		.venv/bin/terraform -version; \
	fi

# 5. Go (docs/DEPS.md item 5) - package manager on both OSes tends to lag
# upstream; the Linux fallback resolves "latest" via go.dev's own version
# endpoint (docs/ubuntu2004.md's existing tarball-into-/usr/local approach,
# generalized off of a hardcoded version).
deps-go:
	@if command -v go >/dev/null; then \
		CURRENT=$$(go version | grep -o 'go[0-9]\+\.[0-9]\+\.[0-9]\+' | sed 's/^go//'); \
		if $(call version_ge,$$CURRENT,$(GO_MIN_VERSION)); then \
			echo "go already installed: v$$CURRENT (>= $(GO_MIN_VERSION) required)"; \
		else \
			echo "WARNING: installed go v$$CURRENT is older than the required >= $(GO_MIN_VERSION); consider upgrading."; \
		fi; \
	elif [ "$(OS_NAME)" = "darwin" ]; then \
		command -v brew >/dev/null || { echo "Homebrew is required: https://brew.sh"; exit 1; }; \
		brew install go; \
	else \
		LATEST=$$(curl -fsSL 'https://go.dev/VERSION?m=text' 2>/dev/null | head -n1 | sed 's/^go//'); \
		if [ -z "$$LATEST" ]; then LATEST=$(GO_MIN_VERSION); echo "Could not detect the latest Go release; using floor v$$LATEST"; fi; \
		echo "Installing Go $$LATEST for linux/$(ARCH)..."; \
		curl -LO "https://go.dev/dl/go$${LATEST}.linux-$(ARCH).tar.gz"; \
		$(SUDO) rm -rf /usr/local/go; \
		$(SUDO) tar -C /usr/local -xzf "go$${LATEST}.linux-$(ARCH).tar.gz"; \
		rm "go$${LATEST}.linux-$(ARCH).tar.gz"; \
		echo "Add Go to PATH: echo 'export PATH=\$$PATH:/usr/local/go/bin' >> ~/.profile && source ~/.profile"; \
	fi

# 6. IPFS Kubo (docs/DEPS.md item 6) - not reliably packaged on Linux, so the
# Linux path resolves "latest" via GitHub's releases API and installs via the
# official Kubo tarball + install.sh; Homebrew on macOS.
deps-ipfs:
	@if command -v ipfs >/dev/null; then \
		CURRENT=$$(ipfs version | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' | head -1); \
		if $(call version_ge,$$CURRENT,$(IPFS_MIN_VERSION)); then \
			echo "ipfs already installed: v$$CURRENT (>= $(IPFS_MIN_VERSION) required)"; \
		else \
			echo "WARNING: installed ipfs v$$CURRENT is older than the required >= $(IPFS_MIN_VERSION); consider upgrading."; \
		fi; \
	elif [ "$(OS_NAME)" = "darwin" ]; then \
		command -v brew >/dev/null || { echo "Homebrew is required: https://brew.sh"; exit 1; }; \
		brew install ipfs; \
	else \
		LATEST=$$(curl -fsSL https://api.github.com/repos/ipfs/kubo/releases/latest 2>/dev/null | grep '"tag_name"' | head -1 | cut -d'"' -f4 | sed 's/^v//'); \
		if [ -z "$$LATEST" ]; then LATEST=$(IPFS_MIN_VERSION); echo "Could not detect the latest Kubo release; using floor v$$LATEST"; fi; \
		echo "Installing IPFS Kubo v$$LATEST for linux/$(ARCH)..."; \
		curl -LO "https://dist.ipfs.tech/kubo/v$${LATEST}/kubo_v$${LATEST}_linux-$(ARCH).tar.gz"; \
		tar -xzf "kubo_v$${LATEST}_linux-$(ARCH).tar.gz"; \
		$(SUDO) bash kubo/install.sh; \
		rm -rf kubo "kubo_v$${LATEST}_linux-$(ARCH).tar.gz"; \
	fi

# helm (docs/DEPS.md, optional) - not required by `terraform apply`; only
# needed for manually inspecting releases with `helm list` / `helm get`.
# Helm's own install script already detects OS/arch and installs latest, so
# it's used on both platforms instead of branching on Homebrew vs. a distro
# package.
deps-helm:
	@if command -v helm >/dev/null; then \
		CURRENT=$$(helm version --short 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' | head -1); \
		if $(call version_ge,$$CURRENT,$(HELM_MIN_VERSION)); then \
			echo "helm already installed: v$$CURRENT (>= $(HELM_MIN_VERSION) suggested)"; \
		else \
			echo "NOTE: installed helm v$$CURRENT is older than the suggested >= $(HELM_MIN_VERSION) (optional dependency)."; \
		fi; \
	else \
		curl -fsSL -o /tmp/get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3; \
		chmod +x /tmp/get_helm.sh; \
		$(SUDO) /tmp/get_helm.sh; \
		rm -f /tmp/get_helm.sh; \
	fi

# Graphviz (docs/DEPS.md, optional) - provides \`dot\` for code2flow / pyreverse
# PNG output (`make diagrams`). System package only; not installed by uv.
deps-graphviz: check-pkg-manager
	@if command -v dot >/dev/null; then \
		echo "graphviz already installed: $$(dot -V 2>&1)"; \
	elif [ "$(PKG_MANAGER)" = "brew" ]; then \
		brew install graphviz; \
	elif [ "$(PKG_MANAGER)" = "apt-get" ]; then \
		$(SUDO) apt-get update && $(SUDO) apt-get install -y graphviz; \
	elif [ "$(PKG_MANAGER)" = "dnf" ]; then \
		$(SUDO) dnf install -y graphviz; \
	elif [ "$(PKG_MANAGER)" = "yum" ]; then \
		$(SUDO) yum install -y graphviz; \
	elif [ "$(PKG_MANAGER)" = "pacman" ]; then \
		$(SUDO) pacman -S --noconfirm graphviz; \
	elif [ "$(PKG_MANAGER)" = "apk" ]; then \
		$(SUDO) apk add graphviz; \
	else \
		echo "Unsupported package manager for Graphviz: $(PKG_MANAGER)"; \
		echo "Install manually: https://graphviz.org/download/"; \
		exit 1; \
	fi

print-versions:
	@command -v docker    >/dev/null && printf "%-10s %s\n" docker    "$$(docker --version)"           || printf "%-10s not installed\n" docker
	@command -v uv        >/dev/null && printf "%-10s %s\n" uv        "$$(uv --version)"                || printf "%-10s not installed\n" uv
	@command -v kind      >/dev/null && printf "%-10s %s\n" kind      "$$(kind version)"                || printf "%-10s not installed\n" kind
	@command -v kubectl   >/dev/null && printf "%-10s %s\n" kubectl   "$$(kubectl version --client)"    || printf "%-10s not installed\n" kubectl
	@command -v terraform >/dev/null && printf "%-10s %s\n" terraform "$$(terraform -version | head -n1)" || printf "%-10s not installed\n" terraform
	@command -v go        >/dev/null && printf "%-10s %s\n" go        "$$(go version)"                  || printf "%-10s not installed\n" go
	@command -v ipfs      >/dev/null && printf "%-10s %s\n" ipfs      "$$(ipfs version)"                || printf "%-10s not installed\n" ipfs
	@command -v helm      >/dev/null && printf "%-10s %s\n" helm      "$$(helm version --short)"        || printf "%-10s not installed (optional)\n" helm
	@command -v dot       >/dev/null && printf "%-10s %s\n" graphviz  "$$(dot -V 2>&1)"                 || printf "%-10s not installed (optional)\n" graphviz

node-up: content-store-ensure node-start

node-start:
	uv run python cats/node.py start

node-stop:
	uv run python cats/node.py stop

node-status:
	uv run python cats/node.py status

content-store-ensure:
	uv run python $(CONTENT_STORE_UTILS) ensure

# In-process Service.execute (same path as POST /cat/node/init, no Flask).
# Example order_cid: QmNU5EAmWNDc7U3bjZ8X2rzjD3iN83KXcarsvnyk8AXA9o
# Usage: make execute-order ORDER_CID=<cid>
execute-order:
	@test -n "$(ORDER_CID)" || { echo "ORDER_CID is required, e.g. make execute-order ORDER_CID=<cid>"; exit 1; }
	uv run python -m cats.execute_order $(ORDER_CID)

diagrams:
	uv run python utils/code2flow/diagram_c2f.py
	uv run pyreverse -o png -p CATs -d images/pyreverse cats
