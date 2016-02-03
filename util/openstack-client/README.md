# openstack-client
Vagrant-automated Ubuntu 15.04 deployment that contains essential OpenStack CLI packages

## Prerequisites:
1.  [Vagrant](www.vagrantup.com)
2.  Desktop Virtualization solution ([VMware App Catalyst](https://www.vmware.com/cloudnative/appcatalyst-download), [VMware Workstation](https://www.vmware.com/products/workstation), [VMware Fusion](https://www.vmware.com/products/fusion), [Virtualbox](https://www.virtualbox.org/wiki/Downloads))

**NOTE:** Vagrant supports Virtualbox by default. Vagrant requires plugins to support VMware solutions:
-  [App Catalyst Vagrant Plugin](https://github.com/vmware/vagrant-vmware-appcatalyst)
-  [Workstation and Fusion Vagrant Plugins](https://www.vagrantup.com/vmware/)

## Usage:
1.  Clone the repo: ```git clone https://github.com/VMTrooper/openstack-client.git```
2.  Change to the **openstack-client** directory and Vagrant up! ```vagrant up```
3.  Wait for the provisioning shell script to complete. You will eventually see some **apt-get** output.
4.  Connect to the VM ```vagrant ssh```
5.  Download your openrc file from your OpenStack cloud. Here is a sample
```
#!/bin/bash
# Optional environment variable to suppress cosmetic HTTPS warnings from the updated OpenStack CLI packages
export PYTHONWARNINGS="ignore:Unverified HTTPS request"
export OS_AUTH_URL=https://your-openstack-deployment.vmware.com:5000/v2.0
export OS_TENANT_NAME="demo-project"
export OS_USERNAME="demo-user"
# Optional environment variable if you do not yet have a signed certificate.
# In VIO, the PEM file is located /etc/ssl/vio.pem on the Load Balancer VMs
export OS_CACERT=/your/path/vio.pem
echo "Please enter your OpenStack Password: "
read -sr OS_PASSWORD_INPUT
export OS_PASSWORD=$OS_PASSWORD_INPUT
```