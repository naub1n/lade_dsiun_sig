#!/bin/bash

# Activation du contexte rootless pour Docker
docker context use rootless

# Création du sous réseau des application SIG (A modifier avec un nom générique si on souhaite faire de 
# ce template un template pour l'ensemble du SI.
docker network create sig-net

# Création d'un mot de passe pour le compte admin de portainer
PASS_FILE=/app/portainer/.portainer_admin_pass
if [ -f "$PASS_FILE" ]; then
    echo "Mot de passe déjà créé."
else
    pwgen 15 1 > $PASS_FILE
fi

cat << EOF
#########################################################
## Le mot de passe du compte admin de portainer sera : ##
## $(cat $PASS_FILE)
#########################################################
EOF

PS3="Indiquer le choix pour l'alias complet à utiliser pour portainer: "
options=("geoportainer.lesagencesdeleau.eu" "geoportainer-int.lesagencesdeleau.eu" "geoportainer-dev.lesagencesdeleau.eu" "Manuel")
select opt in "${options[@]}"
do
    case $opt in
        "geoportainer.lesagencesdeleau.eu")
            echo "L'alias $opt sera utilisé."
            export PORTAINER_HOST=$opt
            export GIT_BRANCH="master"
            break
            ;;
        "geoportainer-int.lesagencesdeleau.eu")
            echo "L'alias $opt sera utilisé."
            export PORTAINER_HOST=$opt
            export GIT_BRANCH="integration"
            break
            ;;
        "geoportainer-dev.lesagencesdeleau.eu")
            echo "L'alias $opt sera utilisé."
            export PORTAINER_HOST=$opt
            export GIT_BRANCH="developpement"
            break
            ;;
        "Manuel")
            echo "Définir le hostname de Portainer"
            read PORTAINER_HOST
            export PORTAINER_HOST
            echo "Définir la branche Git"
            read GIT_BRANCH
            export GIT_BRANCH
            break
            ;;
        *) echo "Option invalide '$REPLY'. Indiquez le numero du choix.";;
    esac
done

# Téléchargement et déploiement de la stack Portainer
wget -O portainer.yml https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/$GIT_BRANCH/docker/standalone/portainer/portainer.yml
docker compose -f portainer.yml -p portainer up -d

# Préparation de la stack Traefik (Déploiement à faire dans Portainer)
mkdir -p /app/traefik/providers
wget -O /app/traefik/providers/tls.yml https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/$GIT_BRANCH/docker/standalone/traefik/tls.yml

# Préparation des certificats pour HTTPS
mkdir -p /app/traefik/.certs

PSX_FILE=/etc/ssl/certs/w_.lesagencesdeleau.eu-serveurs-internes-Wild-LADE-2022.pfx
if ! [ -f "$PSX_FILE" ]; then
    echo "Indiquer le chemin vers le fichier de certificat .pfx à utiliser"
    read PSX_FILE
fi

FULLCHAIN_FILE=/etc/ssl/certs/LADE-fullchain.pem
if ! [ -f "$FULLCHAIN_FILE" ]; then
    echo "Indiquer le chemin vers le fichier de certificat .pfx à utiliser"
    read FULLCHAIN_FILE
fi

#1 - Extraire clé privée du pfx
openssl pkcs12 -in $PSX_FILE -nocerts -nodes -out /app/traefik/.certs/w_.lade-eu.key
#3 - Extraire le certificat
openssl pkcs12 -in $PSX_FILE -clcerts -nodes -nokeys -out /app/traefik/.certs/w_.lade-eu.cer
#4 - Créer un fichier de certificat qui concatène l'étape 3 et la fullchain (respecter cet ordre).
cat /app/traefik/.certs/w_.lade-eu.cer $FULLCHAIN_FILE > /app/traefik/.certs/w_.lade-eu.crt

