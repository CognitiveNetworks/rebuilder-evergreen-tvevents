# a thread with a stop_requested and a timeout leading to a stopped property
# to tell a thread to shut down gracefully with a .join

import threading
from . import log
import time
logger = log.getLogger(__name__)

class CommonThread(threading.Thread):

    def __init__(self, name=None):
        threading.Thread.__init__(self, name=name)
        self.exception = None
        self._stoprequest = threading.Event()
        self._join_timeout = None
        self._join_init = None
        self._join_notified = False
        self._name = name

    # to ping to join.. but not to block for it like join
    def join_notify(self, timeout=None):
        self._join_timeout = timeout
        if timeout:
            self._join_init = time.time()
        self._stoprequest.set()
        self._join_notified = True
        logger.info("%s timeout=%s join_notify..", self, timeout)

    def join(self, timeout=None):
        if not self._join_notified:
            self._join_timeout = timeout
            if timeout:
                self._join_init = time.time()
            self._stoprequest.set()
        logger.info("%s timeout=%s join..", self, timeout)
        super(CommonThread, self).join(timeout)

    # tells if stop requested
    @property
    def stop_requested(self):
        return self._stoprequest.isSet()

    # same as above, except waits for the join timeout before setting true
    @property
    def stopped(self):
        if not self.stop_requested:
            return False
        return not self._join_timeout or time.time() - self._join_init >= self._join_timeout

    # override this
    def __str__(self):
        return "CommonThread name={}".format(self._name)

    # interruptable sleep
    def sleep(self, t):
        x = 0.
        while x < t and not self.stopped:
            time.sleep(.05)
            x += .05

