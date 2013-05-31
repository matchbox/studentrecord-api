import logging


class Importer(object):
    """
    Importer takes a StudentRecord object and a dictionary mapping SRDC
    endpoints to lists of `studentrecord.mapping.Mapping` objects.  You can
    then call the resulting object with dictionaries to map the given data
    into your `StudentRecord` object.
    """
    log_name = 'studentrecord.importer.Importer'

    def __init__(self, sr, mappings):
        self.logger = logging.getLogger(self.log_name)
        self.sr = sr
        self.mappings = mappings

    def __call__(self, *rows):
        """
        Build a dictionary for the given row(s).  If passed a single row, just
        return that row.  If passed a list/tuple, or multiple rows as
        arguments, yield each one in turn.
        """
        if len(rows) == 1 and hasattr(rows[0], 'items'):
            self._build_row(rows[0])
        elif len(rows) == 1:
            rows = rows[0]
        for row in rows:
            self._build_row(row)

    def _build_row(self, row):
        for type_, mappings in self.mappings:
            for mapping in mappings:
                try:
                    obj = mapping(row)
                except:
                    self.logger.error('while rendering %r on row:\n%s',
                                      mapping, row,
                                      exc_info=True,
                                      extra=dict(
                                          action='error',
                                          mapping=mapping,
                                          type=type_))
                    return
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
        if not isinstance(new, dict):
            if old == new:
                return None
            else:
                return new
        output = {}
        for k, v in old.iteritems():
            if k not in new:
                continue
            if k[0] == '_':
                continue
            if isinstance(v, dict):
                v2 = self.get_update(v, new[k])
                if not v2:
                    continue
            elif isinstance(v, list):
                v2 = new[k]
                if len(v) == len(v2) and v:
                    diffs = [self.get_update(*z) for z in zip(v, v2)]
                    if not any(diffs):
                        # they're all the same, don't bother sending the change
                        continue
            else:
                if v is not None:
                    if isinstance(v, basestring):
                        v2 = new.get(k, v)
                        if isinstance(v2, basestring):
                            v2 = v2.decode('utf-8')
                    else:
                        t = type(v)
                        try:
                            v2 = t(new.get(k, v))
                        except ValueError:
                            if t is int:
                                v2 = float(new.get(k, v))
                            else:
                                raise
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
        if not self.sr:
            # dry run, just no-op
            return
        query = self.query_for_obj(obj)
        if not query:
            return
        endpoint = self.sr[type_]
        try:
            existing = endpoint.filter(**query)[:1]
            if existing:
                u = self.get_update(existing[0], obj)
                if u:
                    endpoint[existing[0]] = obj
                    self.logger.info(
                        'updated %s %s', type_.upper(), query,
                        extra=dict(
                            action='updated',
                            type=type_,
                            query=query,
                            update=u,
                            object=obj))
                    print u
                else:
                    self.logger.info(
                        'no change %s %s', type_.upper(), query,
                        extra=dict(
                            action='no change',
                            type=type_,
                            query=query,
                            object=obj))
                return existing[0]
            else:
                r = endpoint.create(obj)
                self.logger.info(
                    'created %s %s', type_.upper(), query,
                    extra=dict(
                        action='created',
                        type=type_,
                        query=query,
                        object=obj))
                return r
        except KeyboardInterrupt:
            raise
        except:
            self.logger.error(
                'error %s %s\nobject: %s', type_.upper(), query, obj,
                exc_info=True,
                extra=dict(
                    action='error',
                    type=type_,
                    query=query,
                    object=obj))
