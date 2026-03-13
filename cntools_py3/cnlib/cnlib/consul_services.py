"""
A simple consul registration and searching of services
in the method of
https://github.com/CognitiveNetworks/dts-py/tree/master/src/cnservices
and
https://github.com/CognitiveNetworks/cn-consul

Uses BaseHTTPServer to create the health check that launches with CommonThread in threads.py.
Has acquire and release of a distributed lock mechanism on consul.
Has methods to search for services in all datacenters. And to clear local services.

See tests/test_consul_services.py for usage.
"""

import socket

import consul
import requests

from .threads import CommonThread
from . import log

logger = log.getLogger(__name__)

from http.server import HTTPServer
from http.server import BaseHTTPRequestHandler


def get_public_ip():
    response = requests.get(
        'http://169.254.169.254/latest/meta-data/public-ipv4', timeout=0.5)
    return response.text


def get_private_ip():
    response = requests.get(
        'http://169.254.169.254/latest/meta-data/local-ipv4', timeout=0.5)
    return response.text


def get_instance_id():
    response = requests.get(
        'http://169.254.169.254/latest/meta-data/instance-id', timeout=0.5)
    return response.text


def version_cmp(a, b):
    av = str(a).split('.')
    bv = str(b).split('.')
    for i in range(0, len(av)):
        try:
            an = av[i]
            bn = bv[i]
            if an > bn:
                return 1
            if an < bn:
                return -1
        except IndexError:
            break
    return 0


class RequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        # logger.debug("GET=%s", self)
        self.send_response(200)
        self.send_header("Content-type", "text")
        self.end_headers()

    def log_message(self, *args, **kwargs):
        pass
        # logger.debug("service_endpoint hit..")
        # logger.debug(*args, **kwargs)


class HTTPEndpoint(HTTPServer, CommonThread):

    def __init__(self, server_address=('127.0.0.1', 0), handler_class=RequestHandler, name="HTTPEndpoint"):
        HTTPServer.__init__(self, server_address, handler_class)
        CommonThread.__init__(self, name)
        self._public_ip = get_public_ip()
        self._private_ip = get_private_ip()

    def get_request(self):
        """Get the request and client address from the socket."""
        # logger.debug("socket timeout..")
        self.socket.settimeout(1.0)
        result = None
        while result is None and not self.stopped:
            try:
                result = self.socket.accept()
            except socket.timeout:
                pass
        # Reset timeout on the new socket
        if result:
            result[0].settimeout(None)
        return result

    def serve(self):
        self.timeout = .1
        logger.debug("serving..")
        while not self.stopped:
            self.handle_request()

    def run(self):
        logger.info("server_bind host=%s port=%s", self.server_name, self.server_port)
        self.serve()

    # return server address
    @property
    def public_url(self):
        return 'http://' + self._public_ip + ':' + str(self.server_port)

    @property
    def local_url(self):
        return 'http://' + self._private_ip + ':' + str(self.server_port)


# A consul interface with an http healthcheck endpoint registered
# Uses the same system as core apps for registering
class ConsulApp:
    def __init__(self, appname):
        span = 1000
        port = 33333
        success = False
        self.appname = appname
        self.running = False
        self.lock_session = None
        self.c = consul.Consul()
        self.agent = self.c.agent
        self.lock_held = None

        try:
            self.agent.self()
        except requests.exceptions.ConnectionError:
            logger.info('unable to connect to Consul agent.')
            return

        for http_port in range(port, span + port):
            logger.debug('consul_service trying to start http on port=%s', http_port)
            try:
                # Keep track of the reactor listener so that it can
                # be cleaned up later
                self.http_listener = HTTPEndpoint(('127.0.0.1', http_port), RequestHandler, http_port)
                self.http_listener.start()
                success = True
                break
            except Exception as e:
                pass
                logger.error("Couldn't bind to {}".format(http_port))
        if not success:
            self.http_listener = None
            logger.warning('failed to start a http server in consul_service!')
            return

        logger.info("%s started on port=%s", self, http_port)

        self.running = True
        self.http_port = http_port
        self.check_url = "http://localhost:%s" % http_port
        self.check_http = consul.Check.http(url=self.check_url, interval="1s")
        self.check_http['status'] = 'passing'
        self.services = []

    def __str__(self):
        return "ConsulApp(appname={})".format(self.appname)

    def register(self, name, zone=None, addr=None, port=0, version=0, tag=None, id=None, service_id=None):
        if not self.running:
            return

        name = "%s-%s" % (self.appname, name)

        if addr is None:
            try:
                addr = get_private_ip()
            except:
                pass

        if id is None:
            try:
                id = get_instance_id()
            except:
                pass

        if isinstance(service_id, list):
            service_id, = service_id

        if not service_id:
            _id_items = [name]
            if zone:
                _id_items.append(str(zone))
            if addr:
                _id_items.append(addr)
            if port:
                _id_items.append(str(port))
            if tag:
                _id_items.append(str(tag))
            service_id = '-'.join(_id_items)

        logger.info('consul_services register name=%s zone=%s addr=%s port=%s version=%s tag=%s service_id=%s',
                    name, zone, addr, port, version, tag, service_id)
        if version is None:
            version = 0

        tags = ["v:%s" % version]

        if zone is not None:
            tags.append("z:%s" % zone)

        if tag is not None:
            tags.append("t:%s" % tag)

        if id is not None:
            tags.append("i:%s" % id)

        try:
            success = self.agent.service.register(name, port=port,
                                                  tags=tags, check=self.check_http,
                                                  service_id=service_id, address=addr)
            logger.info("success=%s name=%s port=%s tags=%s check_http=%s service_id=%s",
                        success, name, port, tags, self.check_http, service_id)
        except:
            logger.exception("consul_services ERROR")
            name = None
            success = False

        if success:
            self.services.append(service_id)
            logger.info('consul_services success registering service_id=%s', service_id)
            return service_id
        else:
            logger.info('consul_services ERROR: no success registering')
            return None

    def deregister(self, service_id):
        if isinstance(service_id, list):
            service_id, = service_id
        logger.info('consul_services deregister service_id=%s', service_id)
        return self.agent.service.deregister(service_id)

    def destruct(self):
        if not self.running:
            return
        logger.info('%s destructing..', self)
        for service_id in self.services:
            self.deregister(service_id)
        # If we're destructing, also clear out the http listener
        self.http_listener.join()
        # Need to release any locks held
        if self.lock_held:
            self.release_lock(self.lock_held)

    def acquire_lock(self, lock_name, timeout=10):
        """
        Acquire a distributed lock.  Return success or failure.
        Timeout is the amount of time the lock will last if acquired in seconds.
        Timeout has to be greater then 10s.
        """
        c = self.c
        if self.lock_held:
            logger.error('_error_ acquiring lock. already have lock! lock_held=%s', self.lock_held)
            return False
        session = c.session.create("test", ttl=timeout)
        success = False
        lock = "service/locks/{0}/{1}".format(self.appname, lock_name)
        try:
            success = c.kv.put(lock, "", acquire=session)
        except:
            logger.exception("session")
        if success:
            self.lock_session = session
            self.lock_held = lock_name
            logger.info('consul_services acquired lock lock_name=%s', lock_name)
        return success

    def release_lock(self, lock_name):
        """
        Tries to release lock.
        Returns success.
        """
        if not self.lock_session:
            return False
        c = self.c
        lock = "service/locks/{0}/{1}".format(self.appname, lock_name)
        success = c.kv.put(lock, "", release=self.lock_session)
        self.lock_session = None
        self.lock_held = None
        if success:
            logger.info('consul_service released lock lock_name=%s', lock_name)
        return success


class Service():
    def __init__(self):
        self._id = None
        self.name = None
        self.host = None
        self.port = None
        self.version = 0
        self.tag = None
        self.zone = None
        self.node = None
        self.id = None

    def __repr__(self):
        return "Service< id={0._id} name={0.name} {0.host}:{0.port} zone={0.zone} v={0.version} tag={0.tag} i={0.id} node={0.node}>".format(
            self)


def get_datacenters():
    c = consul.Consul()
    return c.catalog.datacenters()


def get_services(name, zone=None, version=None, tag=None):
    s = []
    d = get_datacenters()
    for dc in d:
        s = s + get_datacenter_services(name, zone, version, tag, dc=dc)
    return s


def get_datacenter_services(name, zone=None, version=None, tag=None, dc=None):
    logger.debug('querying datacenter %s for %s', dc, name)
    c = consul.Consul()

    filtered_services = []
    services = c.health.service(name, passing=True, dc=dc)[1]
    if services is None:
        logger.error("ERROR: No services response in consul_service!")
        return []

    logger.debug('get_datacenter_services got %s services', len(services))

    for item in services:
        # logger.debug("item=%s", item)

        version_success = True
        tag_success = True

        s = Service()

        service = item['Service']
        tags = service['Tags']
        node = item['Node']

        for tag_ in tags:
            if tag_[0] == 'v':
                s.version = tag_[2:]
                try:
                    s.version = int(s.version)
                except:
                    pass

            if tag_[0] == 't':
                s.tag = tag_[2:]

            if tag_[0] == 'z':
                s.zone = tag_[2:]

            if tag_[0] == 'i':
                s.id = tag_[2:]

        if not version or version_cmp(version, s.version) <= 0:
            version_success = True
        else:
            version_success = False

        if tag is not None and tag != s.tag:
            tag_success = False
        elif zone is not None and s.zone != zone:
            tag_success = False

        if tag_success and version_success:
            logger.debug("service=%s", service)

            addr = service["Address"]
            if len(addr):
                s.host = addr
            else:
                s.host = node["Address"]

            s.port = service["Port"]
            s._id = service["ID"]
            s.name = service["Service"]
            s.node = node["Node"]
            filtered_services.append(s)

    return filtered_services


def clear_local_services(appname=None):
    c = consul.Consul()
    services = c.agent.services()
    cnt = 0
    for k, v in list(services.items()):
        if appname and appname in k:
            logger.info("deregister k=%s v=%s", k, v)
            cnt += 1
            c.agent.service.deregister(k)

    logger.debug('cleared %d services..', cnt)


def get_local_agent():
    return consul.Consul().agent.self().get('Member')
