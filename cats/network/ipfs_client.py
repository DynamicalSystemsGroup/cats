import pickle

import ipfshttpclient
from ipfshttpclient.requests_wrapper import HTTPAdapter
from urllib3 import PoolManager


# ipfshttpclient still passes strict=True (a Python 2 leftover) into
# urllib3.PoolManager; urllib3 2.x emits FutureWarning and will error in v3.
def _init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
    self._pool_connections = connections
    self._pool_maxsize = maxsize
    self._pool_block = block
    self.poolmanager = PoolManager(
        num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs
    )


HTTPAdapter.init_poolmanager = _init_poolmanager


def connect(host='127.0.0.1', port=5001, validate=False):
    addr = f'/ip4/{host}/tcp/{port}'
    if validate:
        client = ipfshttpclient.connect(addr)
    else:
        client = ipfshttpclient.Client(addr)
    return CatsIPFSClient(client)


class CatsIPFSClient:
    """ipfshttpclient wrapper with helpers previously provided by ipfsapi."""

    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        return getattr(self._client, name)

    def add_pyobj(self, py_obj, **kwargs):
        return self._client.add_bytes(pickle.dumps(py_obj), **kwargs)

    def post_upload(self, filepath, **kwargs):
        result = self._client.add(filepath, **kwargs)
        if isinstance(result, dict):
            return result['Hash']
        for attrs in result:
            return attrs['Hash']
        raise ValueError(f'Could not upload {filepath} to IPFS')
