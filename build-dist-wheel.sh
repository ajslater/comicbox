#!/bin/sh
# Build pip installable wheel and sdist files from build.Dockerfile
docker-compose -f docker-compose-build.yaml up --build
