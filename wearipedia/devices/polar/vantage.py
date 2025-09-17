from datetime import datetime

from requests_oauthlib import OAuth2Session

from ...utils import seed_everything
from ..device import BaseDevice
from .vantage_fetch import fetch_real_data
from .vantage_synthetic import create_syn_data


class PolarVantage(BaseDevice):

    """This device allows you to work with data from the `Polar Vantage <https://www.polar.com/us-en/vantage/v2>`_ device.
    Available datatypes for this device are:

    * `sleep`: a list that contains sleep data for each day

    * `daily_activity`: a list that contains daily activity data for each day

    * `training_data`: a list that contains daily activity data for each day

    * `training_by_id`: a list that contains training data for a given training session

    * `activity_by_id`: a list that contains activity data for a given activity session

    :param seed: random seed for synthetic data generation, defaults to 0
    :type seed: int, optional
    :param synthetic_start_date: start date for synthetic data generation, defaults to "2022-03-01"
    :type synthetic_start_date: str, optional
    :param synthetic_end_date: end date for synthetic data generation, defaults to "2022-06-17"
    :type synthetic_end_date: str, optional
    :param use_cache: decide whether to cache the credentials, defaults to True
    :type use_cache: bool, optional
    """

    name = "polar/vantage"

    def __init__(self, seed=0, start_date="2022-03-01", end_date="2022-06-17"):
        params = {
            "seed": seed,
            "start_date": str(start_date),
            "end_date": str(end_date),
        }

        self._initialize_device_params(
            ["sleep", "daily_activity", "training_data", "training_by_id"],
            params,
            {"seed": 0, "start_date": "2022-03-01", "end_date": "2022-06-17"},
        )

        self.auth_url = "https://flow.polar.com/oauth2/authorization"
        self.token_url = "https://polarremote.com/v2/oauth2/token"
        self.user_url = "https://www.polaraccesslink.com/v3/users"

        self.token = None
        self.user_id = None

    def _default_params(self):
        return {
            "training_id": None,
            "start_date": self.init_params["start_date"],
            "end_date": self.init_params["end_date"],
        }

    def _get_real(self, data_type, params):
        if "training_id" in params:
            return fetch_real_data(
                self.token,
                self.user_id,
                params["start_date"],
                params["end_date"],
                data_type,
                params["training_id"],
            )
        else:
            return fetch_real_data(
                self.token,
                self.user_id,
                params["start_date"],
                params["end_date"],
                data_type,
                "",
            )

    def _filter_synthetic(self, data, data_type, params):
        # Here we just return the data we've already generated,
        # but index into it based on the params. Specifically, we
        # want to return the data between the start and end dates.

        # convert the dates to datetime objects
        def date_str_to_obj(x):
            return datetime.strptime(x, "%Y-%m-%d")

        # get the indices by subtracting against the start of the synthetic data
        synthetic_start = date_str_to_obj(self.init_params["start_date"])

        start_idx = (date_str_to_obj(params["start_date"]) - synthetic_start).days
        end_idx = (date_str_to_obj(params["end_date"]) - synthetic_start).days

        return data[start_idx:end_idx]

    def _gen_synthetic(self):
        # generate random data according to seed
        seed_everything(self.init_params["seed"])

        # and based on start and end dates
        self.training_data, self.sleep, self.training_by_id = create_syn_data(
            self.init_params["start_date"],
            self.init_params["end_date"],
        )
        self.daily_activity = []
        self.activity_by_id = []

    def _authenticate(self, auth_creds=None):
        if (
            auth_creds
            and isinstance(auth_creds, dict)
            and auth_creds.get("access_token")
            and auth_creds.get("user_id")
        ):
            self.token = auth_creds["access_token"]
            self.user_id = auth_creds["user_id"]
            return

        elif (
            auth_creds
            and isinstance(auth_creds, dict)
            and "client_id" in auth_creds
            and "client_secret" in auth_creds
            and "redirect_uri" in auth_creds
            ):

            client_id = auth_creds.get('client_id')
            client_secret = auth_creds.get('client_secret')
            redirect_uri = auth_creds.get('redirect_uri')

        else:
            print(
                "Input your client id.\nIf you need a new application, \
                    you can register one at https://admin.polaraccesslink.com\n"
                )

            # Retrieve information from user
            client_id = input("Enter the client id: ")
            client_secret = input("Enter the client secret: ")
            redirect_uri = input("Enter your redirect URI: ")

        # Using requests_oauthlib to simplify code
        oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope="accesslink.read_all")

        # Retrieve authorization URL
        authorization_url, _ = oauth.authorization_url(
            url=self.auth_url
            )

        # Ask user to log in via webbrowser
        print(f"Open the following URL in your webbrowser and copy the resulting URL after loggin in:\n{authorization_url}")
        authorization_response = input('Enter the full callback URL')

        # Fetch authorization token
        token_response = oauth.fetch_token(
            token_url=self.token_url,
            authorization_response=authorization_response,
            client_secret=client_secret
        )

        # Save as class param
        self.token = token_response.get('access_token')
        self.user_id = token_response.get('x_user_id')

        # Register this application as user to fetch the data
        json = {"member-id": self.user_id}
        r = oauth.post(self.user_url,
                       json=json)

        # Verify operation
        if r.status_code >= 200 and r.status_code < 400:
            print("Registered user:")
            print(r.json())
        elif r.status_code != 409:
            print(r)
