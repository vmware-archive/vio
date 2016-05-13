#!/bin/bash
set -e

install_projects() {
  pushd $1
    if [ -e requirements.txt ]; then
      pip install -r requirements.txt
    fi
    pip install -e .
  popd
}

export SCRIPT_DIR=$(cd $(dirname "$0") && pwd)
virtualenv .venv
source .venv/bin/activate
pushd "$SCRIPT_DIR"
  install_projects "shellutil"
  install_projects "sshutil"
  install_projects "buildwebapi"
  install_projects "omsclient"
  install_projects "pyVmomiwrapper"
  install_projects "panda"
popd

panda tempest install
echo "---------------------------------------------"
echo ""
echo "Test projects are successfully installed."
echo "Please run command: source .venv/bin/activate"
