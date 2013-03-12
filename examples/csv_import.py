import studentrecord
import sys
import csv
import yaml

if len(sys.argv) not in (3, 4):
    print ('Usage: %s <configuration file> '
           '(<email> <password>|<auth token>)' % (
               sys.argv[0],))
    sys.exit(-1)


data = yaml.load(file(sys.argv[1]))

if len(sys.argv) == 3:
    auth = sys.argv[2]
else:
    auth = sys.argv[2:4]
sr = studentrecord.StudentRecord(auth)
sr.scheme = 'http'
sr.host = 'localhost:5000'
sr.auth_token  # make sure we're authenticated
sr.choose_customer(sr.customer[0])


def build(row, mapping):
    mapper = MAP_TYPES.get(type(mapping), lambda row, x: unicode(x))
    return mapper(row, mapping)


def build_dict(row, mapping):
    d = dict((k, build(row, v)) for (k, v) in mapping.iteritems())
    d = dict(i for i in d.iteritems() if i[1])
    if '_required' in mapping and not all(d.get('_required', [False])):
        return None
    return d


def build_list(row, mapping):
    # TODO deal with lists which should be concatenated strings
    items = [build(row, i) for i in mapping]
    return [i for i in items if i]


def build_str(row, mapping):
    if '[' in mapping and mapping not in row:
        # if we didn't create the given related object, don't give back the
        # string
        return None
    return row.get(mapping, mapping)


MAP_TYPES = {
    dict: build_dict,
    list: build_list,
    tuple: build_list,
    str: build_str,
    unicode: build_str
}


def _to_key(obj):
    name = obj['name']
    if isinstance(name, basestring):
        return name
    else:
        return ' '.join(name[k] for k in sorted(name))


def dict_to_query(d):
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
    if not obj.get('name') or ' ' not in _to_key(obj):
        return
    query = obj.get('_lookup')
    if not query:
        query = dict(name=obj['name'])
    return dict_to_query(query)


def update(d1, d2):
    output = {}
    for k, v in d1.iteritems():
        if isinstance(v, dict):
            v2 = update(v, d2.get(k, {}))
            if not v2:
                continue
        else:
            if v is not None:
                if isinstance(v, basestring):
                    v2 = d2.get(k, v).decode('utf-8')
                else:
                    t = type(v)
                    v2 = t(d2.get(k, v))
            else:
                v2 = d2.get(k, v)
        if v2 != v and k != 'date':
            output[k] = v
    for k, v in d2.iteritems():
        if k in output or k[0] == '_':
            # already handled, or ignored
            continue
        output[k] = v
    return output


def upsert(type_, obj):
    query = query_for_obj(obj)
    if not query:
        return
    print type_.upper(), obj
    endpoint = getattr(sr, type_)
    try:
        existing = endpoint.filter(**query)[:1]
        if existing:
            u = update(existing[0], obj)
            if u:
                endpoint[existing[0]] = obj
            return existing[0]
        else:
            return endpoint.create(obj)
    except studentrecord.StudentRecordException:
        print 'during upsert of', type_, obj
        raise


for row in csv.DictReader(sys.stdin):
    for type_ in 'school', 'organization', 'person', 'course':
        for mapping in data[type_]:
            obj = build(row, mapping)
            updated = upsert(type_, obj)
            if updated and '_key' in obj:
                key = '%s[%s]' % (type_, obj['_key'])
                row[key] = updated['id']
    applicant = data['applicant']
    obj = build(row, applicant)
    if obj:
        upsert('applicant', obj)
