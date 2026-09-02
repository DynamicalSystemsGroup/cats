##### Platform Dependencies:

> **Quick install:** `make deps` installs everything below automatically on macOS & Linux (see the
> [`Makefile`](../Makefile) at the repo root). It always installs the latest release of each tool (not a pin),
> warns if an already-installed tool is older than the floor documented here, and falls back to that floor only
> if it can't detect the latest release (e.g. no network). Run `make help` for all targets — `make deps-all` also
> installs optional `helm` and Graphviz (`dot`), and `make print-versions` audits what's currently installed. The
> steps below document what each target does and remain the reference for manual installs or troubleshooting.

0. [**Docker:**](https://docs.docker.com/desktop/install/mac-install/) (`make deps-docker`)
1. [**Homebrew**](https://brew.sh/) — macOS package manager used by later `make deps-*` targets
  (`kind`, `kubectl`, `go`, `ipfs`, optional `graphviz`). Install if `brew` is not
  already on `PATH`:
  ```bash
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```
  On Apple Silicon, follow the installer note to add Homebrew to your shell `PATH` (typically
  `eval "$(/opt/homebrew/bin/brew shellenv)"` in `~/.zprofile` or `~/.bash_profile`).
2. <a id="uv"></a>[**uv**](https://docs.astral.sh/uv/) (>= 0.7.0) — manages the pinned Python interpreter, virtual environment
  (`.venv`), and locked dependencies (`uv.lock`) for CATs. Install it, then let it install the Python version
  pinned in [`.python-version`](../.python-version):
  ```bash
  cd <path-to>/cats
  pip install uv      # installs uv
  uv python install   # installs the Python version pinned in .python-version
  uv sync             # creates .venv and installs locked dependencies from uv.lock
  ```
  (`make deps-uv-sync` runs the same three steps. See [`ENV.md`](./ENV.md) for the full `uv sync` / `uv run` workflow.)
3. [**kind**](https://kind.sigs.k8s.io/docs/user/quick-start/#installing-from-release-binaries) (>= 0.20.0)
  (`make deps-kind`)
4. [**kubectl**](https://kubernetes.io/docs/tasks/tools/install-kubectl-macos/) (>= 1.27.3") (`make deps-kubectl`)
5. [**Terraform**:](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli) (pinned **1.15.7**) (`make deps-terraform`)
  Pins the official HashiCorp binary into the uv-managed project env (`.venv/bin`), not Homebrew
  or “latest”. `make deps-terraform` runs `deps-uv-sync` first, then installs if that pin is missing:
  ```bash
  cd <path-to>/cats
  make deps-terraform
  # equivalent manual steps:
  # VER=1.15.7
  # curl -fsSLO "https://releases.hashicorp.com/terraform/${VER}/terraform_${VER}_<os>_<arch>.zip"
  # unzip -o "terraform_${VER}_<os>_<arch>.zip" -d .venv/bin
  # rm "terraform_${VER}_<os>_<arch>.zip"
  .venv/bin/terraform -version   # or: uv run terraform -version
  # > When running Terraform manually from the repo root:
  # >   export TF_DATA_DIR="$PWD/data/input/structure/.terraform-data"
  # >   export INTEGRATION_INPUT_DATA_CACHE="$PWD/data/cache/integration/outputs"
  # > (Use absolute paths; docker-compose treats relative volume paths as named volumes.)
  ```
6. [**Go**](https://go.dev/dl/) (>= v3.13.1) (`make deps-go`)
7. [**IPFS Kubo**](https://docs.ipfs.tech/install/command-line/#system-requirements) (>= 0.21.0) (`make deps-ipfs`) — **optional** operator tooling (CAS-only Node). See [`IPFS.md`](./IPFS.md).
* [**helm**](https://helm.sh/docs/intro/install/) (>= 3.12.1) — optional; `terraform apply` manages Helm
  releases itself via the `hashicorp/helm` provider, which talks to the Helm SDK directly and doesn't shell
  out to a `helm` binary. Only install this CLI if you want to manually inspect releases with commands like
  `helm list` / `helm get` against the `kind-cats` cluster. (`make deps-helm`, or `make deps-all` to include it
  alongside everything else.)
* [**Graphviz**](https://graphviz.org/download/) — optional; required for PNG output from
  [Diagramming](../README.md#diagramming) (`make diagrams`, `code2flow` / `pyreverse`). Provides `dot`
  on `PATH`. (`make deps-graphviz`, or `make deps-all` to include it with helm.) Not installed by `uv`
  or core `make deps`.