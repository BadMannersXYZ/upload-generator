import argparse
import os
from subprocess import CalledProcessError
import tempfile

from description import parse_description
from story import parse_story

OUT_DIR = './out'


def main(story_path=None, description_path=None, config_path='./config.json', keep_out_dir=False, ignore_empty_files=False):
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
        parse_story(story_path, config_path, OUT_DIR, tdir, ignore_empty_files)

      # Parse FA description and convert for each website
      if description_path:
        parse_description(description_path, config_path, OUT_DIR, ignore_empty_files)

    except CalledProcessError as e:
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
                      help='path of BBCode-formatted description file')
  parser.add_argument('-c', '--config', dest='config_path', default='./config.json',
                      help='path of JSON configuration file')
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
  if args.config_path and not os.path.isfile(args.config_path):
    parser.error('--config must be a valid file')

  main(**vars(args))
