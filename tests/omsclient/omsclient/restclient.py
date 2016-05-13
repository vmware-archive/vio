import logging
import requests

LOG = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings()


class RestClient(object):
    """OMS RestClient

    This is the client implementation based on "requests".
    """
    _URL_TEMPLATE_PREFIX = "https://%s:8443/oms/%s"

    def __init__(self, server, username, password):
        """Create a connection to the remote OMS server

        :param server: IP or hostname of the OMS server
        :param username: User name
        :param password: Password
        :return: None
        """
        self._server = server
        self._username = username
        self._password = password

        # TODO Do we need to have logout logic?
        self._session = self._login()

    def _api_url(self, path):
        api_url_template = "api/%s"
        api_path = api_url_template % path
        return self._URL_TEMPLATE_PREFIX % (self._server, api_path)

    def _login_url(self):
        login_url_template = \
            "j_spring_security_check?j_username=%s&j_password=%s"
        login_url = login_url_template % (self._username, self._password)
        return self._URL_TEMPLATE_PREFIX % (self._server, login_url)

    def _login(self):
        session = requests.Session()

        LOG.debug("Request login...")
        response = session.post(self._login_url(), verify=False)
        LOG.debug(response)

        return session

    def login(self):
        self._session = self._login()

    def do_get(self, path):
        url = self._api_url(path)

        LOG.debug("Request GET: %s" % url)
        response = self._session.get(url, verify=False)
        LOG.debug(response)

        return response

    def do_delete(self, path, object_id):
        url = self._api_url(path) + "/" + object_id

        LOG.debug("Request DELETE: %s" % url)
        response = self._session.delete(url, verify=False)
        LOG.debug(response)
        return response

    def do_post(self, path, data):
        url = self._api_url(path)
        headers = {'Content-type': 'application/json'}

        LOG.debug("Request POST: %s" % url)
        response = self._session.post(url, data, headers=headers, verify=False)
        LOG.debug(response)
        return response

    def do_put(self, path, data):
        url = self._api_url(path)
        headers = {'Content-type': 'application/json'}
        LOG.debug("Request PUT: %s" % url)

        response = self._session.put(url, data, headers=headers, verify=False)
        LOG.debug(response)
        return response
