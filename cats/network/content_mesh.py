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
from cats.network.cas import equality_id, ref_id, ref_uri, set_ref
from cats.network.named_binds import (
    is_stock_function_callable,
    named_bind_payload,
    named_bind_source_id,
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
        # Reads via AddressStore (CAS ni: or legacy CID); new writes prefer CAS.
        self.addressStore = addressStore if addressStore is not None else AddressStore(
            ipfsClient,
            cats_home=CATS_HOME,
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

    def fetch_ipfs_object(self, content_id):
        try:
            binary_content = self.catObj(content_id)
            return pickle.loads(binary_content)
        except Exception as e:
            print(f"An error occurred while fetching the object from IPFS: {e}")
            return None

    def catStore(self, CATS_HOME):
        self.CATS_HOME = CATS_HOME
        self.DATA_HOME = self.CATS_HOME + '/data'
        self.JOB_HOME = self.DATA_HOME + '/jobs'
        if getattr(self, 'addressStore', None) is not None:
            self.addressStore.cats_home = CATS_HOME

    def catSubmit(self, order_request):
        """POST an Order to ``/cat/node/init`` (§6d: ``order_uri`` / ``content_id``).

        ``create_order_request`` returns ``{content_id, order_uri, invoice_uri}``.
        Legacy ``order_cid`` on the request dict is still accepted for local
        resolve only — it is never forwarded in the HTTP body.
        """
        from cats.network.cas import content_id_from_uri, is_http_uri

        order_id = (
            order_request.get('content_id')
            or order_request.get('order_id')
            or order_request.get('order_cid')
        )
        order_uri = order_request.get('order_uri')
        if not order_id and order_uri:
            if is_http_uri(order_uri):
                order_id = content_id_from_uri(
                    order_uri, cats_home=self.CATS_HOME
                )
                if order_id is None and self.CATS_HOME:
                    from cats.network.cas import LocatorIndex

                    order_id = LocatorIndex(self.CATS_HOME).find_content_id_for_uri(
                        order_uri
                    )
            else:
                order_id = order_uri
        if not order_id and not order_uri:
            raise RuntimeError(
                'order_request requires content_id, order_uri, or legacy order_cid'
            )

        print("Order:")
        # Fetch by equality id (CAS / legacy CID); order_uri is for HTTP intake only.
        order = json.loads(self.cat(order_id))
        print()
        pprint(order)
        print()

        endpoint = order["endpoint"]
        # §6d intake body: prefer order_uri; never send order_cid/bom_cid/data_cid.
        body = {
            k: v
            for k, v in order_request.items()
            if k not in ('order_cid', 'bom_cid', 'data_cid')
        }
        if not order_uri and order_id:
            from cats.network.ldp import order_ldp_uri

            order_uri = order_ldp_uri(order_id)
        if order_uri:
            body['order_uri'] = order_uri
        body.pop('content_id', None)  # order equality goes via order_uri only

        # Demo-friendly curl equivalent (execution uses requests, same as Kubo RPC).
        curl_cmd = (
            "curl -X POST -H \"Content-Type: application/json\" -d '"
            + json.dumps(body)
            + f"' {endpoint}"
        )
        print(curl_cmd)
        print()
        print(f'POST {endpoint} …', flush=True)
        t0 = time.perf_counter()
        with _activity_spinner(label='Waiting on Node'):
            # Cold Structure reconcile (kind + Helm) can exceed 10m on first apply.
            response = requests.post(endpoint, json=body, timeout=1800)
        elapsed = time.perf_counter() - t0
        if not response.ok:
            detail = ''
            try:
                detail = response.text[:500]
            except Exception:
                pass
            print(
                f'HTTP {response.status_code} after {elapsed:.1f}s: {detail}',
                flush=True,
            )
        response.raise_for_status()
        print(
            f'done in {elapsed:.1f}s → {response.status_code} '
            f'({len(response.content)} bytes)',
            flush=True,
        )
        output_bom = response.json()
        output_bom['POST'] = curl_cmd
        return output_bom
    def put_bytes(self, data: bytes, *, media_type: str | None = None) -> str:
        """CAS-only put; return ``ni:`` and register Node locator."""
        if self.CATS_HOME is None:
            raise RuntimeError('ContentMesh.CATS_HOME required for CAS put_bytes')
        from cats.network.cas import CasHttpStore, LocatorIndex

        content_id = CasHttpStore(self.CATS_HOME).put(bytes(data))
        LocatorIndex(self.CATS_HOME).put_cas_node_locator(
            content_id, media_type=media_type
        )
        return content_id

    def put_json(self, obj, *, media_type: str = 'application/json') -> str:
        """CAS-only JSON put; return ``ni:``."""
        return self.put_bytes(
            (json.dumps(obj) + '\n').encode('utf-8'),
            media_type=media_type,
        )

    def put_tree(self, directory: str) -> str:
        """CAS directory manifest put; return ``ni:`` of the manifest."""
        if self.CATS_HOME is None:
            raise RuntimeError('ContentMesh.CATS_HOME required for CAS put_tree')
        from cats.network.cas import CasHttpStore, LocatorIndex, put_tree

        store = CasHttpStore(self.CATS_HOME)
        content_id = put_tree(store, directory)
        LocatorIndex(self.CATS_HOME).put_cas_node_locator(
            content_id, media_type='application/json'
        )
        return content_id

    def put_dir(self, filepath: str):
        self.ensure_bootstrap_content_store()
        name = filepath.split('/')[-1]
        if self.CATS_HOME is not None:
            dir_id = self.put_tree(filepath)
            return dir_id, name
        dir = self.ipfsClient.add(filepath, recursive=True)
        if type(dir) is list:
            dir_json = list(filter(lambda x: x['Name'] == name, dir))[-1]
            dir_id = dir_json['Hash']
            dir_name = dir_json['Name']
            return dir_id, dir_name
        else:
            dir_id = dir['Hash']
            return dir_id

    def put_file(self, filepath):
        self.ensure_bootstrap_content_store()
        file_name = os.path.basename(filepath)
        if self.CATS_HOME is not None:
            with open(filepath, 'rb') as handle:
                file_id = self.put_bytes(handle.read())
            return file_id, file_name
        file_json = self.ipfsClient.add(filepath)
        file_id = file_json['Hash']
        file_name = file_json['Name']
        return file_id, file_name

    def structure_pairing(self, structure_filepath) -> dict:
        """Apply-complete Structure pairing from a Structure home path.

        Returns uri-only ``{root_uri, plant_uri, infrastructure_uri}``
        (directory content ids). Used by ``create_order_request`` and
        ``linkStructure``.
        """
        self.ensure_bootstrap_content_store()
        structure_filepath = structure_filepath.rstrip('/')
        # Root compose glue: main.tf / outputs.tf / lock (not plant/infra).
        staging_parent = tempfile.mkdtemp(prefix='cats-structure-root-')
        try:
            root_staging = stage_structure_root(
                structure_filepath, staging_parent=staging_parent
            )
            root_id, _ = self.put_dir(root_staging)
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
        plant_id, _ = self.put_dir(os.path.join(structure_filepath, 'plant'))
        infrastructure_id, _ = self.put_dir(
            os.path.join(structure_filepath, 'infrastructure')
        )
        pairing = {}
        set_ref(pairing, 'root', root_id)
        set_ref(pairing, 'plant', plant_id)
        set_ref(pairing, 'infrastructure', infrastructure_id)
        return pairing

    def _fetch_ref(self, obj, stem):
        """Load JSON for ``stem`` via ``*_uri`` or legacy ``*_cid`` / equality id."""
        key = ref_uri(obj, stem) or ref_id(obj, stem, cats_home=self.CATS_HOME)
        if not key:
            return None
        return json.loads(self.cat(key))

    def flatten_bom(self, bom_response):
        bom = bom_response["bom"]
        invoice = self._fetch_ref(bom, 'invoice')
        if invoice is None:
            raise RuntimeError('BOM missing invoice_uri / invoice_cid')
        invoice['order'] = self._fetch_ref(invoice, 'order')
        if invoice['order'] is None:
            raise RuntimeError('Invoice missing order_uri / order_cid')
        seed = self._fetch_ref(invoice, 'seed')
        if seed is not None:
            invoice['seed'] = seed
        order = invoice['order']
        order['flat'] = {
            'function': self._fetch_ref(order, 'function'),
            'structure': self._fetch_ref(order, 'structure'),
            'invoice': self._fetch_ref(order, 'invoice'),
        }
        structure_as_executed = None
        plant = None
        infrastructure_as_executed = None
        object_store_as_executed = None
        structure_as_executed = self._fetch_ref(invoice, 'structure_as_executed')
        if structure_as_executed is not None:
            plant = self._fetch_ref(structure_as_executed, 'plant_as_executed')
            infrastructure_as_executed = self._fetch_ref(
                structure_as_executed, 'infrastructure_as_executed'
            )
            if infrastructure_as_executed is not None:
                object_store_as_executed = self._fetch_ref(
                    infrastructure_as_executed, 'object_store_as_executed'
                )
        log = self._fetch_ref(bom, 'log')
        bom_response["flat_bom"] = {
            'invoice': invoice,
            'log': log,
            'structure_as_executed': structure_as_executed,
            'plant': plant,
            'infrastructure_as_executed': infrastructure_as_executed,
            'object_store_as_executed': object_store_as_executed,
        }
        return bom_response

    def initBOMjson(self,
        structure_id: str, structure_filepath: str, function_id: str, init_data_id: str,
        order_id: str = None, seed_id=None
    ):
        if order_id is not None:
            # Reuse the real, already-submitted Order's own content id directly,
            # so the order.json materialized by getEnhancedBom() and the
            # order ref Executor.execute() later backfills into the final
            # Invoice both refer to the exact same id for this execution -
            # rather than each independently minting their own "equivalent
            # but not identical" copy of the Order (see docs/NodeProductFlow.md#2b's
            # "the original CID-ed Order").
            resolved_order_id = order_id
        else:
            # No real Order to reference yet (initBOMjson without order_id)
            # — mint a standalone placeholder (uri-only refs).
            placeholder_invoice = {}
            if seed_id is not None:
                set_ref(placeholder_invoice, 'seed', seed_id)
            placeholder_invoice_id = self.put_json(placeholder_invoice)
            placeholder_order = {
                'structure_filepath': structure_filepath,
            }
            set_ref(placeholder_order, 'invoice', placeholder_invoice_id)
            set_ref(placeholder_order, 'function', function_id)
            set_ref(placeholder_order, 'structure', structure_id)
            resolved_order_id = self.put_json(placeholder_order)

        invoice = {}
        set_ref(invoice, 'order', resolved_order_id)
        if seed_id is not None:
            set_ref(invoice, 'seed', seed_id)
        invoice_id = self.put_json(invoice)

        init_bom = {}
        set_ref(init_bom, 'invoice', invoice_id)
        set_ref(init_bom, 'init_data', init_data_id)
        init_bom_json_id = self.put_json(init_bom)
        return init_bom_json_id

    def initBOMcar(self,
            structure_id: str, structure_filepath: str, function_id: str, init_data_id: str,
            init_bom_filename: str, order_id: str = None, seed_id=None
        ):
        init_bom_json_id = self.initBOMjson(
            structure_id, structure_filepath, function_id, init_data_id,
            order_id=order_id, seed_id=seed_id,
        )
        car_bom_id, init_bom_json_id = self.convertBOMtoCAR(init_bom_json_id, init_bom_filename)
        return car_bom_id, init_bom_json_id

    def linkData(self, content_id, subdir='outputs'):
        """Return content id of the link matching ``subdir`` (name fragment).

        Legacy UnixFS ``ls`` for CIDs; CAS directory manifests match entry
        prefixes / path fragments.
        """
        from cats.network.cas.digest import is_ni_or_digest
        from cats.network.cas.manifest import is_directory_manifest

        self.ensure_bootstrap_content_store()
        needle = subdir.strip(' -/')
        if not needle:
            needle = 'outputs'
        if is_ni_or_digest(content_id):
            obj = json.loads(self.cat(content_id))
            if not is_directory_manifest(obj):
                raise RuntimeError(
                    f'CAS content {content_id!r} is not a directory manifest'
                )
            for path, file_id in obj['entries'].items():
                if needle in path or path.startswith(needle):
                    return file_id
            raise RuntimeError(
                f'No manifest entry matching {needle!r} under {content_id!r}; '
                f'paths={list(obj["entries"])}'
            )
        links = self.ipfsClient.ls(content_id)
        for link in links:
            name = link.get('Name') or ''
            if needle in name:
                return link['Hash']
        raise RuntimeError(
            f'No ls link matching {needle!r} under {content_id!r}; '
            f'names={[link.get("Name") for link in links]}'
        )

    def get(self, content_id: str, filepath: str, output: str = None):
        self.ensure_bootstrap_content_store()
        if output is None:
            output = self.CATS_HOME
        dest = os.path.join(output, filepath)
        self.addressStore.get(content_id, dest)
        return filepath

    def testGet(self, content_id: str, output: str):
        self.ensure_bootstrap_content_store()
        self.addressStore.get(content_id, output)
        print(f'IPFS download of {output} completed successfully.')

    def cat(self, content_id: str):
        self.ensure_bootstrap_content_store()
        return self.addressStore.cat(content_id)

    def catObj(self, content_id: str):
        self.ensure_bootstrap_content_store()
        return self.addressStore.cat_bytes(content_id)

    def add_named_bind(self, source_id: str, module: str, qualname: str) -> str:
        """Content-address a named-bind JSON leaf for an Order slot."""
        return self.put_json(named_bind_payload(source_id, module, qualname))

    def bind_subproc(self, obj, source_id: str) -> str:
        """Content-address a stock named bind or pickle leaf for ``obj``."""
        self.ensure_bootstrap_content_store()
        if is_stock_function_callable(obj):
            return self.add_named_bind(source_id, obj.__module__, obj.__qualname__)
        return self.put_bytes(pickle.dumps(obj))

    def resolve_subproc(self, slot_id: str, *, expected_source_id: str):
        """Load a slot leaf: named-bind JSON import, else pickle."""
        raw = self.catObj(slot_id)
        spec = parse_named_bind_leaf(raw)
        if spec is None:
            return pickle.loads(raw)
        leaf_id = named_bind_source_id(spec)
        expected_id = equality_id(expected_source_id)
        if leaf_id != expected_id:
            raise RuntimeError(
                f'named bind source {leaf_id!r} does not match '
                f'Order package id {expected_id!r} '
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

    def convertBOMtoCAR(self, bom_id: str, filepath: str):
        from cats.network.cas.digest import is_ni_or_digest

        if is_ni_or_digest(bom_id):
            # CAS blobs are already the address of record; no Kubo CAR re-add.
            raw = self.catObj(bom_id)
            parent = os.path.dirname(filepath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(filepath, 'wb') as handle:
                handle.write(raw)
            return bom_id, bom_id
        self.getCar(bom_id, filepath)
        car_bom_id = None
        try:
            car_bom_id = self.ipfsClient.add(filepath)['Hash']
        except Exception:
            for attrs in self.ipfsClient.add(filepath):
                if attrs['Name'] == filepath:
                    print(attrs)
                    car_bom_id = attrs['Hash']
        return car_bom_id, bom_id

    def getEnhancedBom(self, bom_json_id: str, INPUT_HOME: str = None, OUTPUT_HOME: str = None):
        if INPUT_HOME is None:
            INPUT_HOME = self.INPUT_HOME
        if OUTPUT_HOME is None:
            OUTPUT_HOME = self.OUTPUT_HOME
        self.CAR_HOME = OUTPUT_HOME + '/bom.car'
        self.get(content_id=bom_json_id, output=OUTPUT_HOME, filepath='bom.json')
        bom = json.loads(open(f'{OUTPUT_HOME}/bom.json', 'r').read())
        enhanced_bom = deepcopy(bom)
        enhanced_bom['bom_json_id'] = bom_json_id

        invoice_locator = ref_uri(bom, 'invoice') or ref_id(
            bom, 'invoice', cats_home=self.CATS_HOME
        )
        if not invoice_locator:
            raise RuntimeError('BOM missing invoice_uri / invoice_cid')
        self.get(content_id=invoice_locator, output=OUTPUT_HOME, filepath='invoice.json')
        enhanced_bom['invoice'] = json.loads(
            open(f'{OUTPUT_HOME}/invoice.json', 'r').read()
        )

        order_locator = ref_uri(enhanced_bom['invoice'], 'order') or ref_id(
            enhanced_bom['invoice'], 'order', cats_home=self.CATS_HOME
        )
        if not order_locator:
            raise RuntimeError('Invoice missing order_uri / order_cid')
        self.get(content_id=order_locator, output=INPUT_HOME, filepath='order.json')
        enhanced_bom['order'] = json.loads(open(f'{INPUT_HOME}/order.json', 'r').read())

        # Structure pairing nests root / plant / infrastructure (uri or legacy
        # cid) — see create_order_request(). Materialize all three so Structure
        # home is terraform apply-complete from the Order.
        structure_locator = ref_uri(enhanced_bom['order'], 'structure') or ref_id(
            enhanced_bom['order'], 'structure', cats_home=self.CATS_HOME
        )
        if not structure_locator:
            raise RuntimeError('Order missing structure_uri / structure_cid')
        structure = json.loads(self.cat(structure_locator))
        structure_filepath = enhanced_bom['order']['structure_filepath']
        root_id = ref_id(structure, 'root', cats_home=self.CATS_HOME)
        plant_id = ref_id(structure, 'plant', cats_home=self.CATS_HOME)
        infrastructure_id = ref_id(
            structure, 'infrastructure', cats_home=self.CATS_HOME
        )
        if not root_id:
            raise RuntimeError(
                'structure is missing root_uri / root_cid; recreate the Order '
                'with create_order_request after apply-complete Structure '
                'pairing ({root_uri, plant_uri, infrastructure_uri}).'
            )
        if not plant_id or not infrastructure_id:
            raise RuntimeError(
                'structure is missing plant / infrastructure refs; '
                'recreate the Order.'
            )
        root_locator = ref_uri(structure, 'root') or root_id
        plant_locator = ref_uri(structure, 'plant') or plant_id
        infra_locator = ref_uri(structure, 'infrastructure') or infrastructure_id
        structure_home = os.path.join(INPUT_HOME, structure_filepath)
        with tempfile.TemporaryDirectory(prefix='cats-root-fetch-') as tmp:
            fetch_dir = os.path.join(tmp, STRUCTURE_ROOT_DIRNAME)
            self.get(content_id=root_locator, output=tmp, filepath=STRUCTURE_ROOT_DIRNAME)
            materialize_structure_root_files(fetch_dir, structure_home)
        self.get(
            content_id=plant_locator, output=INPUT_HOME,
            filepath=os.path.join(structure_filepath, 'plant')
        )
        self.get(
            content_id=infra_locator, output=INPUT_HOME,
            filepath=os.path.join(structure_filepath, 'infrastructure')
        )

        # Function nests process / infrafunction binds plus Process /
        # InfraFunction source directory refs — see create_order_request().
        # Materialize source trees for provenance (execution still uses binds).
        function_locator = ref_uri(enhanced_bom['order'], 'function') or ref_id(
            enhanced_bom['order'], 'function', cats_home=self.CATS_HOME
        )
        if not function_locator:
            raise RuntimeError('Order missing function_uri / function_cid')
        function = json.loads(self.cat(function_locator))
        process_source_id = ref_id(
            function, 'process_source', cats_home=self.CATS_HOME
        )
        infrafunction_source_id = ref_id(
            function, 'infrafunction_source', cats_home=self.CATS_HOME
        )
        if not process_source_id or not infrafunction_source_id:
            raise RuntimeError(
                'function is missing process_source / infrafunction_source '
                'refs; recreate the Order with create_order_request after '
                'hybrid Function source ids.'
            )
        process_source_locator = (
            ref_uri(function, 'process_source') or process_source_id
        )
        infrafunction_source_locator = (
            ref_uri(function, 'infrafunction_source') or infrafunction_source_id
        )
        self.get(
            content_id=process_source_locator, output=INPUT_HOME,
            filepath=os.path.join('function', 'process'),
        )
        self.get(
            content_id=infrafunction_source_locator, output=INPUT_HOME,
            filepath=os.path.join('function', 'infrafunction'),
        )
        return deepcopy(enhanced_bom), bom
