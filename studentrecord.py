import requests
import urlparse
import json


class StudentRecordException(Exception):
    """
    This is the base class for all exceptions from this API.
    """


class LoginException(StudentRecordException):
    """
    Raised when there's an issue with the given email/password/auth token.
    """


class NotFound(StudentRecordException):
    """
    Raised when a 404 is returned from the API.
    """


class EndpointIterator(object):
    def __init__(self, api, endpoint, **kwargs):
        self.api = api
        self.endpoint = endpoint
        self.args = kwargs
        self.args['_skip'] = 0
        self.current = None
        self.index = None

    def __iter__(self):
        return self

    def next(self):
        if self.current is None:
            self.current = self.api.get(self.endpoint, **self.args)
            self.index = 0
        if self.index == len(self.current['data']):
            if not self.current['has_more']:
                raise StopIteration
            self.args['_skip'] += len(self.current['data'])
            self.current = self.api.get(self.endpoint, **self.args)
            self.index = 0
        index = self.index
        self.index += 1
        return self.current['data'][index]


class Endpoint(object):
    """
    Endpoint objects represent a connection to a type of API at
    StudentRecord.com.  From here, we can make queries of the data and
    create/update/delete objects.
    """
    def __init__(self, api, endpoint, filters=None):
        self.api = api
        self.endpoint = endpoint
        self.filters = filters or {}

    def __iter__(self):
        """
        Allows iterating through the (possibly filtered) list of objects at
        this endpoint.

        >>> for item in endpoint:
        ...    print item['id']

        or

        >>> for item in endpoint.filter(location__state='MA'):
        ...     item 'in Boston', item
        """
        return EndpointIterator(self.api, self.endpoint,
                                **self.filters)

    def exists(self, **filters):
        """
        Returns a boolean indicating whether objects with the given filters
        exists.
        """
        filters = dict(self.filters, **filters)
        return bool(self.api.get(self.endpoint, _limit=1,
                                 _fields='id', **filters)['data'])

    def filter(self, **kwargs):
        """
        Returns an Endpoint with the additional filters specified as keyword
        arguments.  Pass in no kwargs to reset the filters.
        """
        if not kwargs:
            return Endpoint(self.api, self.endpoint)
        return Endpoint(self.api, self.endpoint, dict(self.filters,
                                                      **kwargs))

    def __getitem__(self, item):
        """
        Returns a chunk of objects from the endpoint.  Three types of data are
        allowed here:

        >>> endpoint[5:10]       # returns items 5 through 10
        >>> endpoint[0]          # returns the first item
        >>> endpoint[object_id]  # returns the item with ID `object_id`
        """
        if isinstance(item, slice):
            skip = item.start or 0
            limit = item.stop - skip if item.stop else 1000
            return self.api.get(self.endpoint,
                                _skip=skip,
                                _limit=limit,
                                **self.filters)['data']
        elif isinstance(item, int):
            data = self.api.get(self.endpoint,
                                _skip=item,
                                _limit=1,
                                **self.filters)
            if data['data']:
                return data['data'][0]
            else:
                raise IndexError
        else:
            return self.api.get(self.endpoint, item)

    def __setitem__(self, item, data):
        """
        A shortcut for `.update()`.

        >>> endpoint[id] = new_data  # is equivalent to
        >>> endpoint.update(id, **new_data)
        """
        response = self.update(item, **data)
        if isinstance(item, dict):
            # if a populated item was passed in, update it with the data
            # returned from the endpoint
            item.update(response)

    def __delitem__(self, item):
        """
        A shortcut for `.remove()`

        >>> del endpoint[id]  # is equivalent to
        >>> endpoint.remove(id)
        """
        self.remove(item)

    def create(self, _data=None, **kwargs):
        """
        Creates a new object at this endpoint.  All keyword arguments are
        passed as data to the endpoint.  Returns the new object as returned
        by the endpoint.
        """
        if _data is None:
            data = kwargs
        else:
            data = dict(_data, **kwargs)
        return self.api.post(self.endpoint, **data)

    def update(self, _data=None, **kwargs):
        """
        Updates a given object at this endpoint.  Takes either a populated
        object or an ID as the first argument; other keyword arguments are
        included as well.  Returns the updated object as returned by the
        endpoint.
        """
        if _data is None:
            data = kwargs
        elif isinstance(_data, dict):
            data = dict(_data, **kwargs)
        else:
            data = kwargs
            data['id'] = _data
        if 'id' not in data:
            raise StudentRecordException('unable to update %s without id' %
                                         self.endpoint.title())
        return self.api.put(self.endpoint, data['id'], **data)

    def remove(self, _id):
        """
        Removes a given object as this endpoint.  Takes either a populated
        object or an ID.
        """
        if isinstance(_id, dict):
            # passed in an actual item
            _id = _id['id']
        return self.api.delete(self.endpoint, _id)


class StudentRecord(object):
    """
    StudentRecord represents the base of the StudentRecord.com API.  Using
    this object, you have easy access to all of the StudentRecord.com
    endpoints.  This class handles the authentication and basic requests, but
    most of your work will be through an `Endpoint` object.

    >>> sr = StudentRecord(('mail@example.com', 'password'))  # or an API token
    >>> first_customer = sr.customer[0]
    >>> sr.choose_customer(first_customer)
    >>> org = sr.organization.filter(name='Matchbox, Inc.')[0]
    >>> sr.organization.update(org, name='Different Name')
    >>> sr.organization.update(org)  # goes back to the old data
    >>> sr.organization.delete(org)
    >>> sr.organization[org['id']]  # raises NotFound
    >>> org = sr.organization.create(name='New Organization')
    """
    scheme = 'https'
    host = 'api.studentrecord.com'
    version = 'v1'

    def __init__(self, auth=None, **kwargs):
        if not isinstance(auth, (list, tuple, basestring)):
            raise TypeError(
                '`auth` must be either a tuple of (email, password) or an '
                'authorization token')
        self.auth = auth
        if isinstance(auth, basestring):
            self._auth_token = auth
        else:
            self._auth_token = None

        self._customer = None

        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def choose_customer(self, customer):
        """
        Set the current customer for the API.  Only the 'login' and 'customer'
        endpoints do not require this.
        """
        if isinstance(customer, dict):
            self._customer = customer['id']
        else:
            self._customer = customer

    @property
    def auth_token(self):
        """
        Returns the current authentication token.  If we don't have one, logs
        us in to get it.
        """
        if self._auth_token is None:
            response = requests.post(self.url('login'), data=dict(
                email=self.auth[0],
                password=self.auth[1]))
            if response.status_code != 200:
                raise LoginException('invalid username/password',
                                     response.content)
            self._auth_token = response.json['authentication_token']
        return self._auth_token

    @property
    def headers(self):
        return {'Authentication-Token': self.auth_token}

    def url(self, endpoint, _id=None):
        """
        Builds a URL for the given endpoint.  If `_id` is given, it's used as
        the object ID to pass to the endpoint.
        """
        if endpoint not in ('login', 'customer'):
            if not self._customer:
                raise StudentRecordException(
                    '%r endpoint requires a customer' % endpoint)
            endpoint = '%s/%s' % (self._customer, endpoint)
        if _id is not None:
            endpoint = '%s/%s' % (endpoint, _id)
        return urlparse.urlunparse((self.scheme, self.host, '/api/%s/%s/' % (
            self.version, endpoint), '', '', ''))

    def dispatch(self, method, endpoint, _id=None, **kwargs):
        """
        Base method to make a request to StudentRecord.com.

        method: the HTTP method (lowercase)
        endpoint: the API endpoint (person, organization, &c)
        _id: optional object ID

        Any additional keyword arguments are passed in a URL arguments (GET
        requests) or as JSON data (POST/PUT requests).
        """
        if method == 'get':
            params = kwargs
            data = None
        else:
            params = None
            data = json.dumps(kwargs)
        resp = requests.request(method, self.url(endpoint, _id), params=params,
                                data=data,
                                headers=self.headers)
        if resp.status_code == 401:
            # Unauthorized
            raise LoginException('invalid authorization')
        elif resp.status_code == 404:
            raise NotFound(self.url(endpoint, _id))
        if resp.status_code != 200:
            raise StudentRecordException(
                '%i from %s' % (resp.status_code, resp.url),
                resp.content)
        return resp.json

    def get(self, endpoint, _id=None, **kwargs):
        """
        Shortcut to make a GET request.
        """
        return self.dispatch('get', endpoint, _id, **kwargs)

    def put(self, endpoint, _id, **kwargs):
        """
        Shortcut to make a PUT request.
        """
        return self.dispatch('put', endpoint, _id, **kwargs)

    def post(self, endpoint, **kwargs):
        """
        Shortcut to make a POST request.
        """
        return self.dispatch('post', endpoint, **kwargs)

    def delete(self, endpoint, _id, **kwargs):
        """
        Shortcut to make a DELETE request.
        """
        return self.dispatch('delete', endpoint, _id, **kwargs)

    # data endpoints
    def __getattr__(self, attr):
        """
        If we don't recognize the attribute, make an API Endpoint to access
        that data.

        >>> sr = StudentRecord(auth=auth)
        >>> sr.person
        <Endpoint>
        >>> sr.organization
        <Endpoint>
        >>> sr.applicant
        <Endpoint>
        """
        return Endpoint(self, attr)
