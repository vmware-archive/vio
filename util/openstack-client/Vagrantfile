# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|
  config.vm.box = "boxcutter/ubuntu1504"
  config.vm.hostname = "openstack-client"
  config.vm.provision "shell", path: "src/base-prep.sh"
end
