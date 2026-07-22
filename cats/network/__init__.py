import contextlib
import importlib
import importlib.util
import itertools
import json
import os
import pickle
import shutil
import sys
import tempfile
import threading
import time
import types
from copy import deepcopy
from pprint import pprint

import requests

from cats.network.clients import CoD
from cats.utils import Text2Python

# Compose glue CIDed as structure_cid.root_cid (not plant/ or infrastructure/).
STRUCTURE_ROOT_DIRNAME = 'structure-root'
STRUCTURE_ROOT_FILES = (
    'main.tf',
    'outputs.tf',
    '.terraform.lock.hcl',
)


def stage_structure_root(structure_filepath, staging_parent=None):
    """Copy allowlisted Structure root files into a temp ``structure-root/`` dir.

    Returns the staging directory path (basename ``structure-root``) for
    ``cidDir``. Caller must remove the parent temp tree when finished if
    ``staging_parent`` was not supplied.
    """
    structure_filepath = structure_filepath.rstrip('/')
    if staging_parent is None:
        staging_parent = tempfile.mkdtemp(prefix='cats-structure-root-')
    staging_dir = os.path.join(staging_parent, STRUCTURE_ROOT_DIRNAME)
    os.makedirs(staging_dir, exist_ok=True)
    missing = []
    for name in STRUCTURE_ROOT_FILES:
        src = os.path.join(structure_filepath, name)
        if not os.path.isfile(src):
            missing.append(name)
            continue
        shutil.copy2(src, os.path.join(staging_dir, name))
    if missing:
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise FileNotFoundError(
            'Structure root allowlist incomplete under '
            f'{structure_filepath!r}; missing: {missing}'
        )
    return staging_dir


def materialize_structure_root_files(fetched_root_dir, structure_home):
    """Copy allowlisted files from a fetched root CID tree into Structure home.

    Does not delete ``structure_home`` (preserves terraform state / child dirs).
    """
    os.makedirs(structure_home, exist_ok=True)
    # Kubo get may land files at dest/ or nest under structure-root/.
    candidates = [fetched_root_dir]
    nested = os.path.join(fetched_root_dir, STRUCTURE_ROOT_DIRNAME)
    if os.path.isdir(nested):
        candidates.append(nested)
    source_dir = None
    for candidate in candidates:
        if all(
            os.path.isfile(os.path.join(candidate, name))
            for name in STRUCTURE_ROOT_FILES
        ):
            source_dir = candidate
            break
    if source_dir is None:
        # Accept whatever allowlisted files exist at the fetch root.
        for candidate in candidates:
            if any(
                os.path.isfile(os.path.join(candidate, name))
                for name in STRUCTURE_ROOT_FILES
            ):
                source_dir = candidate
                break
    if source_dir is None:
        raise RuntimeError(
            f'Structure root_cid fetch at {fetched_root_dir!r} has none of '
            f'{STRUCTURE_ROOT_FILES}'
        )
    for name in STRUCTURE_ROOT_FILES:
        src = os.path.join(source_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(structure_home, name))


# Function package dirs CIDed as function_cid.process_source_cid /
# infrafunction_source_cid (sibling of structure/ under input/).
FUNCTION_PACKAGE_NAMES = ('process', 'infrafunction')

# Stock Order-slot public names (auto named-bind). Not slots: function_0/1.
STOCK_PROCESS_SLOT_QUALNAMES = frozenset({
    'ingress',
    'egress',
    'integration_cache',
    'process_0',
    'process_1',
})
STOCK_INFRAFUNCTION_SLOT_QUALNAMES = frozenset({'infrafunction_subproc'})
STOCK_SLOT_QUALNAMES = STOCK_PROCESS_SLOT_QUALNAMES | STOCK_INFRAFUNCTION_SLOT_QUALNAMES


def is_stock_function_callable(obj) -> bool:
    """True if ``obj`` is a stock Process/InfraFunction Order-slot callable."""
    if not isinstance(obj, types.FunctionType):
        return False
    qualname = getattr(obj, '__qualname__', None)
    module = getattr(obj, '__module__', None) or ''
    if qualname not in STOCK_SLOT_QUALNAMES:
        return False
    if qualname in STOCK_PROCESS_SLOT_QUALNAMES:
        return module == 'data.input.function.process' or module.startswith(
            'data.input.function.process.'
        )
    return module == 'data.input.function.infrafunction' or module.startswith(
        'data.input.function.infrafunction.'
    )


def named_bind_payload(source_cid: str, module: str, qualname: str) -> dict:
    return {
        'source_cid': source_cid,
        'module': module,
        'qualname': qualname,
    }


def parse_named_bind_leaf(raw: bytes):
    """Return named-bind dict if ``raw`` is named-bind JSON, else ``None``."""
    try:
        text = raw.decode('utf-8')
        spec = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(spec, dict):
        return None
    if not all(k in spec for k in ('source_cid', 'module', 'qualname')):
        return None
    if not all(isinstance(spec[k], str) and spec[k] for k in (
        'source_cid', 'module', 'qualname',
    )):
        return None
    return spec


def resolve_function_package_dirs(structure_filepath):
    """Return ``{process, infrafunction}`` paths beside Structure under ``function/``.

    ``structure_filepath`` is ``…/input/structure`` → packages live at
    ``…/input/function/{process,infrafunction}``.
    """
    structure_filepath = structure_filepath.rstrip('/')
    function_home = os.path.join(os.path.dirname(structure_filepath), 'function')
    paths = {
        name: os.path.join(function_home, name) for name in FUNCTION_PACKAGE_NAMES
    }
    missing = [name for name, path in paths.items() if not os.path.isdir(path)]
    if missing:
        raise FileNotFoundError(
            'Function source packages missing under '
            f'{function_home!r}; missing: {missing}'
        )
    return paths


def stage_function_package(package_dir, staging_parent=None, *, basename=None):
    """Copy a Function package tree excluding ``__pycache__`` / ``*.pyc``.

    Returns the staging directory path (basename matches the package name)
    for ``cidDir``. Caller must remove the parent temp tree when finished if
    ``staging_parent`` was not supplied.
    """
    package_dir = package_dir.rstrip('/')
    if basename is None:
        basename = os.path.basename(package_dir)
    if staging_parent is None:
        staging_parent = tempfile.mkdtemp(prefix='cats-function-pkg-')
    staging_dir = os.path.join(staging_parent, basename)
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)

    def _ignore(directory, names):
        ignored = set()
        for name in names:
            if name == '__pycache__' or name.endswith('.pyc'):
                ignored.add(name)
        return ignored

    shutil.copytree(package_dir, staging_dir, ignore=_ignore)
    return staging_dir


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

    def _rebuild_function_cid(
            self,
            prev_function,
            *,
            ingress_subproc=None,
            integrated_subproc=None,
            egress_subproc=None,
            integration_cache_subproc=None,
            infrafunction_subproc=None,
    ):
        """Rebuild function_cid from prior pairing + optional slot replacements."""
        process_source_cid = prev_function.get('process_source_cid')
        infrafunction_source_cid = prev_function.get('infrafunction_source_cid')
        if not process_source_cid or not infrafunction_source_cid:
            raise RuntimeError(
                'function_cid is missing process_source_cid / '
                'infrafunction_source_cid; recreate the Order with '
                'create_order_request after hybrid Function source CIDs.'
            )
        prev_process = json.loads(self.cat(prev_function['process_cid']))
        prev_infrafunction = json.loads(self.cat(prev_function['infrafunction_cid']))

        process = {}
        if ingress_subproc is not None:
            process['ingress_subproc_cid'] = self.bind_subproc(
                ingress_subproc, process_source_cid
            )
        else:
            process['ingress_subproc_cid'] = prev_process['ingress_subproc_cid']
        if integrated_subproc is not None:
            process['integrated_subproc_cid'] = self.bind_subproc(
                integrated_subproc, process_source_cid
            )
        else:
            process['integrated_subproc_cid'] = prev_process['integrated_subproc_cid']
        if egress_subproc is not None:
            process['egress_subproc_cid'] = self.bind_subproc(
                egress_subproc, process_source_cid
            )
        else:
            process['egress_subproc_cid'] = prev_process['egress_subproc_cid']
        if integration_cache_subproc is not None:
            process['integration_cache_subproc_cid'] = self.bind_subproc(
                integration_cache_subproc, process_source_cid
            )
        else:
            process['integration_cache_subproc_cid'] = prev_process[
                'integration_cache_subproc_cid'
            ]

        infrafunction = {}
        if infrafunction_subproc is not None:
            infrafunction['infrafunction_subproc_cid'] = self.bind_subproc(
                infrafunction_subproc, infrafunction_source_cid
            )
        else:
            infrafunction['infrafunction_subproc_cid'] = prev_infrafunction[
                'infrafunction_subproc_cid'
            ]

        return self.ipfsClient.add_str(json.dumps({
            'process_cid': self.ipfsClient.add_str(json.dumps(process)),
            'infrafunction_cid': self.ipfsClient.add_str(json.dumps(infrafunction)),
            'process_source_cid': process_source_cid,
            'infrafunction_source_cid': infrafunction_source_cid,
        }))

    def _resolve_structure_pairing(
            self,
            prev_structure,
            *,
            structure_filepath=None,
            root_cid=None,
            plant_cid=None,
            infrastructure_cid=None,
            require_change_request=True,
    ):
        """Resolve a new Structure pairing; fail if unchanged when requested."""
        for key in ('root_cid', 'plant_cid', 'infrastructure_cid'):
            if not prev_structure.get(key):
                raise RuntimeError(
                    f'prior structure_cid is missing {key}; recreate the Order '
                    'with create_order_request after apply-complete Structure '
                    'pairing ({root_cid, plant_cid, infrastructure_cid}).'
                )

        if require_change_request and structure_filepath is None and all(
            v is None for v in (root_cid, plant_cid, infrastructure_cid)
        ):
            raise RuntimeError(
                'structure mutation requires structure_filepath and/or at least '
                'one of root_cid, plant_cid, infrastructure_cid'
            )

        pairing = {
            'root_cid': prev_structure['root_cid'],
            'plant_cid': prev_structure['plant_cid'],
            'infrastructure_cid': prev_structure['infrastructure_cid'],
        }
        if structure_filepath is not None:
            pairing = self.cid_structure_pairing(structure_filepath)
        if root_cid is not None:
            pairing['root_cid'] = root_cid
        if plant_cid is not None:
            pairing['plant_cid'] = plant_cid
        if infrastructure_cid is not None:
            pairing['infrastructure_cid'] = infrastructure_cid

        if pairing == {
            'root_cid': prev_structure['root_cid'],
            'plant_cid': prev_structure['plant_cid'],
            'infrastructure_cid': prev_structure['infrastructure_cid'],
        }:
            raise RuntimeError(
                'structure mutation produced an unchanged structure pairing; '
                'pass a different structure_filepath or nested CID override'
            )
        return pairing

    def _order_request_from_prior(
            self,
            order,
            *,
            function_cid,
            structure_cid,
            data_cid,
            structure_filepath=None,
    ):
        """Mint Invoice + order_request from a prior Order shell."""
        input_invoice = {'data_cid': data_cid}
        prev_invoice_cid = self.ipfsClient.add_str(json.dumps(input_invoice))
        order = deepcopy(order)
        order.pop('flat', None)
        order['function_cid'] = function_cid
        order['structure_cid'] = structure_cid
        order['invoice_cid'] = prev_invoice_cid
        if structure_filepath is not None:
            order['structure_filepath'] = structure_filepath
        order['endpoint'] = _node_init_endpoint()
        return {'order_cid': self.ipfsClient.add_str(json.dumps(order))}

    def linkProcess(
            self,
            cat_response,
            ingress_subproc=None,
            integrated_subproc=None,
            egress_subproc=None,
            integration_cache_subproc=None,
            infrafunction_subproc=None
    ):
        """Rebuild Order function_cid; carry structure_cid and Invoice data_cid."""
        flattened_bom = self.flatten_bom(cat_response)
        flat_bom = deepcopy(flattened_bom['flat_bom'])
        invoice = flat_bom['invoice']
        order = invoice['order']
        prev_function = order['flat']['function']
        new_function_cid = self._rebuild_function_cid(
            prev_function,
            ingress_subproc=ingress_subproc,
            integrated_subproc=integrated_subproc,
            egress_subproc=egress_subproc,
            integration_cache_subproc=integration_cache_subproc,
            infrafunction_subproc=infrafunction_subproc,
        )
        return self._order_request_from_prior(
            order,
            function_cid=new_function_cid,
            structure_cid=order['structure_cid'],
            data_cid=invoice['data_cid'],
        )

    def linkStructure(
            self,
            cat_response,
            *,
            structure_filepath=None,
            root_cid=None,
            plant_cid=None,
            infrastructure_cid=None,
            structure_filepath_name=None,
    ):
        """Rebuild Order structure_cid; carry function_cid and Invoice data_cid.

        Structure twin of ``linkProcess``. Provide ``structure_filepath`` to
        re-CID root/plant/infra from disk, and/or override individual nested
        CIDs. Fails if the resulting pairing is unchanged.
        """
        flattened_bom = self.flatten_bom(cat_response)
        flat_bom = deepcopy(flattened_bom['flat_bom'])
        invoice = flat_bom['invoice']
        order = invoice['order']
        prev_structure = order['flat']['structure']
        pairing = self._resolve_structure_pairing(
            prev_structure,
            structure_filepath=structure_filepath,
            root_cid=root_cid,
            plant_cid=plant_cid,
            infrastructure_cid=infrastructure_cid,
            require_change_request=True,
        )
        new_structure_cid = self.ipfsClient.add_str(json.dumps(pairing))

        if structure_filepath_name is not None:
            structure_name = structure_filepath_name
        elif structure_filepath is not None:
            structure_name = os.path.basename(structure_filepath.rstrip('/'))
        else:
            structure_name = order['structure_filepath']

        return self._order_request_from_prior(
            order,
            function_cid=order['function_cid'],
            structure_cid=new_structure_cid,
            data_cid=invoice['data_cid'],
            structure_filepath=structure_name,
        )

    def linkOrder(
            self,
            cat_response,
            *,
            ingress_subproc=None,
            integrated_subproc=None,
            egress_subproc=None,
            integration_cache_subproc=None,
            infrafunction_subproc=None,
            structure_filepath=None,
            root_cid=None,
            plant_cid=None,
            infrastructure_cid=None,
            structure_filepath_name=None,
    ):
        """Rebuild Function and/or Structure in one lineage step.

        A-la-carte ``linkProcess`` / ``linkStructure`` remain for single-sided
        mutations. Fails if neither side requests a change.
        """
        function_kwargs = {
            'ingress_subproc': ingress_subproc,
            'integrated_subproc': integrated_subproc,
            'egress_subproc': egress_subproc,
            'integration_cache_subproc': integration_cache_subproc,
            'infrafunction_subproc': infrafunction_subproc,
        }
        structure_requested = (
            structure_filepath is not None
            or root_cid is not None
            or plant_cid is not None
            or infrastructure_cid is not None
        )
        function_requested = any(v is not None for v in function_kwargs.values())
        if not function_requested and not structure_requested:
            raise RuntimeError(
                'linkOrder requires a Function slot change and/or a Structure '
                'mutation (structure_filepath or nested CID override)'
            )

        flattened_bom = self.flatten_bom(cat_response)
        flat_bom = deepcopy(flattened_bom['flat_bom'])
        invoice = flat_bom['invoice']
        order = invoice['order']

        function_cid = order['function_cid']
        if function_requested:
            function_cid = self._rebuild_function_cid(
                order['flat']['function'], **function_kwargs
            )

        structure_cid = order['structure_cid']
        structure_name = None
        if structure_requested:
            pairing = self._resolve_structure_pairing(
                order['flat']['structure'],
                structure_filepath=structure_filepath,
                root_cid=root_cid,
                plant_cid=plant_cid,
                infrastructure_cid=infrastructure_cid,
                require_change_request=True,
            )
            structure_cid = self.ipfsClient.add_str(json.dumps(pairing))
            if structure_filepath_name is not None:
                structure_name = structure_filepath_name
            elif structure_filepath is not None:
                structure_name = os.path.basename(structure_filepath.rstrip('/'))
            else:
                structure_name = order['structure_filepath']

        return self._order_request_from_prior(
            order,
            function_cid=function_cid,
            structure_cid=structure_cid,
            data_cid=invoice['data_cid'],
            structure_filepath=structure_name,
        )

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
        pairing = self.cid_structure_pairing(structure_filepath)
        structure_cid = self.ipfsClient.add_str(json.dumps(pairing))
        data_cid, dir_name = self.cidDir(data_dirpath)
        # Function source packages (directory CIDs) — sibling of structure/
        # under input/function/{process,infrafunction}. Stock callables bind
        # by name into those packages; non-stock still pickle.
        package_dirs = resolve_function_package_dirs(structure_filepath)
        staging_parent = tempfile.mkdtemp(prefix='cats-function-src-')
        try:
            process_staging = stage_function_package(
                package_dirs['process'],
                staging_parent=staging_parent,
                basename='process',
            )
            infrafunction_staging = stage_function_package(
                package_dirs['infrafunction'],
                staging_parent=staging_parent,
                basename='infrafunction',
            )
            process_source_cid, _ = self.cidDir(process_staging)
            infrafunction_source_cid, _ = self.cidDir(infrafunction_staging)
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
        # Process [REPL(aC)]: composes transport callables (ingress,
        # integration_cache, egress) plus the tHOF (integrated_subproc —
        # input→output data transform). Process is the composer, not a tHOF.
        process = {
            'ingress_subproc_cid': self.bind_subproc(
                ingress_subproc, process_source_cid
            ),
            'integrated_subproc_cid': self.bind_subproc(
                integrated_subproc, process_source_cid
            ),
            'egress_subproc_cid': self.bind_subproc(
                egress_subproc, process_source_cid
            ),
            'integration_cache_subproc_cid': self.bind_subproc(
                integration_cache_subproc, process_source_cid
            ),
        }
        # InfraFunction (FaaS): actuator that dispatches the tHOF
        # (integrated_subproc) onto the Plant (see Processor.Integration() in
        # cats/executor/function/__init__.py). Transport callables are not
        # Plant jobs.
        infrafunction = {
            'infrafunction_subproc_cid': self.bind_subproc(
                infrafunction_subproc, infrafunction_source_cid
            ),
        }
        function = {
            'process_cid': self.ipfsClient.add_str(json.dumps(process)),
            'infrafunction_cid': self.ipfsClient.add_str(json.dumps(infrafunction)),
            'process_source_cid': process_source_cid,
            'infrafunction_source_cid': infrafunction_source_cid,
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

    def add_named_bind(self, source_cid: str, module: str, qualname: str) -> str:
        """CID a named-bind JSON leaf for an Order slot."""
        self.ensure_bootstrap_content_store()
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

    def createInvoice(self, orderCID: str, dataCID: str, seedCID: str):
        invoice = {'orderCID': orderCID, 'dataCID': dataCID, 'seedCID': seedCID}
        invoice_cid = self.ipfsClient.add_json(invoice)
        return invoice_cid
