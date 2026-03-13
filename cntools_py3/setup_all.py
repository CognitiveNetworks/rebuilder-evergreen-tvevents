#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
setup all packages
"""

# imports
import argparse
import os
import subprocess
import sys

# module globals
PACKAGES = ['cnlib', 'cndeploy']
__all__ = ['main', 'Parser']
here = os.path.dirname(os.path.realpath(__file__))

class Parser(argparse.ArgumentParser):
    """CLI option parser"""
    def __init__(self, **kwargs):
        kwargs.setdefault('description', __doc__)
        argparse.ArgumentParser.__init__(self, **kwargs)
        self.add_argument('--install', dest='install',
                          action='store_true', default=False,
                          help="run in `install` mode not in `develop` mode")
        self.options = None

    def parse_args(self, *args, **kw):
        options = argparse.ArgumentParser.parse_args(self, *args, **kw)
        self.validate(options)
        self.options = options
        return options

    def validate(self, options):
        """validate options"""

def main(args=sys.argv[1:]):
    """CLI"""

    # parse command line options
    parser = Parser()
    options = parser.parse_args(args)

    command = 'install' if options.install else 'develop'

    # setup for deploy
    for package in PACKAGES:
        directory = os.path.join(here, package)
        subprocess.check_call([sys.executable, 'setup.py', command],
                              cwd=directory)

if __name__ == '__main__':
    main()

