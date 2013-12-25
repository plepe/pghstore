import re
import collections
try:
    import io as StringIO
except ImportError:
    import io


def dumps(obj, key_map=None, value_map=None, encoding='utf-8',
          return_unicode=False):
    r"""Converts a mapping object as PostgreSQL ``hstore`` format.

    .. sourcecode:: pycon

       >>> dumps({u'a': u'1 "quotes"'})
       '"a"=>"1 \\"quotes\\""'
       >>> dumps([('key', 'value'), ('k', 'v')])
       '"key"=>"value","k"=>"v"'

    It accepts only strings as keys and values except ``None`` for values.
    Otherwise it will raise :exc:`TypeError`:

    .. sourcecode:: pycon

       >>> dumps({'null': None})
       '"null"=>NULL'
       >>> dumps([('a', 1), ('b', 2)])
       Traceback (most recent call last):
         ...
       TypeError: value 1 of key 'a' is not a string

    Or you can pass ``key_map`` and ``value_map`` parameters to workaround
    this:

    .. sourcecode:: pycon

       >>> dumps([('a', 1), ('b', 2)], value_map=str)
       '"a"=>"1","b"=>"2"'

    By applying these options, you can store any other Python objects
    than strings into ``hstore`` values:

    .. sourcecode:: pycon

       >>> try:
       ...    import json
       ... except ImportError:
       ...    import simplejson as json
       >>> dumps([('a', range(3)), ('b', 2)], value_map=json.dumps)
       '"a"=>"[0, 1, 2]","b"=>"2"'
       >>> import pickle
       >>> dumps([('a', range(3)), ('b', 2)],
       ...       value_map=pickle.dumps)  # doctest: +ELLIPSIS
       '"a"=>"...","b"=>"..."'

    It returns a UTF-8 encoded string, but you can change the ``encoding``:

    .. sourcecode:: pycon

       >>> dumps({'surname': u'\ud64d'})
       '"surname"=>"\xed\x99\x8d"'
       >>> dumps({'surname': u'\ud64d'}, encoding='utf-32')
       '"surname"=>"\xff\xfe\x00\x00M\xd6\x00\x00"'

    If you set ``return_unicode`` to ``True``, it will return :class:`unicode`
    instead of :class:`str` (byte string):

    .. sourcecode:: pycon

       >>> dumps({'surname': u'\ud64d'}, return_unicode=True)
       u'"surname"=>"\ud64d"'

    :param obj: a mapping object to dump
    :param key_map: an optional mapping function that takes a non-string key
                    and returns a mapped string key
    :param value_map: an optional mapping function that takes a non-string
                      value and returns a mapped string value
    :param encoding: a string encode to use
    :param return_unicode: returns an :class:`unicode` string instead
                           byte :class:`str`.  ``False`` by default
    :type return_unicode: :class:`bool`
    :returns: a ``hstore`` data
    :rtype: :class:`basestring`

    """
    b = StringIO.StringIO()
    dump(obj, b, key_map=key_map, value_map=value_map, encoding=encoding)
    result = b.getvalue()
    if return_unicode:
        return result.decode(encoding)
    return result


def loads(string, encoding='utf-8', return_type=dict):
    """Parses the passed hstore format ``string`` to a Python mapping object.

    .. sourcecode:: pycon

       >>> loads('a=>1')
       {u'a': u'1'}

    If you want to load a hstore value as any other type than :class:`dict`
    set ``return_type`` parameter.  Note that the constructor has to take
    an iterable object.

    .. sourcecode:: pycon

       >>> loads('a=>1, b=>2', return_type=list)
       [(u'a', u'1'), (u'b', u'2')]
       >>> loads('"return_type"=>"tuple"', return_type=tuple)
       ((u'return_type', u'tuple'),)

    :param string: a hstore format string
    :type string: :class:`basestring`
    :param encoding: an encoding of the passed ``string``.  if the ``string``
                     is an :class:`unicode` string, this parameter will be
                     ignored
    :param return_type: a map type of return value.  default is :class:`dict`
    :returns: a parsed map.  its type is decided by ``return_type`` parameter

    """
    return return_type(parse(string, encoding=encoding))


def dump(obj, file, key_map=None, value_map=None, encoding='utf-8'):
    """Similar to :func:`dumps()` except it writes the result into the passed
    ``file`` object instead of returning it.

    .. sourcecode:: pycon

       >>> import StringIO
       >>> f = StringIO.StringIO()
       >>> dump({u'a': u'1'}, f)
       >>> f.getvalue()
       '"a"=>"1"'

    :param obj: a mapping object to dump
    :param file: a file object to write into
    :param key_map: an optional mapping function that takes a non-string key
                    and returns a mapped string key
    :param value_map: an optional mapping function that takes a non-string
                      value and returns a mapped string value
    :param encoding: a string encode to use

    """
    if isinstance(getattr(obj, 'iteritems', None), collections.Callable):
        items = iter(obj.items())
    elif isinstance(getattr(obj, 'items', None), collections.Callable):
        items = list(obj.items())
    elif isinstance(getattr(obj, '__iter__', None), collections.Callable):
        items = iter(obj)
    else:
        raise TypeError('expected a mapping object, not ' + type(obj).__name__)
    if key_map is None:
        def key_map(key):
            raise TypeError('key %r is not a string' % key)
    elif not isinstance(key_map, collections.Callable):
        raise TypeError('key_map must be callable')
    elif not (value_map is None or isinstance(value_map, collections.Callable)):
        raise TypeError('value_map must be callable')
    write = getattr(file, 'write', None)
    if not isinstance(write, collections.Callable):
        raise TypeError('file must be a wrtiable file object that implements '
                        'write() method')
    first = True
    for key, value in items:
        if not isinstance(key, str):
            key = key_map(key)
        elif not isinstance(key, str):
            key = key.encode(encoding)
        if value is None:
            value = None
        elif not isinstance(value, str):
            if value_map is None:
                raise TypeError('value %r of key %r is not a string' %
                                (value, key))
            value = value_map(value)
        elif not isinstance(value, str):
            value = value.encode(encoding)
        if first:
            write('"')
            first = False
        else:
            write(',"')
        write(escape(key))
        if value is None:
            write('"=>NULL')
        else:
            write('"=>"')
            write(escape(value))
            write('"')


def load(file, encoding='utf-8'):
    """Similar to :func:`loads()` except it reads the passed ``file`` object
    instead of a string.

    """
    read = getattr(file, 'read', None)
    if not isinstance(read, collections.Callable):
        raise TypeError('file must be a readable file object that implements '
                        'read() method')
    return load(read(), encoding=encoding)


#: The pattern of pairs.  It captures following four groups:
#:
#: ``kq``
#:    Quoted key string.
#:
#: ``kb``
#:    Bare key string.
#:
#: ``vq``
#:    Quoted value string.
#:
#: ``kq``
#:    Bare value string.
PAIR_RE = re.compile(r'(?:"(?P<kq>(?:[^\\"]|\\.)*)"|(?P<kb>\S+?))\s*=>\s*'
                     r'(?:"(?P<vq>(?:[^\\"]|\\.)*)"|(?P<vn>NULL)|'
                     r'(?P<vb>[^,]+))(?:,|$)', re.IGNORECASE)


def parse(string, encoding='utf-8'):
    r"""More primitive function of :func:`loads()`.  It returns a generator
    that yields pairs of parsed hstore instead of a complete :class:`dict`
    object.

    .. sourcecode:: pycon

       >>> list(parse('a=>1, b => 2, c => null, d => "NULL"'))
       [(u'a', u'1'), (u'b', u'2'), (u'c', None), (u'd', u'NULL')]
       >>> list(parse(r'"a=>1"=>"\"b\"=>2",'))
       [(u'a=>1', u'"b"=>2')]

    """
    offset = 0
    for match in PAIR_RE.finditer(string):
        if offset > match.start() or string[offset:match.start()].strip():
            raise ValueError('malformed hstore value: position %d' % offset)
        kq = match.group('kq')
        if kq:
            key = unescape(kq)
        else:
            key = match.group('kb')
        if isinstance(key, str):
            key = key.decode(encoding)
        vq = match.group('vq')
        if vq:
            value = unescape(vq)
        else:
            vn = match.group('vn')
            value = None if vn else match.group('vb')
        if isinstance(value, str):
            value = value.decode(encoding)
        yield key, value
        offset = match.end()
    if offset > len(string) or string[offset:].strip():
        raise ValueError('malformed hstore value: position %d' % offset)


#: The escape sequence pattern.
ESCAPE_RE = re.compile(r'\\(.)')


def unescape(s):
    r"""Strips escaped sequences.

    .. sourcecode:: pycon

       >>> unescape('abc\\"def\\\\ghi\\ajkl')
       'abc"def\\ghiajkl'
       >>> unescape(r'\"b\"=>2')
       '"b"=>2'

    """
    return ESCAPE_RE.sub(r'\1', s)


def escape(s):
    r"""Escapes quotes and backslashes for use in hstore strings.

    .. sourcecode:: pycon

       >>> escape('string with "quotes"')
       'string with \\"quotes\\"'
    """
    return s.replace('\\', '\\\\').replace('"', '\\"')

