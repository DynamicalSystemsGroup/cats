import json, glob, os, multiprocessing, shutil, subprocess, tempfile, time
from pprint import pprint

import requests

from cats.utils import subproc_run

# Kubo can answer `ipfs id` from the local repo with the daemon down
# (Addresses null). Probe the HTTP API the cats client uses instead.
_IPFS_API_ID_URL = os.environ.get(
    'CATS_IPFS_API_ID_URL', 'http://127.0.0.1:5001/api/v0/id'
)

# True only when this OS process spawned host Kubo via ipfs.daemon().
_host_daemon_owned = False


def _ipfs_is_running(timeout=1.0):
    """True only when the host Kubo HTTP API accepts /api/v0/id."""
    try:
        response = requests.post(_IPFS_API_ID_URL, timeout=timeout)
        return response.ok
    except (requests.RequestException, OSError):
        return False


def _wait_for_ipfs_api(timeout=30.0, poll_interval=0.25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _ipfs_is_running():
            return True
        time.sleep(poll_interval)
    return False


def _wait_for_ipfs_api_down(timeout=10.0, poll_interval=0.25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _ipfs_is_running():
            return True
        time.sleep(poll_interval)
    return False


def _repo_lock_path():
    ipfs_path = os.environ.get('IPFS_PATH') or os.path.expanduser('~/.ipfs')
    return os.path.join(ipfs_path, 'repo.lock')


def _lock_holder_pids(lock_path):
    """PIDs holding an open FD on repo.lock (via lsof). Empty if unknown."""
    try:
        result = subprocess.run(
            ['lsof', '-t', lock_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for line in result.stdout.split():
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def _ipfs_daemon_pids():
    """PIDs matching `ipfs daemon`. Empty if the probe fails (not fail-closed)."""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'ipfs daemon'],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode not in (0, 1):
        return []
    pids = []
    for line in result.stdout.split():
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def _any_ipfs_daemon_process():
    """True if an `ipfs daemon` process or repo.lock holder appears to exist."""
    lock_path = _repo_lock_path()
    if _lock_holder_pids(lock_path) or _ipfs_daemon_pids():
        return True
    return False


def _terminate_pids(pids, wait_seconds=2.0):
    """SIGTERM then SIGKILL stubborn PIDs. Ignores missing processes."""
    alive = []
    for pid in pids:
        try:
            os.kill(pid, 15)  # SIGTERM
            alive.append(pid)
        except OSError:
            continue
    if not alive:
        return
    deadline = time.time() + wait_seconds
    while time.time() < deadline and alive:
        still = []
        for pid in alive:
            try:
                os.kill(pid, 0)
                still.append(pid)
            except OSError:
                continue
        alive = still
        if alive:
            time.sleep(0.1)
    for pid in alive:
        try:
            os.kill(pid, 9)  # SIGKILL
        except OSError:
            pass


def _heal_stale_repo_lock():
    """Best-effort recover from a dead API with a held repo.lock.

    A hung Kubo can hold the flock (and even keep swarm sockets) while the
    HTTP API on :5001 is dead — `ipfs shutdown` talks to that API, so it
    cannot clear this state. Terminate lock holders / daemon PIDs, then
    remove the stale lock file so a fresh daemon can start.
    """
    try:
        subprocess.run(
            ['ipfs', 'shutdown'],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass

    time.sleep(0.5)
    if _ipfs_is_running():
        return

    lock_path = _repo_lock_path()
    pids = set(_lock_holder_pids(lock_path)) | set(_ipfs_daemon_pids())
    if pids:
        print(
            f'Terminating hung host IPFS process(es) holding repo lock: '
            f'{sorted(pids)}',
            flush=True,
        )
        _terminate_pids(sorted(pids))
        time.sleep(0.25)

    if _ipfs_is_running():
        return

    if os.path.exists(lock_path) and not _lock_holder_pids(lock_path):
        try:
            os.unlink(lock_path)
            print(f'Removed stale IPFS repo lock at {lock_path}.', flush=True)
        except OSError:
            pass


def shutdown_owned_daemon():
    """Stop host Kubo only if this process owns it (_host_daemon_owned)."""
    global _host_daemon_owned
    if not _host_daemon_owned:
        return
    try:
        subprocess.run(
            ['ipfs', 'shutdown'],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    _wait_for_ipfs_api_down(timeout=10.0)
    _host_daemon_owned = False


class ipfs:
    def __init__(self, cwd=None):
        self.cwd = cwd
        self.daemon_cmd = None
        self.proc = None

    def daemon(self, daemon_cmd='ipfs daemon', ready_timeout=30.0):
        global _host_daemon_owned
        if _ipfs_is_running():
            return None
        _heal_stale_repo_lock()
        if _ipfs_is_running():
            return None
        print(
            f'Starting host IPFS daemon (waiting for {_IPFS_API_ID_URL})...',
            flush=True,
        )
        self.daemon_cmd = daemon_cmd
        self.proc = subprocess.Popen(
            self.daemon_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            shell=True,
            universal_newlines=True,
            cwd=self.cwd
        )
        if _wait_for_ipfs_api(timeout=ready_timeout):
            _host_daemon_owned = True
            print('Host IPFS daemon API ready.', flush=True)
            return self.proc
        err = ''
        if self.proc.poll() is not None and self.proc.stderr is not None:
            err = self.proc.stderr.read() or ''
        raise RuntimeError(
            'Timed out waiting for host IPFS daemon HTTP API at '
            f'{_IPFS_API_ID_URL}'
            + (f': {err.strip()}' if err.strip() else '')
        )

    def shutdown(self, daemon_cmd='ipfs shutdown'):
        if not _ipfs_is_running():
            return None
        self.daemon_cmd = daemon_cmd
        self.proc = subprocess.Popen(
            self.daemon_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            shell=True,
            universal_newlines=True,
            cwd=self.cwd
        )
        return self.proc


class CoD:
    def __init__(self, INTEGRATION_INPUT_CACHE, cidDir):
        self.CAT_HOME = None
        self.INTEGRATION_INPUT_CACHE = INTEGRATION_INPUT_CACHE
        self.ingress_job_id = None
        self.ingressed_data_cid = None
        self.cidDir = cidDir

    def contains_substring(self, substring):
        return lambda s: substring in s

    def cidDirUponCompletion(self, directory_path, job_id, check_interval=1, timeout=None):
        start_time = time.time()
        while self.checkStatusOfJob_printless(job_id=job_id) != "Completed":
            status = self.checkStatusOfJob(job_id=job_id)
            if status != "":
                print("job not completed: %s - %s" % (job_id, status))
                exit()
            # Check if timeout has been reached
            if timeout and (time.time() - start_time) > timeout:
                print(f"Timeout reached. Directory '{directory_path}' is still empty.")
                exit()
            time.sleep(check_interval)

        data_dir_cid = self.cidDir(directory_path)
        print("job output CIDed: %s" % data_dir_cid)
        return data_dir_cid

    def describeJob(self, job_id):
        cmd = f"bacalhau job describe {job_id} --output json --pretty"
        # print(cmd)
        job_result = subproc_run(cmd)
        # print(job_result.stdout)
        job_dict = json.loads(job_result.stdout)
        return job_dict

    def getJobExecutions(self, job_id):
        cmd = f"bacalhau job executions {job_id} --output json --pretty"
        # print(cmd)
        job_result = subproc_run(cmd)
        # print(job_result.stdout)
        job_dict = json.loads(job_result.stdout)
        return job_dict

    def getJobState(self, job_id):
        return self.describeJob(job_id)['Job']['State']

    def getPublishedURI(self, job_id):
        # print(type(self.getJobExecutions(job_id).pop()["PublishedResult"]))
        # pprint(self.getJobExecutions(job_id).pop()["PublishedResult"])
        return self.getJobExecutions(job_id).pop()["PublishedResult"]

    # def getJobExecutions(self, job_id):
    #     return self.describeJob(job_id)['State']['Executions']

    # def getPublishedURI(self, job_id):
    #     key_to_find = 'State'
    #     value_to_find = 'Completed'
    #     matching_execution = next(
    #         (d for d in self.getJobExecutions(job_id) if d.get(key_to_find) == value_to_find), None
    #     )
    #     return matching_execution['PublishedResults']

    def waitForJobCompletion(self, job_id, check_interval=1, timeout=None):
        start_time = time.time()
        while self.checkStatusOfJob_printless(job_id=job_id) != "Completed":
            status = self.checkStatusOfJob_printless(job_id)
            if status == "":
                print("job status is empty! %s" % job_id)
            elif status != "":
                print("job not completed: %s - %s" % (job_id, status))
            # Check if timeout has been reached
            if timeout and (time.time() - start_time) > timeout:
                print(f"Job Still Processing: %s - %s" % (job_id, status))
                return status
            time.sleep(check_interval)
        print("job completed: %s" % job_id)
        return self.checkStatusOfJob_printless(job_id)

    def checkStatusOfJob_printless(self, job_id: str) -> str:
        assert len(job_id) > 0
        # cmd = f"bacalhau list --output json --id-filter {job_id}"
        # trimmed_job_id = print(job_id.split('j-'))[-1]
        cmd = f"bacalhau job describe {job_id}  --output json --pretty"
        # cmd = f"bacalhau job list --output json --pretty | jq '.[] | select(.ID == \"{trimmed_job_id}\")'"
        p = subproc_run(cmd)
        # print(p.stdout)
        r = self.parseJobStatus(p.stdout)
        return r

    # checkStatusOfJob checks the status of a Bacalhau job
    def checkStatusOfJob(self, job_id: str) -> str:
        r = self.checkStatusOfJob_printless(job_id)
        if r == "":
            print("job status is empty! %s" % job_id)
        elif r == "Completed":
            print("job completed: %s" % job_id)
        else:
            print("job not completed: %s - %s" % (job_id, r))
        return r

    def getCIDedResults(self, job_id: str, log_mode: str = "json", download_timeout_secs: str = "5m0s"):
        output_dir = self.CACHE_HOME
        # job_result.stdout
        cmd = f"bacalhau get {job_id} --output-dir {output_dir} --download-timeout-secs {download_timeout_secs}"
        print(cmd)
        job_result = subproc_run(cmd)
        print(job_result.stdout)
        job_dict = json.loads(job_result.stdout)
        return job_dict

    def codSubmit(self, cmd):
        submit = subproc_run(cmd)
        submit_job_id = submit.stdout.split('\n')[0]
        print("job submitted: %s" % submit_job_id)
        print()
        return submit_job_id

    # submitJob submits a job to the Bacalhau network
    def submitJob(self, cid: str) -> str:
        assert len(cid) > 0
        p = subprocess.run(
            [
                "bacalhau",
                "docker",
                "run",
                "--id-only",
                "--wait=false",
                "--input",
                "ipfs://" + cid + ":/inputs/data.tar.gz",
                "ghcr.io/bacalhau-project/examples/blockchain-etl:0.0.6"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if p.returncode != 0:
            print("failed (%d) job: %s" % (p.returncode, p.stdout))
        job_id = p.stdout.strip()
        print("job submitted: %s" % job_id)

        return job_id

    # getResultsFromJob gets the results from a Bacalhau job
    def getResultsFromJob(self, job_id: str) -> str:
        assert len(job_id) > 0
        temp_dir = tempfile.mkdtemp()
        print("getting results for job: %s" % job_id)
        for i in range(0, 5): # try 5 times
            p = subprocess.run(
                [
                    "bacalhau",
                    "get",
                    "--output-dir",
                    temp_dir,
                    job_id,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if p.returncode == 0:
                break
            else:
                print("failed (exit %d) to get job: %s" % (p.returncode, p.stdout))

        return temp_dir

    # parseJobStatus parses the status of a Bacalhau job
    def parseJobStatus(self, result: str) -> str:
        if len(result) == 0:
            return ""
        r = json.loads(result)
        # print(r["Job"]["State"]["StateType"])
        #
        if len(r) > 0:
            return r["Job"]["State"]["StateType"]
            # return r[0]["Job"]["State"]["StateType"]
        return ""

    # parseHashes splits lines from a text file into a list
    def parseHashes(self, filename: str) -> list:
        assert os.path.exists(filename)
        with open(filename, "r") as f:
            hashes = f.read().splitlines()
        return hashes

    def parseHashesFromFile(self, file: str, num_files: int = -1):
        # Use multiprocessing to work in parallel
        count = multiprocessing.cpu_count()
        with multiprocessing.Pool(processes=count) as pool:
            hashes = self.parseHashes(file)[:num_files]
            print("submitting %d jobs" % len(hashes))
            job_ids = pool.map(self.submitJob, hashes)
            assert len(job_ids) == len(hashes)

            print("waiting for jobs to complete...")
            while True:
                job_statuses = pool.map(self.checkStatusOfJob, job_ids)
                total_finished = sum(map(lambda x: x == "Completed", job_statuses))
                if total_finished >= len(job_ids):
                    break
                print("%d/%d jobs completed" % (total_finished, len(job_ids)))
                time.sleep(2)

            print("all jobs completed, saving results...")
            results = pool.map(self.getResultsFromJob, job_ids)
            print("finished saving results")

            # Do something with the results
            shutil.rmtree("../../results", ignore_errors=True)
            os.makedirs("../../results", exist_ok=True)
            for r in results:
                path = os.path.join(r, "outputs", "*.csv")
                csv_file = glob.glob(path)
                for f in csv_file:
                    print("moving %s to results" % f)
                    shutil.move(f, "../../results")
