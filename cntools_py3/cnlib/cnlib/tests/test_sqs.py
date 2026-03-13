#!/usr/bin/env python
"""
SQS tests.
"""
import time
import unittest

from boto.sqs.connection import SQSConnection
from moto import mock_sqs_deprecated as mock_sqs

from .. import sqs

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'


class PopulateQueueTestCase(unittest.TestCase):
    def setUp(self):
        self.mock = mock_sqs()
        self.mock.start()

        self.connection = SQSConnection()
        self.queue_name = 'cnlib_test_%s' % int(time.time())
        self.queue = self.connection.create_queue(self.queue_name)

        # This is what we're testing.  The rest is some helpful setup.
        self.handler = sqs.PopulateQueue(self.queue_name)

    def tearDown(self):
        self.mock.stop()

    def test_send(self):
        self.handler.send('blah,foo')
        msg = self.queue.get_messages()[0]
        self.assertEqual(msg.get_body(), 'blah,foo')


class ConsumeQueueTestCase(unittest.TestCase):
    def setUp(self):
        self.mock = mock_sqs()
        self.mock.start()

        self.connection = SQSConnection()
        self.queue_name = 'cnlib_test_%s' % int(time.time())
        self.queue = self.connection.create_queue(self.queue_name)

        # This is what we're testing.  The rest is some helpful setup.
        self.handler = sqs.ConsumeQueue(self.queue_name)

    def tearDown(self):
        self.mock.stop()

    def test_poll(self):
        self.queue.write(self.queue.new_message('foo,and,bar'))
        msg = self.handler.poll()
        self.assertEqual(msg.get_body(), 'foo,and,bar')


class InOutQueuesTestCase(unittest.TestCase):
    def setUp(self):
        self.mock = mock_sqs()
        self.mock.start()

        self.connection = SQSConnection()
        self.in_name = 'in_cnlib_test_%s' % int(time.time())
        self.out_name = 'out_cnlib_test_%s' % int(time.time())
        self.in_queue = self.connection.create_queue(self.in_name)
        self.out_queue = self.connection.create_queue(self.out_name)

        # This is what we're testing.  The rest is some helpful setup.
        self.handler = sqs.InOutQueues(self.in_name, self.out_name)

    def tearDown(self):
        self.mock.stop()

    def test_send(self):
        self.handler.send('blah,foo')
        msg = self.out_queue.get_messages()[0]
        self.assertEqual(msg.get_body(), 'blah,foo')

    def test_poll(self):
        self.in_queue.write(self.in_queue.new_message('foo,and,bar'))
        msg = self.handler.poll()
        self.assertEqual(msg.get_body(), 'foo,and,bar')


if __name__ == '__main__':
    unittest.main()
