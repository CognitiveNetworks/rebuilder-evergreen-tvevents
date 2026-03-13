
import unittest
from .. import log, consul_services
import time

logger = log.getLogger(__name__)

class MockConsulApp(consul_services.ConsulApp):
    def __init__(self):
        consul_services.ConsulApp.__init__(self, "MockConsulApp")



class TestConsulServices(unittest.TestCase):
    def test_setup(self):
        logger.debug("hi there!")
        app = MockConsulApp()
        time.sleep(.1)
        app.register("setup")
        time.sleep(.1)
        # time.sleep(1.)
        app.destruct()

    def test_lock(self):
        consul_services.clear_local_services()
        app = MockConsulApp()
        ok = app.acquire_lock("test")
        self.assertEqual(True,ok)
        ok = app.release_lock("test")
        self.assertEqual(True,ok)
        ok = app.acquire_lock("test")
        self.assertEqual(True,ok)
        ok = app.acquire_lock("test")
        self.assertEqual(False,ok)
        ok = app.release_lock("test")
        self.assertEqual(True,ok)
        app.destruct()

    def test_service(self):
        consul_services.clear_local_services()
        app = MockConsulApp()
        name = "service"
        service_id = app.register(
            name=name,
            zone="myzone",
            addr=consul_services.get_private_ip(),
            port=5000,
            version=0,
            tag="test-tag")
        self.assertNotEqual(service_id, None)
        time.sleep(1.)
        try:
            services = consul_services.get_services("%s-%s" %(app.appname, name), zone="myzone")
            logger.debug("services=%s", services)
            self.assertEqual(len(services), 1)
        finally:
            app.destruct()
            time.sleep(.1)
            services = consul_services.get_services("%s-%s" %(app.appname, name), zone="myzone")
            logger.debug("services=%s", services)
            self.assertEqual(len(services), 0)

    def test_simple(self):
        consul_services.clear_local_services()
        app = MockConsulApp()
        name = "simple"
        service_id = app.register(
            name=name
            )
        self.assertNotEqual(service_id, None)
        try:
            time.sleep(1.)
            services = consul_services.get_services("%s-%s" %(app.appname, name))
            self.assertEqual(len(services), 1)
        finally:
            app.destruct()
            services = consul_services.get_services("%s-%s" %(app.appname, name))
            time.sleep(.1)
            self.assertEqual(len(services), 0)

