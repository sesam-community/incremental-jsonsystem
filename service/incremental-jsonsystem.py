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
import logger as log

app = Flask(__name__)

SYSTEM = None
FULL_URL_PATTERN = None
UPDATED_URL_PATTERN = None
UPDATED_PROPERTY = None
OFFSET_BIGGER_AND_EQUAL = None


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

        logger.debug("ExpiresAt={}, now={}, diff={}".format(str(self._token.get("expires_at")), str(datetime.datetime.utcnow().timestamp()) ,str(self._token.get("expires_at", 0)-datetime.datetime.utcnow().timestamp())))
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
    updated_property_in_effect = request.args.get('ms_updated_property',UPDATED_PROPERTY)
    offset_bigger_and_equal_in_effect = request.args.get('ms_offset_bigger_and_equal',OFFSET_BIGGER_AND_EQUAL).lower() == "true"
    do_sort = request.args.get('ms_do_sort',"false").lower() == "true"
    data_property = request.args.get('ms_data_property')
    since_param_at_src = request.args.get('ms_since_param_at_src')
    limit_param_at_src = request.args.get('ms_limit_param_at_src')

    args_to_forward = {}
    for key, value in request.args.items():
        if key not in ['since','limit','ms_updated_property','ms_offset_bigger_and_equal','ms_do_sort','ms_data_property','ms_since_param_at_src','ms_limit_param_at_src']:
            args_to_forward[key] = value

    if since:
        url = UPDATED_URL_PATTERN.replace('__path__', path)
        if since_param_at_src:
            args_to_forward[since_param_at_src] = since
        if '__since__' in url:
            logger.debug('Since is {}, with the value {}'.format(str(type(since)), since))
            regex_iso_date_format = '^\d{4}-[01]\d-[0-3]\dT[0-2]\d:[0-5]\d:[0-5]\d(\.\d{0,7}){0,1}([+-][0-2]\d:[0-5]\d|Z)?'
            try:
                if re.match(regex_iso_date_format, since):
                    logger.debug("SINCE IS A ISO DATE: {}".format(since))
                    since = urllib.parse.quote(since)
                elif isinstance(int(since), int):
                    logger.debug("SINCE IS A VALID INT: {}".format(since))
                    if offset_bigger_and_equal_in_effect:
                        since = str(int(since) + 1)
            except Exception as ex:
                logging.error(error_handling())
            url = url.replace('__since__', since)
            logger.debug("URL WITH SINCE:{}".format(url))
    else:
        url = FULL_URL_PATTERN.replace('__path__', path)
        logger.debug("URL WITHOUT SINCE:{}".format(url))
    if limit:
        if limit_param_at_src:
            args_to_forward[limit_param_at_src] = limit
        if '__limit__' in url:
            url = url.replace('__limit__', limit)
    try:
        with SYSTEM.make_session() as s:
            logger.debug('Getting from url={}, with params={}'.format(url, args_to_forward))
            r = s.get(url, params=args_to_forward)

        if r.status_code not in [200, 204]:
            logger.debug("Error {}:{}".format(r.status_code, r.text))
            abort(r.status_code, r.text)
        rst = r.json() if r.status_code == 200 else []
        if type(rst) == dict:
            rst = [rst]
        logger.debug('Got {} entities'.format(len(rst)))

        #read data from the data_property in the response json
        rst_data = []
        if data_property:
            for entity in rst:
                rst_data.extend(entity[data_property])
        else:
            rst_data = rst

        #apply sorting by updated_property
        if do_sort:
            def get_updated_property(myjson):
                return myjson[updated_property_in_effect]
            rst_data.sort(key=get_updated_property, reverse=False)

        # apply limit'ing
        if limit and not limit_param_at_src:
            limit = int(limit) if limit else -1
            if limit > 0:
                rst_data = rst_data[0:limit]

        #sesamify and generate final response data
        entities_to_return = []
        for data in rst_data:
            data["_updated"] = data[updated_property_in_effect]
            entities_to_return.append(data)
        return json.dumps(entities_to_return)
    except Exception as e:
        exception_str = error_handling()
        logging.error(exception_str)
        return abort(500, exception_str)


if __name__ == '__main__':
    # Set up logging
    logger = log.init_logger('freshdesk-rest-service', os.getenv('LOGLEVEL', 'INFO'))

    FULL_URL_PATTERN = get_var('FULL_URL_PATTERN')
    UPDATED_URL_PATTERN = get_var('UPDATED_URL_PATTERN')
    UPDATED_PROPERTY = get_var('UPDATED_PROPERTY')
    OFFSET_BIGGER_AND_EQUAL = get_var('OFFSET_BIGGER_AND_EQUAL')
    auth_type = get_var('AUTHENTICATION')
    config = json.loads(get_var('CONFIG'))

    print('STARTED UP WITH:')
    print('\tFULL_URL_PATTERN={}'.format(FULL_URL_PATTERN))
    print('\tUPDATED_URL_PATTERN={}'.format(UPDATED_URL_PATTERN))
    print('\tUPDATED_PROPERTY={}'.format(UPDATED_PROPERTY))
    print('\tOFFSET_BIGGER_AND_EQUAL={}'.format(OFFSET_BIGGER_AND_EQUAL))
    print('\tauth_type={}'.format(auth_type))
    if auth_type.upper() == 'OAUTH2':
        SYSTEM = Oauth2System(config)
    else:
        SYSTEM = OpenUrlSystem(config)


    if os.environ.get('WEBFRAMEWORK', '').lower() == 'flask':
        app.run(debug=True, host='0.0.0.0', port=int(
            os.environ.get('PORT', 5000)))
    else:
        import cherrypy
        app = log.add_access_logger(app, logger)
        cherrypy.tree.graft(app, '/')

        # Set the configuration of the web server to production mode
        cherrypy.config.update({
            'environment': 'production',
            'engine.autoreload_on': False,
            'log.screen': True,
            'server.socket_port': int(os.environ.get("PORT", 5000)),
            'server.socket_host': '0.0.0.0'
        })

        # Start the CherryPy WSGI web server
        cherrypy.engine.start()
        cherrypy.engine.block()
        #app.run(threaded=True, debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
