# Process [REPL(aC)] callables a Read-Eval-Print Loop as Code (e.g. cats_demo.py
# Marimo notebook) composes and submits:
#   - ingress / integration_cache / egress — transport *port* callables; they
#     receive a Function-owned TransportPort as `transport` and only call
#     migrate / stage_for_plant. Process does not own Docker/IPFS peers or
#     peering (Structure-owned T&D swarm connect). Executor narrows the
#     Order-submitted IaaS adapter via as_transport_port.
#   - process_0 / process_1 (Order slot: integrated_subproc) — the Transfer
#     Higher-Order Function (tHOF): input→output data transform via
#     ComputePort.run_transfer (Plant-agnostic). Ray Data orchestration lives
#     in Plant RayComputePort, wired by the Plant-owned job entrypoint.
# InfraFunction [FaaS] dispatches only the tHOF onto Plant [SaaS]; transport runs
# locally around that dispatch. Executor wires `transport` like object_store/plant.
#
# Port types are TYPE_CHECKING-only: Ray job workers unpickle this module by
# value and do not have the repo ``data`` package on sys.path.

from __future__ import annotations

from typing import TYPE_CHECKING, Dict

import numpy as np

if TYPE_CHECKING:
    from data.input.function.process.compute_port import ComputePort
    from data.input.function.process.transport_port import TransportPort


def ingress(input_dir_cid, transport: TransportPort):
    """Transport port: migrate invoice data CID via TransportPort.migrate."""
    return transport.migrate(input_dir_cid)


def egress(input_dir_cid, transport: TransportPort):
    """Transport port: migrate integration output CID; return CID only for Invoice."""
    cid, _ = transport.migrate(input_dir_cid)
    return cid


def integration_cache(input_dir_cid, cwd, transport: TransportPort, data_cache=None):
    """Transport port: stage ingress CID onto Plant-facing integration cache."""
    return transport.stage_for_plant(
        input_dir_cid, cwd=cwd, data_cache=data_cache
    )


def function_0(batch: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    vec_a = batch["petal length (cm)"].astype('double')
    vec_b = batch["petal width (cm)"].astype('double')
    batch["petal area (cm^2)"] = vec_a * vec_b
    return batch


def function_1(batch: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    vec_a = batch["petal length (cm)"].astype('double')
    vec_b = batch["petal width (cm)"].astype('double')
    batch["DUPLICATE petal area (cm^2)"] = vec_a * vec_b
    return batch


def process_0(input, compute: ComputePort):
    """tHOF: petal-area transfer via ComputePort (Ray adapter supplies Dataset)."""
    return compute.run_transfer(function_0, input, zip_with_range=True)


def process_1(input, compute: ComputePort):
    """tHOF: duplicate petal-area transfer via ComputePort."""
    return compute.run_transfer(function_1, input, zip_with_range=False)
