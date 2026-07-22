import contextlib
import importlib.util
import itertools
import json
import os
import pickle
import sys
import threading
import time
from copy import deepcopy
from pprint import pprint

import requests

from cats.network.clients import CoD
from cats.utils import Text2Python


def _node_base_url():
    """Flask Node base URL — same defaults as cats/node.py CAT_NODE_*."""
    host = os.environ.get('CAT_NODE_HOST', '127.0.0.1')
    port = int(os.environ.get('CAT_NODE_PORT', '5000'))
    return f'http://{host}:{port}'


def _node_init_endpoint():
    return f'{_node_base_url()}/cat/node/init'


@contextlib.contextmanager
def _activity_spinner(label='Waiting'):
    """Indeterminate activity line on stderr while a long call runs (TTY only).

    Order submit wait is mostly server-side work, not byte transfer — a spinner /
    elapsed counter beats a fake percent bar. Non-TTY (tests/CI): no animation.
    """
    stop = threading.Event()
    started = time.perf_counter()
    use_tty = sys.stderr.isatty()

    def _run():
        frames = itertools.cycle('|/-\\')
        while not stop.wait(0.1):
            elapsed = time.perf_counter() - started
            sys.stderr.write(f'\r{label} {next(frames)} {elapsed:.0f}s')
            sys.stderr.flush()

    thread = None
    if use_tty:
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=1.0)
            sys.stderr.write('\r' + ' ' * 60 + '\r')
            sys.stderr.flush()


def _bootstrap_content_store_utils_path(cats_home):
    """Repo-default content_store_utils.py (not Order-submitted Structure)."""
    if not cats_home:
        return None
    return os.path.join(
        cats_home,
        'data',
        'input',
        'structure',
        'infrastructure',
        'content_store_utils.py',
    )


def _load_bootstrap_content_store_module(cats_home):
    """Load default-tree ContentStore for pre-Structure CID work only.

    Not Order-bound — Order-submitted ensure is TF shell_script.host_ipfs_daemon
    create; InfraStructure.apply only asserts is_ready after terraform apply.
    """
    path = _bootstrap_content_store_utils_path(cats_home)
    if path is None:
        raise RuntimeError('CATS_HOME is required to locate content_store_utils')
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(
        'infrastructure_content_store_utils_bootstrap', path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MeshClient(CoD):
    def __init__(self, ipfsClient, filecoinClient=None, awsClient=None, CATS_HOME=None):
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
        self.filecoinClient = filecoinClient
        self.awsClient = awsClient
        self.context = ...
        CoD.__init__(self, INTEGRATION_INPUT_CACHE=self.INTEGRATION_INPUT_CACHE, cidDir=self.cidDir)

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
                'skipping MeshClient ContentStore readiness check '
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
                    'run make content-store-ensure or cats/node.py ensure '
                    '(MeshClient does not auto-ensure).',
                    flush=True,
                )
        except (RuntimeError, FileNotFoundError, OSError) as exc:
            print(
                f'WARNING: host IPFS bootstrap content store probe failed: {exc}',
                flush=True,
            )
        self._bootstrap_content_store_ensured = True

    def retrieve_cids(self, cid_dict):
        def switch_case(case):
            match case:
                case 'text':
                    try:
                        return lambda cid: self.cat(cid)
                    except Exception as e:
                        print(f"An error occurred while retrieving CID {cid}: {e}")
                        return cid
                case 'obj':
                    try:
                        return lambda cid: pickle.loads(self.catObj(cid))
                    except Exception as e:
                        print(f"An error occurred while fetching the object from IPFS: {e}")
                        return cid
                case _:
                    return cid

        cid_contents = {}
        for key, cid in cid_dict.items():
            if cid is not None:
                try:
                    print(f"{key} - {cid}")
                    cid_contents[key] = switch_case('text')(cid)
                except:
                    try:
                        print(f"{key} - {cid}")
                        py_txt = switch_case('obj')(cid)
                        cid_contents[key] = Text2Python(py_txt)
                    except:
                        print(f"{key} - {cid}")
                        cid_contents[key] = cid
            else:
                cid_contents[key] = switch_case(None)
        return cid_contents

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
            response = requests.post(endpoint, json=order_request, timeout=600)
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

    def linkProcess(
            self,
            cat_response,
            ingress_subproc=None,
            integrated_subproc=None,
            egress_subproc=None,
            integration_cache_subproc=None,
            infrafunction_subproc=None
    ):
        flattened_bom = self.flatten_bom(cat_response)
        flat_bom = deepcopy(flattened_bom['flat_bom'])
        prev_function = flat_bom['invoice']['order']['flat']['function']
        prev_process = json.loads(self.cat(prev_function['process_cid']))
        prev_infrafunction = json.loads(self.cat(prev_function['infrafunction_cid']))

        process = {}
        if ingress_subproc is not None:
            process['ingress_subproc_cid'] = self.ipfsClient.add_pyobj(ingress_subproc)
        else:
            process['ingress_subproc_cid'] = prev_process['ingress_subproc_cid']
        if integrated_subproc is not None:
            process['integrated_subproc_cid'] = self.ipfsClient.add_pyobj(integrated_subproc)
        else:
            process['integrated_subproc_cid'] = prev_process['integrated_subproc_cid']
        if egress_subproc is not None:
            process['egress_subproc_cid'] = self.ipfsClient.add_pyobj(egress_subproc)
        else:
            process['egress_subproc_cid'] = prev_process['egress_subproc_cid']
        if integration_cache_subproc is not None:
            process['integration_cache_subproc_cid'] = self.ipfsClient.add_pyobj(integration_cache_subproc)
        else:
            process['integration_cache_subproc_cid'] = prev_process['integration_cache_subproc_cid']

        infrafunction = {}
        if infrafunction_subproc is not None:
            infrafunction['infrafunction_subproc_cid'] = self.ipfsClient.add_pyobj(infrafunction_subproc)
        else:
            infrafunction['infrafunction_subproc_cid'] = prev_infrafunction['infrafunction_subproc_cid']

        new_function_cid = self.ipfsClient.add_str(json.dumps({
            'process_cid': self.ipfsClient.add_str(json.dumps(process)),
            'infrafunction_cid': self.ipfsClient.add_str(json.dumps(infrafunction)),
        }))

        invoice = flat_bom['invoice']
        input_invoice = {'data_cid': invoice['data_cid']}
        prev_invoice_cid = self.ipfsClient.add_str(json.dumps(input_invoice))

        order = invoice['order']
        order['function_cid'] = new_function_cid
        order['invoice_cid'] = prev_invoice_cid
        del order['flat']
        order['endpoint'] = _node_init_endpoint()

        order_request = {'order_cid': self.ipfsClient.add_str(json.dumps(order))}
        return order_request

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

    def create_order_request(
            self,
            ingress_subproc,
            integrated_subproc,
            egress_subproc,
            integration_cache_subproc,
            infrafunction_subproc,
            data_dirpath,
            structure_filepath,
            endpoint=None,
    ):
        if endpoint is None:
            endpoint = _node_init_endpoint()
        self.ensure_bootstrap_content_store()
        structure_name = os.path.basename(structure_filepath.rstrip('/'))
        # Plant (SaaS): plant/ - the kind cluster + Helm releases
        # that constitute the dynamically scaled execution environment.
        plant_cid, _ = self.cidDir(os.path.join(structure_filepath, 'plant'))
        # InfraStructure (IaaS): infrastructure/ - the IPFS/Docker
        # transport layer used to move content-addressed data in and out
        # of the Plant.
        infrastructure_cid, _ = self.cidDir(os.path.join(structure_filepath, 'infrastructure'))
        structure_cid = self.ipfsClient.add_str(json.dumps({
            'plant_cid': plant_cid,
            'infrastructure_cid': infrastructure_cid,
        }))
        data_cid, dir_name = self.cidDir(data_dirpath)
        # Process [REPL(aC)]: composes transport callables (ingress,
        # integration_cache, egress) plus the tHOF (integrated_subproc —
        # input→output data transform). Process is the composer, not a tHOF.
        process = {
            'ingress_subproc_cid': self.ipfsClient.add_pyobj(ingress_subproc),
            'integrated_subproc_cid': self.ipfsClient.add_pyobj(integrated_subproc),
            'egress_subproc_cid': self.ipfsClient.add_pyobj(egress_subproc),
            'integration_cache_subproc_cid': self.ipfsClient.add_pyobj(integration_cache_subproc),
        }
        # InfraFunction (FaaS): actuator that dispatches the tHOF
        # (integrated_subproc) onto the Plant (see Processor.Integration() in
        # cats/executor/function/__init__.py). Transport callables are not
        # Plant jobs.
        infrafunction = {
            'infrafunction_subproc_cid': self.ipfsClient.add_pyobj(infrafunction_subproc),
        }
        function = {
            'process_cid': self.ipfsClient.add_str(json.dumps(process)),
            'infrafunction_cid': self.ipfsClient.add_str(json.dumps(infrafunction)),
        }
        invoice = {
            "data_cid": data_cid
        }
        order = {
            "function_cid": self.ipfsClient.add_str(json.dumps(function)),
            "structure_cid": structure_cid,
            "invoice_cid": self.ipfsClient.add_str(json.dumps(invoice)),
            "structure_filepath": structure_name,
            "JOB_HOME": self.JOB_HOME,
            "endpoint": endpoint
        }
        order_request = {
            'order_cid': self.ipfsClient.add_str(json.dumps(order))
        }
        return order_request

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
        bom_response["flat_bom"] = {
            'invoice': invoice,
            'log': json.loads(
                self.cat(bom_response["bom"]["log_cid"])
            ),
            'plant': json.loads(
                self.cat(bom_response["bom"]["plant_snapshot_cid"])
            )
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
            # No real Order to reference yet (e.g. Factory.initCAT's
            # from-scratch bootstrapping) - mint a standalone placeholder.
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
        self.ipfsClient.get(cid, dest)
        return filepath

    def testGet(self, cid: str, output: str):
        self.ensure_bootstrap_content_store()
        self.ipfsClient.get(cid, output)
        print(f'IPFS download of {output} completed successfully.')

    def cat(self, cid: str):
        self.ensure_bootstrap_content_store()
        return self.ipfsClient.cat(cid)

    def catObj(self, cid: str):
        self.ensure_bootstrap_content_store()
        return self.ipfsClient.cat_bytes(cid)

    def getCar(self, cid: str, filepath: str):
        self.ensure_bootstrap_content_store()
        self.ipfsClient.dag_export(cid, filepath)

    def getBom(self, cid: str, filepath: str):
        self.get(cid, filepath)
        path = os.path.join(self.CATS_HOME, filepath)
        with open(path, encoding='utf-8') as fh:
            bom = dict(json.load(fh))
        os.remove(path)
        return bom

    def BOMcarToIPFS(self, bom_cid: str, filepath: str):
        self.getCar(bom_cid, filepath)
        storage_bom_cid = self.ipfsClient.post_upload(filepath)
        return storage_bom_cid, bom_cid

    def convertBOMtoCAR(self, bom_cid: str, filepath: str):
        self.getCar(bom_cid, filepath)
        car_bom_cid = None
        try:
            car_bom_cid = self.ipfsClient.add(filepath)['Hash']
        except:
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

        # structure_cid nests plant_cid (module.plant) and infrastructure_cid
        # (module.infrastructure) - see create_order_request() - so each is
        # fetched into its corresponding plant/ or infrastructure/ subdirectory
        # rather than structure_cid itself being a single directory CID.
        structure = json.loads(self.cat(enhanced_bom['order']['structure_cid']))
        structure_filepath = enhanced_bom['order']['structure_filepath']
        self.get(
            cid=structure['plant_cid'], output=INPUT_HOME,
            filepath=os.path.join(structure_filepath, 'plant')
        )
        self.get(
            cid=structure['infrastructure_cid'], output=INPUT_HOME,
            filepath=os.path.join(structure_filepath, 'infrastructure')
        )
        return deepcopy(enhanced_bom), bom

    def createInvoice(self, orderCID: str, dataCID: str, seedCID: str):
        invoice = {'orderCID': orderCID, 'dataCID': dataCID, 'seedCID': seedCID}
        invoice_cid = self.ipfsClient.add_json(invoice)
        return invoice_cid
