"""
setup packaging script for cndeploy
"""

import os
from setuptools import setup

NAME = 'cndeploy'
version_num = "1.1"
branch_name = os.getenv('GIT_BRANCH', 'master')
build_number = os.getenv('BUILD_NUMBER', '0')
commit_id = os.getenv('GIT_COMMIT', 'dev')
version = version_num + '.' + build_number + '+' + commit_id
if branch_name == 'master':
    name = NAME
else:
    name = NAME + '-' + branch_name


dependencies = ['boto>=2.37', 'tempita', 'cnlib']

# allow use of setuptools/distribute or distutils
kw = {}
kw['entry_points'] = """
[console_scripts]
launch-instance = cndeploy.launch_instance:main
spot-prices = cndeploy.prices:main
"""
kw['install_requires'] = dependencies


try:
    here = os.path.dirname(os.path.abspath(__file__))
    description = open(os.path.join(here, 'README.md')).read()
except IOError:
    description = ''


setup(name=name,
      version=version,
      description="Cognitive Networks deployment tools",
      long_description=description,
      # See http://www.python.org/pypi?%3Aaction=list_classifiers
      classifiers=[],
      author='Cognitive Networks',
      author_email='eng@cognitivenetworks.com',
      url='https://github.com/CognitiveNetworks/cntools',
      license='',
      packages=['cndeploy', 'cndeploy/launch', 'cndeploy/manage'],
      include_package_data=True,
      zip_safe=False,
      **kw)
