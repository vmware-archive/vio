# Update package repo sources
sudo apt-get -qq update

# Install pre-req apt packages
sudo apt-get install -qqy vim python-pip python-dev build-essential libxslt1-dev libxml2-dev

# Install pre-req pip package
sudo pip install -q netifaces

# Install OpenStack clients
sudo pip install -q python-novaclient python-glanceclient python-cinderclient python-neutronclient python-heatclient python-openstackclient
