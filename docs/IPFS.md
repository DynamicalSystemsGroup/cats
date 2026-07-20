### Manage the Host IPFS Daemon

CATs relies on a host [IPFS (Kubo)](https://docs.ipfs.tech/install/command-line/#system-requirements) daemon for
content-addressed storage across the [Demo](./DEMO.md) and [Test](./TEST.md) workflows. See [`DEPS.md`](./DEPS.md)
for installing Kubo itself. The Python side talks to that daemon with a thin sync Kubo HTTP RPC client
(`cats/network/clients/ipfs_client.py` → `http://127.0.0.1:5001/api/v0/*` via `requests`), not `ipfshttpclient`.

#### Automatic startup — usually nothing to do

Two places already start the host daemon automatically and idempotently, so you normally don't need to run
`ipfs daemon` yourself:

* **`cats/node.py`**, on every process start:
  ```python
  ipfs(cwd=self.CATS_HOME).daemon()
  ```
  (`cats/network/__init__.py:25`, via the `ipfs` helper in `cats/network/clients/__init__.py`)
* **The Structure's `terraform apply`** (run by `Structure.deploy()` / `redeploy()` / `reconcile()` — see
  `cats/executor/__init__.py` — whenever a CAT executes):
  ```hcl
  resource "shell_script" "host_ipfs_daemon" { ... }
  ```
  (`data/input/structure/modules/infrastructure/main.tf`)

Both probe the Kubo **HTTP API** (`POST http://127.0.0.1:5001/api/v0/id`) before starting anything — not bare
`ipfs id`, which modern Kubo can answer from the local repo with the daemon down. That way they never skip
startup when `:5001` is dead, and never start a second daemon on top of one that's already serving.

The Python helper (`cats/network/clients/__init__.py` → `ipfs.daemon()`) also heals a common stuck state:
API down with a held `~/.ipfs/repo.lock` (often a hung Kubo that still holds the flock / swarm sockets while
`:5001` is dead — `ipfs shutdown` cannot clear that because it talks to the API). Heal best-effort runs
`ipfs shutdown`, terminates lock-holder / `ipfs daemon` PIDs, removes the stale lock, then starts Kubo. If
the API is already up, it reuses that daemon and does **not** take ownership.

#### Manual start (optional)

Run this yourself only if you want the daemon's logs visible in their own terminal:
```bash
ipfs daemon
```
If a daemon is *already* running (from you, `node.py`, or Terraform) and you run this again, you'll see:
```
Error: lock /Users/<you>/.ipfs/repo.lock: someone else has the lock
```
This is expected and harmless — it just means a daemon is already up and serving.

#### Shutdown

```bash
ipfs shutdown
```

`cats/node.py` registers `atexit` / `SIGINT` / `SIGTERM` handlers that call `shutdown_owned_daemon()` — that
runs `ipfs shutdown` **only** when this process started the host daemon (`_host_daemon_owned`). A
pre-existing healthy daemon (manual `ipfs daemon`, another process, or Terraform) is left alone.

#### Checking status

```bash
curl -sf -X POST http://127.0.0.1:5001/api/v0/id
```
Succeeds (HTTP 200 + JSON peer info) if the daemon API is up; fails otherwise. This is the same check both
auto-starters use. Bare `ipfs id` is **not** sufficient — it can succeed offline without `:5001` listening.

#### Docker transport peering

Once the daemon (host or Terraform-started) is up, `data/input/structure/modules/infrastructure/main.tf`'s
`shell_script.docker_compose_ipfs_transport` resource runs `ipfs_connect_peers.sh` to peer the host daemon with the
`ipfs_migration`/`ipfs_integration` Docker Compose transport containers (and peer those containers with each other).
If the host daemon isn't up yet when that runs, peering with the host is skipped gracefully — it isn't required for
the Docker containers to peer with one another.