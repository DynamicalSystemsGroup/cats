# syntax=docker/dockerfile:1
# One-shot Executor image: load one Order, Factory → Executor.execute, sign BOM, exit.
# Function and Structure come from the Order; they are not baked in.
# The Flask peer is not this image — see docs/guide/NodeLifeCycle.md.
#
# Peer-less image (emits nothing): docker build -t cats-executor .

FROM python:3.12.5-slim AS runtime

WORKDIR /app

COPY pyproject.toml README.md ./
COPY cats ./cats

RUN pip install --no-cache-dir . \
    && mkdir -p /var/cats /result

# CATS_HOME is the writable runtime directory (parent of the installed package is /app).
# CAT_RESULT_DIR is outside that tree so a volume survives container teardown.
ENV PYTHONUNBUFFERED=1
ENV CAT_RESULT_DIR=/result

# No port published. Locator args (or ORDER_URI / CONTENT_ID / DATA_URI / BOM_URI / HL)
# are supplied at run time.
ENTRYPOINT ["python", "-m", "cats.executor.once"]

# Default target.
FROM runtime AS peerless
