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
import logging
import codecs
import studentrecord
from studentrecord.mapping import Mapping
from studentrecord.importer import Importer
import sys
import csv
import yaml
from itertools import izip, repeat
from collections import defaultdict
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
try:
    import chardet
except:
    chardet = None


class GetSupportingDefaultDict(defaultdict):
    def get(self, key, default=None):
        return self[key]


def build_row((importer, row)):
    """
    Multiprocessing needs a function to call, so we pass in the importer and
    row as arguments to this global function.
    """
    importer(row)


if __name__ == "__main__":
    def validate_srdc_auth(value):
        if ':' in value:
            return tuple(value.split(':', 1))
        else:
            return value
    usage = 'usage: %prog -s SRDC_AUTH -c CUSTOMER_ID [config filename]'
    parser = argparse.ArgumentParser(
        description='Upload a CSV file to StudentRecord.com.')
    parser.add_argument('-m', dest='multiprocessing', action='store_true',
                        help='Use multiple processes to speed up the import')
    parser.add_argument(
        '-q', dest='quiet', action='append_const', const=True,
        help="-q: only display errors; -qq: don't display anything")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '-s', '--studentrecord', metavar='USERNAME:PASSWORD',
        type=validate_srdc_auth,
        help='Username/password (or auth token) for SRDC (required)',)
    group.add_argument(
        '--dry-run', action='store_true',
        help="""Don't import anything; just check the YAML file.
If CSV files are present, the headers will be scanned and a report of \
used/unused fields will be printed.""")
    parser.add_argument(
        '-c', '--customer', help='Customer ID to push to on StudentRecord.com',
        metavar='CUSTOMER')
    parser.add_argument('config_file', type=argparse.FileType('r'),
                        help='YAML configuration file')
    parser.add_argument(
        'csv_file', nargs='*', type=argparse.FileType('rb'),
        help='CSV files to upload. If none are specified, read from stdin')
    args = parser.parse_args()

    if not args.dry_run:
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
    else:
        sr = None

    data = yaml.load(args.config_file)
    mappings = [
            (type_,
             [Mapping(mapping) for mapping in data[type_]])
            for type_ in 'school', 'organization', 'person', 'course'
            if type_ in data]
    mappings.append(('applicant', [Mapping(data['applicant'])]))
    if args.quiet:
        quiet = len(args.quiet)
        level = None if quiet > 1 else 'ERROR'
    else:
        quiet = 0
        level = 'INFO'

    if level:
        logging.basicConfig(stream=sys.stderr,
                            level='CRITICAL',
                            format='%(message)s')
    importer = Importer(sr, mappings)
    importer.logger.setLevel(level)

    files = args.csv_file
    if not files:
        if args.dry_run:
            files = []
        else:
            files = [sys.stdin]

    if args.multiprocessing:
        import multiprocessing
        pool = multiprocessing.Pool()
    sniffer = csv.Sniffer()
    for f in files:
        encoding = 'UTF-8'
        if f is not sys.stdin and quiet < 2:
            print ('Processing %s...' % f.name),
            sys.stdout.flush()
        data = f.read()
        if f is not sys.stdin and chardet:
            encoding = chardet.detect(data)['encoding']
        dialect = sniffer.sniff(data[:1024], delimiters=',\t')
        f = StringIO(data)
        if f is not sys.stdin and quiet < 2:
            print '(as %s)' % encoding
        if encoding != 'UTF-8':
            f = codecs.iterencode(
                codecs.iterdecode(f, encoding), 'utf-8')
        if args.dry_run:
            # just the headers
            data = [f.next()]
        else:
            data = list(f)
        reader = csv.DictReader(data, dialect=dialect)
        if args.dry_run:
            d = GetSupportingDefaultDict(unicode)
            importer(d)
            print 'Used keys:'
            for k in sorted(d):
                print '*', k
            remaining = set(reader.fieldnames) - set(d)
            if remaining:
                print
                print 'Unused keys:'
                for k in sorted(remaining):
                    print '*', k
        else:
            if args.multiprocessing:
                pool.map_async(build_row, izip(repeat(importer), reader))
            else:
                importer(reader)
    if args.multiprocessing:
        pool.close()
        pool.join()
