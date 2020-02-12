import requests
from requests import HTTPError

from common.utils import KWArgFormatter

PA_SYSTEM_URL = "http://voice:12101/api/text-to-speech"


class PASystem:

    @staticmethod
    def announce(announcement, **kwargs):
        response = requests.post(PA_SYSTEM_URL,
                                 data=KWArgFormatter().format(str(announcement), **kwargs),
                                 headers={
                                     "Content-Type": "text/plain",
                                     "Accept": "application/json, text/plain, */*"
                                 })
        try:
            response.raise_for_status()
            print(str(response.content))
        except HTTPError as err:
            print(str(err))
