#!/usr/bin/env python
import glob
import os.path
from parameterized import parameterized
import re
import tempfile
import unittest
import warnings

from description import parse_description, DescriptionParsingError

class TestParseDescription(unittest.TestCase):
  config = {
    'aryion': 'UserAryion',
    'furaffinity': 'UserFuraffinity',
    'inkbunny': 'UserInkbunny',
    'sofurry': 'UserSoFurry',
    'weasyl': 'UserWeasyl',
  }
  define_options = {'test_parse_description'}

  def setUp(self):
    self.tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    warnings.simplefilter('ignore', ResourceWarning)

  def tearDown(self):
    self.tmpdir.cleanup()
    warnings.simplefilter('default', ResourceWarning)

  @parameterized.expand([
    (re.match(r'.*(input_\d+)\.txt', v)[1], v) for v in sorted(glob.iglob('./test/description/input_*.txt'))
  ])
  def test_parse_success(self, name, test_description):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
      parse_description(test_description, self.config, tmpdir, define_options=self.define_options)
      for expected_output_file in glob.iglob(f'./test/description/output_{name[6:]}/*'):
        received_output_file = os.path.join(tmpdir, os.path.split(expected_output_file)[1])
        self.assertTrue(os.path.exists(received_output_file))
        self.assertTrue(os.path.isfile(received_output_file))
        with open(received_output_file, 'r') as f:
          received_description = f.read()
        with open(expected_output_file, 'r') as f:
          expected_description = f.read()
        self.assertEqual(received_description, expected_description)

  @parameterized.expand([
    (re.match(r'.*(error_.+)\.txt', v)[1], v) for v in sorted(glob.iglob('./test/description/error_*.txt'))
  ])
  def test_parse_errors(self, _, test_description):
    self.assertRaises(DescriptionParsingError, lambda: parse_description(test_description, self.config, self.tmpdir.name, define_options=self.define_options))
    self.assertListEqual(glob.glob(os.path.join(self.tmpdir.name, '*')), [])


if __name__ == '__main__':
    unittest.main()
