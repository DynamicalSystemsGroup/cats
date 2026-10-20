"""Job result directory survives deleting CATS_HOME."""
from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from cats.executor.result import resolve_result_dir, write_job_result
from cats.network.cas.digest import from_ni
from cats.network.cas.store import CasHttpStore, cas_ldp_uri


def _put_json(store: CasHttpStore, obj) -> tuple[str, str]:
    content_id = store.put((json.dumps(obj) + '\n').encode('utf-8'))
    uri = cas_ldp_uri(from_ni(content_id), base_url='http://127.0.0.1:5000')
    return content_id, uri


def test_result_dir_refuses_path_under_cats_home(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    with pytest.raises(RuntimeError, match='must not be under CATS_HOME'):
        resolve_result_dir(str(home), str(home / 'cat-result'))


def test_invoice_content_id_survives_deleting_cats_home(tmp_path):
    cats_home = tmp_path / 'cats-home'
    result_dir = tmp_path / 'cat-result'
    store = CasHttpStore(str(cats_home))

    data_id = store.put(b'egress-bytes')
    data_uri = cas_ldp_uri(from_ni(data_id), base_url='http://127.0.0.1:5000')
    stages_id, stages_uri = _put_json(
        store, {'egressed_data_uri': data_uri}
    )
    order_id, order_uri = _put_json(store, {'function_uri': 'http://n/f'})
    observed = {'rebuilt': False, 'applied_structure_id': None}
    observed_id, observed_uri = _put_json(store, observed)
    log_id, log_uri = _put_json(store, {'status': 'exited'})
    ingress_id = store.put(b'ingress-bytes')
    ingress_uri = cas_ldp_uri(
        from_ni(ingress_id), base_url='http://127.0.0.1:5000'
    )
    invoice = {
        'data_uri': data_uri,
        'data_stages_uri': stages_uri,
        'order_uri': order_uri,
        'structure_as_executed_uri': observed_uri,
    }
    invoice_id, invoice_uri = _put_json(store, invoice)
    bom = {
        'invoice_uri': invoice_uri,
        'log_uri': log_uri,
        'data_uri': data_uri,
        'order_uri': order_uri,
        'stageLineage': [
            {
                '@id': ingress_uri,
                'contentId': ingress_id,
                'prov:wasDerivedFrom': {'contentId': data_id},
            },
            {'@id': observed_uri, 'contentId': observed_id},
        ],
    }
    bom_id = store.put((json.dumps(bom) + '\n').encode('utf-8'))
    bom_response = {'bom': bom, 'content_id': bom_id}

    written = write_job_result(
        bom_response,
        cats_home=str(cats_home),
        result_dir=str(result_dir),
    )
    assert written == result_dir.resolve()
    shutil.rmtree(cats_home)
    assert not cats_home.exists()

    result = json.loads((result_dir / 'result.json').read_text(encoding='utf-8'))
    invoice_out = json.loads((result_dir / 'invoice.json').read_text(encoding='utf-8'))
    bom_out = json.loads((result_dir / 'bom.json').read_text(encoding='utf-8'))
    assert result['invoice_content_id'] == invoice_id
    assert result['content_id'] == bom_response['content_id']
    assert result['invoice_uri'] == invoice_uri
    assert result['data_uri'] == data_uri
    assert result['order_uri'] == order_uri
    assert invoice_out['data_uri'] == data_uri
    assert invoice_out['structure_as_executed_uri'] == observed_uri
    assert bom_out['invoice_uri'] == invoice_uri
    bom_bytes = (result_dir / 'cas' / from_ni(bom_id)).read_bytes()
    assert hashlib.sha256(bom_bytes).hexdigest() == from_ni(bom_id)
    assert (result_dir / 'cas' / from_ni(invoice_id)).is_file()
    assert (result_dir / 'cas' / from_ni(data_id)).read_bytes() == b'egress-bytes'
    assert (result_dir / 'cas' / from_ni(stages_id)).is_file()
    assert (result_dir / 'cas' / from_ni(order_id)).is_file()
    assert (result_dir / 'cas' / from_ni(log_id)).is_file()
    assert (result_dir / 'cas' / from_ni(ingress_id)).read_bytes() == b'ingress-bytes'
    observed_out = json.loads(
        (result_dir / 'cas' / from_ni(observed_id)).read_text(encoding='utf-8')
    )
    assert observed_out['rebuilt'] is False
    assert not (result_dir / '.cats').exists()


def test_missing_cited_blob_raises(tmp_path):
    cats_home = tmp_path / 'cats-home'
    store = CasHttpStore(str(cats_home))
    invoice_id, invoice_uri = _put_json(store, {'data_uri': 'http://n/d'})
    bom = {
        'invoice_uri': invoice_uri,
        'log_uri': 'http://127.0.0.1:5000/ldp/cas/' + ('ab' * 32),
    }
    bom_id = store.put((json.dumps(bom) + '\n').encode('utf-8'))
    with pytest.raises(RuntimeError, match='CAS content not found'):
        write_job_result(
            {'bom': bom, 'content_id': bom_id},
            cats_home=str(cats_home),
            result_dir=str(tmp_path / 'cat-result'),
        )
    assert invoice_id
