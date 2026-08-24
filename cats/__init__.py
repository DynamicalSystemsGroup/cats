import os
from os.path import dirname, abspath
from pathlib import Path

from dotenv import load_dotenv

# Repo root (sibling of this package). Load operator/secrets from `.env`
# here so Node, Marimo, and `uv run` share one file regardless of cwd.
# Existing shell environment wins (override=False).
CATS_HOME = dirname(dirname(abspath(__file__)))
try:
    load_dotenv(Path(CATS_HOME) / '.env')
except OSError:
    pass

from cats.network import ContentMesh
from cats.runtime import Runtime

CWD = os.getcwd()
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
