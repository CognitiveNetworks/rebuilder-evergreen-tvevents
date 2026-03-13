"""
unbuffer a file
"""

import sys
__all__ = ['Unbuffered', 'unbuffer_stdout']

class Unbuffered(object):
    """unbuffer a file-like object"""
    def __init__(self, stream):
        self.stream = stream
    def write(self, data):
       self.stream.write(data)
       self.stream.flush()
    def __getattr__(self, attr):
       return getattr(self.stream, attr)

def unbuffer_stdout():
    """unbuffer stdout"""
    sys.stdout = Unbuffered(sys.stdout)
