# openstack-cli-on-windows
Helpful hints on how to use the OpenStack clients on your Windows desktop

## Prerequisites:
1.  Install the [GitHub Windows client](https://desktop.github.com/)
1.  Install the latest release of [Python 2](https://www.python.org/downloads/) on your Windows desktop.
2.  Upgrade the Python package manager (pip): ```python -m pip install --upgrade pip```
3.  Install the OpenStack CLI packages:
```
pip install python-novaclient python-glanceclient python-neutronclient python-cinderclient python-swiftclient python-heatclient
```

## Usage:
1.  Clone the repo: ```git clone https://github.com/vmware/vio.git```
2.  Download your openrc file from your own tenant on your group's OpenStack cloud.
3.  Change to the **vio/util/openstack-cli-windows** directory and edit the **openstack-cli-env.ps1** file with the values from the openrc file.
4.  Run the **openstack-cli-env.ps1** in a PowerShell window and execute your OpenStack commands as you normally would
**NOTE** Using multiple lines for your OpenStack CLI commands will require a backtick (`) instead of a backslash (\\)
```
glance image-create --property vmware_disktype=preallocated `
--property vmware_adaptertype=lsiLogicsas --name windows-2012-r2-test `
--property vmware_ostype=windows8Server64Guest --container-format bare `
--disk-format vmdk --min-disk 40 --min-ram 512 --progress `
--file z:\windows2012-blank-flat-control.vmdk
```
