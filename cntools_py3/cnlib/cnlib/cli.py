import argparse
import functools
import sys

from . import log
from . import conf
from . import pagerduty


PAGERDUTY_WARN = """Program started without PagerDuty credentials! \
It will not send incidents when it crashes with an exception."""


def prolog(script_description='command line program for this and that',
        incident_description='something failed',
        logger=None):
    """
    This decorator saves you from writing boilerplate for command line scripts.

    You are expected to write something like:
        @prolog('Program description', 'Meaningful failure message')
        def main(config):
            ...

    Later you call main() with no arguments eg:
        if __name__ == '__main__':
            main()

    Execute your program with eg.
        python my_script.py /path/to/config.yaml

    Now you have all the data structures from your config inside your main function.

    In addition the prolog will wrap all of your code inside a try: except:
    block and log unhandled exceptions that reach the top level. If you put
    PagerDuty credentials in your config file, an exception will also send an incident.
    """
    if logger is None:
        logger = log.getLogger(__name__)

    def decorator(main_function):
        @functools.wraps(main_function)
        def inner():
            parser = argparse.ArgumentParser(description=script_description)
            parser.add_argument('CONFIG_FILE', type=str, help='path to yaml configuration')
            parser.add_argument('--configset', type=str, required=False,
                help="limit config to a subkey under 'configsets', useful for big configs", default=None)
            cmdline_args = parser.parse_args()
            config = conf.load(cmdline_args.CONFIG_FILE)
            if cmdline_args.configset:
                config = config['configsets'][cmdline_args.configset]

            pagerduty_subdomain = config.get('pagerduty_subdomain')
            pagerduty_service_key = config.get('pagerduty_service_key')
            pagerduty_api_token = config.get('pagerduty_api_token', 'anything')
            if not pagerduty_subdomain or not pagerduty_service_key:
                logger.warning(PAGERDUTY_WARN)
            try:
                main_function(config)
            except Exception as e:
                logger.exception(e)
                if pagerduty_subdomain and pagerduty_service_key:
                    pagerduty.trigger_incident(
                        pagerduty_subdomain,
                        pagerduty_service_key,
                        incident_description,
                        exception=e,
                        api_token=pagerduty_api_token,
                    )
                sys.exit(1)
        return inner
    return decorator
