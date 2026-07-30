"""Flask Node URL helpers and submit-wait UX."""
import contextlib
import itertools
import os
import sys
import threading
import time

def _node_base_url():
    """Flask Node base URL — same defaults as cats.node CAT_NODE_*."""
    host = os.environ.get('CAT_NODE_HOST', '127.0.0.1')
    port = int(os.environ.get('CAT_NODE_PORT', '5000'))
    return f'http://{host}:{port}'


def _node_init_endpoint():
    return f'{_node_base_url()}/cat/node/init'


@contextlib.contextmanager
def _activity_spinner(label='Waiting'):
    """Indeterminate activity line on stderr while a long call runs (TTY only).

    Order submit wait is mostly server-side work, not byte transfer — a spinner /
    elapsed counter beats a fake percent bar. Non-TTY (tests/CI): no animation.
    """
    stop = threading.Event()
    started = time.perf_counter()
    use_tty = sys.stderr.isatty()

    def _run():
        frames = itertools.cycle('|/-\\')
        while not stop.wait(0.1):
            elapsed = time.perf_counter() - started
            sys.stderr.write(f'\r{label} {next(frames)} {elapsed:.0f}s')
            sys.stderr.flush()

    thread = None
    if use_tty:
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=1.0)
            sys.stderr.write('\r' + ' ' * 60 + '\r')
            sys.stderr.flush()
