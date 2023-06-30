from collections import OrderedDict
import json
import lark
import os
import typing

SUPPORTED_USER_TAGS = ('eka', 'fa', 'weasyl', 'ib', 'sf', 'twitter')

DESCRIPTION_GRAMMAR = r"""
  ?start: document_list

  document_list: document+

  document: b_tag
          | i_tag
          | url_tag
          | self_tag
          | user_tag_root
          | TEXT

  b_tag: "[b]" [document_list] "[/b]"
  i_tag: "[i]" [document_list] "[/i]"
  url_tag: "[url" ["=" [URL]] "]" [document_list] "[/url]"

  self_tag: "[self]" [WS] "[/self]"
  user_tag_root: user_tag
  user_tag: """

DESCRIPTION_GRAMMAR += ' | '.join(f'{tag}_tag' for tag in SUPPORTED_USER_TAGS)

DESCRIPTION_GRAMMAR += ''.join(f'\n  {tag}_tag: "[{tag}" ["=" USERNAME] "]" USERNAME "[/{tag}]" | "[{tag}"  "=" USERNAME  "]" [user_tag] "[/{tag}]"' for tag in SUPPORTED_USER_TAGS)

DESCRIPTION_GRAMMAR += r"""

  USERNAME: /[a-zA-Z0-9][a-zA-Z0-9 _-]*/
  URL: /(https?:\/\/)?[^\]]+/
  TEXT: /([^\[:]|[ \t\r\n]|:(?!icon))+/

  %import common.WS
"""

DESCRIPTION_PARSER = lark.Lark(DESCRIPTION_GRAMMAR, parser='lalr')


class UserTag:
  def __init__(self, default=None, **kwargs):
    self.default: typing.Optional[str] = default
    self._sites: typing.OrderedDict[str, typing.Optional[str]] = OrderedDict()
    for (k, v) in kwargs.items():
      if k in SUPPORTED_USER_TAGS:
        self.__setitem__(k, v)

  def __setitem__(self, name: str, value: typing.Optional[str]) -> None:
    if name in self._sites:
      if value is None:
        self._sites.pop(name)
      else:
        self._sites[name] = value
    elif value is not None:
      self._sites[name] = value

  def __getitem__(self, name: str) -> typing.Optional[str]:
    return self._sites.get(name)

  @property
  def sites(self):
    yield from self._sites

class UploadTransformer(lark.Transformer):
  def __init__(self, *args, **kwargs):
    super(UploadTransformer, self).__init__(*args, **kwargs)
    def _user_tag_factory(tag):
      def user_tag(data):
        attribute, inner = data[0], data[1]
        if attribute and attribute.strip():
          if isinstance(inner, UserTag):
            inner[tag] = attribute.strip()
            return inner
          user = UserTag(default=inner and inner.strip())
          user[tag] = attribute.strip()
          return user
        user = UserTag()
        user[tag] = inner.strip()
        return user
      return user_tag
    for tag in SUPPORTED_USER_TAGS:
      setattr(self, f'{tag}_tag', _user_tag_factory(tag))

  def document_list(self, data):
    return ''.join(data)

  def document(self, data):
    return data[0]

  def b_tag(self, _):
    raise NotImplementedError('UploadTransformer.b_tag is abstract')

  def i_tag(self, _):
    raise NotImplementedError('UploadTransformer.i_tag is abstract')

  def url_tag(self, _):
    raise NotImplementedError('UploadTransformer.url_tag is abstract')

  def self_tag(self, _):
    raise NotImplementedError('UploadTransformer.self_tag is abstract')

  def user_tag_root(self, data):
    user_data: UserTag = data[0]
    for site in user_data.sites:
      if site == 'eka':
        return self.url_tag((f'https://aryion.com/g4/user/{user_data["eka"]}', user_data.default or user_data["eka"]))
      if site == 'fa':
        return self.url_tag((f'https://furaffinity.net/user/{user_data["fa"].replace("_", "")}', user_data.default or user_data['fa']))
      if site == 'ib':
        return self.url_tag((f'https://inkbunny.net/{user_data["ib"]}', user_data.default or user_data['ib']))
      if site == 'sf':
        return self.url_tag((f'https://{user_data["sf"].replace(" ", "-").lower()}.sofurry.com', user_data.default or user_data['sf']))
      if site == 'twitter':
        return self.url_tag((f'https://twitter.com/{user_data["twitter"]}', user_data.default or user_data['twitter']))
      if site == 'weasyl':
        self.url_tag((f'https://www.weasyl.com/~{user_data["weasyl"].replace(" ", "").lower()}', user_data.default or user_data['weasyl']))
    raise TypeError('Invalid UserTag data')

  def user_tag(self, data):
    return data[0]

class BbcodeTransformer(UploadTransformer):
  def b_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'[b]{data[0]}[/b]'

  def i_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'[i]{data[0]}[/i]'

  def url_tag(self, data):
    return f'[url={data[0] or ""}]{data[1] or ""}[/url]'

class MarkdownTransformer(UploadTransformer):
  def b_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'**{data[0]}**'

  def i_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'*{data[0]}*'

  def url_tag(self, data):
    return f'[{data[1] or ""}]({data[0] or ""})'

class PlaintextTransformer(UploadTransformer):
  def b_tag(self, data):
    return f'{data[0] or ""}'

  def i_tag(self, data):
    return f'{data[0] or ""}'

  def url_tag(self, data):
    if data[1] is None or not data[1].strip():
      return f'{data[0] or ""}'
    return f'{data[1].strip()}: {data[0] or ""}'

class AryionTransformer(BbcodeTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(AryionTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(eka=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data['eka']:
      return f':icon{user_data["eka"]}:'
    return super(AryionTransformer, self).user_tag_root(data)

class FuraffinityTransformer(BbcodeTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(FuraffinityTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(fa=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data['fa']:
      return f':icon{user_data["fa"]}:'
    return super(FuraffinityTransformer, self).user_tag_root(data)

class WeasylTransformer(MarkdownTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(WeasylTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(weasyl=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data['weasyl']:
      return f'<!~{user_data["weasyl"].replace(" ", "")}>'
    if user_data.default is None:
      for site in user_data.sites:
        if site == 'fa':
          return f'<fa:{user_data["fa"]}>'
        if site == 'ib':
          return f'<ib:{user_data["ib"]}>'
        if site == 'sf':
          return f'<sf:{user_data["sf"]}>'
    return super(WeasylTransformer, self).user_tag_root(data)

class InkbunnyTransformer(BbcodeTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(InkbunnyTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(ib=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data['ib']:
      return f'[iconname]{user_data["ib"]}[/iconname]'
    if user_data.default is None:
      for site in user_data.sites:
        if site == 'fa':
          return f'[fa]{user_data["fa"]}[/fa]'
        if site == 'sf':
          return f'[sf]{user_data["sf"]}[/sf]'
        if site == 'weasyl':
          return f'[weasyl]{user_data["weasyl"].replace(" ", "").lower()}[/weasyl]'
    return super(InkbunnyTransformer, self).user_tag_root(data)

class SoFurryTransformer(BbcodeTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(SoFurryTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(sf=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data['sf']:
      return f':icon{user_data["sf"]}:'
    if user_data.default is None:
      for site in user_data.sites:
        if site == 'fa':
          return f'fa!{user_data["fa"]}'
        if site == 'ib':
          return f'ib!{user_data["ib"]}'
    return super(SoFurryTransformer, self).user_tag_root(data)

class TwitterTransformer(PlaintextTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(TwitterTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(twitter=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data['twitter']:
      return f'@{user_data["twitter"]}'
    return super(TwitterTransformer, self).user_tag_root(data)

TRANSFORMATIONS = {
  'aryion': ('desc_aryion.txt', AryionTransformer),
  'furaffinity': ('desc_furaffinity.txt', FuraffinityTransformer),
  'inkbunny': ('desc_inkbunny.txt', InkbunnyTransformer),
  'sofurry': ('desc_sofurry.txt', SoFurryTransformer),
  'twitter': ('desc_twitter.txt', TwitterTransformer),
  'weasyl': ('desc_weasyl.md', WeasylTransformer),
}


def parse_description(description, config_path, out_dir):
  parsed_description = DESCRIPTION_PARSER.parse(description)
  with open(config_path, 'r') as f:
    config = json.load(f)
  # Validate JSON
  errors = []
  if type(config) is not dict:
    errors.append(ValueError('Configuration must be a JSON object'))
  else:
    for (website, username) in config.items():
      if website not in TRANSFORMATIONS:
        errors.append(ValueError(f'Website \'{website}\' is unsupported'))
      elif type(username) is not str:
        errors.append(ValueError(f'Website \'{website}\' has invalid username \'{json.dumps(username)}\''))
      elif username.strip() == '':
        errors.append(ValueError(f'Website \'{website}\' has empty username'))
  if errors:
    raise ExceptionGroup('Invalid configuration for description parsing', errors)
  # Create descriptions
  for (website, username) in config.items():
    (filepath, transformer) = TRANSFORMATIONS[website]
    with open(os.path.join(out_dir, filepath), 'w') as f:
      if description:
        f.write(transformer(username).transform(parsed_description))
      else:
        f.write('')
