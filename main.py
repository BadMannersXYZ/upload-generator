#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
import argcomplete
from argcomplete.completers import FilesCompleter, DirectoriesCompleter
import argparse
import json
import os
import re
from subprocess import CalledProcessError
import shutil
import tempfile

from description import parse_description
from story import parse_story
from sites import INVERSE_SUPPORTED_SITE_TAGS


def main(out_dir_path=None, story_path=None, description_path=None, file_paths=[], config_path=None, keep_out_dir=False, ignore_empty_files=False, define_options=[]):
  if not out_dir_path:
    raise ValueError('Missing out_dir_path')
  if not config_path:
    raise ValueError('Missing config_path')
  if not file_paths:
    file_paths = []
  if not define_options:
    define_options = []
  config = None
  if story_path or description_path:
    with open(config_path, 'r') as f:
      config_json = json.load(f)
    if type(config_json) is not dict:
      raise ValueError('The configuration file must contain a valid JSON object')
    config = {}
    for k, v in config_json.items():
      if type(v) is not str:
        raise ValueError(f'Invalid configuration value for entry "{k}": expected string, got {type(v)}')
      new_k = INVERSE_SUPPORTED_SITE_TAGS.get(k)
      if not new_k:
        print(f'Ignoring unknown configuration key "{k}"...')
      if new_k in config:
        raise ValueError(f'Duplicate configuration entry for website "{new_key}": found collision with key "{k}"')
      config[new_k] = v
    if len(config) == 0:
      raise ValueError(f'Invalid configuration file "{config_path}": no valid sites defined')
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
        parse_story(story_path, config, out_dir_path, tdir, ignore_empty_files)

      # Parse FA description and convert for each website
      if description_path:
        define_options_set = set(define_options)
        if len(define_options_set) < len(define_options):
          print('WARNING: duplicated entries defined with -D / --define-option')
        parse_description(description_path, config, out_dir_path, ignore_empty_files, define_options)

      # Copy generic files over to output
      for file_path in file_paths:
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
  parser.add_argument('-D', '--define-option', dest='define_options', action='append',
                      help='options to define as a truthy value when parsing descriptions')
  parser.add_argument('-s', '--story', dest='story_path',
                      help='path of LibreOffice-readable story file').completer = FilesCompleter
  parser.add_argument('-d', '--description', dest='description_path',
                      help='path of BBCode-formatted description file').completer = FilesCompleter
  parser.add_argument('-f', '--file', dest='file_paths', action='append',
                      help='path(s) of generic file(s) to include in output (i.e. an image or thumbnail)').completer = FilesCompleter
  parser.add_argument('-k', '--keep-out-dir', dest='keep_out_dir', action='store_true',
                      help='whether output directory contents should be kept.\nif set, a script error may leave partial files behind')
  parser.add_argument('-I', '--ignore-empty-files', dest='ignore_empty_files', action='store_true',
                      help='do not raise an error if any input file is empty or whitespace-only')
  argcomplete.autocomplete(parser)
  args = parser.parse_args()

  file_paths = args.file_paths or []
  if not (args.story_path or args.description_path or any(file_paths)):
    parser.error('at least one of ( --story | --description | --file ) must be set')
  if args.out_dir_path and os.path.exists(args.out_dir_path) and not os.path.isdir(args.out_dir_path):
    parser.error(f'--output-dir {args.out_dir_path} must be an existing directory or inexistent; found a file instead')
  if args.story_path and not os.path.isfile(args.story_path):
    parser.error(f'--story {args.story_path} is not a valid file')
  if args.description_path and not os.path.isfile(args.description_path):
    parser.error(f'--description {args.description_path} is not a valid file')
  for file_path in file_paths:
    if not os.path.isfile(file_path):
      parser.error(f'--file {file_path} is not a valid file')
  if (args.story_path or args.description_path) and args.config_path and not os.path.isfile(args.config_path):
    parser.error('--config must be a valid file')
  if args.define_options:
    for option in args.define_options:
      if not re.match(r'^[a-zA-Z0-9_-]+$', option):
        parser.error(f'--define-option {option} is not a valid option; it must only contain alphanumeric characters, dashes, or underlines')

  main(**vars(args))
