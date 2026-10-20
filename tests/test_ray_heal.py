"""Live Ray head heal and empty-log job error enrichment."""
import json
from types import SimpleNamespace

from cats.executor.structure.ray_heal import (
    enrich_ray_wait_error,
    heal_live_ray_head,
)


def _cluster_doc(memory='3G'):
    return {
        'apiVersion': 'ray.io/v1',
        'kind': 'RayCluster',
        'metadata': {'name': 'raycluster-kuberay'},
        'spec': {
            'headGroupSpec': {
                'template': {
                    'spec': {
                        'containers': [
                            {
                                'name': 'ray-head',
                                'resources': {
                                    'limits': {'cpu': '1', 'memory': memory},
                                    'requests': {'cpu': '1', 'memory': memory},
                                },
                                'env': [],
                            }
                        ]
                    }
                }
            }
        },
    }


def _pod(uid, memory, *, ready=True, phase='Running'):
    conditions = [{'type': 'Ready', 'status': 'True' if ready else 'False'}]
    return {
        'metadata': {'uid': uid, 'name': f'head-{uid}'},
        'spec': {
            'containers': [
                {
                    'name': 'ray-head',
                    'resources': {'limits': {'memory': memory}},
                }
            ]
        },
        'status': {'phase': phase, 'conditions': conditions},
    }


def test_heal_skipped_without_kube_context():
    assert heal_live_ray_head(kube_context=None, job_endpoint=None) == {
        'skipped': 'no kubeconfig_context',
    }


def test_heal_skipped_without_kubectl(monkeypatch):
    monkeypatch.setattr(
        'cats.executor.structure.ray_heal.shutil.which',
        lambda name: None,
    )
    assert heal_live_ray_head(
        kube_context='kind-cats',
        job_endpoint=None,
    ) == {'skipped': 'kubectl not on PATH'}


def test_heal_skips_roll_when_head_already_4g(monkeypatch):
    def fake_kubectl(context, args, stdin=None):
        if args[:2] == ['get', 'raycluster'] and '-o' in args:
            return SimpleNamespace(
                returncode=0, stdout='raycluster-kuberay\n', stderr=''
            )
        if args[:2] == ['get', 'pods']:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({'items': [_pod('live', '4G')]}),
                stderr='',
            )
        raise AssertionError(args)

    monkeypatch.setattr(
        'cats.executor.structure.ray_heal.shutil.which',
        lambda name: '/usr/bin/kubectl',
    )
    monkeypatch.setattr(
        'cats.executor.structure.ray_heal._kubectl',
        fake_kubectl,
    )
    out = heal_live_ray_head(kube_context='kind-cats', job_endpoint=None)
    assert out['rolled'] is False
    assert out['memory'] == '4G'


def test_heal_applies_and_rolls_3g_head(monkeypatch):
    calls = []
    pods = [_pod('old', '3G')]

    def fake_kubectl(context, args, stdin=None):
        calls.append(args)
        if args[:2] == ['get', 'raycluster'] and args[-1].startswith('jsonpath'):
            return SimpleNamespace(
                returncode=0, stdout='raycluster-kuberay\n', stderr=''
            )
        if args[:3] == ['get', 'raycluster', 'raycluster-kuberay']:
            return SimpleNamespace(
                returncode=0, stdout=json.dumps(_cluster_doc('3G')), stderr=''
            )
        if args[:2] == ['apply', '-f']:
            assert '4G' in (stdin or '')
            return SimpleNamespace(returncode=0, stdout='configured\n', stderr='')
        if args[:2] == ['get', 'pods']:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({'items': list(pods)}),
                stderr='',
            )
        if args[:2] == ['delete', 'pod']:
            pods[:] = [_pod('new', '4G')]
            return SimpleNamespace(returncode=0, stdout='deleted\n', stderr='')
        raise AssertionError(args)

    monkeypatch.setattr(
        'cats.executor.structure.ray_heal.shutil.which',
        lambda name: '/usr/bin/kubectl',
    )
    monkeypatch.setattr(
        'cats.executor.structure.ray_heal._kubectl',
        fake_kubectl,
    )
    monkeypatch.setattr('cats.executor.structure.ray_heal.time.sleep', lambda s: None)
    out = heal_live_ray_head(kube_context='kind-cats', job_endpoint=None)
    assert out == {
        'patched': True,
        'rolled': True,
        'cluster': 'raycluster-kuberay',
        'memory': '4G',
    }
    assert any(args[:2] == ['apply', '-f'] for args in calls)
    assert any(args[:2] == ['delete', 'pod'] for args in calls)


def test_enrich_ray_wait_error_appends_dashboard_message(monkeypatch):
    monkeypatch.setattr(
        'cats.executor.structure.ray_heal.fetch_job_info',
        lambda endpoint, job_id: {
            'error_type': 'JOB_SUPERVISOR_DIED',
            'message': 'JobSupervisor actor died after OOM',
            'status': 'FAILED',
        },
    )
    text = enrich_ray_wait_error(
        RuntimeError(
            'Ray job raysubmit_uBUF9NJTbFzZba2F on Plant job_endpoint '
            'http://127.0.0.1:8265 ended in FAILED:\n'
        ),
        job_endpoint='http://127.0.0.1:8265',
    )
    assert 'JOB_SUPERVISOR_DIED' in text
    assert 'JobSupervisor actor died after OOM' in text
