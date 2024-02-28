from collections import OrderedDict
import io
import json
import lark
import os
import psutil
import re
import subprocess
import typing

from sites import SUPPORTED_SITE_TAGS

SUPPORTED_USER_TAGS: typing.Mapping[str, typing.Set[str]] = {
  **SUPPORTED_SITE_TAGS,
  'twitter': {'twitter'},
  'mastodon': {'mastodon'},
}

DESCRIPTION_GRAMMAR = r"""
  ?start: document_list

  document_list: document+

  document: b_tag
          | i_tag
          | u_tag
          | center_tag
          | url_tag
          | self_tag
          | if_tag
          | user_tag_root
          | siteurl_tag_root
          | TEXT

  b_tag: "[b]" [document_list] "[/b]"
  i_tag: "[i]" [document_list] "[/i]"
  u_tag: "[u]" [document_list] "[/u]"
  center_tag: "[center]" [document_list] "[/center]"
  url_tag: "[url" ["=" [URL]] "]" [document_list] "[/url]"

  self_tag: "[self][/self]"
  if_tag: "[if=" CONDITION "]" [document_list] "[/if]" [ "[else]" [document_list] "[/else]" ]

  user_tag_root: "[user]" user_tag "[/user]"
  user_tag: user_tag_generic | """

DESCRIPTION_GRAMMAR += ' | '.join(f'user_tag_{tag}' for tag in SUPPORTED_USER_TAGS)
for tag, alts in SUPPORTED_USER_TAGS.items():
  DESCRIPTION_GRAMMAR += f'\n  user_tag_{tag}: '
  DESCRIPTION_GRAMMAR += ' | '.join(f'"[{alt}" ["=" USERNAME] "]" USERNAME "[/{alt}]" | "[{alt}" "=" USERNAME  "]" [user_tag] "[/{alt}]"' for alt in alts)

DESCRIPTION_GRAMMAR += r"""
  user_tag_generic: "[generic=" URL "]" USERNAME "[/generic]"

  siteurl_tag_root: "[siteurl]" siteurl_tag "[/siteurl]"
  siteurl_tag: siteurl_tag_generic | """

DESCRIPTION_GRAMMAR += ' | '.join(f'siteurl_tag_{tag}' for tag in SUPPORTED_SITE_TAGS)
for tag, alts in SUPPORTED_SITE_TAGS.items():
  DESCRIPTION_GRAMMAR += f'\n  siteurl_tag_{tag}: '
  DESCRIPTION_GRAMMAR += ' | '.join(f'"[{alt}" "=" URL "]" ( siteurl_tag | TEXT ) "[/{alt}]"' for alt in alts)

DESCRIPTION_GRAMMAR += r"""
  siteurl_tag_generic: "[generic=" URL "]" TEXT "[/generic]"

  USERNAME: / *@?[a-zA-Z0-9][a-zA-Z0-9 @._-]*/
  URL: / *(https?:\/\/)?[^\]]+ */
  TEXT: /([^\[]|[ \t\r\n])+/
  CONDITION: / *[a-z]+ *(==|!=) *[a-zA-Z0-9_-]+ *| *[a-z]+ +in +([a-zA-Z0-9_-]+ *, *)*[a-zA-Z0-9_-]+ */
"""

DESCRIPTION_PARSER = lark.Lark(DESCRIPTION_GRAMMAR, parser='lalr')


class DescriptionParsingError(ValueError):
  pass

class SiteSwitchTag:
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

  def __contains__(self, name: str) -> bool:
    return name in self._sites

  @property
  def sites(self):
    yield from self._sites

class UploadTransformer(lark.Transformer):
  def __init__(self, define_options=set(), *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.define_options = define_options
    # Init user_tag_xxxx methods
    def _user_tag_factory(tag):
      # Create a new user SiteSwitchTag if innermost node, or append to list in order
      def user_tag(data):
        attribute, inner = data[0], data[1]
        if attribute and attribute.strip():
          if isinstance(inner, SiteSwitchTag):
            inner[tag] = attribute.strip()
            return inner
          user = SiteSwitchTag(default=inner and inner.strip())
          user[tag] = attribute.strip()
          return user
        user = SiteSwitchTag()
        user[tag] = inner.strip()
        return user
      return user_tag
    for tag in SUPPORTED_USER_TAGS:
      setattr(self, f'user_tag_{tag}', _user_tag_factory(tag))
    # Init siteurl_tag_xxxx methods
    def _siteurl_tag_factory(tag):
      # Create a new siteurl SiteSwitchTag if innermost node, or append to list in order
      def siteurl_tag(data):
        attribute, inner = data[0], data[1]
        if attribute and attribute.strip():
          if isinstance(inner, SiteSwitchTag):
            inner[tag] = attribute.strip()
            return inner
          siteurl = SiteSwitchTag(default=inner and inner.strip())
          siteurl[tag] = attribute.strip()
          return siteurl
        siteurl = SiteSwitchTag()
        siteurl[tag] = inner.strip()
        return siteurl
      return siteurl_tag
    for tag in SUPPORTED_SITE_TAGS:
      setattr(self, f'siteurl_tag_{tag}', _siteurl_tag_factory(tag))

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

  def center_tag(self, _):
    raise NotImplementedError('UploadTransformer.center_tag is abstract')

  def url_tag(self, _):
    raise NotImplementedError('UploadTransformer.url_tag is abstract')

  def self_tag(self, _):
    raise NotImplementedError('UploadTransformer.self_tag is abstract')

  def transformer_matches_site(self, site: str) -> bool:
    raise NotImplementedError('UploadTransformer.transformer_matches_site is abstract')

  def transformer_matches_define(self, option: str) -> bool:
    return option in self.define_options

  def if_tag(self, data: typing.Tuple[str, str, str]):
    condition, truthy_document, falsy_document = data[0], data[1], data[2]
    # Test equality condition, i.e. `site==foo`
    equality_condition = condition.split('==', 1)
    if len(equality_condition) == 2 and equality_condition[1].strip():
      conditional_test = f'transformer_matches_{equality_condition[0].strip()}'
      if hasattr(self, conditional_test):
        if getattr(self, conditional_test)(equality_condition[1].strip()):
          return truthy_document or ''
        return falsy_document or ''
    # Test inequality condition, i.e. `site!=foo`
    inequality_condition = condition.split('!=', 1)
    if len(inequality_condition) == 2 and inequality_condition[1].strip():
      conditional_test = f'transformer_matches_{inequality_condition[0].strip()}'
      if hasattr(self, conditional_test):
        if not getattr(self, conditional_test)(inequality_condition[1].strip()):
          return truthy_document or ''
        return falsy_document or ''
    # Test inclusion condition, i.e. `site in foo,bar`
    inclusion_condition = condition.split(' in ', 1)
    if len(inclusion_condition) == 2 and inclusion_condition[1].strip():
      conditional_test = f'transformer_matches_{inclusion_condition[0].strip()}'
      if hasattr(self, conditional_test):
        matches = (parameter.strip() for parameter in inclusion_condition[1].split(','))
        if any(getattr(self, conditional_test)(match) for match in matches):
          return truthy_document or ''
        return falsy_document or ''
    raise ValueError(f'Invalid [if][/if] tag condition: {condition}')

  def user_tag_root(self, data):
    user_data: SiteSwitchTag = data[0]
    for site in user_data.sites:
      if site == 'generic':
        return self.url_tag((user_data['generic'], user_data.default))
      elif site == 'aryion':
        return self.url_tag((f'https://aryion.com/g4/user/{user_data["aryion"]}', user_data.default or user_data["aryion"]))
      elif site == 'furaffinity':
        return self.url_tag((f'https://furaffinity.net/user/{user_data["furaffinity"].replace("_", "")}', user_data.default or user_data['furaffinity']))
      elif site == 'weasyl':
        return self.url_tag((f'https://www.weasyl.com/~{user_data["weasyl"].replace(" ", "").lower()}', user_data.default or user_data['weasyl']))
      elif site == 'inkbunny':
        return self.url_tag((f'https://inkbunny.net/{user_data["inkbunny"]}', user_data.default or user_data['inkbunny']))
      elif site == 'sofurry':
        return self.url_tag((f'https://{user_data["sofurry"].replace(" ", "-").lower()}.sofurry.com', user_data.default or user_data['sofurry']))
      elif site == 'twitter':
        return self.url_tag((f'https://twitter.com/{user_data["twitter"].rsplit("@", 1)[-1]}', user_data.default or user_data['twitter']))
      elif site == 'mastodon':
        *_, mastodon_user, mastodon_instance = user_data["mastodon"].rsplit('@', 2)
        return self.url_tag((f'https://{mastodon_instance.strip()}/@{mastodon_user.strip()}', user_data.default or user_data['mastodon']))
      else:
        print(f'Unknown site "{site}" found in user tag; ignoring...')
    raise TypeError('Invalid user SiteSwitchTag data - no matches found')

  def user_tag(self, data):
    return data[0]

  def user_tag_generic(self, data):
    attribute, inner = data[0], data[1]
    user = SiteSwitchTag(default=inner.strip())
    user['generic'] = attribute.strip()
    return user

  def siteurl_tag_root(self, data):
    siteurl_data: SiteSwitchTag = data[0]
    if 'generic' in siteurl_data:
      return self.url_tag((siteurl_data['generic'], siteurl_data.default))
    return ''

  def siteurl_tag(self, data):
    return data[0]

  def siteurl_tag_generic(self, data):
    attribute, inner = data[0], data[1]
    siteurl = SiteSwitchTag(default=inner.strip())
    siteurl['generic'] = attribute.strip()
    return siteurl

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

  def center_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'[center]{data[0]}[/center]'

  def url_tag(self, data):
    if data[0] is None or not data[0].strip():
      return data[1].strip() if data[1] else ''
    return f'[url={data[0].strip()}]{data[1] if data[1] and data[1].strip() else data[0].strip()}[/url]'

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
    if data[0] is None or not data[0].strip():
      return data[1].strip() if data[1] else ''
    return f'[{data[1] if data[1] and data[1].strip() else data[0].strip()}]({data[0].strip()})'

class PlaintextTransformer(UploadTransformer):
  def b_tag(self, data):
    return str(data[0]) if data[0] else ''

  def i_tag(self, data):
    return str(data[0]) if data[0] else ''

  def u_tag(self, data):
    return str(data[0]) if data[0] else ''

  def center_tag(self, data):
    return str(data[0]) if data[0] else ''

  def url_tag(self, data):
    if data[0] is None or not data[0].strip():
      return data[1] if data[1] and data[1].strip() else ''
    if data[1] is None or not data[1].strip():
      return data[0].strip()
    return f'{data[1]}: {data[0].strip()}'

  def user_tag_root(self, data):
    user_data = data[0]
    for site in user_data.sites:
      if site == 'generic':
        break
      elif site == 'aryion':
        return f'{user_data["aryion"]} on Eka\'s Portal'
      elif site == 'furaffinity':
        return f'{user_data["furaffinity"]} on Fur Affinity'
      elif site == 'weasyl':
        return f'{user_data["weasyl"]} on Weasyl'
      elif site == 'inkbunny':
        return f'{user_data["inkbunny"]} on Inkbunny'
      elif site == 'sofurry':
        return f'{user_data["sofurry"]} on SoFurry'
      elif site == 'twitter':
        return f'@{user_data["twitter"].rsplit("@", 1)[-1]} on Twitter'
      elif site == 'mastodon':
        *_, mastodon_user, mastodon_instance = user_data["mastodon"].rsplit('@', 2)
        return f'@{mastodon_user.strip()} on {mastodon_instance.strip()}'
      else:
        print(f'Unknown site "{site}" found in user tag; ignoring...')
    return super().user_tag_root(data)

class AryionTransformer(BbcodeTransformer):
  def __init__(self, self_user=None, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      if self_user:
        return self.user_tag_root((SiteSwitchTag(aryion=self_user),))
      raise ValueError('self_tag is unavailable for AryionTransformer - no user provided')
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site in SUPPORTED_USER_TAGS['aryion']

  def user_tag_root(self, data):
    user_data: SiteSwitchTag = data[0]
    if user_data['aryion']:
      return f':icon{user_data["aryion"]}:'
    return super().user_tag_root(data)

  def siteurl_tag_root(self, data):
    siteurl_data: SiteSwitchTag = data[0]
    if 'aryion' in siteurl_data:
      return self.url_tag((siteurl_data['aryion'], siteurl_data.default))
    return super().siteurl_tag_root(data)

class FuraffinityTransformer(BbcodeTransformer):
  def __init__(self, self_user=None, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      if self_user:
        return self.user_tag_root((SiteSwitchTag(furaffinity=self_user),))
      raise ValueError('self_tag is unavailable for FuraffinityTransformer - no user provided')
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site in SUPPORTED_USER_TAGS['furaffinity']

  def user_tag_root(self, data):
    user_data: SiteSwitchTag = data[0]
    if user_data['furaffinity']:
      return f':icon{user_data["furaffinity"]}:'
    return super().user_tag_root(data)

  def siteurl_tag_root(self, data):
    siteurl_data: SiteSwitchTag = data[0]
    if 'furaffinity' in siteurl_data:
      return self.url_tag((siteurl_data['furaffinity'], siteurl_data.default))
    return super().siteurl_tag_root(data)

class WeasylTransformer(MarkdownTransformer):
  def __init__(self, self_user=None, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      if self_user:
        return self.user_tag_root((SiteSwitchTag(weasyl=self_user),))
      raise ValueError('self_tag is unavailable for WeasylTransformer - no user provided')
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site == 'weasyl'

  def center_tag(self, data):
    if data[0] is None or not data[0].strip():
      return ''
    return f'<div class="align-center">{data[0]}</div>'

  def user_tag_root(self, data):
    user_data: SiteSwitchTag = data[0]
    if user_data['weasyl']:
      return f'<!~{user_data["weasyl"].replace(" ", "")}>'
    for site in user_data.sites:
      if site == 'furaffinity':
        return f'<fa:{user_data["furaffinity"]}>'
      if site == 'inkbunny':
        return f'<ib:{user_data["inkbunny"]}>'
      if site == 'sofurry':
        return f'<sf:{user_data["sofurry"]}>'
    return super().user_tag_root(data)

  def siteurl_tag_root(self, data):
    siteurl_data: SiteSwitchTag = data[0]
    if 'weasyl' in siteurl_data:
      return self.url_tag((siteurl_data['weasyl'], siteurl_data.default))
    return super().siteurl_tag_root(data)

class InkbunnyTransformer(BbcodeTransformer):
  def __init__(self, self_user=None, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      if self_user:
        return self.user_tag_root((SiteSwitchTag(inkbunny=self_user),))
      raise ValueError('self_tag is unavailable for InkbunnyTransformer - no user provided')
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site in SUPPORTED_USER_TAGS['inkbunny']

  def user_tag_root(self, data):
    user_data: SiteSwitchTag = data[0]
    if user_data['inkbunny']:
      return f'[iconname]{user_data["inkbunny"]}[/iconname]'
    for site in user_data.sites:
      if site == 'furaffinity':
        return f'[fa]{user_data["furaffinity"]}[/fa]'
      if site == 'sofurry':
        return f'[sf]{user_data["sofurry"]}[/sf]'
      if site == 'weasyl':
        return f'[weasyl]{user_data["weasyl"].replace(" ", "").lower()}[/weasyl]'
    return super().user_tag_root(data)

  def siteurl_tag_root(self, data):
    siteurl_data: SiteSwitchTag = data[0]
    if 'inkbunny' in siteurl_data:
      return self.url_tag((siteurl_data['inkbunny'], siteurl_data.default))
    return super().siteurl_tag_root(data)

class SoFurryTransformer(BbcodeTransformer):
  def __init__(self, self_user=None, *args, **kwargs):
    super().__init__(*args, **kwargs)
    def self_tag(data):
      if self_user:
        return self.user_tag_root((SiteSwitchTag(sofurry=self_user),))
      raise ValueError('self_tag is unavailable for SoFurryTransformer - no user provided')
    self.self_tag = self_tag

  @staticmethod
  def transformer_matches_site(site: str) -> bool:
    return site in SUPPORTED_USER_TAGS['sofurry']

  def user_tag_root(self, data):
    user_data: SiteSwitchTag = data[0]
    if user_data['sofurry']:
      return f':icon{user_data["sofurry"]}:'
    for site in user_data.sites:
      if site == 'furaffinity':
        return f'fa!{user_data["furaffinity"]}'
      if site == 'inkbunny':
        return f'ib!{user_data["inkbunny"]}'
    return super().user_tag_root(data)

  def siteurl_tag_root(self, data):
    siteurl_data: SiteSwitchTag = data[0]
    if 'sofurry' in siteurl_data:
      return self.url_tag((siteurl_data['sofurry'], siteurl_data.default))
    return super().siteurl_tag_root(data)


def validate_parsed_tree(parsed_tree):
  for node in parsed_tree.iter_subtrees_topdown():
    if node.data in {'b_tag', 'i_tag', 'u_tag', 'url_tag'}:
      node_type = str(node.data)
      for node2 in node.find_data(node_type):
        if node != node2:
          raise DescriptionParsingError(f'Invalid nested {node_type} on line {node2.data.line} column {node2.data.column}')

def parse_description(description_path, config, out_dir, ignore_empty_files=False, define_options=set()):
  for proc in psutil.process_iter(['cmdline']):
    if proc.info['cmdline'] and 'libreoffice' in proc.info['cmdline'][0] and '--writer' in proc.info['cmdline'][1:]:
      if ignore_empty_files:
        print('WARN: LibreOffice Writer appears to be running. This command may output empty files until it is closed.')
        break
      print('WARN: LibreOffice Writer appears to be running. This command may raise an error until it is closed.')
      break

  description = ''
  with subprocess.Popen(('libreoffice', '--cat', description_path), stdout=subprocess.PIPE) as ps:
    description = '\n'.join(line.strip() for line in io.TextIOWrapper(ps.stdout, encoding='utf-8-sig'))
  if not description or re.match(r'^\s+$', description):
    error = f'Description processing returned empty file: libreoffice --cat {description_path}'
    if ignore_empty_files:
      print(f'Ignoring error ({error})')
    else:
      raise RuntimeError(error)

  try:
    parsed_description = DESCRIPTION_PARSER.parse(description)
  except lark.UnexpectedInput as e:
    input_error = e.match_examples(DESCRIPTION_PARSER.parse, {
      'Unclosed tag': ['[b]text', '[i]text', '[u]text', '[url]text'],
      'Unopened tag': ['text[/b]', 'text[/i]', 'text[/u]', 'text[/url]'],
      'Unknown tag': ['[invalid]text[/invalid]'],
      'Missing tag brackets': ['b]text[/b]', '[btext[/b]', '[b]text/b]', '[b]text[/b', 'i]text[/i]', '[itext[/i]', '[i]text/i]', '[i]text[/i', 'u]text[/u]', '[utext[/u]', '[u]text/u]', '[u]text[/u'],
      'Missing tag slash': ['[b]text[b]', '[i]text[i]', '[u]text[u]'],
      'Empty switch tag': ['[user][/user]', '[siteurl][/siteurl]'],
      'Empty user tag': ['[user][aryion][/aryion][/user]', '[user][furaffinity][/furaffinity][/user]', '[user][inkbunny][/inkbunny][/user]', '[user][sofurry][/sofurry][/user]', '[user][weasyl][/weasyl][/user]', '[user][twitter][/twitter][/user]', '[user][mastodon][/mastodon][/user]', '[user][aryion=][/aryion][/user]', '[user][furaffinity=][/furaffinity][/user]', '[user][inkbunny=][/inkbunny][/user]', '[user][sofurry=][/sofurry][/user]', '[user][weasyl=][/weasyl][/user]', '[user][twitter=][/twitter][/user]', '[user][mastodon=][/mastodon][/user]'],
      'Empty siteurl tag': ['[siteurl][aryion][/aryion][/siteurl]', '[siteurl][furaffinity][/furaffinity][/siteurl]', '[siteurl][inkbunny][/inkbunny][/siteurl]', '[siteurl][sofurry][/sofurry][/siteurl]', '[siteurl][weasyl][/weasyl][/siteurl]' '[siteurl][aryion=][/aryion][/siteurl]', '[siteurl][furaffinity=][/furaffinity][/siteurl]', '[siteurl][inkbunny=][/inkbunny][/siteurl]', '[siteurl][sofurry=][/sofurry][/siteurl]', '[siteurl][weasyl=][/weasyl][/siteurl]'],
    })
    raise DescriptionParsingError(f'Unable to parse description. {input_error or "Unknown grammar error"} in line {e.line} column {e.column}:\n{e.get_context(description)}') from e
  validate_parsed_tree(parsed_description)
  transformations = {
    'aryion': ('desc_aryion.txt', AryionTransformer),
    'furaffinity': ('desc_furaffinity.txt', FuraffinityTransformer),
    'inkbunny': ('desc_inkbunny.txt', InkbunnyTransformer),
    'sofurry': ('desc_sofurry.txt', SoFurryTransformer),
    'weasyl': ('desc_weasyl.md', WeasylTransformer),
  }
  # assert all(k in SUPPORTED_SITE_TAGS for k in transformations)
  # Validate JSON
  errors = []
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
        transformed_description = transformer(self_user=username, define_options=define_options).transform(parsed_description)
        cleaned_description = RE_MULTIPLE_EMPTY_LINES.sub('\n\n', transformed_description).strip()
        if cleaned_description:
          f.write(cleaned_description)
          f.write('\n')
      f.write('')
