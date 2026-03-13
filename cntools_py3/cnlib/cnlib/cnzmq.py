"""
zeromq convenient classes
"""
import zmq

from . import log


logger = log.getLogger(__name__)

BIND = 0
CONNECT = 1


class Receiver(object):
    def __init__(self, conn_str, sock_conn_type=CONNECT):
        """
        initialize receiver socket
        """
        self.context = zmq.Context.instance()
        self.listener = self.context.socket(zmq.PULL)
        if sock_conn_type is BIND:
            self.listener.bind(conn_str)
        elif sock_conn_type is CONNECT:
            self.listener.connect(conn_str)

    def recv_json(self):
        msg = self.listener.recv_json()
        logger.debug("Received Message: {}".format(msg))
        return msg

    def close(self):
        logger.debug("Terminating Receiver Connection")
        self.listener.close()

    def poll(self, timeout):
        """
        Poll the socket with the given timeout (in milliseconds).
        Return a message from the socket,
        or None if there was no message and the timeout has elapsed.
        """
        if self.listener.poll(timeout=timeout):
            return self.listener.recv()


class Sender(object):
    def __init__(self, conn_str, sock_conn_type=CONNECT):
        """
        initialize sender socket
        """
        self.context = zmq.Context.instance()
        self.sender = self.context.socket(zmq.PUSH)
        if sock_conn_type is BIND:
            self.sender.bind(conn_str)
        elif sock_conn_type is CONNECT:
            self.sender.connect(conn_str)

    def send_json(self, data_dict):
        ret = self.sender.send_json(data_dict)
        logger.debug("Sending Message: {}".format(data_dict))
        return ret

    def close(self):
        logger.debug("Terminating Sender Connection")
        self.sender.close()


class BrokerQueue(object):
    def __init__(self,
                 conn_in_str,
                 conn_out_str,
                 conn_mon_str=None):
        """
        initialize intermediate broker queue
        """
        self.context = zmq.Context.instance()  # generate zmq context

        # All sockets are binded so
        # the proxy broker stores
        # all the messages

        # init input socket
        self.input = self.context.socket(zmq.PULL)
        self.input.bind(conn_in_str)

        # init output socket
        self.output = self.context.socket(zmq.PUSH)
        self.output.bind(conn_out_str)

        # init monitor socket
        self.monitor = None
        if conn_mon_str:
            self.monitor = self.context.socket(zmq.PUB)
            self.monitor.bind(conn_mon_str)

    def run(self):
        try:
            logger.info("starting zmq device")
            zmq.proxy(self.input, self.output, self.monitor)

        except Exception as e:
            logger.warning("BrokerQueue Exception: {}".format(e))

        finally:
            logger.info("closing zmq device")
            self.input.close()
            self.output.close()
            if self.monitor:
                self.monitor.close()
