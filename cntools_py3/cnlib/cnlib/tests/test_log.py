#!/usr/bin/env python
"""
Logging tests.
"""
import logging
import os
import tempfile
import unittest

from .. import log

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'


class LogTestCase(unittest.TestCase):
    def setUp(self):
        self.log_name = tempfile.mktemp()
        log.logfile(self.log_name, console=False)
        log.file_handler.setLevel(logging.INFO)
        self.logger = log.getLogger(__name__)

    def tearDown(self):
        os.remove(self.log_name)

    def test_file(self):
        self.logger.info('Informational message')
        with open(self.log_name) as f:
            for line in f:
                pass
        self.assertTrue('INFO' in line)
        self.assertTrue('Informational message' in line)


if __name__ == '__main__':
    unittest.main()
