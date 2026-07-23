"""Order compose and lineage ops mixed into ContentMesh."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from copy import deepcopy

from cats.network.node_http import _node_init_endpoint
from cats.network.packaging import (
    resolve_function_package_dirs,
    stage_function_package,
)


class OrderOps:
    """Mixin for ContentMesh: create_order_request + linkProcess/Structure/Order."""

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
