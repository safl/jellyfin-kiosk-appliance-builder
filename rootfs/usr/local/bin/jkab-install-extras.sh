#!/usr/bin/env bash
# Install optional diagnostic and debugging packages
set -e

sudo apt-get update -q
sudo apt-get install -qy \
  intel-gpu-tools \
  mesa-utils \
  psmisc \
  va-driver-all \
  vainfo \
  xfce4-goodies

echo "Done — extras installed."
