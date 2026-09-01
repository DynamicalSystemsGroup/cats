"""Order compose and lineage ops mixed into ContentMesh."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from copy import deepcopy

from cats.network.cas import (
    LocatorIndex,
    is_hl,
    is_http_uri,
    is_ni_or_digest,
    ref_id,
    ref_uri,
    resolve_intake_ref,
    set_ref,
)
from cats.network.ldp import BomLdpStore, fetch_bom_envelope
from cats.network.node_http import _node_init_endpoint
from cats.network.packaging import (
    resolve_function_package_dirs,
    stage_function_package,
)
from cats.network.registry import AmbiguousBomError, BomRegistry, RegistryError


class OrderOps:
    """Mixin for ContentMesh: create_order_request + linkProcess/Structure/Order."""

    def _cats_home(self):
        return getattr(self, 'CATS_HOME', None)

    def _stem_id(self, obj, stem):
        """Equality id from ``*_uri`` or legacy ``*_cid``."""
        return ref_id(obj, stem, cats_home=self._cats_home())

    def _invoice_order_from_flat_bom(self, flat_bom):
        """Invoice + Order from ``flatten_bom`` (``invoice.flat.order``)."""
        invoice = flat_bom.get('invoice')
        if not isinstance(invoice, dict):
            raise RuntimeError('flatten_bom missing invoice')
        order = (invoice.get('flat') or {}).get('order')
        if not isinstance(order, dict):
            raise RuntimeError(
                'flatten_bom invoice.flat.order missing; increase max_depth'
            )
        return invoice, order

    def _cat_stem(self, obj, stem):
        """Fetch JSON for a stem via ``*_uri`` or equality id (AddressStore)."""
        locator = ref_uri(obj, stem) or self._stem_id(obj, stem)
        if not locator:
            raise RuntimeError(f'missing {stem}_uri / {stem}_cid on object')
        return json.loads(self.cat(locator))

    def _reject_legacy_link_kwargs(self, kwargs):
        bad = [k for k in ('bom_cid', 'data_cid') if k in kwargs and kwargs[k] is not None]
        if bad:
            raise RuntimeError(
                f'{", ".join(bad)} no longer accepted; use content_id, data_uri, '
                'or bom_uri / bom_ldp_uri / bom_solid_uri'
            )

    def _response_from_registry(
            self,
            *,
            content_id: str | None = None,
            data_uri: str | None = None,
            bom_uri: str | None = None,
            bom_ldp_uri: str | None = None,
            bom_solid_uri: str | None = None,
            hl: str | None = None,
            **kwargs,
    ):
        """Load a BOM response shell from the Node-local registry + LDP cache.

        Intake: ``content_id`` / ``hl`` (data equality → by-data), ``data_uri``,
        or ``bom_uri`` / ``bom_ldp_uri`` / ``bom_solid_uri``. Values may be
        ``hl:``, ``ni:``, or ``http(s)://``. Legacy ``bom_cid`` / ``data_cid``
        kwargs are rejected.
        """
        self._reject_legacy_link_kwargs(kwargs)
        bom_locator = bom_uri or bom_ldp_uri or bom_solid_uri
        if (
            content_id is None
            and hl is None
            and data_uri is None
            and bom_locator is None
        ):
            raise RuntimeError(
                'content_id, hl, data_uri, or bom_uri required when '
                'cat_response is omitted'
            )

        cats_home = self._cats_home()
        bom_id = None
        data_id = content_id or hl

        def _resolve(value: str, *, label: str) -> str:
            if not (
                is_hl(value)
                or is_http_uri(value)
                or is_ni_or_digest(value)
            ):
                raise RuntimeError(f'invalid {label}={value!r}')
            try:
                found = resolve_intake_ref(value, cats_home=cats_home)
            except ValueError as exc:
                raise RuntimeError(f'invalid {label}={value!r}') from exc
            if found is None:
                raise RuntimeError(f'no content id for {label}={value!r}')
            return found

        if bom_locator is not None:
            # Explicit BOM locator always wins (same preference as prior bom_cid).
            data_id = None
            data_uri = None
            bom_id = _resolve(bom_locator, label='bom_uri')

        if data_uri and not data_id:
            data_id = _resolve(data_uri, label='data_uri')

        if data_id and (is_hl(data_id) or is_http_uri(data_id)):
            data_id = _resolve(data_id, label='content_id')

        registry = BomRegistry(self.CATS_HOME)
        if bom_id is None:
            try:
                bom_id = registry.resolve_unique_bom(data_id)
            except AmbiguousBomError:
                raise
            except RegistryError as exc:
                raise RuntimeError(str(exc)) from exc

        record = registry.get(bom_id)
        if record is None:
            raise RuntimeError(f'no registry record for content_id={bom_id!r}')

        bom = BomLdpStore(self.CATS_HOME).get(bom_id)
        if bom is None:
            locators = record.get('locators') or {}
            uri = locators.get('bom_ldp_uri') or locators.get('bom_solid_uri')
            if not uri:
                raise RuntimeError(
                    f'BOM envelope not in local LDP store and no locator for '
                    f'content_id={bom_id!r}'
                )
            bom = fetch_bom_envelope(uri)

        locators = record.get('locators') or {}
        return {
            'bom': bom,
            'content_id': bom_id,
            'bom_ldp_uri': locators.get('bom_ldp_uri'),
            'bom_solid_uri': locators.get('bom_solid_uri'),
        }

    def _cat_response_for_link(
            self,
            cat_response=None,
            *,
            content_id: str | None = None,
            data_uri: str | None = None,
            bom_uri: str | None = None,
            bom_ldp_uri: str | None = None,
            bom_solid_uri: str | None = None,
            hl: str | None = None,
            **kwargs,
    ):
        self._reject_legacy_link_kwargs(kwargs)
        if cat_response is not None:
            return cat_response
        return self._response_from_registry(
            content_id=content_id,
            data_uri=data_uri,
            bom_uri=bom_uri,
            bom_ldp_uri=bom_ldp_uri,
            bom_solid_uri=bom_solid_uri,
            hl=hl,
        )

    def _rebuild_function(
            self,
            prev_function,
            *,
            ingress_subproc=None,
            integrated_subproc=None,
            egress_subproc=None,
            integration_cache_subproc=None,
            infrafunction_subproc=None,
    ):
        """Rebuild function pairing from prior + optional slot replacements.

        Emits uri-only Function / Process / InfraFunction JSON (no ``*_cid``).
        """
        cats_home = self._cats_home()
        process_source_id = ref_id(
            prev_function, 'process_source', cats_home=cats_home
        )
        infrafunction_source_id = ref_id(
            prev_function, 'infrafunction_source', cats_home=cats_home
        )
        if not process_source_id or not infrafunction_source_id:
            raise RuntimeError(
                'function pairing is missing process_source_cid / '
                'infrafunction_source_cid (or *_uri); recreate the Order with '
                'create_order_request after hybrid Function source CIDs.'
            )
        prev_process = self._cat_stem(prev_function, 'process')
        prev_infrafunction = self._cat_stem(prev_function, 'infrafunction')

        process = {}
        slot_specs = (
            ('ingress_subproc', ingress_subproc, process_source_id),
            ('integrated_subproc', integrated_subproc, process_source_id),
            ('egress_subproc', egress_subproc, process_source_id),
            (
                'integration_cache_subproc',
                integration_cache_subproc,
                process_source_id,
            ),
        )
        for stem, replacement, source_id in slot_specs:
            if replacement is not None:
                set_ref(process, stem, self.bind_subproc(replacement, source_id))
            else:
                prior = ref_id(prev_process, stem, cats_home=cats_home)
                if not prior:
                    raise RuntimeError(
                        f'prior process pairing is missing {stem}_uri / '
                        f'{stem}_cid'
                    )
                set_ref(process, stem, prior)

        infrafunction = {}
        if infrafunction_subproc is not None:
            set_ref(
                infrafunction,
                'infrafunction_subproc',
                self.bind_subproc(infrafunction_subproc, infrafunction_source_id),
            )
        else:
            prior = ref_id(
                prev_infrafunction, 'infrafunction_subproc', cats_home=cats_home
            )
            if not prior:
                raise RuntimeError(
                    'prior infrafunction pairing is missing '
                    'infrafunction_subproc_uri / infrafunction_subproc_cid'
                )
            set_ref(infrafunction, 'infrafunction_subproc', prior)

        function = {}
        set_ref(function, 'process', self.put_json(process))
        set_ref(function, 'infrafunction', self.put_json(infrafunction))
        set_ref(function, 'process_source', process_source_id)
        set_ref(function, 'infrafunction_source', infrafunction_source_id)
        return self.put_json(function)

    def _resolve_structure_pairing(
            self,
            prev_structure,
            *,
            structure_filepath=None,
            root_id=None,
            plant_id=None,
            infrastructure_id=None,
            require_change_request=True,
    ):
        """Resolve a new Structure pairing; fail if unchanged when requested.

        Parameter names ``root_id`` / ``plant_id`` / ``infrastructure_id``
        are content-id overrides (values are ``ni:`` / CID). Minted JSON
        uses ``root_uri`` / ``plant_uri`` / ``infrastructure_uri`` only.
        """
        cats_home = self._cats_home()
        prev_ids = {}
        for stem in ('root', 'plant', 'infrastructure'):
            value = ref_id(prev_structure, stem, cats_home=cats_home)
            if not value:
                raise RuntimeError(
                    f'prior structure_cid is missing {stem}_cid / {stem}_uri; '
                    'recreate the Order with create_order_request after '
                    'apply-complete Structure pairing '
                    '({root_uri, plant_uri, infrastructure_uri}).'
                )
            prev_ids[stem] = value

        if require_change_request and structure_filepath is None and all(
            v is None for v in (root_id, plant_id, infrastructure_id)
        ):
            raise RuntimeError(
                'structure mutation requires structure_filepath and/or at least '
                'one of root_id, plant_id, infrastructure_id'
            )

        if structure_filepath is not None:
            pairing = self.structure_pairing(structure_filepath)
        else:
            pairing = {}
            set_ref(pairing, 'root', prev_ids['root'])
            set_ref(pairing, 'plant', prev_ids['plant'])
            set_ref(pairing, 'infrastructure', prev_ids['infrastructure'])

        # Convert any legacy *_cid keys from structure_pairing into uri-only.
        for stem in ('root', 'plant', 'infrastructure'):
            current = ref_id(pairing, stem, cats_home=cats_home)
            if current:
                set_ref(pairing, stem, current)

        if root_id is not None:
            set_ref(pairing, 'root', root_id)
        if plant_id is not None:
            set_ref(pairing, 'plant', plant_id)
        if infrastructure_id is not None:
            set_ref(pairing, 'infrastructure', infrastructure_id)

        new_ids = {
            stem: ref_id(pairing, stem, cats_home=cats_home)
            for stem in ('root', 'plant', 'infrastructure')
        }
        if new_ids == prev_ids:
            raise RuntimeError(
                'structure mutation produced an unchanged structure pairing; '
                'pass a different structure_filepath or nested CID override'
            )
        return pairing

    def _order_request_from_prior(
            self,
            order,
            *,
            function_id,
            structure_id,
            data_id,
            structure_filepath=None,
    ):
        """Mint Invoice + order_request from a prior Order shell (uri-only JSON)."""
        from cats.network.ldp import (
            InvoiceLdpStore,
            OrderLdpStore,
            invoice_ldp_uri,
            order_ldp_uri,
        )

        invoice = {}
        set_ref(invoice, 'data', data_id)
        invoice_id = self.put_json(invoice)

        order = deepcopy(order)
        order.pop('flat', None)
        set_ref(order, 'function', function_id)
        set_ref(order, 'structure', structure_id)
        set_ref(order, 'invoice', invoice_id)
        if structure_filepath is not None:
            order['structure_filepath'] = structure_filepath
        order['endpoint'] = _node_init_endpoint()
        order_id = self.put_json(order)

        cats_home = self._cats_home()
        order_uri = None
        inv_uri = None
        if cats_home:
            InvoiceLdpStore(cats_home).put(invoice_id, invoice)
            OrderLdpStore(cats_home).put(order_id, order)
            loc = LocatorIndex(cats_home)
            inv_uri = invoice_ldp_uri(invoice_id)
            order_uri = order_ldp_uri(order_id)
            loc.put(invoice_id, uri=inv_uri, media_type='application/json')
            loc.put(order_id, uri=order_uri, media_type='application/json')

        return {
            'content_id': order_id,
            'order_uri': order_uri,
            'invoice_uri': inv_uri,
        }

    def linkProcess(
            self,
            cat_response=None,
            ingress_subproc=None,
            integrated_subproc=None,
            egress_subproc=None,
            integration_cache_subproc=None,
            infrafunction_subproc=None,
            *,
            content_id=None,
            data_uri=None,
            bom_uri=None,
            bom_ldp_uri=None,
            bom_solid_uri=None,
            hl=None,
            **kwargs,
    ):
        """Rebuild Order function pairing; carry structure and Invoice data refs."""
        cat_response = self._cat_response_for_link(
            cat_response,
            content_id=content_id,
            data_uri=data_uri,
            bom_uri=bom_uri,
            bom_ldp_uri=bom_ldp_uri,
            bom_solid_uri=bom_solid_uri,
            hl=hl,
            **kwargs,
        )
        flat_bom = deepcopy(self.flatten_bom(cat_response))
        invoice, order = self._invoice_order_from_flat_bom(flat_bom)
        prev_function = (order.get('flat') or {}).get('function')
        if prev_function is None:
            raise RuntimeError(
                'flatten_bom order.flat.function missing; increase max_depth'
            )
        new_function_id = self._rebuild_function(
            prev_function,
            ingress_subproc=ingress_subproc,
            integrated_subproc=integrated_subproc,
            egress_subproc=egress_subproc,
            integration_cache_subproc=integration_cache_subproc,
            infrafunction_subproc=infrafunction_subproc,
        )
        data_id = self._stem_id(invoice, 'data')
        structure_id = self._stem_id(order, 'structure')
        if not data_id or not structure_id:
            raise RuntimeError(
                'prior Invoice/Order missing data or structure ref '
                '(data_uri/data_cid, structure_uri/structure_cid)'
            )
        return self._order_request_from_prior(
            order,
            function_id=new_function_id,
            structure_id=structure_id,
            data_id=data_id,
        )

    def linkStructure(
            self,
            cat_response=None,
            *,
            structure_filepath=None,
            root_id=None,
            plant_id=None,
            infrastructure_id=None,
            structure_filepath_name=None,
            content_id=None,
            data_uri=None,
            bom_uri=None,
            bom_ldp_uri=None,
            bom_solid_uri=None,
            hl=None,
            **kwargs,
    ):
        """Rebuild Order structure pairing; carry function and Invoice data refs.

        Structure twin of ``linkProcess``. Provide ``structure_filepath`` to
        re-CID root/plant/infra from disk, and/or override individual nested
        content ids via ``root_id`` / ``plant_id`` / ``infrastructure_id``
        (Python API names; minted JSON uses ``*_uri`` only). Fails if the
        resulting pairing is unchanged.
        """
        cat_response = self._cat_response_for_link(
            cat_response,
            content_id=content_id,
            data_uri=data_uri,
            bom_uri=bom_uri,
            bom_ldp_uri=bom_ldp_uri,
            bom_solid_uri=bom_solid_uri,
            hl=hl,
            **kwargs,
        )
        flat_bom = deepcopy(self.flatten_bom(cat_response))
        invoice, order = self._invoice_order_from_flat_bom(flat_bom)
        prev_structure = (order.get('flat') or {}).get('structure')
        if prev_structure is None:
            raise RuntimeError(
                'flatten_bom order.flat.structure missing; increase max_depth'
            )
        pairing = self._resolve_structure_pairing(
            prev_structure,
            structure_filepath=structure_filepath,
            root_id=root_id,
            plant_id=plant_id,
            infrastructure_id=infrastructure_id,
            require_change_request=True,
        )
        new_structure_id = self.put_json(pairing)

        if structure_filepath_name is not None:
            structure_name = structure_filepath_name
        elif structure_filepath is not None:
            structure_name = os.path.basename(structure_filepath.rstrip('/'))
        else:
            structure_name = order['structure_filepath']

        data_id = self._stem_id(invoice, 'data')
        function_id = self._stem_id(order, 'function')
        if not data_id or not function_id:
            raise RuntimeError(
                'prior Invoice/Order missing data or function ref '
                '(data_uri/data_cid, function_uri/function_cid)'
            )
        return self._order_request_from_prior(
            order,
            function_id=function_id,
            structure_id=new_structure_id,
            data_id=data_id,
            structure_filepath=structure_name,
        )

    def linkOrder(
            self,
            cat_response=None,
            *,
            ingress_subproc=None,
            integrated_subproc=None,
            egress_subproc=None,
            integration_cache_subproc=None,
            infrafunction_subproc=None,
            structure_filepath=None,
            root_id=None,
            plant_id=None,
            infrastructure_id=None,
            structure_filepath_name=None,
            content_id=None,
            data_uri=None,
            bom_uri=None,
            bom_ldp_uri=None,
            bom_solid_uri=None,
            hl=None,
            **kwargs,
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
            or root_id is not None
            or plant_id is not None
            or infrastructure_id is not None
        )
        function_requested = any(v is not None for v in function_kwargs.values())
        if not function_requested and not structure_requested:
            raise RuntimeError(
                'linkOrder requires a Function slot change and/or a Structure '
                'mutation (structure_filepath or nested CID override)'
            )

        cat_response = self._cat_response_for_link(
            cat_response,
            content_id=content_id,
            data_uri=data_uri,
            bom_uri=bom_uri,
            bom_ldp_uri=bom_ldp_uri,
            bom_solid_uri=bom_solid_uri,
            hl=hl,
            **kwargs,
        )
        flat_bom = deepcopy(self.flatten_bom(cat_response))
        invoice, order = self._invoice_order_from_flat_bom(flat_bom)
        order_flat = order.get('flat') or {}

        function_id = self._stem_id(order, 'function')
        if not function_id:
            raise RuntimeError(
                'prior Order missing function_uri / function_cid'
            )
        if function_requested:
            prev_function = order_flat.get('function')
            if prev_function is None:
                raise RuntimeError(
                    'flatten_bom order.flat.function missing; increase max_depth'
                )
            function_id = self._rebuild_function(
                prev_function, **function_kwargs
            )

        structure_id = self._stem_id(order, 'structure')
        if not structure_id:
            raise RuntimeError(
                'prior Order missing structure_uri / structure_cid'
            )
        structure_name = None
        if structure_requested:
            prev_structure = order_flat.get('structure')
            if prev_structure is None:
                raise RuntimeError(
                    'flatten_bom order.flat.structure missing; increase max_depth'
                )
            pairing = self._resolve_structure_pairing(
                prev_structure,
                structure_filepath=structure_filepath,
                root_id=root_id,
                plant_id=plant_id,
                infrastructure_id=infrastructure_id,
                require_change_request=True,
            )
            structure_id = self.put_json(pairing)
            if structure_filepath_name is not None:
                structure_name = structure_filepath_name
            elif structure_filepath is not None:
                structure_name = os.path.basename(structure_filepath.rstrip('/'))
            else:
                structure_name = order['structure_filepath']

        data_id = self._stem_id(invoice, 'data')
        if not data_id:
            raise RuntimeError('prior Invoice missing data_uri / data_cid')
        return self._order_request_from_prior(
            order,
            function_id=function_id,
            structure_id=structure_id,
            data_id=data_id,
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
        from cats.network.ldp import (
            InvoiceLdpStore,
            OrderLdpStore,
            invoice_ldp_uri,
            order_ldp_uri,
        )

        if endpoint is None:
            endpoint = _node_init_endpoint()
        self.ensure_bootstrap_content_store()
        structure_name = os.path.basename(structure_filepath.rstrip('/'))
        pairing = self.structure_pairing(structure_filepath)
        # Ensure uri-only Structure pairing (convert any legacy *_cid keys).
        for stem in ('root', 'plant', 'infrastructure'):
            current = ref_id(pairing, stem, cats_home=self._cats_home())
            if current:
                set_ref(pairing, stem, current)
        structure_id = self.put_json(pairing)
        data_id, dir_name = self.put_dir(data_dirpath)
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
            process_source_id, _ = self.put_dir(process_staging)
            infrafunction_source_id, _ = self.put_dir(infrafunction_staging)
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
        # Process [Composed Function]: transport callables (ingress,
        # integration_cache, egress) plus the hotF (integrated_subproc —
        # input→output data transform). Process is the composition, not a hotF.
        process = {}
        set_ref(
            process,
            'ingress_subproc',
            self.bind_subproc(ingress_subproc, process_source_id),
        )
        set_ref(
            process,
            'integrated_subproc',
            self.bind_subproc(integrated_subproc, process_source_id),
        )
        set_ref(
            process,
            'egress_subproc',
            self.bind_subproc(egress_subproc, process_source_id),
        )
        set_ref(
            process,
            'integration_cache_subproc',
            self.bind_subproc(integration_cache_subproc, process_source_id),
        )
        # InfraFunction [Actuator]: dispatches the hotF (integrated_subproc)
        # onto the Plant (see Processor.Integration() in
        # cats/executor/function/__init__.py). Transport callables are not
        # Plant jobs.
        infrafunction = {}
        set_ref(
            infrafunction,
            'infrafunction_subproc',
            self.bind_subproc(infrafunction_subproc, infrafunction_source_id),
        )
        function = {}
        set_ref(function, 'process', self.put_json(process))
        set_ref(function, 'infrafunction', self.put_json(infrafunction))
        set_ref(function, 'process_source', process_source_id)
        set_ref(function, 'infrafunction_source', infrafunction_source_id)
        function_id = self.put_json(function)
        invoice = {}
        set_ref(invoice, 'data', data_id)
        invoice_id = self.put_json(invoice)
        order = {
            'structure_filepath': structure_name,
            'JOB_HOME': self.JOB_HOME,
            'endpoint': endpoint,
        }
        set_ref(order, 'function', function_id)
        set_ref(order, 'structure', structure_id)
        set_ref(order, 'invoice', invoice_id)
        order_id = self.put_json(order)
        # Phase 2b: publish Order/Invoice LDP URIs (address of record).
        cats_home = self._cats_home()
        order_uri = None
        inv_uri = None
        if cats_home:
            InvoiceLdpStore(cats_home).put(invoice_id, invoice)
            OrderLdpStore(cats_home).put(order_id, order)
            loc = LocatorIndex(cats_home)
            inv_uri = invoice_ldp_uri(invoice_id)
            order_uri = order_ldp_uri(order_id)
            loc.put(
                invoice_id,
                uri=inv_uri,
                media_type='application/json',
            )
            loc.put(
                order_id,
                uri=order_uri,
                media_type='application/json',
            )
        return {
            'content_id': order_id,
            'order_uri': order_uri,
            'invoice_uri': inv_uri,
        }
