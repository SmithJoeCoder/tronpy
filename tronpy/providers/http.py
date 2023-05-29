import os
import random
import sys
import threading
import time
from typing import Any, List, Union
from urllib.parse import urljoin

import requests

DEFAULT_TIMEOUT = 10.0
DEFAULT_API_KEYS = [
    'f92221d5-7056-4366-b96f-65d3662ec2d9',
    '1e0a625f-cfa5-43ee-ba41-a09db1aae55f',
    'f399168e-2259-481c-90fc-6b3d984c5463',
    'da63253b-aa9c-46e7-a4e8-22d259a8026d',
    '88c10958-af7b-4d5a-8eef-6e84bf5fb809',
    '169bb4b3-cbe8-449a-984e-80e9adacac55',
]


class AtomicCounter:
    def __init__(self, initial=0, max_value=10):
        """Initialize a new atomic counter to given initial value (default 0)."""
        if initial > max_value:
            raise ValueError("Initial value must be less than or equal to the max value")
        if initial < 0:
            raise ValueError("Initial value must be positive")
        self.value = initial
        self._lock = threading.Lock()
        self.max_value = max_value

    def incr(self, value=1):
        """Atomically increment the counter by num (default 1) and return the
        new value.
        """
        with self._lock:
            if 0 <= self.value < self.max_value:
                self.value += value
            else:
                self.reset()
            return self.value

    def reset(self):
        self.value = 0

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return self.__str__()


class HTTPProvider(object):
    """An HTTP Provider for API request.

    :param endpoint_uri: HTTP API URL base. Default value is ``"https://api.trongrid.io/"``. Can also be configured via
        the ``TRONPY_HTTP_PROVIDER_URI`` environment variable.
    :param timeout: HTTP timeout in seconds.
    :param api_key: TronGRID API Key in str, or list of str.
    """

    def __init__(
        self,
        endpoint_uri: Union[str, dict] = None,
        timeout: float = DEFAULT_TIMEOUT,
        api_key: Union[str, List[str]] = None,
    ):
        super().__init__()

        if endpoint_uri is None:
            self.endpoint_uri = os.environ.get("TRONPY_HTTP_PROVIDER_URI", "https://api.trongrid.io/")
        elif isinstance(endpoint_uri, (dict,)):
            self.endpoint_uri = endpoint_uri["fullnode"]
        elif isinstance(endpoint_uri, (str,)):
            self.endpoint_uri = endpoint_uri
        else:
            raise TypeError("unknown endpoint uri {}".format(endpoint_uri))

        if 'trongrid' in self.endpoint_uri:
            self.use_api_key = True
            if isinstance(api_key, (str,)):
                self._api_keys = [api_key]
            elif isinstance(api_key, (list,)) and api_key:
                self._api_keys = api_key
            else:
                self._api_keys = DEFAULT_API_KEYS.copy()

            self._api_keys_length = len(self._api_keys)

            # Choose the start index randomly.
            self._api_keys_counter = AtomicCounter(
                initial=random.randint(0, self._api_keys_length - 1),
                max_value=self._api_keys_length - 1
            )

            self._default_api_keys = self._api_keys.copy()
        else:
            self.use_api_key = False

        self.sess = requests.session()
        self.sess.headers["User-Agent"] = "Tronpy/0.2"

        self.timeout = timeout
        """Request timeout in second."""

    def make_request(self, method: str, params: Any = None) -> dict:
        if self.use_api_key:
            self.sess.headers["Tron-Pro-Api-Key"] = self.serial_api_key  # Use serial api key to avoid collisions.

        if params is None:
            params = {}
        url = urljoin(self.endpoint_uri, method)
        resp = self.sess.post(url, json=params, timeout=self.timeout)

        if self.use_api_key:
            if resp.status_code == 403 and b'Exceed the user daily usage' in resp.content:
                print("W:", resp.json().get('Error', 'rate limit!'), file=sys.stderr)
                self._handle_rate_limit()
                return self.make_request(method, params)

        resp.raise_for_status()
        return resp.json()

    @property
    def random_api_key(self):
        return random.choice(self._api_keys)

    @property
    def serial_api_key(self):
        return self._api_keys[self._api_keys_counter.incr()]

    def _handle_rate_limit(self):
        if len(self._api_keys) > 1:
            self._api_keys.remove(self.sess.headers["Tron-Pro-Api-Key"])
        else:
            print("W: Please add as-many API-Keys in HTTPProvider", file=sys.stderr)
            time.sleep(0.9)
