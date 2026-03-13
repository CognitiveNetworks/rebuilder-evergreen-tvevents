#!/usr/bin/env python
"""
Tests for cnlib.
"""
import unittest

from test_log import LogTestCase
from test_sqs import (
    PopulateQueueTestCase,
    ConsumeQueueTestCase,
    InOutQueuesTestCase,
)
from test_s3 import BaseS3HandlerTestCase, SingleBucketS3HandlerTestCase


if __name__ == '__main__':
    unittest.main()
