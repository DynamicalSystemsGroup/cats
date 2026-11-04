"""One-shot Executor entrypoint: fail closed, Factory then execute, no Flask bind."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cats.executor import once
from cats.executor.executor import open_structure_ports
from cats.node.app import _MISSING_FUNCTION_STRUCTURE, run_order

REPO_ROOT = Path(__file__).resolve().parents[1]


def _order(*, function=True, structure=True):
    order = {
        'invoice_uri': 'http://127.0.0.1:5000/ldp/invoices/inv1',
    }
    if function:
        order['function_uri'] = 'http://127.0.0.1:5000/ldp/cas/fn1'
    if structure:
        order['structure_uri'] = 'http://127.0.0.1:5000/ldp/cas/st1'
    return order


def _invoice():
    return {'data_uri': 'http://127.0.0.1:5000/ldp/cas/data1'}


def _runtime(calls, *, order=None, invoice=None):
    blobs = {
        'order1': json.dumps(order if order is not None else _order()),
        'http://127.0.0.1:5000/ldp/invoices/inv1': json.dumps(
            invoice if invoice is not None else _invoice()
        ),
    }

    def cat(cid):
        if cid in blobs:
            return blobs[cid]
        raise KeyError(cid)

    runtime = SimpleNamespace()
    runtime.contentMesh = SimpleNamespace(cat=cat)

    def initFactory(order_request, init_data_id):
        calls.append(('initFactory', init_data_id))
        return 'factory', order_request

    def execute(factory, order_request):
        calls.append(('execute', factory))
        return {'content_id': 'bom1', 'invoice_uri': order_request['invoice']['data_uri']}

    runtime.initFactory = initFactory
    runtime.execute = execute
    return runtime


def test_run_order_missing_function_raises():
    calls = []
    runtime = _runtime(calls, order=_order(function=False))
    with pytest.raises(RuntimeError, match='function refs'):
        run_order({'order_id': 'order1'}, runtime=runtime, cats_home=None)
    assert calls == []


def test_run_order_missing_structure_raises():
    calls = []
    runtime = _runtime(calls, order=_order(structure=False))
    with pytest.raises(RuntimeError, match='structure / function refs'):
        run_order({'order_id': 'order1'}, runtime=runtime, cats_home=None)
    assert calls == []


def test_run_order_calls_initFactory_then_execute():
    calls = []
    runtime = _runtime(calls)
    result = run_order({'order_id': 'order1'}, runtime=runtime, cats_home=None)
    assert [step for step, _ in calls] == ['initFactory', 'execute']
    assert calls[0][1] == 'data1'
    assert calls[1][1] == 'factory'
    assert result['content_id'] == 'bom1'


def _handoff_file(tmp_path):
    path = tmp_path / 'handoff.json'
    path.write_text(json.dumps({
        'plant_ray_dashboard_address': 'http://127.0.0.1:8265',
    }))
    return path


def test_once_main_does_not_bind_flask(monkeypatch, capsys, tmp_path):
    run_called = []
    seen = {}
    monkeypatch.setattr(
        'cats.node.app.catNode.run',
        lambda **k: run_called.append(True),
    )

    def _run(body, **kwargs):
        seen['kwargs'] = kwargs
        return {'content_id': 'bom1', 'locators': body}

    monkeypatch.setattr('cats.node.app.run_order', _run)
    monkeypatch.setattr(
        'cats.executor.result.write_job_result',
        lambda bom_response, **k: None,
    )
    monkeypatch.delenv('CATS_MODULE_DIGEST', raising=False)
    locator = 'ni:///sha-256;' + ('ab' * 32)
    handoff = _handoff_file(tmp_path)
    assert once.main([
        '--order-uri', locator,
        '--structure-handoff', str(handoff),
    ]) == 0
    assert run_called == []
    assert seen['kwargs']['apply_structure'] is False
    assert 'module_digest' not in seen['kwargs']
    assert 'run_emitter' not in seen['kwargs']
    assert seen['kwargs']['structure_handoff']['plant_ray_dashboard_address'] == (
        'http://127.0.0.1:8265'
    )
    lines = capsys.readouterr().out.splitlines()
    out = json.loads(lines[0])
    assert out['content_id'] == 'bom1'
    assert out['locators']['order_uri'] == locator


def test_once_main_writes_job_result(monkeypatch, capsys, tmp_path):
    """Successful once writes CAT_RESULT_DIR then prints the BOM."""
    seen = []

    monkeypatch.setattr(
        'cats.node.app.run_order',
        lambda body, **k: {'content_id': 'bom1', 'bom': {'invoice_uri': 'x'}},
    )

    def _write(bom_response, *, cats_home, result_dir=None):
        seen.append(bom_response['content_id'])
        return cats_home

    monkeypatch.setattr('cats.executor.result.write_job_result', _write)
    locator = 'ni:///sha-256;' + ('cd' * 32)
    assert once.main([
        '--order-uri', locator,
        '--structure-handoff', str(_handoff_file(tmp_path)),
    ]) == 0
    assert seen == ['bom1']
    lines = capsys.readouterr().out.splitlines()
    assert json.loads(lines[0])['content_id'] == 'bom1'


def test_init_route_does_not_write_job_result():
    """Flask peer indexes the Node; it does not write CAT_RESULT_DIR."""
    import inspect

    from cats.node.app import execute_init_cat

    source = inspect.getsource(execute_init_cat)
    assert 'write_job_result' not in source
    assert 'CAT_RESULT_DIR' not in source


def test_once_main_missing_locator_exits_nonzero(capsys):
    assert once.main([]) == 1
    err = json.loads(capsys.readouterr().err)
    assert 'order_uri' in err['error']


def test_once_main_missing_handoff_does_not_run_order(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(
        'cats.node.app.run_order',
        lambda *args, **kwargs: called.append(True),
    )
    locator = 'ni:///sha-256;' + ('ef' * 32)
    assert once.main(['--order-uri', locator]) == 1
    assert called == []
    err = json.loads(capsys.readouterr().err)
    assert 'structure handoff' in err['error']


def test_run_order_peer_leaves_apply_structure_unset():
    seen = {}
    calls = []

    def execute(factory, order_request):
        seen['request'] = order_request
        return {'content_id': 'bom1'}

    runtime = _runtime(calls)
    runtime.execute = execute
    run_order(
        {
            'order_id': 'order1',
            'apply_structure': False,
            'structure_handoff': {'plant_ray_dashboard_address': 'http://x'},
        },
        runtime=runtime,
        cats_home=None,
    )
    assert 'apply_structure' not in seen['request']
    assert 'structure_handoff' not in seen['request']


def test_run_order_once_keyword_sets_apply_structure_false():
    seen = {}
    calls = []

    def execute(factory, order_request):
        seen['apply'] = order_request['apply_structure']
        seen['handoff'] = order_request['structure_handoff']
        return {'content_id': 'bom1'}

    runtime = _runtime(calls)
    runtime.execute = execute
    run_order(
        {'order_id': 'order1'},
        runtime=runtime,
        cats_home=None,
        apply_structure=False,
        structure_handoff={'plant_ray_dashboard_address': 'http://x'},
    )
    assert seen['apply'] is False
    assert seen['handoff']['plant_ray_dashboard_address'] == 'http://x'


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _structure(calls):
    plant_utils = _load_module(
        REPO_ROOT / 'data/input/structure/plant/plant_utils.py',
        'test_once_plant_utils',
    )
    obj_utils = _load_module(
        REPO_ROOT / 'data/input/structure/infrastructure/obj_store_utils.py',
        'test_once_obj_store_utils',
    )

    def reconcile():
        calls.append('reconcile')
        return {'rebuilt': True}

    def context():
        calls.append('context')
        return SimpleNamespace(kubeconfig_context=None, job_endpoint=None)

    def obj_store_context():
        calls.append('obj_store')
        return 'from-terraform'

    def plant_port():
        calls.append('plant_port')
        return 'from-terraform-port'

    def transport_context():
        calls.append('transport')
        return 'transport'

    return SimpleNamespace(
        reconcile=reconcile,
        plant=SimpleNamespace(
            context=context,
            plant_port=plant_port,
            _load_plant_utils=lambda: plant_utils,
        ),
        infraStructure=SimpleNamespace(
            obj_store_context=obj_store_context,
            transport_context=transport_context,
            _load_obj_store_module=lambda: obj_utils,
        ),
    )


_HANDOFF = {
    'plant_kind_cluster_name': 'cats',
    'plant_kubeconfig_context': 'kind-cats',
    'plant_ray_release_name': 'raycluster',
    'plant_ray_dashboard_address': 'http://127.0.0.1:8265',
    'infrastructure_minio_scratch_endpoint_host': 'http://127.0.0.1:9000',
    'infrastructure_minio_scratch_endpoint_pod': 'http://172.19.0.1:9000',
    'infrastructure_minio_scratch_bucket': 'cats-scratch',
    'infrastructure_minio_scratch_access_key': 'ak',
    'infrastructure_minio_scratch_secret_key': 'sk',
    'infrastructure_minio_durable_endpoint_host': 'http://127.0.0.1:9100',
    'infrastructure_minio_durable_endpoint_pod': 'http://172.19.0.1:9100',
    'infrastructure_minio_durable_bucket': 'cats-durable',
    'infrastructure_minio_durable_access_key': 'dak',
    'infrastructure_minio_durable_secret_key': 'dsk',
}


def test_open_structure_ports_apply_reconciles():
    calls = []
    _object_store, plant, transport, snapshot = open_structure_ports(
        _structure(calls),
        {},
    )
    assert calls == ['reconcile', 'context', 'obj_store', 'plant_port', 'transport']
    assert plant == 'from-terraform-port'
    assert transport == 'transport'
    assert snapshot == {'rebuilt': True}


def test_open_structure_ports_handoff_skips_reconcile():
    calls = []
    object_store, plant, transport, snapshot = open_structure_ports(
        _structure(calls),
        {'apply_structure': False, 'structure_handoff': _HANDOFF},
    )
    assert calls == ['transport']
    assert object_store.scratch_bucket == 'cats-scratch'
    assert plant.job_endpoint == 'http://127.0.0.1:8265'
    assert transport == 'transport'
    assert snapshot['rebuilt'] is False
    assert snapshot['applied_structure_id'] is None
    assert snapshot['ray_dashboard_address'] == 'http://127.0.0.1:8265'


def test_open_structure_ports_incomplete_handoff_skips_reconcile():
    calls = []
    with pytest.raises(RuntimeError, match='terraform outputs missing'):
        open_structure_ports(
            _structure(calls),
            {
                'apply_structure': False,
                'structure_handoff': {
                    'plant_ray_dashboard_address': 'http://127.0.0.1:8265',
                },
            },
        )
    assert calls == []


def test_run_order_peer_ignores_body_module_digest():
    calls = []
    runtime = _runtime(calls)
    run_order(
        {
            'order_id': 'order1',
            'module_digest': 'sha256:' + ('ab' * 32),
        },
        runtime=runtime,
        cats_home=None,
    )
    assert [step for step, _ in calls] == ['initFactory', 'execute']


def _order_for_digest(hex_digest):
    order = _order()
    order['structure_uri'] = f'http://127.0.0.1:5000/ldp/cas/{hex_digest}'
    return order


def _once_through_run_order(monkeypatch, order, calls):
    runtime = _runtime(calls, order=order)

    def _run(body, **kwargs):
        request = dict(body)
        request['order_id'] = 'order1'
        request['order'] = order
        return run_order(
            request, runtime=runtime, cats_home=None, **kwargs
        )

    monkeypatch.setattr('cats.node.app.run_order', _run)
    monkeypatch.setattr(
        'cats.executor.result.write_job_result',
        lambda bom_response, **k: None,
    )


def test_once_matching_module_digest_reaches_factory(monkeypatch, capsys, tmp_path):
    calls = []
    hex_digest = 'ab' * 32
    _once_through_run_order(
        monkeypatch, _order_for_digest(hex_digest), calls
    )
    assert once.main([
        '--order-uri', 'ni:///sha-256;' + ('11' * 32),
        '--structure-handoff', str(_handoff_file(tmp_path)),
        '--module-digest', 'sha256:' + hex_digest,
    ]) == 0
    assert [step for step, _ in calls] == ['initFactory', 'execute']
    lines = capsys.readouterr().out.splitlines()
    assert json.loads(lines[0])['content_id'] == 'bom1'


def test_once_different_module_digest_exits_before_factory(
    monkeypatch, capsys, tmp_path
):
    calls = []
    _once_through_run_order(
        monkeypatch, _order_for_digest('ab' * 32), calls
    )
    assert once.main([
        '--order-uri', 'ni:///sha-256;' + ('22' * 32),
        '--structure-handoff', str(_handoff_file(tmp_path)),
        '--module-digest', 'sha256:' + ('cd' * 32),
    ]) == 1
    assert calls == []
    err = json.loads(capsys.readouterr().err)
    assert 'module digest' in err['error']


def test_once_malformed_module_digest_exits_before_factory(
    monkeypatch, capsys, tmp_path
):
    calls = []
    _once_through_run_order(
        monkeypatch, _order_for_digest('ab' * 32), calls
    )
    assert once.main([
        '--order-uri', 'ni:///sha-256;' + ('33' * 32),
        '--structure-handoff', str(_handoff_file(tmp_path)),
        '--module-digest', 'sha256:abcd',
    ]) == 1
    assert calls == []
    err = json.loads(capsys.readouterr().err)
    assert 'module digest' in err['error']


def test_module_digest_matches_same_pairing_bytes_only(tmp_path):
    from unittest.mock import MagicMock

    from cats.network import ContentMesh

    client = ContentMesh(ipfsClient=MagicMock(), CATS_HOME=str(tmp_path / 'cas'))
    first = client.put_json({'root_uri': 'http://n/a'})
    again = client.put_json({'root_uri': 'http://n/a'})
    second = client.put_json({'root_uri': 'http://n/b'})
    digest = client.bundle_digest(first)
    assert client.bundle_digest(again) == digest
    assert client.bundle_digest(second) != digest

    calls = []
    carried = _order()
    carried['structure_uri'] = first
    runtime = _runtime(calls, order=carried)
    run_order(
        {'order_id': 'order1'},
        runtime=runtime,
        cats_home=None,
        module_digest=digest,
    )
    assert [step for step, _ in calls] == ['initFactory', 'execute']

    moved = []
    minted = _order()
    minted['structure_uri'] = second
    runtime = _runtime(moved, order=minted)
    with pytest.raises(RuntimeError, match='module digest'):
        run_order(
            {'order_id': 'order1'},
            runtime=runtime,
            cats_home=None,
            module_digest=digest,
        )
    assert moved == []


def test_missing_function_structure_message_matches_factory():
    assert 'structure_uri' in _MISSING_FUNCTION_STRUCTURE
    assert 'function_uri' in _MISSING_FUNCTION_STRUCTURE


def test_init_route_returns_500_on_execute_error(monkeypatch):
    """catSubmit must see a failed execute; HTTP 200 with error fooled CAT0."""
    from cats.node.app import catNode

    monkeypatch.setattr(
        'cats.node.app.run_order',
        lambda body: (_ for _ in ()).throw(RuntimeError('Ray OOM')),
    )
    response = catNode.test_client().post(
        '/cat/node/init', json={'order_uri': 'http://example/order'}
    )
    assert response.status_code == 500
    assert 'Ray OOM' in response.get_json()['error']
