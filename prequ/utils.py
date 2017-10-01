# coding: utf-8
from __future__ import (
    absolute_import, division, print_function, unicode_literals)

import os
import sys
from collections import OrderedDict
from itertools import chain, groupby

import pip
from click import style
from pip.req import InstallRequirement


def first(iterable):
    for x in iterable:
        return x
    return None


def safeint(s):
    try:
        return int(s)
    except ValueError:
        return 0


pip_version_info = tuple(safeint(digit) for digit in pip.__version__.split('.'))

UNSAFE_PACKAGES = {'setuptools', 'distribute', 'pip'}


def assert_compatible_pip_version():
    # Make sure we're using a reasonably modern version of pip
    if not pip_version_info >= (8, 0):
        raise SystemExit((
            'Prequ requires at least version 8.0 of pip ({} found), '
            'perhaps run `pip install --upgrade pip`?').format(pip.__version__))


def key_from_ireq(ireq):
    """Get a standardized key for an InstallRequirement."""
    if ireq.req is None and ireq.link is not None:
        return str(ireq.link)
    else:
        return key_from_req(ireq.req)


def key_from_req(req):
    """Get an all-lowercase version of the requirement's name."""
    if hasattr(req, 'key'):
        # pip 8.1.1 or below, using pkg_resources
        key = req.key
    else:
        # pip 8.1.2 or above, using packaging
        key = req.name

    key = key.replace('_', '-').lower()
    return key


def comment(text):
    return style(text, fg='green')


def make_install_requirement(name, version, extras, constraint=False):
    # If no extras are specified, the extras string is blank
    extras_string = ""
    if extras:
        # Sort extras for stability
        extras_string = "[{}]".format(",".join(sorted(extras)))

    return InstallRequirement.from_line(
        str('{}{}=={}'.format(name, extras_string, version)),
        constraint=constraint)


def is_subdirectory(base, directory):
    """
    Return True if directory is a child directory of base
    """
    base = os.path.join(os.path.realpath(base), '')
    directory = os.path.join(os.path.realpath(directory), '')

    return os.path.commonprefix([base, directory]) == base


def format_requirement(ireq, marker=None):
    """
    Generic formatter for pretty printing InstallRequirements to the terminal
    in a less verbose way than using its `__str__` method.
    """
    if ireq.editable:
        path = ireq.link.path
        if ireq.link.scheme == 'file' and is_subdirectory(os.getcwd(), path):
            # If the ireq.link is relative to the current directory then output a relative path
            path = 'file:' + os.path.join('.', os.path.relpath(path))
        else:
            path = ireq.link

        line = '-e {}'.format(path)
    elif is_vcs_link(ireq):
        line = '{}{}'.format('-e ' if ireq.editable else '', ireq.link)
    else:
        line = str(ireq.req).lower()

    if marker:
        line = '{} ; {}'.format(line, marker)

    return line


def format_specifier(ireq):
    """
    Generic formatter for pretty printing the specifier part of
    InstallRequirements to the terminal.
    """
    # TODO: Ideally, this is carried over to the pip library itself
    specs = ireq.specifier._specs if ireq.req is not None else []
    specs = sorted(specs, key=lambda x: x._spec[1])
    return ','.join(str(s) for s in specs) or '<any>'


def is_pinned_requirement(ireq):
    """
    Returns whether an InstallRequirement is a "pinned" requirement.

    An InstallRequirement is considered pinned if:

    - Is not editable
    - It has at least one "==" specifier with a version that is not a
      wildcard
    - It is not conflicting (i.e. filtering out all possible versions)

    Examples:

    >>> assert is_pinned_requirement('django==1.8')
    >>> assert not is_pinned_requirement('django>1.8')
    >>> assert not is_pinned_requirement('django~=1.8')
    >>> assert not is_pinned_requirement('django==1.8.*')
    >>> assert is_pinned_requirement('django>=1.4,==1.8')
    >>> assert not is_pinned_requirement('django>=1.4,<=1.4')
    >>> assert not is_pinned_requirement('django==1.8,==1.9')
    >>> assert not is_pinned_requirement('django==1.8,>=1.9')
    """
    return get_pinned_version(ireq) is not None


def get_pinned_version(ireq):
    """
    Get pinned version of a requirement, if it is pinned.
    """
    if not isinstance(ireq, InstallRequirement):
        ireq = InstallRequirement(ireq, None)
    assert isinstance(ireq, InstallRequirement)

    if ireq.editable:
        return None

    if not ireq.specifier._specs:
        return None

    specs = (x._spec for x in ireq.specifier._specs)
    versions = set(
        version for (op, version) in specs
        if (op == '==' or op == '===') and not version.endswith('.*'))
    good_versions = ireq.specifier.filter(versions, prereleases=True)
    return first(good_versions)


def is_vcs_link(ireq):
    """
    Returns whether an InstallRequirement is a version control link.
    """

    return ireq.link is not None and not ireq.link.is_artifact


def as_tuple(ireq):
    """
    Pulls out the (name: str, version:str, extras:(str)) tuple from the pinned InstallRequirement.
    """
    if not is_pinned_requirement(ireq):
        raise TypeError('Expected a pinned InstallRequirement, got {}'.format(ireq))

    name = key_from_req(ireq.req)
    version = first(ireq.specifier._specs)._spec[1]
    extras = tuple(sorted(ireq.extras))
    return name, version, extras


def full_groupby(iterable, key=None):
    """Like groupby(), but sorts the input on the group key first."""
    return groupby(sorted(iterable, key=key), key=key)


def flat_map(fn, collection):
    """Map a function over a collection and flatten the result by one-level"""
    return chain.from_iterable(map(fn, collection))


def lookup_table(values, key=None, keyval=None, unique=False, use_lists=False):
    """
    Builds a dict-based lookup table (index) elegantly.

    Supports building normal and unique lookup tables.  For example:

    >>> assert lookup_table(
    ...     ['foo', 'bar', 'baz', 'qux', 'quux'], lambda s: s[0]) == {
    ...     'b': {'bar', 'baz'},
    ...     'f': {'foo'},
    ...     'q': {'quux', 'qux'}
    ... }

    For key functions that uniquely identify values, set unique=True:

    >>> assert lookup_table(
    ...     ['foo', 'bar', 'baz', 'qux', 'quux'], lambda s: s[0],
    ...     unique=True) == {
    ...     'b': 'baz',
    ...     'f': 'foo',
    ...     'q': 'quux'
    ... }

    The values of the resulting lookup table will be values, not sets.

    For extra power, you can even change the values while building up the LUT.
    To do so, use the `keyval` function instead of the `key` arg:

    >>> assert lookup_table(
    ...     ['foo', 'bar', 'baz', 'qux', 'quux'],
    ...     keyval=lambda s: (s[0], s[1:])) == {
    ...     'b': {'ar', 'az'},
    ...     'f': {'oo'},
    ...     'q': {'uux', 'ux'}
    ... }

    """
    if keyval is None:
        if key is None:
            keyval = (lambda v: v)
        else:
            keyval = (lambda v: (key(v), v))

    if unique:
        return dict(keyval(v) for v in values)

    lut = {}
    for value in values:
        k, v = keyval(value)
        try:
            s = lut[k]
        except KeyError:
            if use_lists:
                s = lut[k] = list()
            else:
                s = lut[k] = set()
        if use_lists:
            s.append(v)
        else:
            s.add(v)
    return dict(lut)


def dedup(iterable):
    """Deduplicate an iterable object like iter(set(iterable)) but
    order-reserved.
    """
    return iter(OrderedDict.fromkeys(iterable))


def fs_str(string):
    """
    Convert given string to a correctly encoded filesystem string.

    On Python 2, if the input string is unicode, converts it to bytes
    encoded with the filesystem encoding.

    On Python 3 returns the string as is, since Python 3 uses unicode
    paths and the input string shouldn't be bytes.

    >>> fs_str(u'some path component/Something')
    'some path component/Something'
    >>> assert isinstance(fs_str('whatever'), str)
    >>> assert isinstance(fs_str(u'whatever'), str)

    :type string: str|unicode
    :rtype: str
    """
    if isinstance(string, str):
        return string
    assert not isinstance(string, bytes)
    return string.encode(_fs_encoding)


_fs_encoding = sys.getfilesystemencoding() or sys.getdefaultencoding()
