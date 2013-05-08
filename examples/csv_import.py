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
* If Jinja2 is included, you can use those templates to build more complicated
sets of data.
"""
import argparse
import studentrecord
import sys
import csv
import yaml
from itertools import izip, repeat
try:
    import jinja2
except:
    jinja2 = None  # noqa


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
        return self._build(row, None, self.mapping)

    def _build(self, row, name, o):
        builder = getattr(self, '_build_%s' % type(o).__name__,
                          self._build_default)
        return builder(row, name, o)

    @staticmethod
    def _build_default(row, name, o):
        return unicode(o)

    def _build_dict(self, row, name, o):
        d = dict((k, self._build(row, k, v)) for (k, v) in o.iteritems())
        d = dict(i for i in d.iteritems() if i[1])
        if '_required' in o and not all(d.get('_required', [False])):
            return None
        return d

    def _build_list(self, row, name, o):
        items = [self._build(row, name, i) for i in o]
        return [i for i in items if i]

    _build_tuple = _build_list

    @staticmethod
    def _build_str(row, name, o):
        if jinja2 and '{' in o:
            template = jinja2.Template(o)
            o = template.render(row=row)
        if '[' in o and o not in row:
            # if we didn't create the given related object, don't give back the
            # string
            return None
        return row.get(o, unicode(o))

    _build_unicode = _build_str


class Importer(object):
    """
    Given a YAML file, this builds the configuration needed to process a row
    in the CSV file and upload it to StudentRecord.com.
    """
    def __init__(self, sr, data, quiet=False):
        self.sr = sr
        self.mappings = [
            (type_,
             [CSVMapping(mapping) for mapping in data[type_]])
            for type_ in 'school', 'organization', 'person', 'course'
            if type_ in data]
        self.mappings.append(('applicant', [CSVMapping(data['applicant'])]))
        self.quiet = quiet

    def build_row(self, row):
        for type_, mappings in self.mappings:
            for mapping in mappings:
                obj = mapping.build(row)
                if not obj:
                    # missing a required field
                    continue
                updated = self.upsert(type_, obj)
                if updated and '_key' in obj:
                    key = '%s[%s]' % (type_, obj['_key'])
                    row[key] = updated['id']

    def dict_to_query(self, d):
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
                    self.dict_to_query(v).iteritems()))
            else:
                queries[k] = v
        return queries

    def query_for_obj(self, obj):
        """
        Returns the query dictionary for the given object.  If it has a
        `_lookup` key, use that; otherwise just use the `name` field.
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
        return self.dict_to_query(query)

    def get_update(self, old, new):
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
                v2 = self.get_update(v, new.get(k, {}))
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

    def upsert(self, type_, obj):
        """
        With an object of the given type, either create it or update it at the
        appropriate endpoint.  We check our data against what was returned to
        prevent (some) spurious updates.
        """
        query = self.query_for_obj(obj)
        if not query:
            return
        if not self.quiet:
            print type_.upper(), query,
        endpoint = self.sr[type_]
        try:
            existing = endpoint.filter(**query)[:1]
            if existing:
                u = self.get_update(existing[0], obj)
                if u:
                    if not self.quiet:
                        print 'UPDATED', u
                    endpoint[existing[0]] = obj
                elif not self.quiet:
                    print 'NO CHANGE'
                return existing[0]
            else:
                if not self.quiet:
                    print 'CREATED'
                return endpoint.create(obj)
        except KeyboardInterrupt:
            raise
        except:
            if self.quiet < 2:
                if self.quiet == 1:
                    # we didn't print the type_ and query earlier, so do it
                    # now
                    print type_.upper(), query,
                print 'ERROR'
                print obj
                import traceback
                traceback.print_exc()


def build_row((importer, row)):
    """
    Multiprocessing needs a function to call, so we pass in the importer and
    row as arguments to this global function.
    """
    importer.build_row(row)


if __name__ == "__main__":
    def validate_srdc_auth(value):
        if ':' in value:
            return tuple(value.split(':', 1))
        else:
            return value
    usage = 'usage: %prog -s SRDC_AUTH -c CUSTOMER_ID [config filename]'
    parser = argparse.ArgumentParser(
        description='Upload a CSV file to StudentRecord.com.')
    parser.add_argument('-m', dest='multiprocessing', action='store_const',
                        const=True,
                        help='Use multiple processes to speed up the import')
    parser.add_argument(
        '-q', dest='quiet', action='append_const', const=True,
        help="-q: only display errors; -qq: don't display anything")
    parser.add_argument(
        '-s', '--studentrecord', metavar='USERNAME:PASSWORD', required=True,
        type=validate_srdc_auth,
        help='Username/password (or auth token) for SRDC (required)',)
    parser.add_argument(
        '-c', '--customer', help='Customer ID to push to on StudentRecord.com',
        metavar='CUSTOMER')
    parser.add_argument('config_file', type=argparse.FileType('r'),
                        help='YAML configuration file')
    parser.add_argument(
        'csv_file', nargs='*', type=argparse.FileType('r'),
        help='CSV files to upload. If none are specified, read from stdin')
    args = parser.parse_args()

    sr = studentrecord.StudentRecord(args.studentrecord)

    try:
        sr.auth_token  # make sure we're authenticated
    except studentrecord.LoginException as e:
        print 'ERROR: %s' % e.args[0]
        sys.exit(2)
    if args.customer:
        sr.choose_customer(args.customer)
    else:
        customers = list(sr['customer'])
        if len(customers) == 1:
            sr.choose_customer(customers[0])
        else:
            print 'ERROR: must specify a Customer (-c).  Options:'
            for c in customers:
                print '%s: %s' % (c['name'], c['id'])
            print
            sys.exit(1)

    data = yaml.load(args.config_file)
    if args.quiet:
        quiet = len(args.quiet)
    else:
        quiet = False
    importer = Importer(sr, data, quiet=quiet)

    files = args.csv_file
    if not files:
        files = [sys.stdin]

    if args.multiprocessing:
        import multiprocessing
        pool = multiprocessing.Pool()
    for f in files:
        if f is not sys.stdin and quiet < 2:
            print 'Processing %s' % f.name
        reader = csv.DictReader(f)
        if args.multiprocessing:
            pool.map_async(build_row, izip(repeat(importer), reader))
        else:
            for row in reader:
                importer.build_row(row)
    if args.multiprocessing:
        pool.close()
        pool.join()
