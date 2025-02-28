#!/bin/sh

# Update package list
apt-get update

# Install necessary packages
apt-get install -y \
    xvfb \
    x11-xserver-utils \
    xorg \
    openbox \
    mesa-utils \
    libopengl0 \
    xauth

# Kill any existing Xvfb or openbox processes
pkill Xvfb
pkill openbox

# Set display environment variable
export DISPLAY=:0

# Start Xvfb
Xvfb :0 -screen 0 800x600x24 +extension GLX +render -noreset &
sleep 2

# Start openbox
openbox &
