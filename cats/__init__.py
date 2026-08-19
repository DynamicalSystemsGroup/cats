import os
from os.path import dirname, abspath

from cats.network import ContentMesh
from cats.runtime import Runtime

CWD = os.getcwd()
CATS_HOME = dirname(dirname(abspath(__file__)))
# CAS-only Node (§6r/§6s): no CatsIPFSClient — legacy CID read retired.
CONTENT_MESH = ContentMesh(
    ipfsClient=None,
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
