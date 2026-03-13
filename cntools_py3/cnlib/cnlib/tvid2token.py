#!/usr/bin/env python

"""
convert TVIDs to tokens
"""

# imports
import argparse
import csv
import sys
from .redshift import RedshiftParser

string = (str, unicode)

def read_tvids(fp):
    """read tvids from a file, `fp`"""

    if isinstance(fp, string):
        with open(fp, 'r') as f:
            return read_tvids(f)
    return fp.read().strip().split()


def tvids2tokens(rs, *tvids):
    """translate tvids to tokens"""

    data = rs("select tvid, token from user_history where tvid in %s", [tvids])
    return {tvid.strip(): token for tvid, token in data}

def main(args=sys.argv[1:]):
    """CLI"""

    # parse command line
    parser = RedshiftParser(description=__doc__)
    parser.add_argument('tvids', metavar='TVID', nargs='*',
                        help="TVIDs to translate to tokens")
    parser.add_argument('-f', '--file', dest='tvid_file',
                        help="file to read TVIDs from")
    parser.add_argument('-o', '--output', dest='output',
                        type=argparse.FileType('a'), default=sys.stdout,
                        help="file to output to, or stdout by default")
    options = parser.parse_args(args)

    # ensure you have TVIDs
    tvids = list(options.tvids)
    if options.tvid_file:
        tvids.extend(read_tvids(options.tvid_file))
    if not tvids:
        parser.error("No TVIDs supplied")

    # get redshift connection
    rs = parser.redshift()

    # translate them
    tokens = tvids2tokens(rs, *tvids)

    # output
    writer = csv.writer(options.output)
    for tvid in tvids:
        writer.writerow([tvid, tokens.get(tvid)])


if __name__ == '__main__':
    main()
