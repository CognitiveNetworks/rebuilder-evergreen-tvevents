"""
Library for working with s3.
"""
import os
import time
import yaml
import datetime
import threading

import six
from six import BytesIO
from six.moves.urllib.parse import urlparse

from boto.s3 import connect_to_region
from boto.s3.key import Key

from . import log

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'


logger = log.getLogger(__name__)


class ConnectorMixin(object):
    """
    Basic mixin for connecting to S3, obtaining buckets and keys.
    """
    def __init__(self, aws_key=None, secret_key=None):
        self._connection = self._get_connection(aws_key, secret_key)

    def _get_all_buckets(self):
        try:
            return self._connection.get_all_buckets()
        except Exception as e:
            logger.critical('Unable to list s3 buckets: %s' % e)
            raise

    @staticmethod
    def _get_connection(aws_key=None, secret_key=None):
        try:
            aws_region = os.environ.get('AWS_REGION', 'us-east-1')
            return connect_to_region(aws_region)
        except Exception as msg:
            logger.critical('Unable to connect to s3: %s' % msg)
            raise

    @staticmethod
    def _get_bucket(connection, bucket_name):
        try:
            return connection.get_bucket(bucket_name, validate=False)
        except Exception as msg:
            logger.critical('Unable to get bucket %s: %s' % (bucket_name, msg))
            raise

    @staticmethod
    def _get_or_create_bucket(connection, bucket_name):
        try:
            bucket = connection.lookup(bucket_name, validate=True)
            if bucket is None:
                bucket = connection.create_bucket(bucket_name)
            return bucket
        except Exception as msg:
            logger.critical(
                'Unable to get or create bucket %s: %s' % (bucket_name, msg))
            raise

    @classmethod
    def _list_keys(cls, bucket, prefix='', delimiter='', marker=''):
        try:
            return bucket.list(prefix, delimiter, marker)
        except Exception as msg:
            logger.critical('Unable to list keys: %s' % msg)
            raise

    @classmethod
    def _get_key(cls, bucket, key_name):
        try:
            return bucket.get_key(key_name)
        except Exception as msg:
            logger.critical('Unable to get key %s: %s' % (key_name, msg))
            raise

    @classmethod
    def _delete_key(cls, bucket, key_name):
        try:
            return bucket.delete_key(key_name)
        except Exception as msg:
            logger.critical('Unable to delete key %s: %s' % (key_name, msg))
            raise

    @classmethod
    def _delete_keys(cls, bucket, keys, raise_on_errors=True):
        try:
            r = bucket.delete_keys(keys)
            if raise_on_errors and r.errors:
                raise RuntimeError('Keys not deleted', r.errors)
            return r
        except Exception as msg:
            logger.critical('Unable to delete keys: {}'.format(msg))
            raise

    @classmethod
    def url_to_key(cls, url):
        path = urlparse(url).path
        if path.startswith('/'):
            return path[1:]
        return path


class SingleBucketMixin(ConnectorMixin):
    """
    Mixing for a typical work-flow using a single bucket.
    """
    def __init__(self, bucket_name, create_missing=False,
                 aws_key=None, secret_key=None):
        ConnectorMixin.__init__(self, aws_key, secret_key)
        if create_missing:
            self.bucket = self._get_or_create_bucket(
                self._connection, bucket_name)
        else:
            self.bucket = self._get_bucket(self._connection, bucket_name)

    def validate_bucket(self, bucket_name):
        if self.bucket.name != bucket_name:
            msg = 'Unexpected bucket name: %s instead of %s' % (
                bucket_name, self.bucket.name)
            logger.critical(msg)
            raise Exception(msg)


class ReadWriteMixin(object):
    """
    Mixing providing read and write methods.
    """
    enable_encryption = os.getenv("S3_ENCRYPTION", False)

    @classmethod
    def _write_from_file(cls, bucket, key, fp):
        try:
            return Key(bucket, key).set_contents_from_file(fp, encrypt_key=cls.enable_encryption)
        except Exception as msg:
            logger.critical('Error writing into key %s: %s' % (key, msg))
            raise

    @classmethod
    def _write_from_filename(cls, bucket, key, filename):
        with open(filename, 'rb') as fp:
            return cls._write_from_file(bucket, key, fp)

    @classmethod
    def _write_from_string(cls, bucket, key, line):
        try:
            if not isinstance(line, six.binary_type):
                line = line.encode('utf-8')
            fp = BytesIO(line)
            return cls._write_from_file(bucket, key, fp)
        except Exception as msg:
            logger.critical('Error using content %s: %s' % (line, msg))
            raise

    @classmethod
    def _read_to_file(cls, bucket, key, fp):
        try:
            Key(bucket, key).get_contents_to_file(fp)
        except Exception as msg:
            logger.critical('Error reading from key %s: %s' % (key, msg))
            raise

    @classmethod
    def _read_to_filename(cls, bucket, key, filename):
        with open(filename, 'wb') as fp:
            cls._read_to_file(bucket, key, fp)

    @classmethod
    def _read_to_string(cls, bucket, key, encoding=None):
        try:
            fp = BytesIO()
            cls._read_to_file(bucket, key, fp)
            value = fp.getvalue()
            if encoding is not None:
                value = value.decode(encoding)
            return value
        except Exception as msg:
            logger.critical('Error reading from key %s: %s' % (key, msg))
            raise


class BaseS3Handler(ConnectorMixin, ReadWriteMixin):
    """
    Handler for s3 services.
    """
    def __init__(self, aws_key=None, secret_key=None):
        ConnectorMixin.__init__(self, aws_key, secret_key)

    def get_bucket(self, bucket_name):
        return self._get_bucket(self._connection, bucket_name)

    def get_or_create_bucket(self, bucket_name):
        return self._get_or_create_bucket(self._connection, bucket_name)

    @classmethod
    def write_from_file(cls, bucket, key, fp):
        return cls._write_from_file(bucket, key, fp)

    @classmethod
    def write_from_filename(cls, bucket, key, filename):
        return cls._write_from_filename(bucket, key, filename)

    @classmethod
    def write_from_string(cls, bucket, key, line):
        return cls._write_from_string(bucket, key, line)

    @classmethod
    def read_to_file(cls, bucket, key, fp):
        return cls._read_to_file(bucket, key, fp)

    @classmethod
    def read_to_filename(cls, bucket, key, filename):
        return cls._read_to_filename(bucket, key, filename)

    @classmethod
    def read_to_string(cls, bucket, key, encoding=None):
        return cls._read_to_string(bucket, key, encoding)


class ReadWriteAdapterMixin(ReadWriteMixin):
    def write_from_file(self, key, fp):
        return self._write_from_file(self.bucket, key, fp)

    def write_from_filename(self, key, filename):
        return self._write_from_filename(self.bucket, key, filename)

    def write_from_string(self, key, line):
        return self._write_from_string(self.bucket, key, line)

    def read_to_file(self, key, fp):
        return self._read_to_file(self.bucket, key, fp)

    def read_to_filename(self, key, filename):
        return self._read_to_filename(self.bucket, key, filename)

    def read_to_string(self, key, encoding=None):
        return self._read_to_string(self.bucket, key, encoding)

    def list_keys(self, prefix='', delimiter='', marker=''):
        return self._list_keys(self.bucket, prefix, delimiter, marker)

    def get_key(self, key_name):
        return self._get_key(self.bucket, key_name)

    def delete_key(self, key_name):
        return self._delete_key(self.bucket, key_name)

    def delete_keys(self, keys, raise_on_errors=True):
        return self._delete_keys(self.bucket, keys, raise_on_errors)


class SingleBucketS3Handler(SingleBucketMixin, ReadWriteAdapterMixin):
    pass


class SingleEncryptedBucketS3Handler(SingleBucketMixin, ReadWriteAdapterMixin):
    enable_encryption = True


class S3ObjectStatus(threading.Thread):
    def __init__(self, bucket_name, key, period=60, handler=None, **kwargs):
        super(S3ObjectStatus, self).__init__(**kwargs)

        self.key = key
        self.period = period
        self.sync_status = {}
        self.s3_handler = handler or SingleBucketS3Handler(bucket_name, **kwargs)

    def run(self):
        try:
            while True:
                self.update_sync_status()
                time.sleep(self.period)
        except Exception as e:
            logger.exception(e)

    def _get_last_modified(self, key):
        obj = self.s3_handler.get_key(self.key)
        return time.mktime(
            datetime.datetime.strptime(
            obj.last_modified, "%a, %d %b %Y %H:%M:%S %Z").timetuple())

    def update_sync_status(self):
        try:
            last_synced = self.sync_status[self.key]["last_updated_ts"]
        except KeyError:
            pass
        else:
            last_modified = self._get_last_modified(self.key)
            self.sync_status[self.key]["sync_needed"] = last_synced < last_modified

    def needs_sync(self):
        try:
            needs_sync = self.sync_status[self.key]["sync_needed"]
        except KeyError:
            needs_sync = True

        return needs_sync

    def sync(self):
        last_modified = self._get_last_modified(self.key)

        if not self.key in self.sync_status:
            self.sync_status[self.key] = {}

        self.sync_status[self.key]["last_updated_ts"] = last_modified


class EnvS3Handler(SingleBucketS3Handler):
    def __init__(self, bucket_name, key, period=60, handler=None, **kwargs):
        super(SingleBucketS3Handler, self).__init__(bucket_name, **kwargs)

        self.bucket_name = bucket_name
        self.key = key
        self.cache = {}

        self.s3_handler = handler or SingleBucketS3Handler(bucket_name, **kwargs)
        self.sync_thread = S3ObjectStatus(bucket_name, key, period, self.s3_handler)
        self.sync_thread.daemon = True
        self.sync_thread.start()

    def _needs_sync(self):
        return self.sync_thread.needs_sync()

    def _get_status(self):
        return self.sync_thread.sync_status[self.key]

    def _sync(self):
        return self.sync_thread.sync()

    def get_value(self, varname):

        try:
            key_status = self._get_status()
        except KeyError:
            pass
        else:
            if varname in self.cache and not self._needs_sync():
                return self.cache[varname]
        
        file_contents = self.s3_handler.read_to_string(self.key)
        y = yaml.load(file_contents, Loader=yaml.FullLoader)

        try:
            new_value = y[varname]
        except KeyError:
            try:
                new_value = y["environment"][os.environ["ZOO"]][varname]
            except KeyError:
                new_value = None
        
        self.cache[varname] = new_value
        self._sync()

        return new_value


