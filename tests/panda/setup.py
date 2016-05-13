import os

from setuptools import setup


def package_files(directory):
    paths = []
    for (path, directories, filenames) in os.walk(directory):
        for filename in filenames:
            paths.append('/'.join(os.path.join(path, filename).split('/')[1:]))
    return paths


extra_files = package_files('panda/data')

setup(
    name='panda',
    version='0.0.1',
    scripts=['bin/panda'],
    packages=['panda'],
    package_data={
        'panda': extra_files
    },
    install_requires=[
        'buildwebapi',
        'ssh-util',
        'shell-util',
        'oms-client',
        'pyVmomiwrapper',
        'python-keystoneclient',
        'python-neutronclient',
        'python-novaclient',
        'python-subunit',
        'junitxml',
        'testtools'
    ]
)
