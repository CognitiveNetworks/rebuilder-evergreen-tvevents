#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

See:
- http://pymotw.com/2/smtplib/
- http://www.mkyong.com/python/how-do-send-email-in-python-via-smtplib/
- https://github.com/CognitiveNetworks/daily-reports/blob/master/send_added_tv_count.py
"""

# import
import argparse
import email.utils
import os
import smtplib
import sys
from email.mime.text import MIMEText

__all__ = ['MailSender', 'main']

class MailSender(object):

    def __init__(self, host, sender, password, port=587, type='plain', verbose=False):
        self.host = host
        self.sender = sender
        self.password = password
        self.port = port
        self.type = type
        self.verbose = verbose

    def __call__(self, message, *recipients, **headers):

        if not recipients:
            return  # nothing to do

        # construct the message
        msg = MIMEText(message, self.type)
        headers.setdefault('From', self.sender)
        headers.setdefault('To', ','.join(recipients))
        for key, value in list(headers.items()):
            msg[key] = value

        # connect to mail server
        server = smtplib.SMTP(self.host, self.port)
        try:
            if self.verbose:
                server.set_debuglevel(True)

            # identify ourselves, prompting server for supported features
            server.ehlo()

            # If we can encrypt this session, do it
            if server.has_extn('STARTTLS'):
                server.starttls()
                server.ehlo() # re-identify ourselves over TLS connection

            # login
            server.login(self.sender, self.password)

            # send the email
            server.sendmail(self.sender, recipients, msg.as_string())
        finally:
            server.quit()


def main(args=sys.argv[1:]):

    # parse command line
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('sender')
    parser.add_argument('password')
    parser.add_argument('-r', '--recipients', dest='recipients',
                        nargs='+', required=True,
                        help="recipients")
    parser.add_argument('-m', '--message', dest='message', required=True)
    parser.add_argument('--port', dest='port', type=int, default=587,
                        help="port to connect to [DEFAULT: %(default)s]")
    options = parser.parse_args(args)

    message = options.message

    # instantiate sender
    sender = MailSender(options.host, options.sender, options.password, options.port)

    # send email
    sender(message, *options.recipients)


if __name__ == '__main__':
    main()
