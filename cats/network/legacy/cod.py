"""Legacy Bacalhau CoD helpers — quarantine for CoDTransport mining.

Not part of the ContentMesh content-store path.
See ``cats.network.plant_transport.CoDTransport``.
"""

import json, glob, os, multiprocessing, shutil, subprocess, tempfile, time

from cats.utils import subproc_run

# Host Kubo ensure/heal lives in InfraStructure content_store_utils
# (ContentStore) under infrastructure_cid — not as Node-owned lifecycle.


class CoD:
    def __init__(self, INTEGRATION_INPUT_CACHE, put_dir):
        self.CAT_HOME = None
        self.INTEGRATION_INPUT_CACHE = INTEGRATION_INPUT_CACHE
        self.ingress_job_id = None
        self.ingressed_data_cid = None
        self.put_dir = put_dir

    def contains_substring(self, substring):
        return lambda s: substring in s

    def put_dir_upon_completion(self, directory_path, job_id, check_interval=1, timeout=None):
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

        data_dir_id = self.put_dir(directory_path)
        print("job output CIDed: %s" % data_dir_id)
        return data_dir_id

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
