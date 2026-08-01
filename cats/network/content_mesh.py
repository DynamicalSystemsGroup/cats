"""ContentMesh — content-store mesh API (Orders/BOMs/binds + Node submit).

Reads (``cat`` / ``catObj``) use ``AddressStore`` (optional IPFS HTTP gateway +
CID verify). Writes use ``CatsIPFSClient``. Plant CoD transport is
``cats.network.plant_transport.CoDTransport``, not this class.
"""
from __future__ import annotations

import importlib
import json
import os
import pickle
import shutil
import sys
import tempfile
import time
from copy import deepcopy
from pprint import pprint

import requests

from cats.network.address_store import AddressStore
from cats.network.bootstrap import (
    _bootstrap_content_store_utils_path,
    _load_bootstrap_content_store_module,
)
from cats.network.named_binds import (
    is_stock_function_callable,
    named_bind_payload,
    parse_named_bind_leaf,
)
from cats.network.node_http import _activity_spinner
from cats.network.order import OrderOps
from cats.network.packaging import (
    STRUCTURE_ROOT_DIRNAME,
    materialize_structure_root_files,
    stage_structure_root,
)


class ContentMesh(OrderOps):
    def __init__(self, ipfsClient, CATS_HOME=None, addressStore=None):
        self.CATS_HOME = None
        self.DATA_HOME = None
        self.JOB_HOME = None
        self.CACHE_HOME = None
        self.INPUT_HOME = None
        self.OUTPUT_HOME = None
        self.OUTPUT_DATA_HOME = None
        self.INPUT_STRUCTURE_HOME = None
        self.INPUT_DATA_HOME = None
        if CATS_HOME is not None:
            self.catStore(CATS_HOME)
        # Bootstrap ContentStore readiness is lazy (ensure_bootstrap_content_store),
        # not at import — assert/soft-warn only, never Order-bound ensure.
        # Order-submitted ensure is TF host_ipfs_daemon create; apply asserts.
        self._bootstrap_content_store_ensured = False

        self.INGRESS_HOME = None
        self.INTEGRATION_HOME = None
        self.INTEGRATION_INPUT_CACHE = None
        self.INTEGRATION_INPUT_DATA_CACHE = None
        self.EGRESS_INPUT_DATA = None
        self.EGRESS_HOME = None

        self.CAT_HOME = None
        self.CAR_HOME = None
        self.ipfsClient = ipfsClient
        # Reads (cat/catObj) go through AddressStore; writes stay on ipfsClient.
        self.addressStore = addressStore if addressStore is not None else AddressStore(
            ipfsClient
        )
        self.ingress_job_id = None
        self.ingressed_data_cid = None

    def ensure_bootstrap_content_store(self):
        """Lazy default-tree ContentStore readiness check (no ensure/heal).

        Soft-warns once if the HTTP API is down. Does not call
        ``ContentStore.ensure`` — operator heal is ``node ensure`` /
        ``content-store-ensure``; automatic Order mutate is TF
        ``host_ipfs_daemon`` create. Not Order-bound (repo default tree only).
        """
        if self._bootstrap_content_store_ensured:
            return
        path = _bootstrap_content_store_utils_path(self.CATS_HOME)
        if path is None or not os.path.isfile(path):
            print(
                'WARNING: bootstrap content_store_utils.py missing; '
                'skipping ContentMesh ContentStore readiness check '
                f'(path={path!r})',
                flush=True,
            )
            self._bootstrap_content_store_ensured = True
            return
        try:
            module = _load_bootstrap_content_store_module(self.CATS_HOME)
            if not module.ContentStore.is_ready():
                print(
                    'WARNING: host IPFS ContentStore API not ready; '
                    'run make content-store-ensure or python -m cats.node ensure '
                    '(ContentMesh does not auto-ensure).',
                    flush=True,
                )
        except (RuntimeError, FileNotFoundError, OSError) as exc:
            print(
                f'WARNING: host IPFS bootstrap content store probe failed: {exc}',
                flush=True,
            )
        self._bootstrap_content_store_ensured = True

    def fetch_ipfs_object(self, cid):
        try:
            binary_content = self.catObj(cid)
            return pickle.loads(binary_content)
        except Exception as e:
            print(f"An error occurred while fetching the object from IPFS: {e}")
            return None

    def catStore(self, CATS_HOME):
        self.CATS_HOME = CATS_HOME
        self.DATA_HOME = self.CATS_HOME + '/data'
        self.JOB_HOME = self.DATA_HOME + '/jobs'

    def catSubmit(self, order_request):
        print("Order:")
        order = json.loads(self.cat(order_request["order_cid"]))
        print()
        pprint(order)
        print()

        endpoint = order["endpoint"]
        # Demo-friendly curl equivalent (execution uses requests, same as Kubo RPC).
        curl_cmd = (
            "curl -X POST -H \"Content-Type: application/json\" -d '"
            + json.dumps(order_request)
            + f"' {endpoint}"
        )
        print(curl_cmd)
        print()
        print(f'POST {endpoint} …', flush=True)
        t0 = time.perf_counter()
        with _activity_spinner(label='Waiting on Node'):
            # Cold Structure reconcile (kind + Helm) can exceed 10m on first apply.
            response = requests.post(endpoint, json=order_request, timeout=1800)
        elapsed = time.perf_counter() - t0
        response.raise_for_status()
        print(
            f'done in {elapsed:.1f}s → {response.status_code} '
            f'({len(response.content)} bytes)',
            flush=True,
        )
        output_bom = response.json()
        output_bom['POST'] = curl_cmd
        return output_bom
    def cidDir(self, filepath: str):
        self.ensure_bootstrap_content_store()
        # print(filepath)
        name = filepath.split('/')[-1]
        dir = self.ipfsClient.add(filepath, recursive=True)
        if type(dir) is list:
            # dir_json = list(filter(lambda x: x['Name'] == 'outputs', dir))[-1]
            dir_json = list(filter(lambda x: x['Name'] == name, dir))[-1]
            dir_cid = dir_json['Hash']
            dir_name = dir_json['Name']
            return dir_cid, dir_name
        else:
            dir_cid = dir['Hash']
            # dir_name = dir['Name']
            return dir_cid

    def cidFile(self, filepath):
        self.ensure_bootstrap_content_store()
        file_json = self.ipfsClient.add(filepath)
        file_cid = file_json['Hash']
        file_name = file_json['Name']
        return file_cid, file_name

    def cid_structure_pairing(self, structure_filepath) -> dict:
        """CID apply-complete Structure pairing from a Structure home path.

        Returns ``{root_cid, plant_cid, infrastructure_cid}`` (directory CIDs).
        Used by ``create_order_request`` and ``linkStructure``.
        """
        self.ensure_bootstrap_content_store()
        structure_filepath = structure_filepath.rstrip('/')
        # Root compose glue: main.tf / outputs.tf / lock (not plant/infra).
        staging_parent = tempfile.mkdtemp(prefix='cats-structure-root-')
        try:
            root_staging = stage_structure_root(
                structure_filepath, staging_parent=staging_parent
            )
            root_cid, _ = self.cidDir(root_staging)
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
        plant_cid, _ = self.cidDir(os.path.join(structure_filepath, 'plant'))
        infrastructure_cid, _ = self.cidDir(
            os.path.join(structure_filepath, 'infrastructure')
        )
        return {
            'root_cid': root_cid,
            'plant_cid': plant_cid,
            'infrastructure_cid': infrastructure_cid,
        }
    def flatten_bom(self, bom_response):
        invoice = json.loads(
            self.cat(bom_response["bom"]["invoice_cid"])
        )
        invoice['order'] = json.loads(
            self.cat(invoice['order_cid']),
        )
        invoice['order']['flat'] = {
            'function': json.loads(self.cat(invoice['order']["function_cid"])),
            'structure': json.loads(self.cat(invoice['order']["structure_cid"])),
            'invoice': json.loads(self.cat(invoice['order']["invoice_cid"]))
        }
        structure_as_executed = None
        plant = None
        infrastructure_as_executed = None
        object_store_as_executed = None
        structure_as_executed_cid = invoice.get('structure_as_executed_cid')
        if structure_as_executed_cid:
            structure_as_executed = json.loads(self.cat(structure_as_executed_cid))
            plant_cid = structure_as_executed.get('plant_as_executed_cid')
            infra_cid = structure_as_executed.get('infrastructure_as_executed_cid')
            if plant_cid:
                plant = json.loads(self.cat(plant_cid))
            if infra_cid:
                infrastructure_as_executed = json.loads(self.cat(infra_cid))
                os_cid = infrastructure_as_executed.get(
                    'object_store_as_executed_cid'
                )
                if os_cid:
                    object_store_as_executed = json.loads(self.cat(os_cid))
        bom_response["flat_bom"] = {
            'invoice': invoice,
            'log': json.loads(
                self.cat(bom_response["bom"]["log_cid"])
            ),
            'structure_as_executed': structure_as_executed,
            'plant': plant,
            'infrastructure_as_executed': infrastructure_as_executed,
            'object_store_as_executed': object_store_as_executed,
        }
        return bom_response

    def initBOMjson(self,
        structure_cid: str, structure_filepath: str, function_cid: str, init_data_cid: str,
        order_cid: str = None, seed_cid=None
    ):
        if order_cid is not None:
            # Reuse the real, already-submitted Order's own CID directly, so
            # the order.json materialized by getEnhancedBom() and the
            # order_cid Executor.execute() later backfills into the final
            # Invoice both refer to the exact same CID for this execution -
            # rather than each independently minting their own "equivalent
            # but not identical" copy of the Order (see docs/NodeProductFlow.md#2b's
            # "the original CID-ed Order").
            resolved_order_cid = order_cid
        else:
            # No real Order to reference yet (initBOMjson without order_cid)
            # — mint a standalone placeholder.
            placeholder_invoice = {'order_cid': None, 'seed_cid': seed_cid}
            placeholder_invoice_cid = self.ipfsClient.add_json(placeholder_invoice)
            placeholder_order = {
                'invoice_cid': placeholder_invoice_cid,
                'function_cid': function_cid,
                'structure_cid': structure_cid,
                'structure_filepath': structure_filepath
            }
            resolved_order_cid = self.ipfsClient.add_json(placeholder_order)

        invoice = {'order_cid': resolved_order_cid, 'seed_cid': seed_cid}
        invoice_cid = self.ipfsClient.add_json(invoice)

        init_bom = {
            'invoice_cid': invoice_cid,
            'log_cid': None,
            'init_data_cid': init_data_cid
        }
        init_bom_json_cid = self.ipfsClient.add_json(init_bom)
        return init_bom_json_cid

    def initBOMcar(self,
            structure_cid: str, structure_filepath: str, function_cid: str, init_data_cid: str,
            init_bom_filename: str, order_cid: str = None, seed_cid=None
        ):
        init_bom_json_cid = self.initBOMjson(
            structure_cid, structure_filepath, function_cid, init_data_cid,
            order_cid=order_cid, seed_cid=seed_cid,
        )
        car_bom_cid, init_bom_json_cid = self.convertBOMtoCAR(init_bom_json_cid, init_bom_filename)
        return car_bom_cid, init_bom_json_cid

    def linkData(self, cid, subdir='outputs'):
        """Return Hash of the UnixFS link matching ``subdir`` (name fragment).

        Legacy CLI filter strings like ``' - outputs/'`` are normalized to
        ``outputs``.
        """
        self.ensure_bootstrap_content_store()
        needle = subdir.strip(' -/')
        if not needle:
            needle = 'outputs'
        links = self.ipfsClient.ls(cid)
        for link in links:
            name = link.get('Name') or ''
            if needle in name:
                return link['Hash']
        raise RuntimeError(
            f'No ls link matching {needle!r} under {cid!r}; '
            f'names={[link.get("Name") for link in links]}'
        )

    def get(self, cid: str, filepath: str, output: str = None):
        self.ensure_bootstrap_content_store()
        if output is None:
            output = self.CATS_HOME
        dest = os.path.join(output, filepath)
        self.addressStore.get(cid, dest)
        return filepath

    def testGet(self, cid: str, output: str):
        self.ensure_bootstrap_content_store()
        self.addressStore.get(cid, output)
        print(f'IPFS download of {output} completed successfully.')

    def cat(self, cid: str):
        self.ensure_bootstrap_content_store()
        return self.addressStore.cat(cid)

    def catObj(self, cid: str):
        self.ensure_bootstrap_content_store()
        return self.addressStore.cat_bytes(cid)

    def add_named_bind(self, source_cid: str, module: str, qualname: str) -> str:
        """CID a named-bind JSON leaf for an Order slot."""
        return self.ipfsClient.add_str(
            json.dumps(named_bind_payload(source_cid, module, qualname))
        )

    def bind_subproc(self, obj, source_cid: str) -> str:
        """CID a stock named bind or pickle leaf for ``obj``."""
        self.ensure_bootstrap_content_store()
        if is_stock_function_callable(obj):
            return self.add_named_bind(source_cid, obj.__module__, obj.__qualname__)
        return self.ipfsClient.add_pyobj(obj)

    def resolve_subproc(self, slot_cid: str, *, expected_source_cid: str):
        """Load a slot leaf: named-bind JSON import, else pickle."""
        raw = self.catObj(slot_cid)
        spec = parse_named_bind_leaf(raw)
        if spec is None:
            return pickle.loads(raw)
        if spec['source_cid'] != expected_source_cid:
            raise RuntimeError(
                f'named bind source_cid {spec["source_cid"]!r} does not match '
                f'Order package CID {expected_source_cid!r} '
                f'(module={spec["module"]!r}, qualname={spec["qualname"]!r})'
            )
        if self.CATS_HOME and self.CATS_HOME not in sys.path:
            sys.path.insert(0, self.CATS_HOME)
        try:
            module = importlib.import_module(spec['module'])
        except ImportError as exc:
            raise RuntimeError(
                f'named bind failed to import module {spec["module"]!r}: {exc}'
            ) from exc
        try:
            target = module
            for part in spec['qualname'].split('.'):
                target = getattr(target, part)
        except AttributeError as exc:
            raise RuntimeError(
                f'named bind qualname {spec["qualname"]!r} not found on '
                f'module {spec["module"]!r}: {exc}'
            ) from exc
        return target

    def getCar(self, cid: str, filepath: str):
        self.ensure_bootstrap_content_store()
        self.addressStore.dag_export(cid, filepath)

    def convertBOMtoCAR(self, bom_cid: str, filepath: str):
        self.getCar(bom_cid, filepath)
        car_bom_cid = None
        try:
            car_bom_cid = self.ipfsClient.add(filepath)['Hash']
        except Exception:
            for attrs in self.ipfsClient.add(filepath):
                if attrs['Name'] == filepath:
                    print(attrs)
                    car_bom_cid = attrs['Hash']
        return car_bom_cid, bom_cid

    def getEnhancedBom(self, bom_json_cid: str, INPUT_HOME: str = None, OUTPUT_HOME: str = None):
        if INPUT_HOME is None:
            INPUT_HOME = self.INPUT_HOME
        if OUTPUT_HOME is None:
            OUTPUT_HOME = self.OUTPUT_HOME
        self.CAR_HOME = OUTPUT_HOME + '/bom.car'
        self.get(cid=bom_json_cid, output=OUTPUT_HOME, filepath='bom.json')
        bom = json.loads(open(f'{OUTPUT_HOME}/bom.json', 'r').read())
        enhanced_bom = deepcopy(bom)
        enhanced_bom['bom_json_cid'] = bom_json_cid

        self.get(cid=bom['invoice_cid'], output=OUTPUT_HOME, filepath='invoice.json')
        enhanced_bom['invoice'] = json.loads(open(f'{OUTPUT_HOME}/invoice.json', 'r').read())

        self.get(cid=enhanced_bom['invoice']['order_cid'], output=INPUT_HOME, filepath='order.json')
        enhanced_bom['order'] = json.loads(open(f'{INPUT_HOME}/order.json', 'r').read())

        # structure_cid nests root_cid (compose glue), plant_cid, and
        # infrastructure_cid — see create_order_request(). Materialize all
        # three so Structure home is terraform apply-complete from the Order.
        structure = json.loads(self.cat(enhanced_bom['order']['structure_cid']))
        structure_filepath = enhanced_bom['order']['structure_filepath']
        root_cid = structure.get('root_cid')
        if not root_cid:
            raise RuntimeError(
                'structure_cid is missing root_cid; recreate the Order with '
                'create_order_request after apply-complete Structure pairing '
                '({root_cid, plant_cid, infrastructure_cid}).'
            )
        for key in ('plant_cid', 'infrastructure_cid'):
            if not structure.get(key):
                raise RuntimeError(
                    f'structure_cid is missing {key}; recreate the Order.'
                )
        structure_home = os.path.join(INPUT_HOME, structure_filepath)
        with tempfile.TemporaryDirectory(prefix='cats-root-fetch-') as tmp:
            fetch_dir = os.path.join(tmp, STRUCTURE_ROOT_DIRNAME)
            self.get(cid=root_cid, output=tmp, filepath=STRUCTURE_ROOT_DIRNAME)
            materialize_structure_root_files(fetch_dir, structure_home)
        self.get(
            cid=structure['plant_cid'], output=INPUT_HOME,
            filepath=os.path.join(structure_filepath, 'plant')
        )
        self.get(
            cid=structure['infrastructure_cid'], output=INPUT_HOME,
            filepath=os.path.join(structure_filepath, 'infrastructure')
        )

        # function_cid nests pickle bind CIDs plus Process / InfraFunction
        # source directory CIDs — see create_order_request(). Materialize
        # source trees for provenance (execution still uses pickles).
        function = json.loads(self.cat(enhanced_bom['order']['function_cid']))
        process_source_cid = function.get('process_source_cid')
        infrafunction_source_cid = function.get('infrafunction_source_cid')
        if not process_source_cid or not infrafunction_source_cid:
            raise RuntimeError(
                'function_cid is missing process_source_cid / '
                'infrafunction_source_cid; recreate the Order with '
                'create_order_request after hybrid Function source CIDs '
                '({process_cid, infrafunction_cid, process_source_cid, '
                'infrafunction_source_cid}).'
            )
        self.get(
            cid=process_source_cid, output=INPUT_HOME,
            filepath=os.path.join('function', 'process'),
        )
        self.get(
            cid=infrafunction_source_cid, output=INPUT_HOME,
            filepath=os.path.join('function', 'infrafunction'),
        )
        return deepcopy(enhanced_bom), bom
