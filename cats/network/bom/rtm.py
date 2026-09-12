"""Local Flexo RTM Dataset. Optional extra ``cats[rtm]`` (rdflib + pyshacl).

Do not import this module from Factory / Executor. ``walk_*`` and
``interrogate.rerun`` (BOM-only) need no extra. Dataset load / SHACL do.
"""
from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from cats.network.feedback.envelope import EXECUTOR_RUN_ID

GRAPH_IRIS = {
    'ontology': 'urn:cats:rtm:ontology',
    'structural': 'urn:cats:rtm:structural',
    'plan': 'urn:cats:rtm:plan',
    'plan-execution': 'urn:cats:rtm:plan-execution',
    'evidence': 'urn:cats:rtm:evidence',
    'attestations': 'urn:cats:rtm:attestations',
    'audit': 'urn:cats:rtm:audit',
}

CFL_STEPS = (
    'accept',
    'ingress',
    'hotF',
    'egress',
    'sign_execution_bom',
)

CATS_NS = 'https://cats.dynamicalsystemsgroup.com/ns#'
PPLAN_NS = 'http://purl.org/net/p-plan#'
PROV_NS = 'http://www.w3.org/ns/prov#'
EARL_NS = 'http://www.w3.org/ns/earl#'
DCT_NS = 'http://purl.org/dc/terms/'
DCAT_NS = 'http://www.w3.org/ns/dcat#'

_RTM_EXTRA = 'cats[rtm] extra required (rdflib, pyshacl)'

SHAPE_FILES = {
    'forward': 'forward.ttl',
    'backward': 'backward.ttl',
    'evidence': 'evidence.ttl',
    'provenance': 'provenance.ttl',
    'plan_instantiation': 'plan_instantiation.ttl',
}


def _require_rdflib():
    try:
        import rdflib
        from rdflib import Dataset, Graph, Literal, Namespace, URIRef
    except ImportError as exc:
        raise ImportError(_RTM_EXTRA) from exc
    return rdflib, Dataset, Graph, Literal, Namespace, URIRef


def _require_pyshacl():
    try:
        from pyshacl import validate
    except ImportError as exc:
        raise ImportError(_RTM_EXTRA) from exc
    return validate


def walk_forward(
    allocate_doc: dict[str, Any],
    *,
    order_dcat: dict[str, Any] | None = None,
    clause: str = 'egress',
) -> dict[str, Any]:
    """Requirement → implementation: clause → P5 target + Order cite."""
    edges = allocate_doc.get('cats:edges') or []
    suffix = f'#{clause}'
    edge = next(
        (
            item
            for item in edges
            if isinstance(item, dict)
            and isinstance(item.get('@id'), str)
            and item['@id'].endswith(suffix)
        ),
        None,
    )
    promised = None
    if isinstance(order_dcat, dict):
        promised = order_dcat.get('dct:conformsTo')
    return {
        'clause': (edge or {}).get('@id'),
        'target': (edge or {}).get('cats:allocatesTo'),
        'order_promised': promised,
    }


def walk_backward(
    allocate_doc: dict[str, Any],
    invoice_dcat: dict[str, Any],
    *,
    lot: str | None = None,
    clause: str = 'egress',
) -> dict[str, Any]:
    """Implementation → requirement: lot → contract @id → allocate inverse."""
    contract = invoice_dcat.get('dct:conformsTo') if isinstance(invoice_dcat, dict) else None
    suffix = f'#{clause}'
    clause_id = None
    for target in allocate_doc.get('cats:targets') or []:
        if not isinstance(target, dict):
            continue
        from_id = target.get('cats:allocatedFrom') or target.get('cats:clause')
        if isinstance(from_id, str) and from_id.endswith(suffix):
            clause_id = from_id
            break
    if clause_id is None and isinstance(contract, str):
        clause_id = f'{contract}#{clause}'
    lot_ni = lot
    if lot_ni is None and isinstance(invoice_dcat, dict):
        for dataset in invoice_dcat.get('dcat:dataset') or []:
            if not isinstance(dataset, dict):
                continue
            if dataset.get('dct:title') == 'egressed_data':
                ident = dataset.get('dct:identifier')
                if isinstance(ident, str):
                    lot_ni = ident
                break
    return {
        'lot': lot_ni,
        'contract': contract,
        'clause': clause_id,
    }


def _parse_jsonld(graph, doc: dict[str, Any]) -> None:
    payload = json.dumps(doc)
    graph.parse(data=payload, format='json-ld')


def _ontology_doc() -> dict[str, Any]:
    steps = [
        {
            '@id': f'urn:cats:rtm:step:{name}',
            '@type': 'p-plan:Step',
            'dct:title': name,
        }
        for name in CFL_STEPS
    ]
    return {
        '@context': {
            'rtm': 'https://cats.dynamicalsystemsgroup.com/ns/rtm#',
            'p-plan': PPLAN_NS,
            'prov': PROV_NS,
            'dct': DCT_NS,
            'cats': CATS_NS,
        },
        '@graph': [
            {'@id': f'{CATS_NS}allocatesTo', '@type': 'rdf:Property'},
            {'@id': f'{CATS_NS}allocatedFrom', '@type': 'rdf:Property'},
            {'@id': f'{PPLAN_NS}correspondsToStep', '@type': 'rdf:Property'},
            *steps,
        ],
    }


def _activity_iri() -> str:
    return f"{GRAPH_IRIS['plan-execution']}{EXECUTOR_RUN_ID}"


def _plan_execution_doc(bom: dict[str, Any]) -> dict[str, Any]:
    activity_iri = _activity_iri()
    steps = [
        {'@id': f'urn:cats:rtm:step:{name}'}
        for name in CFL_STEPS
    ]
    entities: list[dict[str, Any]] = []
    for entity in bom.get('stageLineage') or []:
        if not isinstance(entity, dict):
            continue
        node = {
            '@id': entity.get('@id') or entity.get('contentId'),
            '@type': 'prov:Entity',
            'prov:wasGeneratedBy': {'@id': activity_iri},
        }
        content_id = entity.get('contentId')
        if isinstance(content_id, str) and content_id.strip():
            node['cats:contentId'] = content_id
        derived = entity.get('prov:wasDerivedFrom')
        if isinstance(derived, dict) and derived.get('@id'):
            node['prov:wasDerivedFrom'] = {'@id': derived['@id']}
        if node.get('@id'):
            entities.append(node)
    return {
        '@context': {
            'prov': PROV_NS,
            'p-plan': PPLAN_NS,
            'cats': CATS_NS,
        },
        '@graph': [
            {
                '@id': activity_iri,
                '@type': 'prov:Activity',
                'p-plan:correspondsToStep': steps,
            },
            *entities,
        ],
    }


def _audit_syft_doc() -> dict[str, Any]:
    return {
        '@context': {
            'earl': EARL_NS,
            'rtm': 'https://cats.dynamicalsystemsgroup.com/ns/rtm#',
        },
        '@graph': [
            {
                '@id': 'urn:cats:rtm:audit:syft',
                '@type': 'earl:Assertion',
                'earl:test': {'@id': 'urn:cats:rtm:syft'},
                'earl:mode': {'@id': f'{EARL_NS}automatic'},
            }
        ],
    }


def _has_syft(runtime_sbom: dict[str, Any] | None) -> bool:
    if not isinstance(runtime_sbom, dict):
        return False
    if runtime_sbom.get('syft_uri'):
        return True
    nest = runtime_sbom.get('nest')
    if isinstance(nest, dict) and nest.get('syft_uri'):
        return True
    docs = runtime_sbom.get('documents')
    if isinstance(docs, dict) and docs.get('syft'):
        return True
    return False


def _as_uri(value: Any, URIRef):
    if isinstance(value, str) and value.strip():
        return URIRef(value.strip())
    return None


def _add_conforms_to(graph, catalog: dict[str, Any], URIRef) -> None:
    catalog_id = _as_uri(catalog.get('@id'), URIRef)
    conforms = _as_uri(catalog.get('dct:conformsTo'), URIRef)
    if catalog_id is None or conforms is None:
        return
    graph.add((catalog_id, URIRef(f'{DCT_NS}conformsTo'), conforms))


def _add_allocate_triples(graph, allocate_doc: dict[str, Any], URIRef) -> None:
    allocates = URIRef(f'{CATS_NS}allocatesTo')
    allocated_from = URIRef(f'{CATS_NS}allocatedFrom')
    clause_pred = URIRef(f'{CATS_NS}clause')
    for edge in allocate_doc.get('cats:edges') or []:
        if not isinstance(edge, dict):
            continue
        clause = _as_uri(edge.get('@id'), URIRef)
        target = _as_uri(edge.get('cats:allocatesTo'), URIRef)
        if clause is not None and target is not None:
            graph.add((clause, allocates, target))
    for target_doc in allocate_doc.get('cats:targets') or []:
        if not isinstance(target_doc, dict):
            continue
        target = _as_uri(target_doc.get('@id'), URIRef)
        clause = _as_uri(
            target_doc.get('cats:allocatedFrom') or target_doc.get('cats:clause'),
            URIRef,
        )
        if target is None or clause is None:
            continue
        graph.add((target, allocated_from, clause))
        graph.add((target, clause_pred, clause))


def load_rtm(
    *,
    sysml_doc: dict[str, Any] | None = None,
    allocate_doc: dict[str, Any] | None = None,
    contract_doc: dict[str, Any] | None = None,
    order_dcat: dict[str, Any] | None = None,
    invoice_dcat: dict[str, Any] | None = None,
    bom: dict[str, Any] | None = None,
    runtime_sbom: dict[str, Any] | None = None,
):
    """Parse joins + envelopes into the seven named graphs. Cite ``ni:`` only."""
    _rdflib, Dataset, Graph, _Literal, _Namespace, URIRef = _require_rdflib()
    dataset = Dataset()
    graphs = {name: dataset.graph(URIRef(iri)) for name, iri in GRAPH_IRIS.items()}
    _parse_jsonld(graphs['ontology'], _ontology_doc())
    if isinstance(contract_doc, dict):
        _parse_jsonld(graphs['ontology'], contract_doc)
    if isinstance(sysml_doc, dict):
        _parse_jsonld(graphs['structural'], sysml_doc)
    if isinstance(allocate_doc, dict):
        _parse_jsonld(graphs['structural'], allocate_doc)
        _add_allocate_triples(graphs['structural'], allocate_doc, URIRef)
    if isinstance(order_dcat, dict):
        _parse_jsonld(graphs['plan'], order_dcat)
        _add_conforms_to(graphs['plan'], order_dcat, URIRef)
    if isinstance(invoice_dcat, dict):
        _parse_jsonld(graphs['evidence'], invoice_dcat)
        _add_conforms_to(graphs['evidence'], invoice_dcat, URIRef)
    if isinstance(bom, dict):
        _parse_jsonld(graphs['plan-execution'], _plan_execution_doc(bom))
    if _has_syft(runtime_sbom):
        _parse_jsonld(graphs['audit'], _audit_syft_doc())
    return dataset


def copy_dataset(dataset):
    """Independent Dataset copy (named-fail cells mutate one join)."""
    _rdflib, Dataset, _Graph, _Literal, _Namespace, URIRef = _require_rdflib()
    out = Dataset()
    for name, iri in GRAPH_IRIS.items():
        dest = out.graph(URIRef(iri))
        for triple in dataset.graph(URIRef(iri)):
            dest.add(triple)
    return out


def drop_conforms_to(dataset, graph_name: str) -> None:
    """Remove ``dct:conformsTo`` triples from one named graph (in place)."""
    _rdflib, _Dataset, _Graph, _Literal, _Namespace, URIRef = _require_rdflib()
    graph = dataset.graph(URIRef(GRAPH_IRIS[graph_name]))
    predicate = URIRef(f'{DCT_NS}conformsTo')
    for triple in list(graph.triples((None, predicate, None))):
        graph.remove(triple)


def drop_allocate_inverse(dataset) -> None:
    """Remove allocate inverse triples so Backward cannot start at a port."""
    _rdflib, _Dataset, _Graph, _Literal, _Namespace, URIRef = _require_rdflib()
    graph = dataset.graph(URIRef(GRAPH_IRIS['structural']))
    for pred in (f'{CATS_NS}allocatedFrom', f'{CATS_NS}clause', f'{CATS_NS}allocatesTo'):
        predicate = URIRef(pred)
        for triple in list(graph.triples((None, predicate, None))):
            graph.remove(triple)


def union_graphs(dataset, names: tuple[str, ...]):
    _rdflib, _Dataset, Graph, _Literal, _Namespace, URIRef = _require_rdflib()
    out = Graph()
    for name in names:
        for triple in dataset.graph(URIRef(GRAPH_IRIS[name])):
            out.add(triple)
    return out


def _shape_graph(name: str):
    _rdflib, _Dataset, Graph, _Literal, _Namespace, _URIRef = _require_rdflib()
    filename = SHAPE_FILES[name]
    text = (files('cats.network.bom.shapes') / filename).read_text(encoding='utf-8')
    graph = Graph()
    graph.parse(data=text, format='turtle')
    return graph


def _validate(data_graph, shape_name: str) -> dict[str, Any]:
    validate = _require_pyshacl()
    conforms, results_graph, results_text = validate(
        data_graph,
        shacl_graph=_shape_graph(shape_name),
        inference='none',
        abort_on_first=False,
    )
    focus = None
    try:
        from rdflib.namespace import SH

        for subj in results_graph.subjects(SH.focusNode, None):
            focus = str(next(results_graph.objects(subj, SH.focusNode)))
            break
        if focus is None:
            for _s, _p, obj in results_graph.triples(
                (None, SH.focusNode, None)
            ):
                focus = str(obj)
                break
    except Exception:
        focus = None
    return {
        'conforms': bool(conforms),
        'shape': shape_name,
        'focus': focus,
        'text': results_text,
    }


def validate_forward(dataset) -> dict[str, Any]:
    """mBOM promise: clauses allocate and Order DCAT cites the contract."""
    data = union_graphs(dataset, ('ontology', 'structural', 'plan'))
    return _validate(data, 'forward')


def validate_backward(dataset) -> dict[str, Any]:
    """aBOM lot → Invoice cite → allocate inverse."""
    data = union_graphs(dataset, ('ontology', 'structural', 'evidence'))
    return _validate(data, 'backward')


def validate_named(dataset, name: str) -> dict[str, Any]:
    graphs = {
        'forward': ('ontology', 'structural', 'plan'),
        'backward': ('ontology', 'structural', 'evidence'),
        'evidence': ('evidence',),
        'provenance': ('plan-execution',),
        'plan_instantiation': ('plan-execution', 'ontology'),
    }
    data = union_graphs(dataset, graphs[name])
    return _validate(data, name)


def has_attestation(dataset) -> bool:
    _rdflib, _Dataset, _Graph, _Literal, _Namespace, URIRef = _require_rdflib()
    attestation = URIRef('https://cats.dynamicalsystemsgroup.com/ns/rtm#Attestation')
    rdf_type = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#type')
    for name in GRAPH_IRIS:
        for _s, _p, _o in dataset.graph(URIRef(GRAPH_IRIS[name])).triples(
            (None, rdf_type, attestation)
        ):
            return True
    return False


def has_earl_automatic(dataset) -> bool:
    _rdflib, _Dataset, _Graph, _Literal, _Namespace, URIRef = _require_rdflib()
    mode = URIRef(f'{EARL_NS}mode')
    automatic = URIRef(f'{EARL_NS}automatic')
    audit = dataset.graph(URIRef(GRAPH_IRIS['audit']))
    return any(audit.triples((None, mode, automatic)))


class interrogate:
    """Walk PROV / P-PLAN. Does not re-sign the BOM."""

    @staticmethod
    def rerun(bom: dict[str, Any], dataset: Any = None) -> list[str]:
        if not isinstance(bom, dict):
            return []
        activity = bom.get('prov:wasGeneratedBy')
        if not isinstance(activity, dict):
            return []
        if dataset is not None:
            names = interrogate._steps_from_dataset(dataset)
            if names:
                return names
        if activity.get('@id') == EXECUTOR_RUN_ID or activity.get('@type'):
            return list(CFL_STEPS)
        return []

    @staticmethod
    def _steps_from_dataset(dataset) -> list[str]:
        try:
            _rdflib, _Dataset, _Graph, _Literal, _Namespace, URIRef = _require_rdflib()
        except ImportError:
            return []
        pred = URIRef(f'{PPLAN_NS}correspondsToStep')
        found: set[str] = set()
        for name in ('plan-execution', 'ontology'):
            graph = dataset.graph(URIRef(GRAPH_IRIS[name]))
            for _s, _p, obj in graph.triples((None, pred, None)):
                token = str(obj)
                step = token.rsplit(':', 1)[-1]
                if step in CFL_STEPS:
                    found.add(step)
        return [step for step in CFL_STEPS if step in found]


def drop_order_conforms_copy(dataset):
    """Copy + drop plan ``dct:conformsTo`` (Forward-only fail)."""
    cloned = copy_dataset(dataset)
    drop_conforms_to(cloned, 'plan')
    return cloned


def break_backward_copy(dataset):
    """Copy + drop evidence cite and allocate inverse (Backward-only fail)."""
    cloned = copy_dataset(dataset)
    drop_conforms_to(cloned, 'evidence')
    drop_allocate_inverse(cloned)
    return cloned
