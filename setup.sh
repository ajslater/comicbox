#!/bin/sh
if [ -n "$CIRCLE_BRANCH" ]; then
    # Circle buster doesn't have non-free available by default
    echo 'deb ftp://ftp.us.debian.org/debian/ buster non-free
deb http://security.debian.org/ buster/updates non-free deb http://volatile.debian.org/debian-volatile buster/volatile non-free' | sudo tee -a /etc/apt/sources.list.d/buster.non-free.list
    sudo apt-get update
fi

if [ -n "$(which apt-get)" ]; then
    sudo apt-get install -y unrar
elif [ -n "$(which brew)" ]; then
    brew install unrar
elif [ -n "$(which pacman)" ]; then
    pacman -S unrar
elif [ -n "$(which yum)" ]; then
    sudo yum install unrar
else
    echo "Comicbox requires unrar to open cbr files. Please install it."
fi

pip3 install poetry
poetry update
