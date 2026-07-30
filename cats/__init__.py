import os
from os.path import dirname, abspath

from cats.network import ContentMesh
from cats.network.clients.ipfs_client import connect as connect_ipfs
from cats.runtime import Runtime

CWD = os.getcwd()
CATS_HOME = dirname(dirname(abspath(__file__)))
CONTENT_MESH = ContentMesh(
    ipfsClient=connect_ipfs(),
    CATS_HOME=CATS_HOME,
)
RUNTIME = Runtime(
    contentMesh=CONTENT_MESH,
    CATS_HOME=CATS_HOME
)
DATA_HOME = RUNTIME.DATA_HOME
JOB_HOME = RUNTIME.JOB_HOME
CACHE_HOME = RUNTIME.CACHE_HOME
INPUT_STRUCTURE_HOME = RUNTIME.INPUT_STRUCTURE_HOME
INPUT_DATA_HOME = RUNTIME.INPUT_DATA_HOME
OUTPUT_DATA_HOME = RUNTIME.OUTPUT_DATA_HOME
