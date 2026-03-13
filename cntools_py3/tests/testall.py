#!/usr/bin/env python

"""
run all unit tests
"""

import os
import sys
import unittest

here = os.path.dirname(os.path.abspath(__file__))

def main(args=sys.argv[1:]):

    results = unittest.TestResult()
    suite = unittest.TestLoader().discover(here, 'test_*.py')
    suite.run(results)
    n_errors = len(results.errors)
    n_failures = len(results.failures)
    print ("Run {} tests ({} failures; {} errors)".format(results.testsRun,
                                                          n_failures,
                                                          n_errors))
    if results.wasSuccessful():
        print ("Success")
        sys.exit(0)
    else:
        # print failures and errors
        for label, item in (('FAIL', results.failures),
                            ('ERROR', results.errors)):
            if item:
                print ("\n{}::\n".format(label))
                for index, (i, message) in enumerate(item):
                    print ('{})  {}:'.format(index, str(i)))
                    print (message)
        sys.exit(1)

if __name__ == '__main__':
    main()


