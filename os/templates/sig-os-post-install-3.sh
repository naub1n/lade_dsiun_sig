#!/bin/bash

# Installation du paquet docker pour python
pip install docker python_on_whales cryptography httpie

# Téléchargement de la procédure de déploiement
wget https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/master/os/templates/sig-os-post-install-3.py

# Lancement du déploiement
python3 sig-os-post-install-3.py deploy