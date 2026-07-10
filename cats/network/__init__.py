import json, subprocess
import os
from copy import copy, deepcopy
from pprint import pprint
import pickle

from cats.network.clients import CoD, ipfs
from cats.utils import Text2Python


class MeshClient(CoD):
    def __init__(self, ipfsClient, filecoinClient=None, awsClient=None, CATS_HOME=None):
        self.CATS_HOME = None
        self.DATA_HOME = None
        self.JOB_HOME = None
        self.CACHE_HOME = None
        self.INPUT_HOME = None
        self.OUTPUT_HOME = None
        self.OUTPUT_DATA_HOME = None
        self.INPUT_STRUCTURE_HOME = None
        self.INPUT_DATA_HOME = None
        if CATS_HOME is not None:
            self.catStore(CATS_HOME)
        # ipfs(cwd=self.CATS_HOME).shutdown()
        ipfs(cwd=self.CATS_HOME).daemon()

        self.INGRESS_HOME = None
        self.INTEGRATION_HOME = None
        self.INTEGRATION_INPUT_CACHE = None
        self.INTEGRATION_INPUT_DATA_CACHE = None
        self.EGRESS_INPUT_DATA = None
        self.EGRESS_HOME = None

        self.CAT_HOME = None
        self.CAR_HOME = None
        self.ipfsClient = ipfsClient
        self.filecoinClient = filecoinClient
        self.awsClient = awsClient
        self.context = ...
        CoD.__init__(self, INTEGRATION_INPUT_CACHE=self.INTEGRATION_INPUT_CACHE, cidDir=self.cidDir)

    def retrieve_cids(self, cid_dict):
        def switch_case(case):
            match case:
                case 'text':
                    try:
                        return lambda cid: self.cat(cid)
                    except Exception as e:
                        print(f"An error occurred while retrieving CID {cid}: {e}")
                        return cid
                case 'obj':
                    try:
                        return lambda cid: pickle.loads(self.catObj(cid))
                    except Exception as e:
                        print(f"An error occurred while fetching the object from IPFS: {e}")
                        return cid
                case _:
                    return cid

        cid_contents = {}
        for key, cid in cid_dict.items():
            if cid is not None:
                try:
                    print(f"{key} - {cid}")
                    cid_contents[key] = switch_case('text')(cid)
                except:
                    try:
                        print(f"{key} - {cid}")
                        py_txt = switch_case('obj')(cid)
                        cid_contents[key] = Text2Python(py_txt)
                    except:
                        print(f"{key} - {cid}")
                        cid_contents[key] = cid
            else:
                cid_contents[key] = switch_case(None)
        return cid_contents

    def fetch_ipfs_object(self, cid):
        try:
            # Fetch the binary content from IPFS
            binary_content = self.cat(cid)
            # Deserialize the object using pickle
            obj = pickle.loads(binary_content)
            return obj
        except Exception as e:
            print(f"An error occurred while fetching the object from IPFS: {e}")
            return None

    def catStore(self, CATS_HOME):
        self.CATS_HOME = CATS_HOME
        self.DATA_HOME = self.CATS_HOME + '/data'
        self.JOB_HOME = self.DATA_HOME + '/jobs'

    def catSubmit(self, order_request):
        print("Order:")
        order = json.loads(self.cat(order_request["order_cid"]))
        print()
        pprint(order)
        print()

        ppost = lambda args, endpoint: \
            f'curl -X POST -H "Content-Type: application/json" -d \\\n\'{json.dumps(**args)}\' {endpoint}'
        post = lambda args, endpoint: \
            'curl -X POST -H "Content-Type: application/json" -d \'' + json.dumps(**args) + f'\' {endpoint}'

        post_cmd = post({'obj': order_request}, order["endpoint"])
        print(ppost({'obj': order_request}, order["endpoint"]))
        print()
        response_str = subprocess.check_output(post_cmd, shell=True)
        output_bom = json.loads(response_str)

        output_bom['POST'] = post_cmd
        return output_bom

    def linkProcess(
            self,
            cat_response,
            ingress_subproc=None,
            integrated_subproc=None,
            egress_subproc=None,
            integration_cache_subproc=None,
            infrafunction_subproc=None
    ):
        flattened_bom = self.flatten_bom(cat_response)
        flat_bom = deepcopy(flattened_bom['flat_bom'])
        prev_function = flat_bom['invoice']['order']['flat']['function']
        prev_process = json.loads(self.cat(prev_function['process_cid']))
        prev_infrafunction = json.loads(self.cat(prev_function['infrafunction_cid']))

        process = {}
        if ingress_subproc is not None:
            process['ingress_subproc_cid'] = self.ipfsClient.add_pyobj(ingress_subproc)
        else:
            process['ingress_subproc_cid'] = prev_process['ingress_subproc_cid']
        if integrated_subproc is not None:
            process['integrated_subproc_cid'] = self.ipfsClient.add_pyobj(integrated_subproc)
        else:
            process['integrated_subproc_cid'] = prev_process['integrated_subproc_cid']
        if egress_subproc is not None:
            process['egress_subproc_cid'] = self.ipfsClient.add_pyobj(egress_subproc)
        else:
            process['egress_subproc_cid'] = prev_process['egress_subproc_cid']
        if integration_cache_subproc is not None:
            process['integration_cache_subproc_cid'] = self.ipfsClient.add_pyobj(integration_cache_subproc)
        else:
            process['integration_cache_subproc_cid'] = prev_process['integration_cache_subproc_cid']

        infrafunction = {}
        if infrafunction_subproc is not None:
            infrafunction['infrafunction_subproc_cid'] = self.ipfsClient.add_pyobj(infrafunction_subproc)
        else:
            infrafunction['infrafunction_subproc_cid'] = prev_infrafunction['infrafunction_subproc_cid']

        new_function_cid = self.ipfsClient.add_str(json.dumps({
            'process_cid': self.ipfsClient.add_str(json.dumps(process)),
            'infrafunction_cid': self.ipfsClient.add_str(json.dumps(infrafunction)),
        }))

        invoice = flat_bom['invoice']
        input_invoice = {'data_cid': invoice['data_cid']}
        prev_invoice_cid = self.ipfsClient.add_str(json.dumps(input_invoice))

        order = invoice['order']
        order['function_cid'] = new_function_cid
        order['invoice_cid'] = prev_invoice_cid
        del order['flat']
        order['endpoint'] = 'http://127.0.0.1:5000/cat/node/init'

        order_request = {'order_cid': self.ipfsClient.add_str(json.dumps(order))}
        return order_request

    def cidDir(self, filepath: str):
        # print(filepath)
        name = filepath.split('/')[-1]
        dir = self.ipfsClient.add(filepath, recursive=True)
        if type(dir) is list:
            # dir_json = list(filter(lambda x: x['Name'] == 'outputs', dir))[-1]
            dir_json = list(filter(lambda x: x['Name'] == name, dir))[-1]
            dir_cid = dir_json['Hash']
            dir_name = dir_json['Name']
            return dir_cid, dir_name
        else:
            dir_cid = dir['Hash']
            # dir_name = dir['Name']
            return dir_cid

    def cidFile(self, filepath):
        file_json = self.ipfsClient.add(filepath)
        file_cid = file_json['Hash']
        file_name = file_json['Name']
        return file_cid, file_name

    def create_order_request(
            self,
            ingress_subproc,
            integrated_subproc,
            egress_subproc,
            integration_cache_subproc,
            infrafunction_subproc,
            data_dirpath,
            structure_filepath,
            endpoint='http://127.0.0.1:5000/cat/node/execute'
    ):
        structure_name = os.path.basename(structure_filepath.rstrip('/'))
        # Plant (SaaS): modules/plant - the kind cluster + Helm releases
        # that constitute the dynamically scaled execution environment.
        plant_cid, _ = self.cidDir(os.path.join(structure_filepath, 'modules', 'plant'))
        # InfraStructure (IaaS): modules/infrastructure - the IPFS/Docker
        # transport layer used to move content-addressed data in and out
        # of the Plant.
        infrastructure_cid, _ = self.cidDir(os.path.join(structure_filepath, 'modules', 'infrastructure'))
        structure_cid = self.ipfsClient.add_str(json.dumps({
            'plant_cid': plant_cid,
            'infrastructure_cid': infrastructure_cid,
        }))
        data_cid, dir_name = self.cidDir(data_dirpath)
        # Process (FaaS): the Functional Data Processors themselves.
        process = {
            'ingress_subproc_cid': self.ipfsClient.add_pyobj(ingress_subproc),
            'integrated_subproc_cid': self.ipfsClient.add_pyobj(integrated_subproc),
            'egress_subproc_cid': self.ipfsClient.add_pyobj(egress_subproc),
            'integration_cache_subproc_cid': self.ipfsClient.add_pyobj(integration_cache_subproc),
        }
        # InfraFunction (FaaS): the orchestrator that dispatches Process
        # onto the Plant (see Processor.Integration() in
        # cats/executor/function/__init__.py).
        infrafunction = {
            'infrafunction_subproc_cid': self.ipfsClient.add_pyobj(infrafunction_subproc),
        }
        function = {
            'process_cid': self.ipfsClient.add_str(json.dumps(process)),
            'infrafunction_cid': self.ipfsClient.add_str(json.dumps(infrafunction)),
        }
        invoice = {
            "data_cid": data_cid
        }
        order = {
            "function_cid": self.ipfsClient.add_str(json.dumps(function)),
            "structure_cid": structure_cid,
            "invoice_cid": self.ipfsClient.add_str(json.dumps(invoice)),
            "structure_filepath": structure_name,
            "JOB_HOME": self.JOB_HOME,
            "endpoint": endpoint
        }
        order_request = {
            'order_cid': self.ipfsClient.add_str(json.dumps(order))
        }
        return order_request

    def flatten_bom(self, bom_response):
        invoice = json.loads(
            self.cat(bom_response["bom"]["invoice_cid"])
        )
        invoice['order'] = json.loads(
            self.cat(invoice['order_cid']),
        )
        invoice['order']['flat'] = {
            'function': json.loads(self.cat(invoice['order']["function_cid"])),
            'structure': json.loads(self.cat(invoice['order']["structure_cid"])),
            'invoice': json.loads(self.cat(invoice['order']["invoice_cid"]))
        }
        bom_response["flat_bom"] = {
            'invoice': invoice,
            'log': json.loads(
                self.cat(bom_response["bom"]["log_cid"])
            ),
            'plant': json.loads(
                self.cat(bom_response["bom"]["plant_snapshot_cid"])
            )
        }
        return bom_response

    def initBOMjson(self,
        structure_cid: str, structure_filepath: str, function_cid: str, init_data_cid: str,
        seed_cid=None
    ):
        init_invoice = {
            'order_cid': None,
            # 'data_cid': None,
            'seed_cid': seed_cid,
        }
        init_order = {
            'invoice_cid': None,
            'function_cid': function_cid,
            'structure_cid': structure_cid,
            'structure_filepath': structure_filepath
        }

        init_invoice_cid = self.ipfsClient.add_json(init_invoice)
        init_order['invoice_cid'] = init_invoice_cid
        init_order_cid = self.ipfsClient.add_json(init_order)

        invoice = copy(init_invoice)
        invoice['order_cid'] = init_order_cid
        invoice_cid = self.ipfsClient.add_json(invoice)

        init_bom = {
            'invoice_cid': invoice_cid,
            'log_cid': None,
            'init_data_cid': init_data_cid
        }
        init_bom_json_cid = self.ipfsClient.add_json(init_bom)
        return init_bom_json_cid

    def initBOMcar(self,
            structure_cid: str, structure_filepath: str, function_cid: str, init_data_cid: str,
            init_bom_filename: str, seed_cid=None
        ):
        init_bom_json_cid = self.initBOMjson(structure_cid, structure_filepath, function_cid, init_data_cid)
        car_bom_cid, init_bom_json_cid = self.convertBOMtoCAR(init_bom_json_cid, init_bom_filename)
        return car_bom_cid, init_bom_json_cid

    def linkData(self, cid, subdir=' - outputs/'):
        cmd = f"ipfs ls {cid}"
        response = subprocess.check_output(cmd.split(' ')).decode()
        dirs = response.split('\n')
        res = [i for i in dirs if subdir in i]
        return res[0].split(' - ')[0]

    def get(self, cid: str, filepath: str, output: str = None):
        if output is None:
            output = self.CATS_HOME
        subprocess.check_output(
            f"ipfs get {cid} --output {output}/{filepath}",
            stderr=subprocess.STDOUT,
            shell=True,
            cwd=output
        )
        return filepath

    def testGet(self, cid: str, output: str):
        subprocess.check_output(
            f"ipfs get {cid} --output {output} --progress=true && echo 'IPFS download of {output} completed successfully.' || echo 'IPFS download of {cid} failed.'",
            stderr=subprocess.STDOUT,
            shell=True,
            cwd=output
        )

    def cat(self, cid: str):
        return subprocess.check_output(['ipfs', 'cat', cid]).decode()

    def catObj(self, cid: str):
        return subprocess.check_output(['ipfs', 'cat', cid])

    def getCar(self, cid: str, filepath: str):
        subprocess.check_output(
            f"ipfs dag export {cid} > {filepath}",
            stderr=subprocess.STDOUT,
            shell=True
        )

    def getBom(self, cid: str, filepath: str):
        self.get(cid, filepath)
        bom = dict(json.loads(filepath))
        subprocess.check_output(
            f"rm {filepath}",
            stderr=subprocess.STDOUT,
            shell=True
        )
        return bom

    def BOMcarToIPFS(self, bom_cid: str, filepath: str):
        self.getCar(bom_cid, filepath)
        storage_bom_cid = self.ipfsClient.post_upload(filepath)
        return storage_bom_cid, bom_cid

    def convertBOMtoCAR(self, bom_cid: str, filepath: str):
        self.getCar(bom_cid, filepath)
        car_bom_cid = None
        try:
            car_bom_cid = self.ipfsClient.add(filepath)['Hash']
        except:
            for attrs in self.ipfsClient.add(filepath):
                if attrs['Name'] == filepath:
                    print(attrs)
                    car_bom_cid = attrs['Hash']
        return car_bom_cid, bom_cid

    def getEnhancedBom(self, bom_json_cid: str, INPUT_HOME: str = None, OUTPUT_HOME: str = None):
        if INPUT_HOME is None:
            INPUT_HOME = self.INPUT_HOME
        if OUTPUT_HOME is None:
            OUTPUT_HOME = self.OUTPUT_HOME
        self.CAR_HOME = OUTPUT_HOME + '/bom.car'
        self.get(cid=bom_json_cid, output=OUTPUT_HOME, filepath='bom.json')
        bom = json.loads(open(f'{OUTPUT_HOME}/bom.json', 'r').read())
        enhanced_bom = deepcopy(bom)
        enhanced_bom['bom_json_cid'] = bom_json_cid

        self.get(cid=bom['invoice_cid'], output=OUTPUT_HOME, filepath='invoice.json')
        enhanced_bom['invoice'] = json.loads(open(f'{OUTPUT_HOME}/invoice.json', 'r').read())

        self.get(cid=enhanced_bom['invoice']['order_cid'], output=INPUT_HOME, filepath='order.json')
        enhanced_bom['order'] = json.loads(open(f'{INPUT_HOME}/order.json', 'r').read())

        # structure_cid nests plant_cid (module.plant) and infrastructure_cid
        # (module.infrastructure) - see create_order_request() - so each is
        # fetched into its corresponding modules/ subdirectory rather than
        # structure_cid itself being a single directory CID.
        structure = json.loads(self.cat(enhanced_bom['order']['structure_cid']))
        structure_filepath = enhanced_bom['order']['structure_filepath']
        self.get(
            cid=structure['plant_cid'], output=INPUT_HOME,
            filepath=os.path.join(structure_filepath, 'modules', 'plant')
        )
        self.get(
            cid=structure['infrastructure_cid'], output=INPUT_HOME,
            filepath=os.path.join(structure_filepath, 'modules', 'infrastructure')
        )
        return deepcopy(enhanced_bom), bom

    def createInvoice(self, orderCID: str, dataCID: str, seedCID: str):
        invoice = {'orderCID': orderCID, 'dataCID': dataCID, 'seedCID': seedCID}
        invoice_cid = self.ipfsClient.add_json(invoice)
        return invoice_cid
