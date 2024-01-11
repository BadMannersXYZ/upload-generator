import itertools
import typing

SUPPORTED_SITE_TAGS: typing.Mapping[str, typing.Set[str]] = {
  'aryion': {'aryion', 'eka', 'eka_portal'},
  'furaffinity': {'furaffinity', 'fa'},
  'weasyl': {'weasyl'},
  'inkbunny': {'inkbunny', 'ib'},
  'sofurry': {'sofurry', 'sf'},
}

INVERSE_SUPPORTED_SITE_TAGS: typing.Mapping[str, str] = \
  dict(itertools.chain.from_iterable(zip(v, itertools.repeat(k)) for (k, v) in SUPPORTED_SITE_TAGS.items()))
