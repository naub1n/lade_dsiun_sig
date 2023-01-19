#!/bin/bash

# Activation du contexte rootless pour Docker
docker context use rootless

# Création du sous réseau des application SIG (A modifier avec un nom générique si on souhaite faire de 
# ce template un template pour l'ensemble du SI.
docker network create sig-net

# Téléchargement et déploiement de la stack Portainer
wget -O portainer.yml https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/master/docker/standalone/portainer/portainer.yml
echo "Indiquer l'alias complet à utiliser pour portainer. Ex: geoportainer.lesagencesdeleau.eu"
read PORTAINER_HOST
docker compose -f portainer.yml -p portainer up -d

# Préparation, téléchargement et déploiement de la stack Traefik
mkdir -p /app/traefik/providers
wget -O /app/traefik/providers/tls.yml https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/master/docker/standalone/traefik/tls.yml
wget -O traefik.yml https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/master/docker/standalone/traefik/traefik.yml
docker compose -f traefik.yml -p traefik up -d
