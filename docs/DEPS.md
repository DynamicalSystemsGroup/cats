##### Platform Dependencies:

> **Quick install:** `make deps` installs everything below automatically on macOS & Linux (see the
> [`Makefile`](../Makefile) at the repo root). It always installs the latest release of each tool (not a pin),
> warns if an already-installed tool is older than the floor documented here, and falls back to that floor only
> if it can't detect the latest release (e.g. no network). Run `make help` for all targets — `make deps-all` also
> installs optional `helm` and Graphviz (`dot`), and `make print-versions` audits what's currently installed. The
> steps below document what each target does and remain the reference for manual installs or troubleshooting.

0. [**Docker:**](https://docs.docker.com/desktop/install/mac-install/) (`make deps-docker`)
1. [**uv**](https://docs.astral.sh/uv/) (>= 0.7.0) — manages the pinned Python interpreter, virtual environment
  (`.venv`), and locked dependencies (`uv.lock`) for CATs. Install it, then let it install the Python version
  pinned in [`.python-version`](../.python-version):
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  cd <path-to>/cats
  uv python install   # installs Python 3.12.5 per .python-version; no separate Python install needed
  ```
  (`make deps-uv` runs the same two steps. See [`ENV.md`](./ENV.md) for the full `uv sync` / `uv run` workflow.)
2. [**kind**](https://kind.sigs.k8s.io/docs/user/quick-start/#installing-from-release-binaries) (>= 0.20.0)
  (`make deps-kind`)
3. [**kubectl**](https://kubernetes.io/docs/tasks/tools/install-kubectl-macos/) (>= 1.27.3") (`make deps-kubectl`)
4. [**Terraform**:](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli) (>= 1.15.7) (`make deps-terraform`)
  * Use Terraform's standalone binary if `brew install` fails due to an outdated Xcode, download the official precompiled binary directly and place it on your `PATH` (e.g. the project's `.venv/bin`, created by `uv sync`) — this is exactly what `make deps-terraform` falls back to automatically:
  ```bash
  cd <path-to>/cats
  VER=1.15.7   # adjust as needed
  curl -LO "https://releases.hashicorp.com/terraform/${VER}/terraform_${VER}_darwin_arm64.zip"
  unzip "terraform_${VER}_darwin_arm64.zip"
  mv terraform .venv/bin/
  rm "terraform_${VER}_darwin_arm64.zip"
  terraform -version
  # > Note: use `darwin_amd64` instead of `darwin_arm64` on Intel Macs. After installing, restart
  #  > `python -m cats.node` so the running process picks up the new binary on `PATH`.
  #  > When running Terraform manually from the repo root:
  #  >   export TF_DATA_DIR="$PWD/data/input/structure/.terraform-data"
  #  >   export INTEGRATION_INPUT_DATA_CACHE="$PWD/data/cache/integration/outputs"
  #  > (Use absolute paths; docker-compose treats relative volume paths as named volumes.)
  ```
5. [**Go**](https://go.dev/dl/) (>= v3.13.1) (`make deps-go`)
6. [**IPFS Kubo**](https://docs.ipfs.tech/install/command-line/#system-requirements) (>= 0.21.0) (`make deps-ipfs`)
  (See [`IPFS.md`](./IPFS.md) for running/managing the host daemon.)
* [**helm**](https://helm.sh/docs/intro/install/) (>= 3.12.1) — optional; `terraform apply` manages Helm
  releases itself via the `hashicorp/helm` provider, which talks to the Helm SDK directly and doesn't shell
  out to a `helm` binary. Only install this CLI if you want to manually inspect releases with commands like
  `helm list` / `helm get` against the `kind-cats` cluster. (`make deps-helm`, or `make deps-all` to include it
  alongside everything else.)
* [**Graphviz**](https://graphviz.org/download/) — optional; required for PNG output from
  [Diagramming](../README.md#diagramming) (`make diagrams`, `code2flow` / `pyreverse`). Provides `dot`
  on `PATH`. (`make deps-graphviz`, or `make deps-all` to include it with helm.) Not installed by `uv`
  or core `make deps`.