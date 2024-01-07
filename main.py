#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
import argcomplete
from argcomplete.completers import FilesCompleter, DirectoriesCompleter
import argparse
import os
from subprocess import CalledProcessError
import shutil
import tempfile

from description import parse_description
from story import parse_story


def main(out_dir_path=None, story_path=None, description_path=None, file_path=None, config_path=None, keep_out_dir=False, ignore_empty_files=False):
  if not out_dir_path:
    raise ValueError('Missing out_dir_path')
  if not config_path:
    raise ValueError('Missing config_path')
  remove_out_dir = not keep_out_dir and os.path.isdir(out_dir_path)
  with tempfile.TemporaryDirectory() as tdir:
    # Clear output dir if it exists and shouldn't be kept
    if remove_out_dir:
      os.rename(out_dir_path, os.path.join(tdir, 'old_out'))
    if not os.path.isdir(out_dir_path):
      os.mkdir(out_dir_path)

    try:
      # Convert original file to .rtf (Aryion) and .txt (all others)
      if story_path:
        parse_story(story_path, config_path, out_dir_path, tdir, ignore_empty_files)

      # Parse FA description and convert for each website
      if description_path:
        parse_description(description_path, config_path, out_dir_path, ignore_empty_files)

      # Copy generic file over to output
      if file_path:
        shutil.copy(file_path, out_dir_path)

    except CalledProcessError as e:
      if remove_out_dir:
        # Revert directory removal on error
        os.rename(out_dir_path, os.path.join(tdir, 'get_rid_of_this'))
        os.rename(os.path.join(tdir, 'old_out'), out_dir_path)
      print(f'Command exited with code {e.returncode}: {e.stderr.decode("utf-8-sig")}')
      exit(1)
    except Exception as e:
      if remove_out_dir:
        # Revert directory removal on error
        os.rename(out_dir_path, os.path.join(tdir, 'get_rid_of_this'))
        os.rename(os.path.join(tdir, 'old_out'), out_dir_path)
      raise e


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='generate multi-gallery upload-ready files')
  parser.add_argument('-o', '--output-dir', dest='out_dir_path', default='./out',
                      help='path of output directory').completer = DirectoriesCompleter
  parser.add_argument('-c', '--config', dest='config_path', default='./config.json',
                      help='path of JSON configuration file').completer = FilesCompleter
  parser.add_argument('-s', '--story', dest='story_path',
                      help='path of LibreOffice-readable story file').completer = FilesCompleter
  parser.add_argument('-d', '--description', dest='description_path',
                      help='path of BBCode-formatted description file').completer = FilesCompleter
  parser.add_argument('-f', '--file', dest='file_path',
                      help='path of generic file to include in output (i.e. an image or thumbnail)').completer = FilesCompleter
  parser.add_argument('-k', '--keep-out-dir', dest='keep_out_dir', action='store_true',
                      help='whether output directory contents should be kept.\nif set, a script error may leave partial files behind')
  parser.add_argument('-I', '--ignore-empty-files', dest='ignore_empty_files', action='store_true',
                      help='do not raise an error if any input file is empty or whitespace-only')
  argcomplete.autocomplete(parser)
  args = parser.parse_args()

  if not any([args.story_path, args.description_path]):
    parser.error('at least one of ( --story | --description ) must be set')
  if args.out_dir_path and os.path.exists(args.out_dir_path) and not os.path.isdir(args.out_dir_path):
    parser.error('--output-dir must be an existing directory or inexistent')
  if args.story_path and not os.path.isfile(args.story_path):
    parser.error('--story must be a valid file')
  if args.description_path and not os.path.isfile(args.description_path):
    parser.error('--description must be a valid file')
  if args.file_path and not os.path.isfile(args.file_path):
    parser.error('--file must be a valid file')
  if args.config_path and not os.path.isfile(args.config_path):
    parser.error('--config must be a valid file')

  main(**vars(args))
