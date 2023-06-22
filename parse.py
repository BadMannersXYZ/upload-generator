import json
import lark
import os

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
  user_tag: eka_tag
          | fa_tag
          | weasyl_tag
          | ib_tag
          | sf_tag

  eka_tag: "[eka" ["=" USERNAME] "]" USERNAME "[/eka]"
         | "[eka"  "=" USERNAME  "]" [user_tag] "[/eka]"
  fa_tag: "[fa" ["=" USERNAME] "]" USERNAME "[/fa]"
        | "[fa"  "=" USERNAME  "]" [user_tag] "[/fa]"
  weasyl_tag: "[weasyl" ["=" USERNAME] "]" USERNAME "[/weasyl]"
            | "[weasyl"  "=" USERNAME  "]" [user_tag] "[/weasyl]"
  ib_tag: "[ib" ["=" USERNAME] "]" USERNAME "[/ib]"
        | "[ib"  "=" USERNAME  "]" [user_tag] "[/ib]"
  sf_tag: "[sf" ["=" USERNAME] "]" USERNAME "[/sf]"
        | "[sf"  "=" USERNAME  "]" [user_tag] "[/sf]"

  USERNAME: /[a-zA-Z0-9][a-zA-Z0-9 _-]*/
  URL: /(https?:\/\/)?[^\]]+/
  TEXT: /([^\[:]|[ \t\r\n]|:(?!icon))+/

  %import common.WS
"""

DESCRIPTION_PARSER = lark.Lark(DESCRIPTION_GRAMMAR, parser='lalr')


class UserTag:
  def __init__(self, default=None, eka=None, fa=None, weasyl=None, ib=None, sf=None):
    self.default = default
    self.eka = eka
    self.fa = fa
    self.weasyl = weasyl
    self.ib = ib
    self.sf = sf

class UploadTransformer(lark.Transformer):
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
    if user_data.fa:
      return self.url_tag((f'https://furaffinity.net/user/{user_data.fa.replace("_", "")}', user_data.default or user_data.fa))
    if user_data.eka:
      return self.url_tag((f'https://aryion.com/g4/user/{user_data.eka}', user_data.default or user_data.eka))
    if user_data.ib:
      return self.url_tag((f'https://inkbunny.net/{user_data.ib}', user_data.default or user_data.ib))
    if user_data.sf:
      return self.url_tag((f'https://{user_data.sf.replace(" ", "-").lower()}.sofurry.com', user_data.default or user_data.sf))
    if user_data.weasyl:
      self.url_tag((f'https://www.weasyl.com/~{user_data.weasyl}', user_data.default or user_data.weasyl))
    raise TypeError('Invalid UserTag data')

  def user_tag(self, data):
    return data[0]

  def eka_tag(self, data):
    attribute, inner = data[0], data[1]
    if attribute and attribute.strip():
      if isinstance(inner, UserTag):
        inner.eka = attribute.strip()
        return inner
      return UserTag(eka=attribute.strip(), default=inner and inner.strip())
    return UserTag(eka=inner.strip())

  def fa_tag(self, data):
    attribute, inner = data[0], data[1]
    if attribute and attribute.strip():
      if isinstance(inner, UserTag):
        inner.fa = attribute.strip()
        return inner
      return UserTag(fa=attribute.strip(), default=inner and inner.strip())
    return UserTag(fa=inner.strip())

  def weasyl_tag(self, data):
    attribute, inner = data[0], data[1]
    if attribute and attribute.strip():
      if isinstance(inner, UserTag):
        inner.weasyl = attribute.strip()
        return inner
      return UserTag(weasyl=attribute.strip(), default=inner and inner.strip())
    return UserTag(weasyl=inner.strip())

  def ib_tag(self, data):
    attribute, inner = data[0], data[1]
    if attribute and attribute.strip():
      if isinstance(inner, UserTag):
        inner.ib = attribute.strip()
        return inner
      return UserTag(ib=attribute.strip(), default=inner and inner.strip())
    return UserTag(ib=inner.strip())

  def sf_tag(self, data):
    attribute, inner = data[0], data[1]
    if attribute and attribute.strip():
      if isinstance(inner, UserTag):
        inner.sf = attribute.strip()
        return inner
      return UserTag(sf=attribute.strip(), default=inner and inner.strip())
    return UserTag(sf=inner.strip())

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

class AryionTransformer(BbcodeTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(AryionTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(eka=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data.eka:
      return f':icon{user_data.eka}:'
    return super(AryionTransformer, self).user_tag_root(data)

class FuraffinityTransformer(BbcodeTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(FuraffinityTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(fa=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data.fa:
      return f':icon{user_data.fa}:'
    return super(FuraffinityTransformer, self).user_tag_root(data)

class WeasylTransformer(MarkdownTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(WeasylTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(weasyl=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data.weasyl:
      return f'<!~{user_data.weasyl}>'
    if user_data.default is None:
      if user_data.fa:
        return f'<fa:{user_data.fa}>'
      if user_data.ib:
        return f'<ib:{user_data.ib}>'
      if user_data.sf:
        return f'<sf:{user_data.sf}>'
    return super(WeasylTransformer, self).user_tag_root(data)

class InkbunnyTransformer(BbcodeTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(InkbunnyTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(ib=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data.ib:
      return f'[iconname]{user_data.ib}[/iconname]'
    if user_data.default is None:
      if user_data.fa:
        return f'[fa]{user_data.fa}[/fa]'
      if user_data.sf:
        return f'[sf]{user_data.sf}[/sf]'
      if user_data.weasyl:
        return f'[weasyl]{user_data.weasyl}[/weasyl]'
    return super(InkbunnyTransformer, self).user_tag_root(data)

class SoFurryTransformer(BbcodeTransformer):
  def __init__(self, this_user, *args, **kwargs):
    super(SoFurryTransformer, self).__init__(*args, **kwargs)
    self.self_tag = lambda _: self.user_tag_root((UserTag(sf=this_user),))

  def user_tag_root(self, data):
    user_data = data[0]
    if user_data.sf:
      return f':icon{user_data.sf}:'
    if user_data.default is None:
      if user_data.fa:
        return f'fa!{user_data.fa}'
      if user_data.ib:
        return f'ib!{user_data.ib}'
    return super(SoFurryTransformer, self).user_tag_root(data)

TRANSFORMATIONS = {
  'furaffinity': ('desc_furaffinity.txt', FuraffinityTransformer),
  'aryion': ('desc_aryion.txt', AryionTransformer),
  'weasyl': ('desc_weasyl.md', WeasylTransformer),
  'inkbunny': ('desc_inkbunny.txt', InkbunnyTransformer),
  'sofurry': ('desc_sofurry.txt', SoFurryTransformer),
}


def parse_description(description, out_dir):
  parsed_description = DESCRIPTION_PARSER.parse(description)
  with open('config.json', 'r') as f:
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
