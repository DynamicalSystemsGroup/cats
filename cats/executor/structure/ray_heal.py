"""Heal the live Kind Ray head. Order-submitted Plant IaC is frozen.

``once --order-uri`` rematerializes ``plant/`` from the Order's plant CID, so
edits to ``data/input/structure/plant/main.tf`` never Helm-upgrade an already
applied Structure. After an OOM kill of JobSupervisor the dashboard stays up
and later jobs FAIL with empty logs. This patches the live RayCluster CR
(4G head, Ray worker OOM monitor off) from cats/, then **deletes the head
pod** so KubeRay recreates it. Waiting only on :8265 is not enough — the old
3G process already answered there.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

HEAD_MEMORY = '4G'
_JOB_ID_RE = re.compile(r'Ray job (\S+) on Plant')
_HEAD_LABEL = 'ray.io/node-type=head'


def _kubectl(
    kube_context: str,
    args: list[str],
    *,
    stdin: str | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['kubectl', '--context', kube_context, *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _ray_cluster_name(kube_context: str) -> str:
    proc = _kubectl(
        kube_context,
        ['get', 'raycluster', '-o', 'jsonpath={.items[0].metadata.name}'],
    )
    name = (proc.stdout or '').strip()
    if proc.returncode != 0 or not name:
        raise RuntimeError(
            'kubectl get raycluster failed: '
            f'{(proc.stderr or proc.stdout or "").strip()}'
        )
    return name


def _cluster_doc(kube_context: str, cluster: str) -> dict:
    proc = _kubectl(kube_context, ['get', 'raycluster', cluster, '-o', 'json'])
    if proc.returncode != 0:
        raise RuntimeError(
            f'kubectl get raycluster {cluster} failed: '
            f'{(proc.stderr or proc.stdout or "").strip()}'
        )
    return json.loads(proc.stdout)


def _head_container(doc: dict) -> dict:
    containers = (
        doc.get('spec', {})
        .get('headGroupSpec', {})
        .get('template', {})
        .get('spec', {})
        .get('containers')
        or []
    )
    if not containers:
        raise RuntimeError('RayCluster headGroupSpec has no containers')
    for container in containers:
        if container.get('name') in ('ray-head', 'ray-node'):
            return container
    return containers[0]


def _upsert_env(container: dict, name: str, value: str) -> None:
    env = container.setdefault('env', [])
    for item in env:
        if item.get('name') == name:
            item['value'] = value
            return
    env.append({'name': name, 'value': value})


def _set_head_memory(doc: dict) -> dict:
    container = _head_container(doc)
    resources = container.setdefault('resources', {})
    resources.setdefault('limits', {})['memory'] = HEAD_MEMORY
    resources.setdefault('limits', {}).setdefault('cpu', '1')
    resources.setdefault('requests', {})['memory'] = HEAD_MEMORY
    resources.setdefault('requests', {}).setdefault('cpu', '1')
    _upsert_env(container, 'RAY_memory_monitor_refresh_ms', '0')
    return doc


def _memory_is_healed(value: str) -> bool:
    text = (value or '').strip().lower().replace('gi', 'g')
    if text in ('4g', '4096mi', '4000m'):
        return True
    if text.isdigit() and int(text) >= 4_000_000_000:
        return True
    return False


def _head_pod(kube_context: str) -> dict | None:
    proc = _kubectl(
        kube_context,
        ['get', 'pods', '-l', _HEAD_LABEL, '-o', 'json'],
    )
    if proc.returncode != 0:
        return None
    items = json.loads(proc.stdout or '{}').get('items') or []
    return items[0] if items else None


def _pod_memory(pod: dict | None) -> str:
    if not pod:
        return ''
    containers = pod.get('spec', {}).get('containers') or []
    if not containers:
        return ''
    return (
        (containers[0].get('resources') or {})
        .get('limits', {})
        .get('memory')
        or ''
    )


def _pod_ready(pod: dict | None) -> bool:
    if not pod:
        return False
    status = pod.get('status') or {}
    if status.get('phase') != 'Running':
        return False
    for cond in status.get('conditions') or []:
        if cond.get('type') == 'Ready' and cond.get('status') == 'True':
            return True
    return False


def _wait_dashboard(job_endpoint: str, *, timeout: float = 180) -> None:
    url = job_endpoint.rstrip('/') + '/api/version'
    deadline = time.time() + timeout
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if 200 <= resp.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
        time.sleep(2)
    raise RuntimeError(
        f'Ray dashboard at {job_endpoint} did not recover after head restart'
    ) from last_exc


def _wait_new_head(
    kube_context: str,
    *,
    old_uid: str | None,
    timeout: float = 180,
) -> dict:
    deadline = time.time() + timeout
    last: dict | None = None
    while time.time() < deadline:
        last = _head_pod(kube_context)
        uid = (last or {}).get('metadata', {}).get('uid')
        if last and uid and uid != old_uid and _pod_ready(last):
            return last
        time.sleep(2)
    phase = (last or {}).get('status', {}).get('phase')
    raise RuntimeError(
        'Ray head pod did not become Ready after restart '
        f'(phase={phase!r}, memory={_pod_memory(last)!r}). '
        'Raise Docker Desktop memory if the pod is Pending.'
    )


def heal_live_ray_head(*, kube_context: str | None, job_endpoint: str | None) -> dict:
    """Patch the live RayCluster head to 4G, roll the pod, wait for dashboard."""
    if not kube_context:
        return {'skipped': 'no kubeconfig_context'}
    if shutil.which('kubectl') is None:
        return {'skipped': 'kubectl not on PATH'}
    cluster = _ray_cluster_name(kube_context)
    pod = _head_pod(kube_context)
    if _memory_is_healed(_pod_memory(pod)) and _pod_ready(pod):
        print(
            f'Ray head already {HEAD_MEMORY} and Ready on {kube_context}; skip roll.'
        )
        return {
            'patched': False,
            'rolled': False,
            'cluster': cluster,
            'memory': HEAD_MEMORY,
        }

    print(
        f'Heal live Ray head {cluster!r} on {kube_context} '
        f'to {HEAD_MEMORY} and roll the head pod (Order Plant Helm is frozen).'
    )
    doc = _set_head_memory(_cluster_doc(kube_context, cluster))
    apply = _kubectl(
        kube_context,
        ['apply', '-f', '-'],
        stdin=json.dumps(doc),
    )
    if apply.returncode != 0:
        raise RuntimeError(
            f'kubectl apply raycluster {cluster} failed: '
            f'{(apply.stderr or apply.stdout or "").strip()}'
        )
    spec_memory = _head_container(doc)['resources']['limits']['memory']
    if not _memory_is_healed(spec_memory):
        raise RuntimeError(f'RayCluster spec memory stayed {spec_memory!r}')

    old_uid = (pod or {}).get('metadata', {}).get('uid')
    delete = _kubectl(
        kube_context,
        ['delete', 'pod', '-l', _HEAD_LABEL, '--wait=true', '--timeout=120s'],
    )
    if delete.returncode != 0:
        raise RuntimeError(
            'kubectl delete Ray head pod failed: '
            f'{(delete.stderr or delete.stdout or "").strip()}'
        )
    new_pod = _wait_new_head(kube_context, old_uid=old_uid)
    if job_endpoint:
        _wait_dashboard(job_endpoint)
    live_memory = _pod_memory(new_pod)
    if not _memory_is_healed(live_memory):
        raise RuntimeError(
            f'Ray head pod came back with memory {live_memory!r}, want {HEAD_MEMORY}'
        )
    return {
        'patched': True,
        'rolled': True,
        'cluster': cluster,
        'memory': live_memory or HEAD_MEMORY,
    }


def fetch_job_info(job_endpoint: str, job_id: str) -> dict:
    url = f'{job_endpoint.rstrip("/")}/api/jobs/{job_id}'
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode())


def enrich_ray_wait_error(exc: BaseException, *, job_endpoint: str | None) -> str:
    """Append dashboard job message when Plant wait() only had empty logs."""
    text = str(exc)
    if not job_endpoint:
        return text
    match = _JOB_ID_RE.search(text)
    if not match:
        return text
    try:
        info = fetch_job_info(job_endpoint, match.group(1))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return text
    extra = []
    for key in ('error_type', 'message', 'status'):
        value = info.get(key) if isinstance(info, dict) else None
        if value:
            extra.append(f'{key}: {value}')
    if not extra:
        return text
    return text.rstrip() + '\n' + '\n'.join(extra)
