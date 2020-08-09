#!/bin/sh
# TODO Could speed up ci by replacing this with an image

if [ -n "$CIRCLE_BRANCH" ]; then
    # CircleCI buster doesn't have non-free available by default
    sudo apt-get install -y software-properties-common
    sudo apt-add-repository non-free
    sudo apt-add-repository contrib
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