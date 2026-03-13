"""
Library for working with queues.
"""
import time
import os

from boto.sqs import connect_to_region
from boto.sqs.message import Message

from . import log

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'


logger = log.getLogger(__name__)


class QueueConnectorMixin(object):
    """
    Basic mixin for connecting to SQS service, listing queues, etc.
    """
    def __init__(self, aws_key=None, secret_key=None):
        self._connection = self._get_connection(aws_key, secret_key)

    def _get_all_queues(self, prefix=''):
        try:
            return self._connection.get_all_queues(prefix=prefix)
        except Exception as e:
            logger.critical('Unable to list SQS queues')
            raise

    @staticmethod
    def _get_connection(aws_key=None, secret_key=None):
        try:
            aws_region = os.environ.get('AWS_REGION', 'us-east-1')
            return connect_to_region(aws_region)
        except Exception as e:
            logger.critical('Unable to open SQS connection')
            raise


class QueueManager(QueueConnectorMixin):
    def get_all_queues(self, prefix=''):
        return self._get_all_queues(prefix=prefix)

    def delete_queue(self, queue):
        try:
            return self._connection.delete_queue(queue)
        except Exception as e:
            logger.critical('Unable to delete queue')
            raise

    def create_queue(self, queue_name):
        try:
            return self._connection.create_queue(queue_name)
        except Exception as e:
            logger.critical('Unable to create queue')
            raise


class QueueHandlerMixin(object):
    """
    Mixing providing methods for a specific queue.
    """
    def __init__(self, msg_invisible_interval=1200, poll_wait_time=20):
        self.msg_invisible_interval = msg_invisible_interval
        self.poll_wait_time = poll_wait_time

    @staticmethod
    def _get_queue(connection, queue_name, create_missing=False):
        try:
            queue = connection.get_queue(queue_name)
            if queue is None and create_missing:
                queue = connection.create_queue(queue_name)
            return queue
        except Exception as e:
            logger.critical('Unable to get queue {0}'.format(queue_name))
            raise

    def _poll(self, queue):
        """
        Poll the queue for a message.
        Return a new message if available, or None.
        """
        try:
            messages = queue.get_messages(
                num_messages=1,
                visibility_timeout=self.msg_invisible_interval,
                wait_time_seconds=self.poll_wait_time)
            if messages:
                return messages[0]
        except Exception as e:
            logger.error('Unable to poll SQS: %s' % e)
            raise

    @staticmethod
    def _delete(queue, msg):
        """
        Delete a given message from the queue.
        Return boolean success status.
        """
        try:
            return queue.delete_message(msg)
        except Exception as e:
            logger.error('Unable to delete SQS message: %s' % e)
            raise

    @staticmethod
    def _send(queue, contents):
        """
        Send a given message to the queue.
        Return the new message (same content as sent, but new ID)
        or False if sending failed.
        """
        try:
            msg = Message(body=contents)
            status = queue.write(msg)
            logger.debug('Successfully written to SQS Queue: %s' % contents)
            return status
        except Exception as e:
            logger.error('Unable to write SQS message: %s' % e)
            raise


class PopulateQueue(QueueConnectorMixin, QueueHandlerMixin):
    """
    Handler for a single SQS queue to populate.
    """
    def __init__(self, queue_name, aws_key=None, secret_key=None):
        QueueConnectorMixin.__init__(self, aws_key, secret_key)

        self._out_queue = self._get_queue(
            self._connection, queue_name, create_missing=True)
        logger.info('SQS Handler started for populating %s' % queue_name)

    def send(self, contents):
        return self._send(self._out_queue, contents)


class ConsumeQueue(QueueConnectorMixin, QueueHandlerMixin):
    """
    Handler for a single SQS queue to consume.
    """
    GET_QUEUE_INTERVAL_SEC = 20

    def __init__(self, queue_name,
                 aws_key=None, secret_key=None,
                 msg_invisible_interval=1200, poll_wait_time=20):
        QueueConnectorMixin.__init__(self, aws_key, secret_key)
        QueueHandlerMixin.__init__(
            self, msg_invisible_interval, poll_wait_time)

        self._in_queue_name = queue_name
        self._in_queue = self._get_queue(self._connection, queue_name)
        logger.info('SQS Handler started for consuming %s' % queue_name)

    def check_input_queue(self):
        """
        If we don't have an input queue, wait a bit and try re-obtaining it.
        Do nothing if we have good input queue.
        """
        if self._in_queue is None:
            logger.warning('No input queue. Will retry in %s sec'
                           % self.GET_QUEUE_INTERVAL_SEC)
            time.sleep(self.GET_QUEUE_INTERVAL_SEC)
            self._in_queue = self._get_queue(
                self._connection, self._in_queue_name)

    def poll(self):
        self.check_input_queue()
        return self._poll(self._in_queue)

    def delete(self, msg):
        self.check_input_queue()
        return self._delete(self._in_queue, msg)


class InOutQueues(ConsumeQueue, PopulateQueue):
    """
    Handler for the typical case of the two queues:
    incoming queue to consume and outgoing queue to populate.
    """
    def __init__(self, in_name, out_name,
                 aws_key=None, secret_key=None,
                 msg_invisible_interval=1200, poll_wait_time=20):
        QueueConnectorMixin.__init__(self, aws_key, secret_key)
        QueueHandlerMixin.__init__(
            self, msg_invisible_interval, poll_wait_time)

        self._in_queue_name = in_name
        self._in_queue = self._get_queue(self._connection, in_name)
        self._out_queue = self._get_queue(
            self._connection, out_name, create_missing=True)
        logger.info(
            'SQS Handler started for consuming %s and populating %s' % (
                in_name, out_name))
