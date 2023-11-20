from collections import OrderedDict
import io
import json
import lark
import os
import psutil
import re
import subprocess
import typing


SUPPORTED_USER_TAGS = ['eka', 'fa', 'weasyl', 'ib', 'sf', 'twitter', 'mastodon']

DESCRIPTION_GRAMMAR = r"""
  ?start: document_list

  document_list: document+

  document: b_tag
          | i_tag
          | u_tag
          | url_tag
          | self_tag
          | if_tag
          | user_tag_root
          | TEXT

  b_tag: "[b]" [document_list] "[/b]"
  i_tag: "[i]" [document_list] "[/i]"
  u_tag: "[u]" [document_list] "[/u]"
  url_tag: "[url" ["=" [URL]] "]" [document_list] "[/url]"

  self_tag: "[self][/self]"
  if_tag: "[if=" CONDITION "]" [document_list] "[/if]" [ "[else]" document_list "[/else]" ]

  user_tag_root: user_tag
  user_tag: generic_tag | """

DESCRIPTION_GRAMMAR += ' | '.join(f'{tag}_tag' for tag in SUPPORTED_USER_TAGS)
DESCRIPTION_GRAMMAR += ''.join(f'\n  {tag}_tag: "[{tag}" ["=" USERNAME] "]" USERNAME "[/{tag}]" | "[{tag}" "=" USERNAME  "]" [user_tag] "[/{tag}]"' for tag in SUPPORTED_USER_TAGS)

DESCRIPTION_GRAMMAR += r"""
  generic_tag: "[generic=" URL "]" USERNAME "[/generic]"

  USERNAME: /[a-zA-Z0-9][a-zA-Z0-9 _-]*/
  URL: /(https?:\/\/)?[^\]]+/
  TEXT: /([^\[]|[ \t\r\n])+/
  CONDITION: / *[a-z]+ *(==|!=) *[a-zA-Z0-9]+ */
"""

DESCRIPTION_PARSER = lark.Lark(DESCRIPTION_GRAMMAR, parser='lalr')


class UserTag:
  def __init__(self, default: typing.Optional[str]=None, **kwargs):
    self.default = default
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
    super().__init__(*args, **kwargs)
    def _user_tag_factory(tag):
      # Create a new UserTag if innermost node, or append to list in order
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

  def u_tag(self, _):
    raise NotImplementedError('UploadTransformer.u_tag is abstract')

  def url_tag(self, _):
    raise NotImplementedError('UploadTransformer.url_tag is abstract')

  def self_tag(self, _):
    raise NotImplementedError('UploadTransformer.self_tag is abstract')

  def transformer_matches_site(self, site: str) -> bool:
    raise NotImplementedError('UploadTransformer.transformer_matches_site is abstract')

  def if_tag(self, data: typing.Tuple[str, str, str]):
    condition, truthy_document, falsy_document = data
    equality_condition = condition.split('==', 1)
    if len(equality_condition) == 2 and equality_condition[1].strip():
      conditional_test = f'transformer_matches_{equality_condition[0].strip()}'
      if hasattr(self, conditional_test):
        if getattr(self, conditional_test)(equality_condition[1].strip()):
          return truthy_document or ''
        return falsy_document or ''
    inequality_condition = condition.split('!=', 1)
    if len(inequality_condition) == 2 and inequality_condition[1].strip():
      conditional_test = f'transformer_matches_{inequality_condition[0].strip()}'
      if hasattr(self, conditional_test):
        if not getattr(self, conditional_test)(inequality_condition[1].strip()):
          return truthy_document or ''
        return falsy_document or ''
    raise ValueError(f'Invalid [if][/if] tag condition: {condition}')

  def user_tag_root(self, data):
    user_data: UserTag = data[0]
    for site in user_data.sites:
      if site == 'generic':
        return self.url_tag((user_data['generic'].strip(), user_data.default))
      elif site == 'eka':
        return self.url_tag((f'https://aryion.com/g4/user/{user_data["eka"]}', user_data.default or user_data["eka"]))
      elif site == 'fa':
        return self.url_tag((f'https://furaffinity.net/user/{user_data["fa"].replace("_", "")}', user_data.default or user_data['fa']))
      elif site == 'weasyl':
        return self.url_tag((f'https://www.weasyl.com/~{user_data["weasyl"].replace(" ", "").lower()}', user_data.default or user_data['weasyl']))
      elif site == 'ib':
        return self.url_tag((f'https://inkbunny.net/{user_data["ib"]}', user_data.default or user_data['ib']))
      elif site == 'sf':
        return self.url_tag((f'https://{user_data["sf"].replace(" ", "-").lower()}.sofurry.com', user_data.default or user_data['sf']))
      elif site == 'twitter':
        return self.url_tag((f'https://twitter.com/{user_data["twitter"].rsplit("@", 1)[-1]}', user_data.default or user_data['twitter']))
      elif site == 'mastodon':
        *_, mastodon_user, mastodon_instance = user_data["mastodon"].rsplit('@', 2)
        return self.url_tag((f'https://{mastodon_instance}/@{mastodon_user}', user_data.default or user_data['mastodon']))
      else:
        print(f'Unknown site "{site}" found in user tag; ignoring...')
    raise TypeError('Invalid UserTag data')

  def user_tag(self, data):
    return data[0]

  def generic_tag(self, data):
    attribute, inner = data[0], data[1]
    user = UserTag(default=inner.strip())
    user['generic'] = attribute.strip()
    return user

class BbcodeTransformer(UploadTransformer):
  def b_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'[b]{data[0]}[/b]'

  def i_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'[i]{data[0]}[/i]'

  def u_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'[u]{data[0]}[/u]'

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

  def u_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'<u>{data[0]}</u>'  # Markdown should support simple HTML tags

  def url_tag(self, data):
    return f'[{data[1] or ""}]({data[0] or ""})'

class PlaintextTransformer(UploadTransformer):
  def b_tag(self, data):
    return str(data[0]) if data[0] else ''

  def i_tag(self, data):
    return str(data[0]) if data[0] else ''

  def u_tag(self, data):
    return str(data[0]) if data[0] else ''

  def url_tag(self, data):
    if data[1] is None or not data[1].strip():
      return str(data[0]) if data[0] else ''
    return f'{data[1].strip()}: {data[0] or ""}'

  def user_tag_root(self, data):
    user_data = data[0]
    for site in user_data.sites:
      if site == 'generic':
        break
      elif site == 'eka':
        return f'{user_data["eka"]} on Eka\'s Portal'
      elif site == 'fa':
        return f'{user_data["fa"]} on Fur Affinity'
      elif site == 'weasyl':
        return f'{user_data["weasyl"]} on Weasyl'
      elif site == 'ib':
        return f'{user_data["ib"]} on Inkbunny'
      elif site == 'sf':
        return f'{user_data["sf"]} on SoFurry'
      elif site == 'twitter':
        return f'@{user_data["twitter"].rsplit("@", 1)[-1]} on Twitter'
      elif site == 'mastodon':
        *_, mastodon_user, mastodon_instance = user_data["mastodon"].rsplit('@', 2)
        return f'@{mastodon_user} on {mastodon_instance}'
      else:
        print(f'Unknown site "{site}" found in user tag; ignoring...')
    return super().user_tag_root(data)

class AryionTransformer(BbcodeTransformer):
  def __init__(self, self_user, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      return self.user_tag_root((UserTag(eka=self_user),))
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site in ('eka', 'aryion')

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data['eka']:
      return f':icon{user_data["eka"]}:'
    return super().user_tag_root(data)

class FuraffinityTransformer(BbcodeTransformer):
  def __init__(self, self_user, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      return self.user_tag_root((UserTag(fa=self_user),))
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site in ('fa', 'furaffinity')

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data['fa']:
      return f':icon{user_data["fa"]}:'
    return super().user_tag_root(data)

class WeasylTransformer(MarkdownTransformer):
  def __init__(self, self_user, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      return self.user_tag_root((UserTag(weasyl=self_user),))
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site == 'weasyl'

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
    return super().user_tag_root(data)

class InkbunnyTransformer(BbcodeTransformer):
  def __init__(self, self_user, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      return self.user_tag_root((UserTag(ib=self_user),))
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site in ('ib', 'inkbunny')

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
    return super().user_tag_root(data)

class SoFurryTransformer(BbcodeTransformer):
  def __init__(self, self_user, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      return self.user_tag_root((UserTag(sf=self_user),))
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site in ('sf', 'sofurry')

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
    return super().user_tag_root(data)


def parse_description(description_path, config_path, out_dir, ignore_empty_files=False):
  for proc in psutil.process_iter(['cmdline']):
    if proc.info['cmdline'] and 'libreoffice' in proc.info['cmdline'][0] and '--writer' in proc.info['cmdline'][1:]:
      if ignore_empty_files:
        print('WARN: LibreOffice Writer appears to be running. This command may output empty files until it is closed.')
        break
      print('WARN: LibreOffice Writer appears to be running. This command may raise an error until it is closed.')
      break

  ps = subprocess.Popen(('libreoffice', '--cat', description_path), stdout=subprocess.PIPE)
  description = '\n'.join(line.strip() for line in io.TextIOWrapper(ps.stdout, encoding='utf-8-sig'))
  if not description or re.match(r'^\s+$', description):
    error = f'Description processing returned empty file: libreoffice --cat {description_path}'
    if ignore_empty_files:
      print(f'Ignoring error ({error})')
    else:
      raise RuntimeError(error)

  parsed_description = DESCRIPTION_PARSER.parse(description)
  transformations = {
    'aryion': ('desc_aryion.txt', AryionTransformer),
    'furaffinity': ('desc_furaffinity.txt', FuraffinityTransformer),
    'inkbunny': ('desc_inkbunny.txt', InkbunnyTransformer),
    'sofurry': ('desc_sofurry.txt', SoFurryTransformer),
    'weasyl': ('desc_weasyl.md', WeasylTransformer),
  }
  with open(config_path, 'r') as f:
    config = json.load(f)
  # Validate JSON
  errors = []
  if type(config) is not dict:
    errors.append(ValueError('Configuration must be a JSON object'))
  else:
    for (website, username) in config.items():
      if website not in transformations:
        errors.append(ValueError(f'Website \'{website}\' is unsupported'))
      elif type(username) is not str:
        errors.append(ValueError(f'Website \'{website}\' has invalid username \'{json.dumps(username)}\''))
      elif username.strip() == '':
        errors.append(ValueError(f'Website \'{website}\' has empty username'))
    if not any(ws in config for ws in transformations):
      errors.append(ValueError('No valid websites found'))
  if errors:
    raise ExceptionGroup('Invalid configuration for description parsing', errors)
  # Create descriptions
  RE_MULTIPLE_EMPTY_LINES = re.compile(r'\n\n+')
  for (website, username) in config.items():
    (filepath, transformer) = transformations[website]
    with open(os.path.join(out_dir, filepath), 'w') as f:
      if description.strip():
        transformed_description = transformer(username).transform(parsed_description)
        f.write(RE_MULTIPLE_EMPTY_LINES.sub('\n\n', transformed_description).strip() + '\n')
      else:
        f.write('')
