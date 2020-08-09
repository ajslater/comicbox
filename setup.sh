#!/bin/sh
if [ -n "$CIRCLE_BRANCH" ]; then
    # Circle buster doesn't have non-free available by default
    sudo cp .circleci/buster.non-free.list /etc/apt/sources.list.d/
    sudo apt-get update
    sudo apt-get upgrade
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
