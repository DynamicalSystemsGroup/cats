# Process [Composed Function] callables (composed via the REPLaC Workflow UI of
# Function [FaaS] — this demo: Marimo / cats_demo.py):
#   - ingress / integration_cache / egress — transport *port* callables; they
#     receive a Function-owned TransportPort as `transport` and only call
#     migrate / stage_for_plant. When num_partitions > 1, ingress/egress also
#     take an IoPort (Plant-backed partitioned CAR I/O). Process does not own
#     Docker/IPFS peers or peering (Structure-owned T&D swarm connect).
#   - process_0 / process_1 (Order slot: integrated_subproc) — the Higher-Order
#     Transfer Function (hotF): input→output data transform via
#     ComputePort.run_transfer (Plant-agnostic). Ray Data orchestration lives
#     in Plant RayComputePort, wired by the Plant-owned job entrypoint.
# InfraFunction [Actuator] dispatches only the hotF onto Plant [SaaS]; transport
# runs locally around that dispatch. Executor wires `transport` like
# object_store/plant.
#
# Port types are TYPE_CHECKING-only: Ray job workers unpickle this module by
# value and do not have the repo ``data`` package on sys.path.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from data.input.function.process.compute_port import ComputePort
    from data.input.function.process.io_port import IoPort
    from data.input.function.process.transport_port import TransportPort


def ingress(
    input_dir_id,
    transport: TransportPort,
    *,
    io: IoPort | None = None,
    num_partitions: int = 1,
):
    """Transport / IoPort: migrate or partition-ingress invoice data id."""
    if num_partitions > 1 and io is not None:
        return io.partition_ingress(
            input_dir_id, num_partitions=num_partitions
        )
    return transport.migrate(input_dir_id)


def egress(
    input_dir_id,
    transport: TransportPort,
    *,
    io: IoPort | None = None,
    num_partitions: int = 1,
):
    """Transport / IoPort: migrate or partition-egress; return id for Invoice."""
    if num_partitions > 1 and io is not None:
        return io.partition_egress(
            input_dir_id, num_partitions=num_partitions
        )
    cid, _ = transport.migrate(input_dir_id)
    return cid


def integration_cache(input_dir_id, cwd, transport: TransportPort, data_cache=None):
    """Transport port: stage ingress id onto Plant-facing integration cache."""
    return transport.stage_for_plant(
        input_dir_id, cwd=cwd, data_cache=data_cache
    )


def function_0(batch: Dict[str, Any]) -> Dict[str, Any]:
    vec_a = batch["petal length (cm)"].astype('double')
    vec_b = batch["petal width (cm)"].astype('double')
    batch["petal area (cm^2)"] = vec_a * vec_b
    return batch


def function_1(batch: Dict[str, Any]) -> Dict[str, Any]:
    vec_a = batch["petal length (cm)"].astype('double')
    vec_b = batch["petal width (cm)"].astype('double')
    batch["DUPLICATE petal area (cm^2)"] = vec_a * vec_b
    return batch


def process_0(input, compute: ComputePort, *, num_partitions: int = 1):
    """hotF: petal-area transfer via ComputePort (Ray adapter supplies Dataset)."""
    return compute.run_transfer(
        function_0, input, zip_with_range=True, num_partitions=num_partitions
    )


def process_1(input, compute: ComputePort, *, num_partitions: int = 1):
    """hotF: duplicate petal-area transfer via ComputePort."""
    return compute.run_transfer(
        function_1, input, zip_with_range=False, num_partitions=num_partitions
    )
