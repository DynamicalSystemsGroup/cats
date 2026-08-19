import os, time, subprocess, threading


class Dict2Class(object):
    def __init__(self, my_dict):
        for key in my_dict:
            setattr(self, key, my_dict[key])


def subproc_run(cmd, cwd=None):
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        text=True,
        cwd=cwd
    )
    return proc


def executeCMD(cmd, cwd=None):
    """Run ``cmd``, stream stdout live, and fail with stderr in the message.

    stderr is drained on a side thread so a verbose failing process cannot
    deadlock when the stderr pipe buffer fills (Popen + unread stderr).
    """
    popen = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        universal_newlines=True,
        cwd=cwd,
    )
    err_chunks: list[str] = []

    def _drain_stderr():
        assert popen.stderr is not None
        for line in iter(popen.stderr.readline, ''):
            err_chunks.append(line)

    drain = threading.Thread(target=_drain_stderr, daemon=True)
    drain.start()
    assert popen.stdout is not None
    for stdout_line in iter(popen.stdout.readline, ''):
        print(stdout_line, end='')
    popen.stdout.close()
    return_code = popen.wait()
    drain.join(timeout=30)
    err = ''.join(err_chunks)
    if return_code != 0:
        if err:
            print('Error:\n', err)
        # RuntimeError so Flask / catSubmit see stderr (CalledProcessError.__str__
        # omits the stderr attribute).
        raise RuntimeError(
            f'Command {cmd!r} returned non-zero exit status {return_code}.\n'
            f'{err}'.rstrip()
        )
    return popen


def wait_for_directory(directory_path, check_interval=1):
    """
    Waits until the specified directory exists.

    :param directory_path: The path to the directory to wait for.
    :param check_interval: Time (in seconds) between checks.
    """
    while not os.path.exists(directory_path):
        print(f"Waiting for directory: {directory_path}")
        time.sleep(check_interval)
    print(f"Directory {directory_path} now exists.")


def read_exit_code(file_path):
    try:
        with open(file_path, 'r') as file:
            exit_code_str = file.read().strip()
            exit_code = int(exit_code_str)
            return exit_code
    except FileNotFoundError:
        print(f"Error: The file {file_path} does not exist.")
        return None
    except ValueError:
        print(f"Error: The file {file_path} does not contain a valid exit code.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


def wait_for_directory_to_be_populated(directory_path, check_interval=1, timeout=None):
    """
    Waits until the specified directory contains at least one file.

    :param directory_path: The path to the directory to monitor.
    :param check_interval: Time (in seconds) between checks. Default is 1 second.
    :param timeout: Maximum time (in seconds) to wait. None for no timeout. Default is None.
    :return: True if the directory was populated, False if timed out.
    """
    start_time = time.time()

    while True:
        # Check if the directory contains any files
        if os.path.isdir(directory_path) and os.listdir(directory_path):
            print(f"Directory '{directory_path}' is populated.")
            return True

        # Check if timeout has been reached
        if timeout and (time.time() - start_time) > timeout:
            print(f"Timeout reached. Directory '{directory_path}' is still empty.")
            return False

        # Wait for the specified interval before checking again
        time.sleep(check_interval)
