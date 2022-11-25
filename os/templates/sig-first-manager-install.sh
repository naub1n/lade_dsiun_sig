#!/bin/bash

# Initalisation de Docker Swarm en mode manager
docker swarm init --advertise-addr $(ip -f inet addr show eth1 | awk '/inet / {print $2}')

# Telechargement du fichier compose DSIUN de Portainer
curl -L https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/master/docker/swarm/portainer/portainer.yml -o portainer.yml

# Lancement de la stack docker
docker stack deploy -c portainer.yml portainer