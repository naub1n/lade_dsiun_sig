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

echo "Indiquer l'utilisateur avec lequel lancer le daemon Docker"
read DOCKER_USER

# Déclaration de l'utilisateur dans loginctl (indispensable pour démarrer systemctl avec l'utilisateur)
sudo loginctl enable-linger $DOCKER_USER

# Exposer les ports < 1024
sudo setcap cap_net_bind_service=ep $(which rootlesskit)

# Installation de docker en mode rootless, démarrage du service et déclaration des variables d'environnement nécessaires
# Cette partie doit se faire en ouvrant une session avec l'utilisateur concerné et ainsi démarrer une session loginctl.
# Afin de ne pas lancer les commandes dans un autres script avec l'utilisateur souhaité, une connexion ssh locale est ouverte pour réaliser les commandes.
sudo ssh -o StrictHostKeyChecking=accept-new $DOCKER_USER@localhost \
    'dockerd-rootless-setuptool.sh install &&
    systemctl --user enable docker &&
    systemctl --user start docker && 
    echo "XDG_RUNTIME_DIR=/run/user/$(id -u)" >> ~/.profile &&
    echo "DOCKER_HOST=unix://\$XDG_RUNTIME_DIR/docker.sock" >> ~/.profile && 
    echo "PATH=/usr/bin:\$PATH" >> ~/.profile && 
    . ~/.profile && 
    docker context use rootless && 
    wget -O portainer.yml https://github.com/naub1n/lade_dsiun_sig/blob/production/docker/standalone/portainer.yml && 
    wget -O traefik.yml https://github.com/naub1n/lade_dsiun_sig/blob/production/docker/standalone/traefik.yml && 
    docker compose -f portainer.yml -p portainer up -d && 
    docker compose -f traefik.yml -p traefik up -d'
