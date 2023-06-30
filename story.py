import io
import json
import os
import re
import subprocess


def get_rtf_styles(rtf_source: str):
  match_list = re.findall(r'\\s(\d+)(?:\\sbasedon\d+)?\\snext\d+((?:\\[a-z0-9]+ ?)+)(?: ([A-Z][a-zA-Z ]*));', rtf_source)
  if not match_list:
    raise ValueError(f'Couldn\'t find valid RTF styles')
  rtf_styles = {}
  for (style_number, partial_rtf_style, style_name) in match_list:
    rtf_style = r'\s' + style_number + partial_rtf_style
    rtf_styles[int(style_number)] = rtf_style
    rtf_styles[style_name] = rtf_style
  return rtf_styles

def parse_story(story_path, config_path, out_dir, temp_dir, ignore_empty_files=False):
  with open(config_path, 'r') as f:
    config = json.load(f)
  if type(config) is not dict:
    raise ValueError('Configuration must be a JSON object')
  should_create_txt_story = any(ws in config for ws in ('furaffinity', 'weasyl', 'inkbunny', 'sofurry'))
  should_create_rtf_story = any(ws in config for ws in ('aryion',))
  if not should_create_txt_story and not should_create_rtf_story:
    raise ValueError('')

  story_filename = os.path.split(story_path)[1].rsplit('.')[0]
  txt_out_path = os.path.join(out_dir, f'{story_filename}.txt') if should_create_txt_story else os.devnull
  txt_tmp_path = os.path.join(temp_dir, f'{story_filename}.txt') if should_create_rtf_story else os.devnull
  RE_EMPTY_LINE = re.compile('^$')
  is_only_empty_lines = True
  ps = subprocess.Popen(('libreoffice', '--cat', story_path), stdout=subprocess.PIPE)
  with open(txt_out_path, 'w', newline='\r\n') as txt_out, open(txt_tmp_path, 'w') as txt_tmp:
    needs_empty_line = False
    for line in io.TextIOWrapper(ps.stdout, encoding='utf-8-sig'):
      # Remove empty lines
      line = line.strip()
      if RE_EMPTY_LINE.search(line) and not is_only_empty_lines:
        needs_empty_line = True
      else:
        if is_only_empty_lines:
          txt_out.writelines((line,))
          txt_tmp.writelines((line,))
          is_only_empty_lines = False
        else:
          if needs_empty_line:
            txt_out.writelines(('\n\n', line))
            needs_empty_line = False
          else:
            txt_out.writelines(('\n', line))
          txt_tmp.writelines(('\n', line))
    txt_out.writelines(('\n'))
  if is_only_empty_lines:
    error = f'Story processing returned empty file: libreoffice --cat {story_path}'
    if ignore_empty_files:
      print(f'Ignoring error ({error})')
    else:
      raise RuntimeError(error)
  if should_create_rtf_story:
    rtf_out_path = os.path.join(out_dir, f'{story_filename}.rtf')
    # Convert temporary .txt to .rtf
    subprocess.run(['libreoffice', '--convert-to', 'rtf:Rich Text Format', '--outdir', out_dir, txt_tmp_path], check=True, capture_output=True)
    # Convert monospace font ('Preformatted Text') to serif ('Normal')
    with open(rtf_out_path, 'r+') as f:
      rtf = f.read()
      rtf_styles = get_rtf_styles(rtf)
      monospace_style = rtf_styles['Preformatted Text']  # rtf_styles[20]
      serif_style = rtf_styles['Normal']                 # rtf_styles[0]
      f.seek(0)
      f.write(rtf.replace(monospace_style, serif_style))
      f.truncate()
