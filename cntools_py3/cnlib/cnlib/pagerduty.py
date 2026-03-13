import sys
import os

import boto.utils
import pygerduty


class Pager(object):

    def __init__(self, subdomain, service_key, details={}, exception=None, instance_id=None,
                 api_token='anything'):
        self.pager = pygerduty.PagerDuty(subdomain, api_token)
        self.service_key = service_key
        
        if instance_id is None:
            self.instance_id = self.__get_instance_id()
        else:
            self.instance_id = instance_id
            
        self.details = self.__set_details(details, exception)

    
    def trigger_incident(self, description):
        """
        The function will try to include the AWS instance id and some info about
        the executable and cmdline args.

        To trigger and resolve incidents, you don't need an api_token, just a 
        service_key and subdomain.
        Note that you get the incident_key and pager as return value 
        in case you want to resolve your incidents later with eg:
            pager.resolve_incident(service_key, incident_key [, ...])

        """

        key = ",".join([self.service_key, self.instance_id, 
                       self.details["executable"]])

        incident_key = self.pager.trigger_incident(
            self.service_key, 
            description, 
            incident_key=key,
            details=self.details)

        return incident_key


    @staticmethod
    def __get_instance_id():

        try:
            instance_id = boto.utils.get_instance_identity(
                timeout=5, num_retries=1)['document']['instanceId']
        except Exception:
            instance_id = 'n/a'

        return instance_id


    def __set_details(self, details={}, exception=None):

        if exception:
            details["exception"] = str(exception)

        details["instance_id"] = self.instance_id
        details["executable"] = " ".join([sys.executable, 
            os.path.abspath(sys.argv[0]), ' '.join(sys.argv[1:])])

        return details
        


def trigger_incident(subdomain, service_key, description, exception=None, instance_id=None,
                     details={}, api_token='anything'):
    pager = Pager(subdomain, service_key, details, exception, instance_id, api_token)
    return (pager.trigger_incident(description), 
            pager)

