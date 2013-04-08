"""
This example takes a YAML file representing the data you'd like to push
to StudentRecord.com and maps it to API requests.

There's an example YAML file in examples/csv_import.yaml, but the general
features are:

* Each endpoint has a YAML hash associated with it, which maps CSV rows to
that type of object.
* You can refer to a previously created object like `person[key]`, where that
person has a `_key` attribute.
* Values are specified as CSV column names.  If the column isn't found, it's
assumed that it's a regular string.
"""
import studentrecord
import sys
import csv
import yaml

if len(sys.argv) not in (3, 4):
    print ('Usage: %s <configuration file> '
           '(<email> <password>|<auth token>) < <file>' % (
               sys.argv[0],))
    print
    print __doc__
    sys.exit(-1)


data = yaml.load(file(sys.argv[1]))

if len(sys.argv) == 3:
    auth = sys.argv[2]
else:
    auth = sys.argv[2:4]
sr = studentrecord.StudentRecord(auth)
sr.auth_token  # make sure we're authenticated
# TODO allow picking a customer from the list
sr.choose_customer(sr['customer'][0])


class CSVMapping(object):
    """
    This takes care of mapping the values in the CSV file into a dictionary
    that we can pass to the API.
    """
    def __init__(self, mapping):
        self.mapping = mapping

    def build(self, row):
        """
        Build a dictionary for the given row.
        """
        return self._build(row, self.mapping)

    def _build(self, row, o):
        builder = getattr(self, '_build_%s' % type(o).__name__,
                          self._build_default)
        return builder(row, o)

    @staticmethod
    def _build_default(row, o):
        return unicode(o)

    def _build_dict(self, row, o):
        d = dict((k, self._build(row, v)) for (k, v) in o.iteritems())
        d = dict(i for i in d.iteritems() if i[1])
        if '_required' in o and not all(d.get('_required', [False])):
            return None
        return d

    def _build_list(self, row, o):
        # TODO deal with lists which should be concatenated strings
        items = [self._build(row, i) for i in o]
        return [i for i in items if i]

    _build_tuple = _build_list

    @staticmethod
    def _build_str(row, o):
        if '[' in o and o not in row:
            # if we didn't create the given related object, don't give back the
            # string
            return None
        return row.get(o, unicode(o))

    _build_unicode = _build_str


def dict_to_query(d):
    """
    Given a dictionary, remaps it into ORM-style queries.  For example:

    >>> dict_to_query({'foo':
    ...     {'bar': 'baz'}})
    ...
    {'foo__bar': 'baz'}
    """
    queries = {}
    for k, v in d.iteritems():
        if isinstance(v, dict):
            queries.update(dict(
                ('%s__%s' % (k, k2), v2) for (k2, v2) in
                dict_to_query(v).iteritems()))
        else:
            queries[k] = v
    return queries


def query_for_obj(obj):
    """
    Returns the query dictionary for the given object.  If it has a `_lookup`
    key, use that; otherwise just use the `name` field.
    """
    if not obj.get('name'):
        # even if we're looking up by something else, names are required.
        return
    elif isinstance(obj['name'], dict):
        if not set(obj['name']).intersection(set(('first', 'last'))):
            # they have to have at least a first or last name
            return
    query = obj.get('_lookup')
    if not query:
        query = dict(name=obj['name'])
    return dict_to_query(query)


def get_update(old, new):
    """
    This function looks through an old and new dictionary, and returns a
    dictionary containing the updated values.  Recurses into child
    dictionaries, but not child lists.
    """
    output = {}
    for k, v in old.iteritems():
        if k[0] == '_':
            continue
        if isinstance(v, dict):
            v2 = get_update(v, new.get(k, {}))
            if not v2:
                continue
        else:
            if v is not None:
                if isinstance(v, basestring):
                    v2 = new.get(k, v).decode('utf-8')
                else:
                    t = type(v)
                    v2 = t(new.get(k, v))
            else:
                v2 = new.get(k, v)
        if v2 != v:
            output[k] = v
    for k, v in new.iteritems():
        if k in old or k[0] == '_':
            # already handled, or ignored
            continue
        # otherwise it's a key we added
        output[k] = v
    return output


def upsert(type_, obj):
    """
    With an object of the given type, either create it or update it at the
    appropriate endpoint.  We check our data against what was returned to
    prevent (some) spurious updates.
    """
    query = query_for_obj(obj)
    if not query:
        return
    print type_.upper(), query,
    endpoint = sr[type_]
    try:
        existing = endpoint.filter(**query)[:1]
        if existing:
            u = get_update(existing[0], obj)
            if u:
                print 'UPDATED'
                endpoint[existing[0]] = obj
            else:
                print 'NO CHANGE'
            return existing[0]
        else:
            print 'CREATED'
            return endpoint.create(obj)
    except studentrecord.StudentRecordException:
        print 'ERROR'
        raise


MAPPINGS = [(type_,
             [CSVMapping(mapping) for mapping in data[type_]])
            for type_ in 'school', 'organization', 'person', 'course']
MAPPINGS.append(('applicant', [CSVMapping(data['applicant'])]))


def build_row(row):
    for type_, mappings in MAPPINGS:
        for mapping in mappings:
            obj = mapping.build(row)
            if not obj:
                # missing a required field
                continue
            updated = upsert(type_, obj)
            if updated and '_key' in obj:
                key = '%s[%s]' % (type_, obj['_key'])
                row[key] = updated['id']


if __name__ == "__main__":
    import multiprocessing
    pool = multiprocessing.Pool()
    pool.map_async(build_row,
                   csv.DictReader(sys.stdin))
    pool.close()
    pool.join()
