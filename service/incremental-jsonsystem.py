
from flask import Flask, request, abort, send_from_directory, Response
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
from sesamutils import sesam_logger, Dotdictify
from sesamutils.flask import serve

app = Flask(__name__)

logger = sesam_logger("incremental-jsonsystem", app=app)

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
        session.headers = self._config['headers']
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
        if not hasattr(self, "_token") or self._token["expires_at"] < datetime.datetime.now().timestamp():
            oauth2_client = BackendApplicationClient(client_id=self._config["oauth2"]["client_id"])
            session = OAuth2Session(client=oauth2_client)
            logger.info("Updating token...")
            self._token = session.fetch_token(**self._config["oauth2"])

        logger.debug("ExpiresAt={}, now={}, diff={}".format(str(self._token.get("expires_at")), str(datetime.datetime.now().timestamp()) ,str(self._token.get("expires_at", 0)-datetime.datetime.now().timestamp())))
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

def generate_response_data(url, microservice_args, args_to_forward):
    is_first_yield = True
    is_limit_reached = False
    entity_count = 0
    limit = int(microservice_args.get('limit')) if microservice_args.get('limit') else None
    if microservice_args.get('ms_pagenum_param_at_src') and args_to_forward[microservice_args.get('ms_pagenum_param_at_src')]:
        pagenum = int(args_to_forward[microservice_args.get('ms_pagenum_param_at_src')])
    yield '['
    try:
        with SYSTEM.make_session() as s:
            while True:
                logger.debug('Getting from url={}, with params={}, with do_page={}, with headers={}'.format(url, args_to_forward, microservice_args.get('do_page'),s.headers))
                r = s.get(url, params=args_to_forward)
                if r.status_code not in [200, 204]:
                    logger.debug("Error {}:{}".format(r.status_code, r.text))
                    abort(r.status_code, r.text)

                rst = r.json() if r.ok else []
                if isinstance(rst, dict):
                    rst = [] if rst == {} else [rst]
                logger.debug('Got {} entities'.format(len(rst)))

                #read data from the data_property in the response json
                rst_data = []
                if microservice_args.get('ms_data_property'):
                    for entity in rst:
                        entity_doctified = Dotdictify(entity)
                        dp = entity_doctified.get(microservice_args.get('ms_data_property'))
                        if isinstance(dp, list):
                            rst_data.extend(dp)
                        else:
                            rst_data.append(dp)
                else:
                    rst_data = rst

                #apply sorting by updated_property
                if microservice_args.get('ms_do_sort'):
                    def get_updated_property(myjson):
                        myjson_dotdictified =  Dotdictify(myjson)
                        return myjson_dotdictified.get(microservice_args.get('ms_updated_property'))
                    rst_data.sort(key=get_updated_property, reverse=False)

                entity_count += len(rst_data)
                # apply limit'ing
                if limit:
                    limit = limit - len(rst_data)
                    if limit < 0:
                        rst_data = rst_data[0:limit]
                        is_limit_reached = True

                #sesamify and generate final response data
                entities_to_return = []
                if microservice_args.get('call_issued_time') or microservice_args.get('ms_updated_property'):
                    for data in rst_data:
                        if microservice_args.get('call_issued_time'):
                            data["_updated"] = microservice_args.get('call_issued_time')
                        elif microservice_args.get('ms_updated_property'):
                            data_dotdictified = Dotdictify(data)
                            data["_updated"] = str(data_dotdictified.get(microservice_args.get('ms_updated_property')))
                        entities_to_return.append(data)
                else:
                    entities_to_return = rst_data

                for entity in entities_to_return:
                    if is_first_yield:
                        is_first_yield = False
                    else:
                        yield ','
                    yield json.dumps(entity)

                if not microservice_args.get('do_page') or len(entities_to_return) == 0 or is_limit_reached:
                        break
                else:
                    pagenum+=1
                    args_to_forward[microservice_args.get('ms_pagenum_param_at_src')] = pagenum
        yield ']'
    except Exception as err:
        yield error_handling()

def parse_qs(request):
    microservice_args = {'since':None, 'limit':None, 'ms_updated_property': UPDATED_PROPERTY,
                        'ms_offset_bigger_and_equal': OFFSET_BIGGER_AND_EQUAL, 'ms_do_sort':False,
                        'ms_data_property':None, 'ms_since_param_at_src':None,
                        'ms_limit_param_at_src':None, 'ms_pagenum_param_at_src':None,
                        'ms_use_currenttime_as_updated': False}
    limit = request.args.get('limit')
    since = request.args.get('since')

    if since:
        url = UPDATED_URL_PATTERN.replace('__path__', request.path[1:])
        url = url.replace('__since__', since)
    else:
        url = FULL_URL_PATTERN.replace('__path__', request.path[1:])

    if limit:
        url = url.replace('__limit__', limit)

    parsed_url = urllib.parse.urlsplit(url)
    url = urllib.parse.urlunsplit((parsed_url[0],parsed_url[1],parsed_url[2], None, parsed_url[4]))
    url_args = urllib.parse.parse_qs(parsed_url[3])
    request_args = urllib.parse.parse_qs(request.query_string.decode('utf-8'))
    #collect microservice_args from url_args and request_args giving the latter higher precedence
    for arg in microservice_args.keys():
        value = url_args.get(arg, [None])[0]
        if isinstance(value, bool):
            value = (value.lower() == "true")
        microservice_args[arg] = value

    for arg in microservice_args.keys():
        value = request_args.get(arg, [None])[0]
        if isinstance(value, bool):
            value = (value.lower() == "true")
        if value:
            microservice_args[arg] = value

    #set call_issued_time to use as _updated value
    if microservice_args.get('ms_use_currenttime_as_updated'):
        microservice_args.set('call_issued_time', datetime.datetime.now().isoformat())
    del microservice_args['ms_use_currenttime_as_updated']

    #collect args_to_forward from url_args and request_args giving the latter higher precedence
    args_to_forward = {}
    for key, value in url_args.items():
        if key not in microservice_args:
            args_to_forward.setdefault(key, value[0])
    for key, value in request_args.items():
        if key not in microservice_args:
            args_to_forward[key] = value[0]

    if microservice_args.get('ms_pagenum_param_at_src') and args_to_forward.get(microservice_args.get('ms_pagenum_param_at_src')):
        microservice_args['do_page'] = True
    if 'since' in urllib.parse.parse_qs(parsed_url[3]):
        microservice_args['ms_since_param_at_src'] = 'since'
    if 'limit' in urllib.parse.parse_qs(parsed_url[3]):
        microservice_args['ms_since_param_at_src'] = 'limit'

    if since:
        if microservice_args.get('ms_since_param_at_src'):
            args_to_forward[microservice_args.get('ms_since_param_at_src')] = since
        if '__since__' in url:
            logger.debug('Since is {}, with the value {}'.format(str(type(since)), since))
            regex_iso_date_format = '^\d{4}-[01]\d-[0-3]\dT[0-2]\d:[0-5]\d:[0-5]\d(\.\d{0,7}){0,1}([+-][0-2]\d:[0-5]\d|Z)?'
            try:
                if re.match(regex_iso_date_format, since):
                    logger.debug("SINCE IS A ISO DATE: {}".format(since))
                    since = urllib.parse.quote(since)
                elif isinstance(int(since), int):
                    logger.debug("SINCE IS A VALID INT: {}".format(since))
                    if microservice_args.get('ms_offset_bigger_and_equal'):
                        since = str(int(since) + 1)
            except Exception as ex:
                logging.error(error_handling())
            url = url.replace('__since__', since)
            logger.debug("URL WITH SINCE:{}".format(url))
    else:
        logger.debug("URL WITHOUT SINCE:{}".format(url))
    if limit:
        if microservice_args.get('ms_limit_param_at_src'):
            args_to_forward[microservice_args.get('ms_limit_param_at_src')] = limit
        if '__limit__' in url:
            url = url.replace('__limit__', limit)
        if limit and not microservice_args.get('ms_limit_param_at_src'):
            microservice_args[limit] = int(limit)
    return url, microservice_args, args_to_forward


@app.route("/<path:path>", methods=["GET"])
def get_data(path):
    try:
        url, microservice_args, args_to_forward = parse_qs(request)
        response_data = generate_response_data(url, microservice_args, args_to_forward)
        return Response(response=response_data, content_type="application/json")
    except Exception as e:
        exception_str = error_handling()
        logging.error(exception_str)
        return abort(500, exception_str)


if __name__ == '__main__':
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
    if not auth_type:
        SYSTEM = OpenUrlSystem(config)
    elif auth_type.upper() == 'OAUTH2':
        SYSTEM = Oauth2System(config)

    if os.environ.get('WEBFRAMEWORK', '').lower() == 'flask':
        app.run(debug=True, host='0.0.0.0', port=int(
            os.environ.get('PORT', 5000)))
    else:
        serve(app,int(os.environ.get("PORT", 5000)))
