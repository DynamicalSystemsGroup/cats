### Manage the Host IPFS Daemon

CATs relies on a host [IPFS (Kubo)](https://docs.ipfs.tech/install/command-line/#system-requirements) daemon for
content-addressed storage across the [Demo](./DEMO.md) and [Test](./TEST.md) workflows. See [`DEPS.md`](./DEPS.md)
for installing Kubo itself.

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

Both probe with `ipfs id` (the daemon's live API) before starting anything, so they never try to start a second
daemon on top of one that's already running — whether it was started by you, by the other auto-starter, or from a
previous session.

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

#### Checking status

```bash
ipfs id
```
Succeeds (prints your peer info) if a daemon is up and responsive; fails otherwise. This is the same check both
auto-starters use, and the quickest way to tell whether you need to do anything at all.

#### Docker transport peering

Once the daemon (host or Terraform-started) is up, `data/input/structure/modules/infrastructure/main.tf`'s
`shell_script.docker_compose_ipfs_transport` resource runs `ipfs_connect_peers.sh` to peer the host daemon with the
`ipfs_migration`/`ipfs_integration` Docker Compose transport containers (and peer those containers with each other).
If the host daemon isn't up yet when that runs, peering with the host is skipped gracefully — it isn't required for
the Docker containers to peer with one another.