from flask import Flask, request, abort
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
import requests
from datetime import datetime

import json
import logging
import os

app = Flask(__name__)

SYSTEM = None
URL_PATTERN = None
UPDATED_PROPERTY = None


def get_updated_property(json):
    """
    Sort function
    """
    return json[UPDATED_PROPERTY]


def get_var(var):
    envvar = None
    if var.upper() in os.environ:
        envvar = os.environ[var.upper()]
    else:
        envvar = request.args.get(var)
    logger.debug("Setting %s = %s" % (var, envvar))
    return envvar


class OpenUrlSystem():
    def __init__(self, config):
        self._confg = config

    def make_session(self):
        session = requests.Session()
        session.headers = self.config['headers']
        return session


class Oauth2System():
    def __init__(self, config):
        """init AzureOauth2Client with a json config"""
        self._config = config
        self._get_token()

    def _get_token(self):
        """docstring for get_session"""
        # If no token has been created yet or if the previous token has expired, fetch a new access token
        # before returning the session to the callee
        if not hasattr(self, "_token") or self._token["expires_at"] < datetime.utcnow().timestamp():
            oauth2_client = BackendApplicationClient(client_id=self._config["oauth2"]["client_id"])
            session = OAuth2Session(client=oauth2_client)
            # self._token = session.fetch_token(token_url=self._config["token_url"],
            #                                  client_id=self._config["client_id"],
            #                                  client_secret=self._config["client_secret"],
            #                                  resource=self._config["resource"])
            logger.info("Updating token...")
            self._token = session.fetch_token(**self._config["oauth2"])

        return self._token

    def make_session(self):
        token = self._get_token()
        client = BackendApplicationClient(client_id=self._config["oauth2"]["client_id"])
        session = OAuth2Session(client=client, token=token)
        if 'headers' in self._config:
            session.headers = self._config['headers']
        return session


@app.route("/<path:path>", methods=["GET"])
def get_data(path):
    since = request.args.get('since')
    limit = request.args.get('limit')
    url = URL_PATTERN.replace('__path__', path)
    if since:
        url = url.replace('__since__', since)
    if limit:
        url = url.replace('__limit__', limit)
    try:
        with SYSTEM.make_session() as s:
            logger.debug('Getting from {}'.format(url))
            r = s.get(url)

        if r.status_code != 200:
            abort(r.status_code, r.text)
        rst = r.json()
        logger.debug('Got {} entities'.format(len(rst)))
        truncated = None
        limit = int(limit) if limit else -1
        if limit > 0 and limit < len(rst):
            # Todo: support datetime sorting
            rst.sort(key=get_updated_property, reverse=False)
            truncated = rst[0:limit]
        if truncated is None:
            truncated = rst
        entities = []
        for data in truncated:
            data["_updated"] = data[UPDATED_PROPERTY]
            entities.append(data)
        return json.dumps(entities)
    except Exception as e:
        return abort(500, e)


if __name__ == '__main__':
    # Set up logging
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logger = logging.getLogger('incremental-jsonsystem')

    # Log to stdout
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(logging.Formatter(format_string))
    logger.addHandler(stdout_handler)

    loglevel = os.environ.get("LOGLEVEL", "INFO")
    if "INFO" == loglevel.upper():
        logger.setLevel(logging.INFO)
    elif "DEBUG" == loglevel.upper():
        logger.setLevel(logging.DEBUG)
    elif "WARN" == loglevel.upper():
        logger.setLevel(logging.WARN)
    elif "ERROR" == loglevel.upper():
        logger.setLevel(logging.ERROR)
    else:
        logger.setlevel(logging.INFO)
        logger.info("Define an unsupported loglevel. Using the default level: INFO.")

    URL_PATTERN = get_var('URL_PATTERN')
    UPDATED_PROPERTY = get_var('UPDATED_PROPERTY')
    auth_type = get_var('AUTHENTICATION')
    config = json.loads(get_var('CONFIG'))
    if auth_type.upper() == 'OAUTH2':
        SYSTEM = Oauth2System(config)
    else:
        SYSTEM = OpenUrlSystem(config)
    app.run(threaded=True, debug=True, host='0.0.0.0')
