"""Comicbox."""

from os import environ

if environ.get("PYTHONDEVMODE"):
    from icecream import install

    install()
