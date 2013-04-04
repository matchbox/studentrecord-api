from optparse import OptionParser, OptionGroup
import sys
import multiprocessing
import studentrecord
import requests
import json
from itertools import repeat, izip

MBX_BASE_URL = 'https://app.admitpad.com/api/v2/%s'


def mbx_url(program):
    return MBX_BASE_URL % program


def push_applicant((program, auth, key_path, applicant)):
    if key_path not in applicant['key']:
        return (None, None)
    key = applicant['key'][key_path]
    response = requests.get('%s/application/?external_id=%s' % (
        mbx_url(program), key),
                            auth=auth)
    response.raise_for_status()
    post_data = dict(
        program_id=program,
        name_prefix=applicant['name']['prefix'],
        first_name=applicant['name']['first'],
        middle_name=applicant['name']['middle'],
        last_name=applicant['name']['last'],
        name_suffix=applicant['name']['suffix'],
        email=applicant['key'].get('email', ''),
        external_id=key,
        details={'srdc': applicant})
    objects = response.json()['objects']
    if objects:
        func = requests.patch
        resource_uri = '/application/%s/' % (
            objects[0]['id'])
        rv = 'PATCH'
    else:
        func = requests.post
        resource_uri = '/application/'
        rv = 'POST'

    r = func('%s%s' % (mbx_url(program), resource_uri),
             data=json.dumps(post_data),
             auth=auth)
    r.raise_for_status()
    return key, rv


if __name__ == '__main__':
    def validate_srdc_auth(option, opt, value, parser):
        if ':' in value:
            parser.values.studentrecord = tuple(value.split(':', 1))
        else:
            parser.values.studentrecord = value

    def validate_mbx_auth(option, opt, value, parser):
        parser.values.matchbox = tuple(value.split(':', 1))

    usage = 'usage: %prog -s SRDC_AUTH -m MATCHBOX_AUTH'
    parser = OptionParser(usage=usage)
    srdc_group = OptionGroup(parser, 'StudentRecord.com options')
    srdc_group.add_option(
        '-s', '--studentrecord', dest='studentrecord', action='callback',
        help='Username/password (or auth token) for SRDC (required)',
        metavar='USERNAME:PASSWORD', callback=validate_srdc_auth,
        type=str)
    srdc_group.add_option(
        '-c', '--customer', dest='studentrecord_customer',
        help='Customer ID to pull from on SRDC',
        metavar='CUSTOMER')
    srdc_group.add_option(
        '-k', '--key', dest='key',
        help='Key to use for `external_id`; defaults to "ssn"',
        default='ssn')
    mbx_group = OptionGroup(parser, 'Matchbox options')
    mbx_group.add_option(
        '-m', '--matchbox', dest='matchbox', action='callback',
        help='Username/password for Matchbox (required)',
        metavar='USERNAME:PASSWORD', callback=validate_mbx_auth,
        type=str)
    mbx_group.add_option(
        '-p', '--program', dest='matchbox_program',
        help='Program to push to on Matchbox (required)',
        metavar='PROGRAM')
    parser.add_option_group(srdc_group)
    parser.add_option_group(mbx_group)

    options, args = parser.parse_args()
    if (not options.studentrecord or not options.matchbox or
        not options.matchbox_program):
        parser.print_help()
        sys.exit(1)

    sr = studentrecord.StudentRecord(options.studentrecord)
    sr.auth_token  # make sure we're authenticated
    if options.studentrecord_customer:
        sr.choose_customer(options.studentrecord_customer)
    else:
        customers = list(sr['customer'])
        if len(customers) == 1:
            sr.choose_customer(customers[0])
        else:
            print 'ERROR: must specify a Customer.  Options:'
            for c in customers:
                print '%s: %s' % (c['name'], c['id'])
            print
            parser.print_help()
            sys.exit(1)

    pool = multiprocessing.Pool()
    iterator = izip(repeat(options.matchbox_program),
                    repeat(options.matchbox),
                    repeat(options.key),
                    sr['applicant'])
    for (key, rv) in pool.imap_unordered(push_applicant, iterator):
        if key is None:
            continue
        elif rv == 'PATCH':
            print key, 'updated'
        else:
            print key, 'created'
    pool.close()
    pool.join()
