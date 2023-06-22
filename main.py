import argparse
import io
import os
import re
import subprocess
import tempfile

from parse import parse_description

OUT_DIR = './out'


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

def main(story_path=None, description_path=None, keep_out_dir=False, ignore_empty_files=False):
  remove_out_dir = not keep_out_dir and os.path.isdir(OUT_DIR)
  with tempfile.TemporaryDirectory() as tdir:
    # Clear OUT_DIR if it exists and shouldn't be kept
    if remove_out_dir:
      os.rename(OUT_DIR, os.path.join(tdir, 'old_out'))
    if not os.path.isdir(OUT_DIR):
      os.mkdir(OUT_DIR)

    try:
      # Convert original file to .rtf (Aryion) and .txt (all others)
      if story_path:
        story_filename = os.path.split(story_path)[1].rsplit('.')[0]
        txt_out_path = os.path.join(OUT_DIR, f'{story_filename}.txt')
        txt_tmp_path = os.path.join(tdir, f'{story_filename}.txt')
        rtf_out_path = os.path.join(OUT_DIR, f'{story_filename}.rtf')
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
        # Convert temporary .txt to .rtf
        subprocess.run(['libreoffice', '--convert-to', 'rtf:Rich Text Format', '--outdir', OUT_DIR, txt_tmp_path], check=True, capture_output=True)
        # Convert monospace font ('Preformatted Text') to serif ('Normal')
        with open(rtf_out_path, 'r+') as f:
          rtf = f.read()
          rtf_styles = get_rtf_styles(rtf)
          monospace_style = rtf_styles['Preformatted Text']  # rtf_styles[20]
          serif_style = rtf_styles['Normal']                 # rtf_styles[0]
          f.seek(0)
          f.write(rtf.replace(monospace_style, serif_style))
          f.truncate()

      # Parse FA description and convert for each website
      if description_path:
        ps = subprocess.Popen(('libreoffice', '--cat', description_path), stdout=subprocess.PIPE)
        desc = '\n'.join(line.strip() for line in io.TextIOWrapper(ps.stdout, encoding='utf-8-sig'))
        if not desc or re.match(r'^\s+$', desc):
          error = f'Description processing returned empty file: libreoffice --cat {description_path}'
          if ignore_empty_files:
            print(f'Ignoring error ({error})')
          else:
            raise RuntimeError(error)
        parse_description(desc, OUT_DIR)

    except subprocess.CalledProcessError as e:
      if remove_out_dir:
        # Revert directory removal on error
        os.rename(OUT_DIR, os.path.join(tdir, 'get_rid_of_this'))
        os.rename(os.path.join(tdir, 'old_out'), OUT_DIR)
      print(f'Command exited with code {e.returncode}: {e.stderr.decode("utf-8-sig")}')
      exit(1)
    except Exception as e:
      if remove_out_dir:
        # Revert directory removal on error
        os.rename(OUT_DIR, os.path.join(tdir, 'get_rid_of_this'))
        os.rename(os.path.join(tdir, 'old_out'), OUT_DIR)
      raise e


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='generate multi-gallery upload-ready files')
  parser.add_argument('-s', '--story', dest='story_path',
                      help='path of LibreOffice-readable story file')
  parser.add_argument('-d', '--description', dest='description_path',
                      help='path of LibreOffice-readable description file')
  parser.add_argument('-k', '--keep-out-dir', dest='keep_out_dir', action='store_true',
                      help='whether output directory contents should be kept')
  parser.add_argument('-i', '--ignore-empty-files', dest='ignore_empty_files', action='store_true',
                      help='do not raise an error if any input file is empty or whitespace-only')
  args = parser.parse_args()

  if not any([args.story_path, args.description_path]):
    parser.error('at least one of ( --story | --description ) must be set')
  if args.story_path and not os.path.isfile(args.story_path):
    parser.error('--story must be a valid file')
  if args.description_path and not os.path.isfile(args.description_path):
    parser.error('--description must be a valid file')

  main(**vars(args))
