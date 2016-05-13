buildwebapi
=============

A python library for querying buildweb resources using buildapi.


Installation
=============

 python setup.py install

 pip install --index-url http://p3-pypi.eng.vmware.com:3141/slave/dev/+simple --trusted-host p3-pypi.eng.vmware.com buildwebapi

Usage
======

Example 1: Get latest succeeded build id (MetricResource)

.. code:: python

  from buildwebapi import api as buildapi
  build_metrics = buildapi.MetricResource.by_name(
              'build', product='vmw_openstack', buildstate='succeeded')


Example 2: Get a list of all builds (ListResource)

.. code:: python

  from buildwebapi import api as buildapi
  builds = buildapi.ListResource.by_name(
              'build', product='vmw_openstack')


Example 3: Get build details by its Id (ItemResource)

.. code:: python

  from buildwebapi import api as buildapi
  build = buildapi.ItemResource.by_id('build', 1924554)