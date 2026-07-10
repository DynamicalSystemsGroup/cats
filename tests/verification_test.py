### Execute Initial CAT0:
##### Instantiate CAT Mesh Client:
import glob, os
from pprint import pprint
import pandas as pd

from cats import DATA_HOME, MESH_CLIENT as meshClient
from cats import INPUT_STRUCTURE_HOME, INPUT_DATA_HOME

##### Compose Initial CAT Order request for CAT Node
from data.input.process import *

def files_to_pandasDF(output, format):
    # Get the files from the path provided
    files = glob.glob(os.path.join(output, format))
    dfs = list(pd.read_csv(f).assign(filename=f) for f in files)
    df = None
    for dfx in dfs:
        if df is None:
            df = dfx
        else:
            df = pd.concat([df, dfx], ignore_index=True)
    return df

def cid_to_pandasDF(cid, download_dir, format='*.csv'):
    os.makedirs(download_dir)
    meshClient.testGet(cid, download_dir)

    # Get the files from the path provided
    return files_to_pandasDF(output=download_dir, format=format)

class catDataVerification:
    cat_input_data_cid = None
    cat_output_data_cid = None
    cat_order_request_0 = None
    cat_order_request_1 = None
    cat_input_df = None
    cat_output_df = None
    cat_input_path = f'{DATA_HOME}/testing/cat_input'
    cat_output_path = f'{DATA_HOME}/testing/cat_output'

    def create_cat0_order_request(self):
        self.cat_order_request_0 = meshClient.create_order_request(
            ingress_subproc=ingress,
            integrated_subproc=process_0,
            egress_subproc=egress,
            integration_cache_subproc=integration_cache,
            data_dirpath=INPUT_DATA_HOME,  # f'{INPUT_DATA_HOME}/iris.csv',
            structure_filepath=INPUT_STRUCTURE_HOME,
            endpoint='http://127.0.0.1:5000/cat/node/init'
        )
        pprint(self.cat_order_request_0)
        print()
        return self.cat_order_request_0

    def create_cat1_order_request(self):
        self.cat_order_request_1 = meshClient.create_order_request(
            ingress_subproc=ingress,
            integrated_subproc=process_1,
            egress_subproc=egress,
            integration_cache_subproc=integration_cache,
            data_dirpath=INPUT_DATA_HOME,  # f'{INPUT_DATA_HOME}/iris.csv',
            structure_filepath=INPUT_STRUCTURE_HOME,
            endpoint='http://127.0.0.1:5000/cat/node/init'
        )
        pprint(self.cat_order_request_1)
        print()
        return self.cat_order_request_1

    def verify(self, cat_order_request):
        ##### Submit modified CAT Order request to CAT Node
        cat_invoiced_response = meshClient.catSubmit(cat_order_request)
        pprint(cat_invoiced_response)
        print()
        if 'error' in cat_invoiced_response:
            raise RuntimeError(
                f"CAT node returned an error: {cat_invoiced_response['error']}"
            )
        flat_cat_invoiced_response = meshClient.flatten_bom(cat_invoiced_response)
        pprint(flat_cat_invoiced_response)
        print()
        self.cat_input_data_cid = flat_cat_invoiced_response['flat_bom']['invoice']['order']['flat']['invoice'][
            'data_cid']
        print(self.cat_input_data_cid)
        print()
        self.cat_output_data_cid = flat_cat_invoiced_response['flat_bom']['invoice']['data_cid']
        print(self.cat_output_data_cid)
        print()

        cat_input_df = cid_to_pandasDF(
            cid=self.cat_input_data_cid,
            download_dir=self.cat_input_path + f"_{int(time.time())}"
        )
        cat_input_df = cat_input_df \
            .drop(columns=["filename"]) \
            .apply(pd.to_numeric, errors='coerce').astype(float)
        self.cat_input_df = cat_input_df.sort_values(by=list(cat_input_df.columns)).reset_index(drop=True)

        self.cat_output_df = cid_to_pandasDF(
            cid=self.cat_output_data_cid,
            download_dir=self.cat_output_path + f"_{int(time.time())}"
        )


class TestDataVerificationCATs:
    catsVerification = catDataVerification()
    cat0_order_request = catsVerification.create_cat0_order_request()
    cat1_order_request = catsVerification.create_cat1_order_request()
    cat0_input_df = None
    cat0_output_df = None
    cat1_input_df = None
    cat1_output_df = None

    def cat0_transfer_link(self, cat0_output_df):
        self.cat0_output_df = cat0_output_df \
            .sort_values(by="id") \
            .drop(columns=["id", "filename", "petal area (cm^2)"]) \
            .apply(pd.to_numeric, errors='coerce').astype(float)
        self.cat0_output_df = self.cat0_output_df \
            .sort_values(by=list(self.cat0_output_df.columns)) \
            .reset_index(drop=True)
        return self.cat0_output_df

    def cat1_transfer_link(self, cat1_output_df):
        self.cat1_output_df = cat1_output_df \
            .drop(columns=["filename", "DUPLICATE petal area (cm^2)"]) \
            .apply(pd.to_numeric, errors='coerce').astype(float)
        self.cat1_output_df = self.cat1_output_df.sort_values(by=list(self.cat1_output_df.columns)) \
            .reset_index(drop=True)
        return self.cat1_output_df

    def cat1_input_lineage_verification(self):
        self.catsVerification.verify(self.cat0_order_request)
        self.cat0_input_df = self.catsVerification.cat_input_df
        self.catsVerification.verify(self.cat1_order_request)
        self.cat1_input_df = self.catsVerification.cat_input_df

    def test_cat0_data_verification(self):
        ### Execute CAT0:
        self.catsVerification.verify(self.cat0_order_request)
        self.cat0_input_df = self.catsVerification.cat_input_df
        self.cat0_output_df = self.cat0_transfer_link(self.catsVerification.cat_output_df)

        assert np.array_equal(
            self.cat0_input_df.values,
            self.cat0_output_df.values
        )

    def test_cat1_data_verification(self):
        ### Execute CAT1:
        self.catsVerification.verify(self.cat1_order_request)
        self.cat1_input_df = self.catsVerification.cat_input_df
        self.cat1_output_df = self.cat1_transfer_link(self.catsVerification.cat_output_df)

        assert np.array_equal(
            self.cat1_input_df.values,
            self.cat1_output_df.values
        )

    def test_cat1_input_lineage_verification(self):
        self.catsVerification.verify(self.cat0_order_request)
        self.cat0_input_df = self.catsVerification.cat_input_df
        self.catsVerification.verify(self.cat1_order_request)
        self.cat1_input_df = self.catsVerification.cat_input_df
        assert np.array_equal(
            self.cat0_input_df.values,
            self.cat1_input_df.values,
        )

    def test_cat1_output_lineage_verification(self):
        self.catsVerification.verify(self.cat0_order_request)
        self.cat0_input_df = self.catsVerification.cat_input_df
        self.catsVerification.verify(self.cat1_order_request)
        self.cat1_output_df = self.cat1_transfer_link(self.catsVerification.cat_output_df)
        assert np.array_equal(
            self.cat0_input_df.values,
            self.cat1_output_df.values
        )

    def test_catMesh_data_transfer_verification(self):
        self.catsVerification.verify(self.cat0_order_request)
        self.cat0_output_df = self.cat0_transfer_link(self.catsVerification.cat_output_df)
        self.catsVerification.verify(self.cat1_order_request)
        self.cat1_input_df = self.catsVerification.cat_input_df
        assert np.array_equal(
            self.cat0_output_df.values,
            self.cat1_input_df.values
        )
