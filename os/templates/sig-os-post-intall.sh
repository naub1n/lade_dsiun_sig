#!/bin/bash

## Préparation du repository
## https://docs.docker.com/engine/install/debian/#set-up-the-repository

# Mettre à jour l'index des paquets apt et installer les paquets autorisant apt à utiliser le repository en HTTPS :
sudo apt-get update
sudo apt-get -y install \
    ca-certificates \
    curl \
    gnupg \
    lsb-release
# Ajouter la clé GPG Docker officielle 
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg
# Ajouter le repository stable
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

## Installation de Docker Engine
## source : https://docs.docker.com/engine/install/debian/#install-docker-engine

# Prévenir l'erreur GPG
sudo chmod a+r /etc/apt/keyrings/docker.gpg
# Mettre à jour l'index des paquets apt
sudo apt-get update
# Installation d'une version specifique de Docker-ce
VERSION_STRING=5:20.10.21~3-0~debian-bullseye
sudo apt-get install -y docker-ce=$VERSION_STRING docker-ce-cli=$VERSION_STRING containerd.io docker-compose-plugin

## Executer Docker sans les droits root
## source : https://docs.docker.com/engine/security/rootless/

# Preparation
sudo apt-get update
sudo apt-get install -y uidmap \
    dbus-user-session \
    fuse-overlayfs \
    slirp4netns \
    docker-ce-rootless-extras \
    iptables

# Installation
dockerd-rootless-setuptool.sh install

# Demarrer Docker
systemctl --user start docker

# Activer Docker au demarrage
systemctl --user enable docker
sudo loginctl enable-linger $(whoami)

# Définir le chemin vers le socket
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock

