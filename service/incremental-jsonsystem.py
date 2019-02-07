from flask import Flask, request, abort, send_from_directory
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
import requests
import datetime

import json
import logging
import os
import re
import sys
import urllib.parse

app = Flask(__name__)

SYSTEM = None
FULL_URL_PATTERN = None
UPDATED_URL_PATTERN = None
UPDATED_PROPERTY = None
OFFSET_BIGGER_AND_EQUAL = None


def get_updated_property(json):
    return json[UPDATED_PROPERTY]


def get_var(var):
    envvar = None
    envvar = os.getenv(var.upper())
    logger.debug("Setting %s = %s" % (var, envvar))
    return envvar

def error_handling():
    return '{} - {}, at line {}'.format(sys.exc_info()[0],
                                    sys.exc_info()[1],
                                    sys.exc_info()[2].tb_lineno)
 


class OpenUrlSystem():
    def __init__(self, config):
        self._config = config

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
        if not hasattr(self, "_token") or self._token["expires_at"] < datetime.datetime.utcnow().timestamp():
            oauth2_client = BackendApplicationClient(client_id=self._config["oauth2"]["client_id"])
            session = OAuth2Session(client=oauth2_client)
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

# to remove favicon not found errormessages in the log
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                          'favicon.ico',mimetype='image/vnd.microsoft.icon')

@app.route("/<path:path>", methods=["GET"])
def get_data(path):
    since = request.args.get('since')
    limit = request.args.get('limit')
    if since:
        url = UPDATED_URL_PATTERN.replace('__path__', path)
        logger.debug('Since is {}, with the value {}'.format(str(type(since)), since))
        regex_iso_date_format = '^\d{4}-[01]\d-[0-3]\dT[0-2]\d:[0-5]\d:[0-5]\d(\.\d{0,7}){0,1}([+-][0-2]\d:[0-5]\d|Z)'
        try:
            if re.match(regex_iso_date_format, since):
                logger.debug("SINCE IS A ISO DATE: {}".format(since))
                since = urllib.parse.quote(since)
            elif isinstance(int(since), int):
                logger.debug("SINCE IS A VALID INT: {}".format(since))
                if OFFSET_BIGGER_AND_EQUAL.upper() == "TRUE":
                    since = str(int(since) + 1)
        except Exception as ex:
            logging.error(error_handling())
        url = url.replace('__since__', since)
        logger.debug("URL WITH SINCE:{}".format(url))
    else:
        url = FULL_URL_PATTERN.replace('__path__', path)
        logger.debug("URL WITHOUT SINCE:{}".format(url))
    if limit:
        url = url.replace('__limit__', limit)
    try:
        with SYSTEM.make_session() as s:
            logger.info('Getting from {}'.format(url))
            r = s.get(url)

        if r.status_code != 200:
            logger.debug("Error {}:{}".format(r.status_code, r.text))
            abort(r.status_code, r.text)
        rst = r.json()
        logger.info('Got {} entities'.format(len(rst)))
        truncated = None
        limit = int(limit) if limit else -1
        if limit > 0 and limit < len(rst):
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
        logging.error(error_handling())
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

    FULL_URL_PATTERN = get_var('FULL_URL_PATTERN')
    UPDATED_URL_PATTERN = get_var('UPDATED_URL_PATTERN')
    UPDATED_PROPERTY = get_var('UPDATED_PROPERTY')
    OFFSET_BIGGER_AND_EQUAL = get_var('OFFSET_BIGGER_AND_EQUAL')
    auth_type = get_var('AUTHENTICATION')
    config = json.loads(get_var('CONFIG'))
    if auth_type.upper() == 'OAUTH2':
        SYSTEM = Oauth2System(config)
    else:
        SYSTEM = OpenUrlSystem(config)
    app.run(threaded=True, debug=True, host='0.0.0.0')
