import unittest
from collections import defaultdict

import botocore

from ..firehose import Firehose, FirehoseException

__author__ = 'Ben Williams <ben.williams@inscape.tv>'


class MockFirehoseClient(object):
    put_counter = 0

    def put_record_batch(self, DeliveryStreamName, Records):
        raise NotImplementedError


class MockFirehoseGoodClient(MockFirehoseClient):
    """ All records submitted successfully """
    def put_record_batch(self, DeliveryStreamName, Records):
        response = {'FailedPutCount': 0, 'RequestResponses': []}

        for i in range(len(Records)):
            response['RequestResponses'].append({'RecordId': str(i)})

        self.put_counter += len(Records)

        return response


class MockFirehoseBadClient(MockFirehoseClient):
    """ Some records go in, others need to be retried """
    def put_record_batch(self, DeliveryStreamName, Records):
        response = {'FailedPutCount': 0, 'RequestResponses': []}

        failed = 0
        for i in range(len(Records)):
            if i % 2 == 0:
                response['RequestResponses'].append({'RecordId': str(i)})
                self.put_counter += len(Records)
            else:
                failed += 1
                response['RequestResponses'].append(
                    {'ErrorCode': str(i), 'ErrorMessage': 'Error'})

        response['FailedPutCount'] = failed
        return response


class MockFirehoseReallyBadClient(MockFirehoseClient):
    """ No records go in """
    def put_record_batch(self, DeliveryStreamName, Records):
        response = {'FailedPutCount': len(Records), 'RequestResponses': []}

        failed = 0
        for i in range(len(Records)):
            failed += 1
            response['RequestResponses'].append(
                {'ErrorCode': str(i), 'ErrorMessage': 'Error'})
        return response


class MockFirehoseExceptionClient(MockFirehoseClient):
    """ No records go in and exception is raised """
    def put_record_batch(self, DeliveryStreamName, Records):
        raise botocore.exceptions.ClientError(defaultdict(dict), '')


class FirehoseTestCase(unittest.TestCase):

    def setUp(self):
        self.firehose = Firehose('foo', client='bar', max_batch_size=500)

    def test_record_batching(self):
        firehose = self.firehose

        records = []
        batches = firehose._batch_records(records)

        self.assertEqual(len(batches), 0)

        records = range(500)

        batches = firehose._batch_records(records)

        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 500)
        self.assertEqual(batches[0][0], 0)

        records = range(499)
        batches = firehose._batch_records(records)

        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 499)

        records = range(1010)
        batches = firehose._batch_records(records)
        self.assertEqual(len(batches), 3)
        self.assertEqual(len(batches[0]), 500)
        self.assertEqual(len(batches[2]), 10)
        self.assertEqual(batches[0][0], 0)
        self.assertEqual(batches[1][10], 510)

    def test_get_record_retries(self):
        firehose = self.firehose
        records = ['a', 'b', 'c']
        response = {'FailedPutCount': 0,
                    'RequestResponses':
                        [{'RecordId': 0}, {'RecordId': 1}, {'RecordId': 3}]
                    }

        retries, errors = firehose._get_records_to_retry(response, records)
        self.assertEqual(len(retries), 0)

        response = {'FailedPutCount': 2,
                    'RequestResponses':
                        [{'ErrorCode': 1, 'ErrorMessage': ''}, {'RecordId': 3},
                         {'ErrorCode': 2, 'ErrorMessage': ''}]
                    }

        retries, errors = firehose._get_records_to_retry(response, records)
        self.assertEqual(len(retries), 2)
        self.assertEqual(retries, ['a', 'c'])

    def test_put_record_batch(self):
        firehose = self.firehose
        records = ['a', 'b', 'c']

        firehose._client = MockFirehoseGoodClient()
        records_to_retry, errors = firehose._put_record_batch(records)
        self.assertEqual(len(records_to_retry), 0)

        firehose._client = MockFirehoseBadClient()
        records_to_retry, errors = firehose._put_record_batch(records)
        self.assertEqual(len(records_to_retry), 1)

        firehose._client = MockFirehoseExceptionClient()
        firehose.service_unavailable_retries = 2
        firehose.service_unavailable_timeout = 0
        with self.assertRaises(FirehoseException):
            firehose._put_record_batch(records)

    def test_send_records(self):
        firehose = self.firehose
        records = ['a']*1025

        firehose._client = MockFirehoseGoodClient()
        firehose.send_records(records)
        self.assertEqual(firehose._client.put_counter, 1025)

        firehose.record_retry_limit = 3
        firehose._client = MockFirehoseBadClient()
        with self.assertRaises(FirehoseException):
            firehose.send_records(records)
