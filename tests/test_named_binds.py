"""Named-bind JSON leaves vs pickle for Function Order slots."""
import json
import pickle
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network import (
    ContentMesh,
    is_stock_function_callable,
    named_bind_payload,
    parse_named_bind_leaf,
)
from cats.network.cas import is_ni_or_digest
from data.input.function.infrafunction import infrafunction_subproc
from data.input.function.process import (
    egress,
    ingress,
    integration_cache,
    process_0,
    process_1,
)


def _pickleable_leaf():
    """Module-level callable used as a non-stock pickle leaf."""
    return 42


def test_is_stock_function_callable_allowlist():
    """Stock Process/InfraFunction callables are allowlisted; locals are not."""
    assert is_stock_function_callable(process_0)
    assert is_stock_function_callable(process_1)
    assert is_stock_function_callable(ingress)
    assert is_stock_function_callable(egress)
    assert is_stock_function_callable(integration_cache)
    assert is_stock_function_callable(infrafunction_subproc)
    assert not is_stock_function_callable(lambda: None)

    def local_fn():
        return None

    assert not is_stock_function_callable(local_fn)


def test_parse_named_bind_leaf():
    """parse_named_bind_leaf accepts named-bind JSON and rejects pickle/partials."""
    payload = named_bind_payload('QmSrc', 'data.input.function.process.callables', 'process_0')
    raw = json.dumps(payload).encode('utf-8')
    assert parse_named_bind_leaf(raw) == payload
    assert parse_named_bind_leaf(pickle.dumps(process_0)) is None
    assert parse_named_bind_leaf(b'not-json') is None
    assert parse_named_bind_leaf(json.dumps({'source_cid': 'Qm'}).encode()) is None


def test_bind_subproc_stock_vs_lambda(monkeypatch, tmp_path):
    """bind_subproc uses named-bind JSON for stock callables and pickle for lambdas."""
    fake = MagicMock()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    cid = client.bind_subproc(process_0, 'QmProcSrc')
    assert is_ni_or_digest(cid) or cid.startswith('ni:')
    named_payload = json.loads(client.cat(cid))
    assert named_payload == {
        'source_cid': 'QmProcSrc',
        'module': process_0.__module__,
        'qualname': 'process_0',
    }

    # Module-level non-stock callable pickles under CAS.
    pickle_cid = client.bind_subproc(_pickleable_leaf, 'QmProcSrc')
    assert is_ni_or_digest(pickle_cid)
    raw = client.catObj(pickle_cid)
    assert pickle.loads(raw).__name__ == '_pickleable_leaf'


def test_resolve_subproc_named_and_pickle(tmp_path, monkeypatch):
    """resolve_subproc loads named-bind leaves and pickle leaves correctly."""
    fake = MagicMock()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(Path(__file__).resolve().parents[1]))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    named = named_bind_payload(
        'QmProcSrc',
        process_0.__module__,
        process_0.__qualname__,
    )
    monkeypatch.setattr(
        client,
        'catObj',
        lambda cid: {
            'QmNamed': json.dumps(named).encode('utf-8'),
            'QmPickle': pickle.dumps(process_1),
        }[cid],
    )

    resolved = client.resolve_subproc('QmNamed', expected_source_cid='QmProcSrc')
    assert resolved is process_0

    resolved_pickle = client.resolve_subproc('QmPickle', expected_source_cid='QmProcSrc')
    assert resolved_pickle.__name__ == 'process_1'


def test_resolve_subproc_source_mismatch(tmp_path, monkeypatch):
    """resolve_subproc rejects named binds whose source_cid does not match."""
    fake = MagicMock()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    named = named_bind_payload(
        'QmWrong',
        process_0.__module__,
        process_0.__qualname__,
    )
    monkeypatch.setattr(client, 'catObj', lambda cid: json.dumps(named).encode('utf-8'))
    with pytest.raises(RuntimeError, match='does not match'):
        client.resolve_subproc('QmNamed', expected_source_cid='QmProcSrc')


def _write_order_fixture(tmp_path: Path):
    structure = tmp_path / 'structure'
    (structure / 'plant').mkdir(parents=True)
    (structure / 'infrastructure').mkdir(parents=True)
    (structure / 'main.tf').write_text('module "plant" { source = "./plant" }\n')
    (structure / 'outputs.tf').write_text('output "x" { value = 1 }\n')
    (structure / '.terraform.lock.hcl').write_text('# lock\n')
    (structure / 'plant' / 'x.tf').write_text('x')
    (structure / 'infrastructure' / 'y.tf').write_text('y')
    process_pkg = tmp_path / 'function' / 'process'
    infra_pkg = tmp_path / 'function' / 'infrafunction'
    process_pkg.mkdir(parents=True)
    infra_pkg.mkdir(parents=True)
    (process_pkg / '__init__.py').write_text('# process\n')
    (infra_pkg / '__init__.py').write_text('# infrafunction\n')
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'f.csv').write_text('a\n')
    return structure, data


def test_create_order_request_stock_emits_named_bind_leaves(monkeypatch, tmp_path):
    """create_order_request binds stock callables as named-bind JSON leaves."""
    fake = MagicMock()
    structure, data = _write_order_fixture(tmp_path)

    def _cid_dir(path):
        name = Path(path).name
        return f'Qm{name}', name

    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cidDir', _cid_dir)
    put_objs = []
    real_put = client.put_json

    def _spy_put(obj, **kwargs):
        put_objs.append(obj)
        return real_put(obj, **kwargs)

    monkeypatch.setattr(client, 'put_json', _spy_put)

    client.create_order_request(
        ingress_subproc=ingress,
        integrated_subproc=process_0,
        egress_subproc=egress,
        integration_cache_subproc=integration_cache,
        infrafunction_subproc=infrafunction_subproc,
        data_dirpath=str(data),
        structure_filepath=str(structure),
    )

    named_leaves = [
        obj for obj in put_objs
        if isinstance(obj, dict)
        and set(obj) >= {'qualname', 'source_cid', 'module'}
    ]
    qualnames = {leaf['qualname'] for leaf in named_leaves}
    assert qualnames == {
        'ingress',
        'process_0',
        'egress',
        'integration_cache',
        'infrafunction_subproc',
    }
    assert all(leaf['source_cid'] in ('Qmprocess', 'Qminfrafunction') for leaf in named_leaves)


def test_link_process_rewrites_stock_named_bind(monkeypatch, tmp_path):
    """linkProcess rewrites stock slot changes as named-bind leaves."""
    fake = MagicMock()

    prev_process = {
        'ingress_subproc_cid': 'QmIn',
        'integrated_subproc_cid': 'QmInt',
        'egress_subproc_cid': 'QmEg',
        'integration_cache_subproc_cid': 'QmCache',
    }
    prev_infrafunction = {'infrafunction_subproc_cid': 'QmIfr'}
    prev_function = {
        'process_cid': 'QmProcBind',
        'infrafunction_cid': 'QmIfrBind',
        'process_source_cid': 'QmProcSrc',
        'infrafunction_source_cid': 'QmIfrSrc',
    }
    cat_response = {
        'bom': {
            'invoice_cid': 'QmInv',
            'log_cid': 'QmLog',
        }
    }

    def _cat(cid):
        if cid == 'QmInv':
            return json.dumps({'order_cid': 'QmOrder', 'data_cid': 'QmData'})
        if cid == 'QmOrder':
            return json.dumps({
                'function_cid': 'QmFn',
                'structure_cid': 'QmStruct',
                'invoice_cid': 'QmInvOld',
                'structure_filepath': 'structure',
                'endpoint': 'http://127.0.0.1:5000/cat/node/init',
            })
        if cid == 'QmFn':
            return json.dumps(prev_function)
        if cid == 'QmStruct':
            return json.dumps({
                'root_cid': 'QmRoot',
                'plant_cid': 'QmPlant',
                'infrastructure_cid': 'QmInfra',
            })
        if cid == 'QmInvOld':
            return json.dumps({'data_cid': 'QmData'})
        if cid == 'QmProcBind':
            return json.dumps(prev_process)
        if cid == 'QmIfrBind':
            return json.dumps(prev_infrafunction)
        if cid == 'QmLog':
            return json.dumps({})
        return '{}'

    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')
    put_objs = []
    real_put = client.put_json

    def _spy_put(obj, **kwargs):
        put_objs.append(obj)
        return real_put(obj, **kwargs)

    monkeypatch.setattr(client, 'put_json', _spy_put)

    client.linkProcess(cat_response, integrated_subproc=process_1)

    named_leaves = [
        obj for obj in put_objs
        if isinstance(obj, dict)
        and set(obj) >= {'qualname', 'source_cid'}
    ]
    assert len(named_leaves) == 1
    assert named_leaves[0]['qualname'] == 'process_1'
    assert named_leaves[0]['source_cid'] == 'QmProcSrc'

    # Carried slots: process bind JSON should still reference prior leaf CIDs
    # for unchanged slots.
    process_maps = [
        obj for obj in put_objs
        if isinstance(obj, dict)
        and 'ingress_subproc_cid' in obj
        and 'integrated_subproc_cid' in obj
    ]
    assert process_maps
    assert process_maps[-1]['ingress_subproc_cid'] == 'QmIn'
    assert process_maps[-1]['egress_subproc_cid'] == 'QmEg'
