#!/usr/bin/env bash
# Install optional diagnostic and debugging packages
set -e

sudo apt-get update -q
sudo apt-get install -qy \
  intel-gpu-tools \
  mesa-utils \
  psmisc \
  va-driver-all \
  vainfo

echo "Done — extras installed."
