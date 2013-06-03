try:
    import jinja2
except ImportError:
    jinja2 = None  # noqa


class Mapping(object):
    """
    Given a mapping of dictionaries/lists to strings, this builds an
    object which can take a set of data and map it into a new format.  Example:

    >>> m = Mapping({
    ...     'foo': 'bar',
    ...      'baz': 'Hello {{ row['other field'] }}!'  # if jinja2 is present
    ... })
    >>> m({'bar': 'bar value', 'other field': 'world'})
    {'foo': 'bar value', 'baz': 'Hello world!'}
    """

    def __init__(self, mapping):
        self.mapping = mapping

    def __str__(self):
        return 'Mapping(%r)' % (self.mapping,)

    def __repr__(self):
        return str(self)

    def __call__(self, *rows):
        """
        Build a dictionary for the given row(s).  If passed a single row, just
        return that row.  If passed a list/tuple, or multiple rows as
        arguments, yield each one in turn.
        """
        if len(rows) == 1 and hasattr(rows[0], 'items'):
            return self._build(rows[0], None, self.mapping)
        elif len(rows) == 1:
            # list or tuple
            rows = rows[0]
        for row in rows:
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
            o = template.render(row=row,
                                min=min,
                                max=max)
        if '[' in o and o not in row:
            # if we didn't create the given related object, don't give back the
            # string
            return None
        if name == '_key':
            # Don't do a lookup on keys
            return unicode(o)
        o = row.get(o, unicode(o))
        # convert booleans to real boolean values
        if o in ('true', 'True'):
            o = True
        elif o in ('false', 'False'):
            o = False
        return o

    _build_unicode = _build_str

    @staticmethod
    def _build_datetime(row, name, o):
        return o.isoformat()
