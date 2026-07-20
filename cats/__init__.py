import os
from os.path import dirname, abspath

from cats.network import MeshClient
from cats.network.clients.ipfs_client import connect as connect_ipfs
from cats.service import Service

CWD = os.getcwd()
CATS_HOME = dirname(dirname(abspath(__file__)))
MESH_CLIENT = MeshClient(
    ipfsClient=connect_ipfs(),
    CATS_HOME=CATS_HOME,
)
SERVICE = Service(
    meshClient=MESH_CLIENT,
    CATS_HOME=CATS_HOME
)
DATA_HOME = SERVICE.DATA_HOME
JOB_HOME = SERVICE.JOB_HOME
CACHE_HOME = SERVICE.CACHE_HOME
INPUT_STRUCTURE_HOME = SERVICE.INPUT_STRUCTURE_HOME
INPUT_DATA_HOME = SERVICE.INPUT_DATA_HOME
OUTPUT_DATA_HOME = SERVICE.OUTPUT_DATA_HOME
