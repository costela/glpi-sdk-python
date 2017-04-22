# Copyright 2017 Predict & Truly Systems All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# GLPI API Rest documentation:
# https://github.com/glpi-project/glpi/blob/9.1/bugfixes/apirest.md

import json as json_import
import requests
from requests.structures import CaseInsensitiveDict
import os

from version import __version__


def load_from_vcap_services(service_name):
    vcap_services = os.getenv("VCAP_SERVICES")
    if vcap_services is not None:
        services = json_import.loads(vcap_services)
        if service_name in services:
            return services[service_name][0]["credentials"]
    else:
        return None


def _remove_null_values(dictionary):
    if isinstance(dictionary, dict):
        return dict([(k, v) for k, v in dictionary.items() if v is not None])
    return dictionary


def _cleanup_param_value(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return value


def _cleanup_param_values(dictionary):
    if isinstance(dictionary, dict):
        return dict(
            [(k, _cleanup_param_value(v)) for k, v in dictionary.items()])
    return dictionary


class GlpiException(Exception):
    pass


class GlpiInvalidArgument(GlpiException):
    pass


class GlpiService(object):
    """ Polymorphic class of GLPI REST API Service. """

    def __init__(self, url_apirest, token_app, uri,
                 username=None, password=None, token_auth=None,
                 use_vcap_services=False, vcap_services_name=None):
        """
        [TODO] Loads credentials from the VCAP_SERVICES environment variable if
        available, preferring credentials explicitly set in the request.
        If VCAP_SERVICES is not found (or use_vcap_services is set to False),
        username and password credentials must be specified.

        You can choose in setup initial authentication using username and
        password, or setup with Authorization HTTP token. If token_auth is set,
        username and password credentials must be ignored.
        """
        self.__version__ = __version__
        self.url = url_apirest
        self.app_token = token_app
        self.uri = uri

        self.username = username
        self.password = password
        self.token_auth = token_auth

        self.session = None

        if token_auth is not None:
            if username is not None or password is not None:
                raise GlpiInvalidArgument(
                    'Cannot set token_auth and username and password together')
            self.set_token_auth(token_auth)
        else:
            self.set_username_and_password(username, password)

        if use_vcap_services and not self.username and not self.token_auth:
            self.vcap_service_credentials = load_from_vcap_services(
                vcap_services_name)
            if self.vcap_service_credentials is not None and isinstance(
                    self.vcap_service_credentials, dict):
                self.url = self.vcap_service_credentials['url']
                if 'username' in self.vcap_service_credentials:
                    self.username = self.vcap_service_credentials['username']
                if 'password' in self.vcap_service_credentials:
                    self.password = self.vcap_service_credentials['password']
                if 'token_auth' in self.vcap_service_credentials:
                    self.token_auth =\
                        self.vcap_service_credentials['token_auth']
                if 'app_token' in self.vcap_service_credentials:
                    self.app_token = self.vcap_service_credentials['app_token']

        if self.app_token is None:
            raise GlpiException(
                'You must specify GLPI API-Token(app_token) to make API calls')

        if (self.username is None or self.password is None)\
                and self.token_auth is None:
            raise GlpiException(
                'You must specify your username and password, or token_auth'
                'service credentials ')

    def set_username_and_password(self, username=None, password=None):
        if username == 'YOUR SERVICE USERNAME':
            username = None
        if password == 'YOUR SERVICE PASSWORD':
            password = None

        self.username = username
        self.password = password

    def set_token_auth(self, token_auth):
        if token_auth == 'YOUR AUTH TOKEN':
            token_auth = None

        self.token_auth = token_auth

    def set_uri(self, uri):
        self.uri = uri

    def get_version(self):
        return self.__version__

    """
    Session Token
    """
    def set_session_token(self):
        """ Set up new session ID """

        # URL should be like: http://glpi.example.com/apirest.php
        full_url = self.url + '/initSession'
        auth = None

        headers = {"App-Token": self.app_token,
                   "Content-Type": "application/json"}

        if self.token_auth is not None:
            auth = self.token_auth
        else:
            auth = (self.username, self.password)

        r = requests.request('GET', full_url,
                             auth=auth, headers=headers)

        try:
            self.session = r.json()['session_token']
            return True
        except Exception as e:
            raise Exception("Unable to init session in GLPI server: %s" % e)

        return False

    def get_session_token(self):
        """ Returns current session ID """

        if self.session is not None:
            return self.session
        else:
            if self.set_session_token():
                return self.session
            else:
                return 'Unable to get Session Token'

    def update_session_token(self, session_id):
        """ Update session ID """

        if session_id:
            self.session = session_id

        return self.session

    """ Request """
    # Could make this compute the label_id based on the variable name of the
    # dictionary passed in (using **kwargs), but
    # this might be confusing to understand.
    @staticmethod
    def unpack_id(dictionary, label_id):
        if isinstance(dictionary, dict) and label_id in dictionary:
            return dictionary[label_id]
        return dictionary

    @staticmethod
    def _get_error_message(response):
        """
        Gets the error message from a JSON response.
        {
            code: 400
            error: 'Bad request'
        }
        """
        error_message = 'Unknown error'
        try:
            error_json = response.json()
            if 'error' in error_json:
                if isinstance(error_json['error'], dict) and 'description' in \
                        error_json['error']:
                    error_message = 'Error: ' + error_json['error'][
                        'description']
                else:
                    error_message = 'Error: ' + error_json['error']
            elif 'error_message' in error_json:
                error_message = 'Error: ' + error_json['error_message']
            elif 'msg' in error_json:
                error_message = 'Error: ' + error_json['msg']
            elif 'statusInfo' in error_json:
                error_message = 'Error: ' + error_json['statusInfo']
            if 'description' in error_json:
                error_message += ', Description: ' + error_json['description']
            error_message += ', Code: ' + str(response.status_code)
        except:
            pass
        return error_message

    def request(self, method, url, accept_json=False, headers={},
                params=None, json=None, data=None, files=None, **kwargs):
        """ Make a request to GLPI Rest API """

        full_url = self.url + url
        if self.session is None:
            new_session = True

        input_headers = _remove_null_values(headers) if headers else {}

        headers = CaseInsensitiveDict(
             {'user-agent': 'glpi-sdk-python-' + __version__})

        if accept_json:
            headers['accept'] = 'application/json'

        try:
            if self.session is None:
                self.set_session_token()
            headers.update({'Session-Token': self.session})
        except Exception as e:
            raise Exception("Unable to get Session token. ERROR: %s" % e)

        if self.app_token is not None:
            headers.update({'App-Token': self.app_token})

        headers.update(input_headers)

        # Remove keys with None values
        params = _remove_null_values(params)
        params = _cleanup_param_values(params)
        json = _remove_null_values(json)
        data = _remove_null_values(data)
        files = _remove_null_values(files)

        response = requests.request(method=method, url=full_url,
                                    headers=headers, params=params,
                                    data=data, **kwargs)

        if 200 <= response.status_code <= 299:
            if accept_json:
                response_json = response.json()
                if 'status' in response_json and response_json['status'] \
                        == 'ERROR':
                    response.status_code = 400
                    error_message = 'Unknown error'

                    if 'statusInfo' in response_json:
                        error_message = response_json['statusInfo']
                    if error_message == 'invalid-app-token':
                        response.status_code = 401
                    raise GlpiException('Error: ' + error_message)
                return response_json
            return response
        else:
            if response.status_code == 401:
                error_message = 'Unauthorized: Access is denied due to ' \
                                'invalid credentials '
            else:
                error_message = self._get_error_message(response)
            raise GlpiException(error_message)

    def get_payload(self, data_req):
        """ Extract payload for REST API from JSON data. """

        data_str = ""
        null_str = "<DEFAULT_NULL>"
        for k in data_req:
            if data_str is not "":
                data_str = "%s," % data_str

            if data_req[k] == null_str:
                data_str = '%s "%s": null' % (data_str, k)
            elif isinstance(data_req[k], str):
                data_str = '%s "%s": "%s"' % (data_str, k, data_req[k])
            else:
                data_str = '%s "%s": %s' % (data_str, k, str(data_req[k]))

        return data_str

    """ Generic Items methods """
    def get_all(self):
        """ Return all content of Item in JSON format. """

        res = self.request('GET', self.uri)
        return res.json()

    def get(self, item_id):
        """ Return the JSON item with ID item_id. """

        if isinstance(item_id, int):
            uri = '/%s/%d' % (self.uri, item_id)
            response = self.request('GET', uri)
            return response.json()
        else:
            return {'error_message': 'Unale to get %s ID [%s]' % (self.uri,
                                                                  item_id)}

    def create(self, object_data):
        """ Create an object Item. """

        if (object_data is None):
            return "{ 'error_message' : 'Object not found.'}"

        payload = '{"input": { %s }}' % (self.get_payload(object_data))
        response = self.request('POST', self.uri, data=payload,
                                accept_json=True)

        return response

    def search_options(self, item_name):

        new_uri = "%s/%s" % (self.uri, item_name)
        response = self.request('GET', new_uri, accept_json=True)

        return response


class GlpiItem(object):
    """ Polymorphic class of GLPI Item object. """

    def __init__(self, data={}):
        self.data = data
        self.null_str = "<DEFAULT_NULL>"

    def get_data(self):
        """ Returns entire attributes of Item data. """
        return self.data

    def get_attributes(self):
        """ Return an specific attribute of Item data. """
        return self.get_data()

    def get_attribute(self, attr):
        """ Returns an specific attribute. """
        if attr in self.data:
            return self.data[attr]

    def set_attribute(self, attr, value):
        """ Define the 'value' to an key. """
        self.data[attr] = value

    def set_attributes(self, attributes={}):
        """ Define attributes to override defaults.  """
        if attributes is {}:
            return self.data

        for k in attributes:
            if k in self.data.keys():
                self.data[k] = attributes[k]
            else:
                self.data.update({k: attributes[k]})

    def unset_attributes(self):
        """ Clean all attributes. """
        self.data = {}
        return self.data

    def get_stream(self):
        """ Get stream of data with format acceptable in GLPI API.  """
        input_data = ""
        for k in self.data:
            if input_data is not "":
                input_data = "%s," % input_data

            if self.data[k] == self.null_str:
                input_data = '%s "%s": null' % (input_data, k)
            elif isinstance(self.data[k], str):
                input_data = '%s "%s": "%s"' % (input_data, k, self.data[k])
            else:
                input_data = '%s "%s": %s' % (input_data, k, str(self.data[k]))

        return input_data


class GLPI(object):

    """
    Generic implementation of GLPI Items can manage all
    Itens in one GLPI server connection.
    We can use this class to save implementation of "new classes" and
    can reuse API sessions.
    To support new items you should create the dict key/value in item_map.
    """

    def __init__(self, url, app_token, auth_token,
                 item_map=None):
        """ Construct generic object """

        self.url = url
        self.app_token = app_token
        self.auth_token = auth_token

        self.item_uri = None
        self.item_map = {
            "ticket": "/Ticket",
            "knowbase": "/knowbaseitem",
            "listSearchOptions": "/listSearchOptions",
        }
        self.api_rest = None
        self.api_session = None

        if item_map is not None:
            self.set_item_map(item_map)

    def help_item(self):
        """ Help item values """
        return {"available_items": self.item_map}

    def set_item(self, item_name):
        """ Define an item to object """
        self.item_uri = self.item_map[item_name]

    def set_item_map(self, item_map={}):
        """ Set an custom item_map. """
        self.item_map = item_map

    def set_api_uri(self):
        """
        Update URI in Service API object.
        We should do this every new Item requested.
        """
        self.api_rest.set_uri(self.item_uri)

    def init_api(self):
        """ Initialize the API Rest connection """
        if self.item_uri is None:
            return {"message_error": "Please use set_item() before init API."}

        self.api_rest = GlpiService(self.url, self.app_token,
                                    self.item_uri, token_auth=self.auth_token)

        self.api_session = self.api_rest.get_session_token()

        if self.api_session is not None:
            return {"session_token": self.api_session}
        else:
            return {"message_error": "Unable to InitSession in GLPI Server."}

    def init_item(self, item_name):
        """ Initialize an Item context. """
        update_api = False

        if self.item_uri != self.item_map[item_name]:
            self.set_item(item_name)
            update_api = True

        if self.api_rest is None:
            try:
                self.init_api()
            except:
                print "message_error: Unable to InitSession in GLPI Server."
                return False

        if update_api:
            self.set_api_uri()

        return True

    # Itens operations
    def get_all(self, item_name):
        """ Get all resources from item_name """
        if not self.init_item(item_name):
            return {"message_error": "Unable to get Item in GLPI Server."}

        return self.api_rest.get_all()

    def get(self, item_name, item_id):
        """ Get item_name resource by ID """
        if not self.init_item(item_name):
            return {"message_error": "Unable to get Item by ID in GLPI Server."}

        return self.api_rest.get(item_id)

    def create(self, item_name, item_data):
        """ Create an Resource Item """
        if not self.init_item(item_name):
            return {"message_error": "Unable to create an Item in GLPI Server."}

        return self.api_rest.create(item_data)

    def search_options(self, item_name):
        if not self.init_item('listSearchOptions'):
            return {"message_error": "Unable to create an Item in GLPI Server."}

        return self.api_rest.search_options(item_name)

    def search_criteria(self, data, criteria):
        """ Search in data some criteria """
        result = []
        for d in data:
            find = False
            for c in criteria:
                if c['value'].lower() in d[c['field']].lower():
                    find = True
            if find:
                result.append(d)
        return result

    def search_metacriteria(self, metacriteria):
        """ TODO: Search in metacriteria in source Item """
        return {"message_info": "Not implemented yet"}

    def search(self, item_name, criteria):
        """
        Return an Item with that matchs with criteria
        criteria: [
            {
                "field": "name",
                "value": "search value"
            }
        ]
        """
        if criteria.has_key('criteria'):
            data = self.get_all(item_name)
            return self.search_criteria(data, criteria['criteria'])
        elif criteria.has_key('metacriteria'):
            return self.search_metacriteria(criteria['metacriteria'])
        else:
            return {"message_error": "Unable to find a valid criteria."}
