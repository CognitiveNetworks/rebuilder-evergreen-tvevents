"""
setup for cnlib
"""

import os
from setuptools import setup

NAME = 'cnlib'
version_num = "3"
branch_name = os.getenv('GIT_BRANCH', 'master')
build_number = os.getenv('BUILD_NUMBER', '0')
commit_id = os.getenv('GIT_COMMIT', 'dev')
version = version_num + '.' + build_number + '+' + commit_id
if branch_name == 'master':
    name = NAME
else:
    name = NAME + '-' + branch_name

dependencies = [
    'boto',
    'boto3',
    'fakeredis',
    'redis>=4.1.0',
    'python-dateutil',
    'psycopg2-binary',
    'PyYAML',
    'requests',
    'pygerduty',
    'pyzmq',
    'pymysql>=0.10.1',
    'six',
    'click',
    'jinja2',
    'pymemcache',
    'schema',
    'python-consul'
]

ubuntu_dependencies = ['libpq-dev', 'python-dev', 'libzmq3-dev']

kw = {}
kw['install_requires'] = dependencies
kw['entry_points'] = """[console_scripts]
cdb-interface = cnlib.cdb:main
parse-date = cnlib.parse_date:main
dp25-status = cnlib.dp25.status:main
rs2csv = cnlib.redshift:main
tvid2token = cnlib.tvid2token:main
newrelic = cnlib.newrelic_cli:cli
"""

try:
    here = os.path.dirname(os.path.abspath(__file__))
    long_description = open(os.path.join(here, 'README.md')).read()
except IOError:
    long_description = ''

try:
    setup(
        name=name,
        version=version,
        description='Common libraries for the Cognitive Networks code.',
        long_description=long_description,
        author='Cognitive Networks',
        author_email='cris.crews@cognitivenetworks.com',
        url='https://github.com/CognitiveNetworks/cntools_py3',
        license='',
        packages=['cnlib', 'cnlib/dp25', 'cnlib/cnredis'],
        zip_safe=False,
        **kw
    )
except:
    print("Make sure the following ubuntu packages are installed:")
    print("sudo apt-get -y install {}".format(" ".join(ubuntu_dependencies)))
    raise
