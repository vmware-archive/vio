from setuptools import setup

setup(
    name='ssh-util',
    version='0.0.1',
    scripts=['bin/ssh_exec', 'bin/ssh_scp'],
    packages=['sshutil'],
    include_package_data=True,

    install_requires=[
        'paramiko'
    ]
)
