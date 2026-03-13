#!/usr/bin/env python
"""
S3 tests.
"""
import time
from six import BytesIO
import unittest

from boto.s3.connection import S3Connection
from boto.s3.key import Key
from moto import mock_s3_deprecated as mock_s3

from .. import s3

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'


class BaseS3HandlerTestCase(unittest.TestCase):
    def setUp(self):
        self.mock = mock_s3()
        self.mock.start()

        self.connection = S3Connection()
        token = int(time.time())
        self.bucket_name = 'test_bucket_%s' % token
        self.bucket = self.connection.create_bucket(self.bucket_name)
        self.key = '/test/key/%s/' % token
        Key(self.bucket, name=self.key).set_contents_from_string(
            'foo\nbar\nbaz\n')

        # This is what we're testing.  The rest is some helpful setup.
        self.handler = s3.BaseS3Handler()

    def tearDown(self):
        self.bucket.delete_key(self.key)
        self.bucket.delete()
        self.mock.stop()

    def test_get_bucket(self):
        bucket = self.handler.get_bucket(self.bucket_name)
        self.assertIsNotNone(bucket)
        self.assertEqual(bucket.__class__.__name__, 'Bucket')

    def test_get_bucket_bad(self):
        bucket = self.handler.get_bucket('foobar')
        self.assertRaises(Exception, bucket.get_tags)

    def test_get_or_create_bucket(self):
        old_bucket = self.handler.get_or_create_bucket(self.bucket_name)
        new_bucket = self.handler.get_or_create_bucket('foo_and_bar')
        for bucket in (old_bucket, new_bucket):
            self.assertIsNotNone(bucket)
            self.assertEqual(bucket.__class__.__name__, 'Bucket')

    def test_write_from_file(self):
        contents = b'baz\nand\nalso\nfoo'
        fp = BytesIO(contents)
        size = self.handler.write_from_file(self.bucket, self.key, fp)
        self.assertEqual(size, len(contents))

        new_contents = Key(self.bucket, name=self.key).get_contents_as_string()
        self.assertEqual(new_contents, contents)

    def test_read_to_string(self):
        contents = b'foo\nand\nbaz'
        key_obj = self.bucket.get_key(self.key)
        key_obj.set_contents_from_string(contents)
        got_contents = self.handler.read_to_string(self.bucket, key=self.key)
        self.assertEqual(contents, got_contents)

    def test_write_from_string(self):
        contents = 'foo\nand\nbaz\nblabla'
        self.handler.write_from_string(bucket=self.bucket, key=self.key, line=contents)
        key_obj = self.bucket.get_key(self.key)
        got_contents = key_obj.get_contents_as_string(encoding='utf8')
        self.assertEqual(contents, got_contents)

    def test_write_from_string_bytes(self):
        contents = b'foo\nand\nbaz\nblabla'
        self.handler.write_from_string(bucket=self.bucket, key=self.key, line=contents)
        key_obj = self.bucket.get_key(self.key)
        got_contents = key_obj.get_contents_as_string()
        self.assertEqual(contents, got_contents)

    def test_write_from_string_unicode(self):
        contents = u'foo\nand\nbaz\nblabla'
        self.handler.write_from_string(bucket=self.bucket, key=self.key, line=contents)
        key_obj = self.bucket.get_key(self.key)
        got_contents = key_obj.get_contents_as_string(encoding='utf-8')
        self.assertEqual(contents, got_contents)


class SingleBucketS3HandlerTestCase(unittest.TestCase):
    def setUp(self):
        self.mock = mock_s3()
        self.mock.start()

        self.connection = S3Connection()
        token = int(time.time())
        self.bucket_name = 'test_bucket_%s' % token
        self.bucket = self.connection.create_bucket(self.bucket_name)
        self.key = '/test/key/%s/' % token
        Key(self.bucket, name=self.key).set_contents_from_string(
            'foo\nbar\nbaz\n')

        # This is what we're testing.  The rest is some helpful setup.
        self.handler = s3.SingleBucketS3Handler(self.bucket_name)

    def tearDown(self):
        self.bucket.delete_key(self.key)
        self.bucket.delete()
        self.mock.stop()

    def test_write_from_file(self):
        contents = b'baz\nand\nalso\nfoo'
        fp = BytesIO(contents)
        size = self.handler.write_from_file(self.key, fp)
        self.assertEqual(size, len(contents))

        new_contents = Key(self.bucket, name=self.key).get_contents_as_string()
        self.assertEqual(new_contents, contents)

    def test_read_to_string(self):
        contents = b'foo\nand\nbaz'
        key_obj = self.bucket.get_key(self.key)
        key_obj.set_contents_from_string(contents)
        got_contents = self.handler.read_to_string(key=self.key)
        self.assertEqual(contents, got_contents)

    def test_read_to_filename(self):
        contents = b'foo333\nand33\nbaz44'
        key_obj = self.bucket.get_key(self.key)
        key_obj.set_contents_from_string(contents)

        filename = '/tmp/afafadfaqcqvbvryrw4524sgs'
        self.handler.read_to_filename(
            key=self.key,
            filename=filename)
        with open(filename, 'rb') as fp:
            got_contents = fp.read()

        self.assertEqual(contents, got_contents)

    def test_write_from_string(self):
        contents = 'foo\nand\nbaz\nblabla'
        self.handler.write_from_string(self.key, contents)
        key_obj = self.bucket.get_key(self.key)
        got_contents = key_obj.get_contents_as_string(encoding='utf-8')
        self.assertEqual(contents, got_contents)

    def test_write_from_string_bytes(self):
        contents = b'foo\nand\nbaz\nblabla'
        self.handler.write_from_string(self.key, contents)
        key_obj = self.bucket.get_key(self.key)
        got_contents = key_obj.get_contents_as_string()
        self.assertEqual(contents, got_contents)

    def test_write_from_string_unicode(self):
        contents = u'foo\nand\nbaz\nblabla'
        self.handler.write_from_string(self.key, contents)
        key_obj = self.bucket.get_key(self.key)
        got_contents = key_obj.get_contents_as_string(encoding='utf-8')
        self.assertEqual(contents, got_contents)

    def test_write_from_filename(self):
        contents = u'foo\nand\nbaz\nblabla1234'
        filename = '/tmp/fadfadfadsfasdfadsfadfadf524524'
        with open(filename, 'w') as fp:
            fp.write(contents)

        self.handler.write_from_filename(self.key, filename=filename)
        key_obj = self.bucket.get_key(self.key)
        got_contents = key_obj.get_contents_as_string(encoding='utf-8')
        self.assertEqual(contents, got_contents)

if __name__ == '__main__':
    unittest.main()
