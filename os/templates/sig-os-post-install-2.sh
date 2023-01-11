#!/bin/bash

# Installation de docker en mode rootless, démarrage du service et déclaration des variables d'environnement nécessaires
# Cette partie doit se faire en ouvrant une session avec l'utilisateur concerné et ainsi démarrer une session loginctl.
# A lancer avec l'utilisateur 'maint' ou un utiliateur spécifique à l'application

# Création du dossier pour les data docker. Attention le dossier /app doit être présent avec 'maint' comme propriétaire.
mkdir -p /app/docker/data

# Création du fichier de configuration de docker pour changer le chemin vers les data de Docker
echo '{"data-root": "/app/docker/data"}' | python3 -m json.tool > ~/.config/docker/daemon.json

# Installation de docker en mode rootless
dockerd-rootless-setuptool.sh install

# Démarrage du service et activation au démarrage de la machine
systemctl --user enable docker
systemctl --user start docker

# Ajout des variables d'environnement pour l'utilisateur
echo "XDG_RUNTIME_DIR=/run/user/$(id -u)" >> ~/.profile
echo "DOCKER_HOST=unix://\$XDG_RUNTIME_DIR/docker.sock" >> ~/.profile
echo "PATH=/usr/bin:\$PATH" >> ~/.profile

# Actualisation des variables d'environnement
. ~/.profile

# Activation du contexte rootless pour Docker
docker context use rootless
