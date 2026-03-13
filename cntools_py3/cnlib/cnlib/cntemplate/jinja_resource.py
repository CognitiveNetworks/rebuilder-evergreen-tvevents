"""
Resource handlers that support loading from remote resource
"""
import datetime
import random
import boto3
from abc import abstractmethod
from botocore.exceptions import ClientError
from gzip import GzipFile
from io import BytesIO
from jinja2 import TemplateNotFound


class ResourceHandler(object):
    """
    Abstract resource handler
    """
    @abstractmethod
    def load_from_remote(self, path2resource, key, update_stat):
        """
        load template from remote resource
        """
        pass

    @abstractmethod
    def isUp2date(self, path2resource, key, ts):
        """
        check if template has been updated
        """
        return True


class DummyHandler(ResourceHandler):
    """
    Dummy class to support Scheduler testing
    signals source modification at random
    """
    def load_from_remote(self, path2resource, key, update_stat):
        print('loading from ' + path2resource + '/' + key)
        update_stat['status'] = True
        update_stat['ts'] = datetime.datetime.now()
        return 'Hello {{ name }}!'

    def isUp2date(self, path2resource, key, ts):
        print('checking modification @', datetime.datetime.now())
        if random.randint(0, 3) > 0:
            return True
        else:
            return False


class S3Handler(ResourceHandler):
    """
    S3 resource handler: reads object using bucket/key
    """
    def __init__(self):
        self.s3 = boto3.client('s3')
        super(S3Handler, self).__init__()

    def gunzip(self, gzcontent):
        """
        handle gzip content
        """
        gzbuffer = BytesIO(gzcontent)
        return GzipFile(None, 'rb', fileobj=gzbuffer).read()

    def load_from_remote(self, path2resource, key, update_stat):
        try:
            obj = self.s3.get_object(Bucket=path2resource, Key=key)
            if 'ContentEncoding' in obj and 'gzip' in obj['ContentEncoding']:
                body = self.gunzip(obj['Body'].read())
            else:
                body = obj['Body'].read()

            update_stat['status'] = True
            update_stat['ts'] = obj['LastModified']
            return body
        except ClientError as e:
            if "NoSuchKey" in e.__str__():
                raise TemplateNotFound(key)
            else:
                raise e

    def isup2date(self, path2resource, key, ts):
        try:
            obj = self.s3.get_object(Bucket=path2resource, Key=key)
            print('ts: ', obj['LastModified'])
            return obj['LastModified'] <= ts
        except ClientError as e:
            if "NoSuchKey" in e.__str__():
                raise TemplateNotFound(key)
            else:
                raise e
