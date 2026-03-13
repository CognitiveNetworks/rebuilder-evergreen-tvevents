"""
Jinja template loader
"""
import datetime
import threading
import time

from jinja2 import BaseLoader

ZERO = datetime.timedelta(0)


class UTCtzinfo(datetime.tzinfo):
    """
    UTC specific tzinfo implementation
    """

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO


UTC = UTCtzinfo()


class ScheduledLoader(BaseLoader):
    """
    Template Loader that is checks/loads template content periodically
    """
    timerThread = None
    updated = {}

    def __init__(self, path2resource, key_list, resource_handler, period=60):
        self.path2resource = path2resource
        self.key_list = key_list

        for k in key_list:
            self.updated[k] = {'status': False, 'ts': datetime.datetime(2000, 1, 1, tzinfo=UTC)}

        self.resource_handler = resource_handler
        self.container = {}
        self.period = period
        self.timerThread = threading.Thread(target=self.exec_periodically)
        self.timerThread.daemon = True
        self.timerThread.start()

        super(ScheduledLoader, self).__init__()

    def exec_periodically(self):
        """
        perform periodic modification check
        """
        next_call = time.time()
        while True:
            for k in self.key_list:
                self.updated[k]['status'] = self.resource_handler.isUp2date(self.path2resource, k,
                                                                            self.updated[k]['ts'])

            next_call = next_call + self.period
            time.sleep(next_call - time.time())

    def get_source(self, environment, template):
        """
        get template source and define modification check function
        """
        source = self.load_from_remote(template)

        def uptodate():
            """
            return True if change detected; False otherwise
            """
            try:
                return self.updated[template]['status']
            except OSError:
                return False
        return source, None, uptodate

    def list_templates(self):
        return sorted(self.container)

    def load_from_remote(self, template):
        """
        loads template from remote location
        """
        self.container[template] = self.resource_handler.load_from_remote(self.path2resource, template,
                                                                          self.updated[template]).decode('utf-8')
        return self.container[template]
