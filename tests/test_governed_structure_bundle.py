"""Governed Structure pairing: second tree, no secrets, sha256: spelling."""
import json
import re
from pathlib import Path
from unittest.mock import MagicMock

from cats.network import ContentMesh
from cats.network.cas import from_ni, set_ref

CATS_ROOT = Path(__file__).resolve().parents[1]
DEMO_STRUCTURE = CATS_ROOT / 'data' / 'input' / 'structure'
GOVERNED_STRUCTURE = CATS_ROOT / 'data' / 'input' / 'governed-structure'

_BOUND_NAMES = ('case', 'act', 'execution', 'expires_at')
_VARIABLE = re.compile(
    r'variable\s+"(?P<name>case|act|execution|expires_at)"\s*\{(?P<body>[^{}]*)\}',
    re.S,
)
_IDENT = re.compile(r'\b(?:case|act|execution|expires_at)\b')
_COMMENT = re.compile(r'#.*')
_SECRET = re.compile(
    r'kubeconfig|docker\.sock|'
    r'\b(?:credentials|password|secret|access_key|client_secret|private_key)\s*=',
    re.IGNORECASE,
)


def _client(tmp_path):
    return ContentMesh(ipfsClient=MagicMock(), CATS_HOME=str(tmp_path / 'cas'))


def _governed_sources():
    skip = {'.terraform'}
    for path in GOVERNED_STRUCTURE.rglob('*'):
        if not path.is_file() or skip.intersection(path.parts):
            continue
        yield path


def test_governed_pairing_differs_from_demo(tmp_path):
    """The governed tree mints a different pairing content id."""
    client = _client(tmp_path)
    demo = client.structure_pairing(str(DEMO_STRUCTURE))
    governed = client.structure_pairing(str(GOVERNED_STRUCTURE))
    demo_id = client.put_json(demo)
    governed_id = client.put_json(governed)
    assert demo_id.startswith('ni:///sha-256;')
    assert governed_id.startswith('ni:///sha-256;')
    assert governed_id != demo_id
    for stem in ('root_uri', 'plant_uri', 'infrastructure_uri'):
        assert governed[stem] != demo[stem]


def test_governed_tree_has_no_secrets_or_bound_literals():
    """No credentials, and case/act/execution/expires_at have no written values."""
    declared = set()
    for path in _governed_sources():
        text = path.read_text()
        assert _SECRET.search(text) is None, path
        for match in _VARIABLE.finditer(text):
            assert 'default' not in match.group('body'), path
            declared.add(match.group('name'))
        stripped = _VARIABLE.sub(' ', text)
        stripped = _COMMENT.sub('', stripped)
        stripped = re.sub(
            r'\bvar\.(?:case|act|execution|expires_at)\b',
            ' ',
            stripped,
        )
        stripped = re.sub(
            r'\b(?:case|act|execution|expires_at)\b(\s*=)',
            r' \1',
            stripped,
        )
        leftover = _IDENT.findall(stripped)
        assert leftover == [], (path, leftover)
    assert set(_BOUND_NAMES) == declared


def test_bundle_digest_round_trips_pairing_bytes(tmp_path):
    """sha256: plus from_ni is the same 32 bytes as the pairing content id."""
    client = _client(tmp_path)
    pairing = client.structure_pairing(str(GOVERNED_STRUCTURE))
    content_id = client.put_json(pairing)
    spelled = client.bundle_digest(content_id)
    hex_digest = spelled.removeprefix('sha256:')
    assert spelled == 'sha256:' + from_ni(content_id)
    raw = bytes.fromhex(hex_digest)
    assert raw == bytes.fromhex(from_ni(content_id))
    assert len(raw) == 32

    order = {}
    set_ref(order, 'structure', content_id)
    encoded = json.dumps(order)
    assert 'sha256:' not in encoded
    assert content_id.startswith('ni:///sha-256;')
