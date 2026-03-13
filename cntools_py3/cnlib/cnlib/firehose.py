import time

import boto3
import botocore

from . import log

__author__ = 'Ben Williams <ben.williams@inscape.tv>'

logger = log.getLogger(__name__)


class FirehoseException(Exception):
    pass


class Firehose(object):
    """ Handles record batching and retries """

    def __init__(self, delivery_stream, client=None, aws_key=None,
                 secret_key=None, max_batch_size=500,
                 service_unavailable_retries=10,
                 service_unavailable_timeout=60,
                 record_retry_limit=100):

        self.delivery_stream = delivery_stream
        self.max_batch_size = max_batch_size

        # parameters related to firehose itself being unreachable
        self.service_unavailable_retries = service_unavailable_retries
        self.service_unavailable_timeout = service_unavailable_timeout

        # parameter related to firehose being reachable but some records
        # not going in
        self.record_retry_limit = record_retry_limit

        if client:
            self._client = client
        else:
            self._client = boto3.client('firehose',
                                        aws_access_key_id=aws_key,
                                        aws_secret_access_key=secret_key)

    def send_records(self, records):
        have_retried = False
        batched_records = self._batch_records(records)
        i, retry_times = 0, 0
        while i < len(batched_records):
            batch = batched_records[i]
            records_to_retry, errors = self._put_record_batch(batch)

            if records_to_retry:
                if not have_retried:
                    logger.info('Failed to load {} records. Retrying. Errors: {}'
                                .format(len(records_to_retry), list(errors)))
                batched_records += [records_to_retry]
                retry_times += 1
                have_retried = True

            if retry_times >= self.record_retry_limit:
                raise FirehoseException('Record retry limit reached, ' +
                                        'giving up.')

            i += 1

    def _put_record_batch(self, records):
        retries = self.service_unavailable_retries
        while retries > 0:
            try:
                response = self._client.put_record_batch(
                    DeliveryStreamName=self.delivery_stream,
                    Records=records)
                return self._get_records_to_retry(response, records)

            except botocore.exceptions.ClientError as e:
                logger.info('Waiting and retrying: {}'.format(e))
                retries -= 1
                time.sleep(self.service_unavailable_timeout)
        else:
            raise FirehoseException('Unable to put records into firehose after'
                                    ' {} attempts, giving up.'.format(
                                        self.service_unavailable_retries))

    def _batch_records(self, records):
        batched_records, batch = [], []
        for record in records:
            batch.append(record)
            if len(batch) == self.max_batch_size:
                batched_records.append(batch)
                batch = []

        # get leftovers
        if len(batch):
            batched_records.append(batch)

        return batched_records

    def _get_records_to_retry(self, response, records):
        failed_count = response['FailedPutCount']
        error_messages = set()
        records_to_retry = []
        if failed_count > 0:
            for i, record_response in enumerate(response['RequestResponses']):
                error_code = record_response.get('ErrorCode')
                if error_code:
                    records_to_retry.append(records[i])
                    error_messages.add((error_code,
                                        record_response['ErrorMessage']))

        return records_to_retry, error_messages

