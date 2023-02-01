import os
import requests
import secrets
import string

from python_on_whales import DockerClient
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from getpass import getpass

# Paramétrage des hostnames
apps_env = {
    "1": "production",
    "2": "integration",
    "3": "developpement",
    "4": "Personnalisé"
}

for key, env in apps_env.items():
    print(f"{key}. {env}")

choice = input("Choisissez l'environnement de déploiement: ")
while choice not in apps_env:
    choice = input(f"Indiquez une des valeurs suivante: {', '.join(apps_env)}: ")

if choice == "1":
    portainer_host = 'geoportainer.lesagencesdeleau.eu'
    traefik_host = 'geotraefik.lesagencesdeleau.eu'
    traefik_loglevel = 'ERROR'
    git_branch = 'master'
elif choice == "2":
    portainer_host = 'geoportainer-int.lesagencesdeleau.eu'
    traefik_host = 'geotraefik-int.lesagencesdeleau.eu'
    traefik_loglevel = 'ERROR'
    git_branch = apps_env[choice]
elif choice == "3":
    portainer_host = 'geoportainer-dev.lesagencesdeleau.eu'
    traefik_host = 'geotraefik-dev.lesagencesdeleau.eu'
    traefik_loglevel = 'DEBUG'
    git_branch = apps_env[choice]
elif choice == "4":
    portainer_host = input("Indiquez le hostname de Portainer à utiliser: ")
    git_branch = input("Indiquez le nom de la branche Git à utiliser: ")
    traefik_host = input("Indiquez le hostname de Traefik à utiliser: ")
    traefik_loglevel = 'ERROR'

# Paramétrage du mot de passe admin de Portainer
portainer_pass_file = '/app/portainer/.portainer_admin_pass'
if os.path.exists(portainer_pass_file):
    with open(portainer_pass_file, "r") as file:
        portainer_pass = file.read()
else:
    alphabet = string.ascii_letters + string.digits
    portainer_pass = ''.join(secrets.choice(alphabet) for i in range(20))
    with open(portainer_pass_file, "w") as file:
        file.write(portainer_pass)

print("###########################################################",
      "#######                 Récapitulatif :             #######",
      "###########################################################",
      "Environnement : %s" % apps_env[choice],
      "Hostname Portainer : %s" % portainer_host,
      "Branche Git : %s" % git_branch,
      "Hostname Traefik : %s" % traefik_host,
      "Traefik LogLevel : %s" % traefik_loglevel,
      "MdP admin Portainer : %s" % portainer_pass,
      "###########################################################",
      sep=os.linesep)

home_path = os.path.expanduser('~')

portainer_stack_url = "https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/%s/docker/standalone/portainer/portainer.yml" % git_branch
portainer_stack_file = os.path.join(home_path, "portainer.yml")
portainer_env_file = os.path.join(home_path, "portainer.env")

with open(portainer_stack_file, "wb") as file:
    content = requests.get(portainer_stack_url, stream=True).content
    file.write(content)

with open(portainer_env_file, "w") as file:
    file.writelines("\n".join([
       'XDG_RUNTIME_DIR=%s' % os.getenv("XDG_RUNTIME_DIR"),
       'PORTAINER_HOST=%s' % portainer_host
    ]))

# Préparation du client docker pour Portainer
docker = DockerClient(context='rootless',
                      compose_files=portainer_stack_file,
                      compose_env_file=portainer_env_file,
                      compose_project_name='portainer')

# Déploiement de portainer
print("Déploiement de portainer :")
docker.compose.up(detach=True)

# Préparation du client docker pour Traefik
docker = DockerClient(context='rootless',
                      compose_files=portainer_stack_file,
                      compose_env_file=portainer_env_file,
                      compose_project_name='portainer')

# Déploiement de portainer
print("Déploiement de portainer...")
docker.compose.up(detach=True)

# Préparation Traefik

print("Mise en place des prérequis pour le déploiement de Traefik.")
traefik_providers_path = '/app/traefik/providers'
traefik_tls_file = os.path.join(traefik_providers_path, 'tls.yml')
traefik_tls_url = "https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/%s/docker/standalone/traefik/tls.yml" % git_branch

# Création du dossier qui contiendra le fichier tls.yml
os.makedirs(traefik_providers_path, exist_ok=True)

# Téléchargement du fichier tls.yml
print("Téléchargement du fichier tls.yml dans %s" % traefik_providers_path)
with open(traefik_tls_file, "wb") as file:
    content = requests.get(traefik_tls_url, stream=True).content
    file.write(content)

traefik_certs_path = '/app/traefik/.certs'
traefik_cert_path = os.path.join(traefik_certs_path, 'w_.lade-eu.cer')
traefik_privatekey_path = os.path.join(traefik_certs_path, 'w_.lade-eu.key')
traefik_fullcrt_path = os.path.join(traefik_certs_path, 'w_.lade-eu.crt')
pfx_path = '/etc/ssl/certs/w_.lesagencesdeleau.eu-serveurs-internes-Wild-LADE-2022.pfx'
fullchain_path = '/etc/ssl/certs/LADE-fullchain.pem'

# Création du dossier qui contiendra le fichier tls.yml
os.makedirs(traefik_certs_path, exist_ok=True)

print("Préparation du certificats pour les connexions HTTPS")
# Vérification de l'existence du fichier pfx
if not os.path.exists(pfx_path):
    print("ATTENTION - Le fichier %s n'existe pas." % pfx_path)
    pfx_path = input("Indiquez le chemin complet vers le fichier de certificat .pfx: ")

# Vérification de l'existence de la fullchain
if not os.path.exists(fullchain_path):
    print("ATTENTION - Le fichier %s n'existe pas." % pfx_path)
    fullchain_path = input("Indiquez le chemin complet vers la fullchain: ")

with open(pfx_path, 'rb') as pfx:
    private_key, cert, _ = load_key_and_certificates(
        pfx.read(),
        password=getpass("Indiquez le mot de passe du fichier .pfx: ").encode('UTF-8'),
    )

with open(traefik_privatekey_path, 'wb') as file:
    _ = file.write(private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))

with open(traefik_cert_path, 'wb') as file:
    _ = file.write(cert.public_bytes(Encoding.PEM))

with open(fullchain_path, "r") as file:
    fullchain_data = file.read()

with open(traefik_fullcrt_path, 'wb') as file:
    _ = file.write(cert.public_bytes(Encoding.PEM))
    _ = file.write(str.encode(fullchain_data))

# Préparation QWC2
print("Préparation des dossiers pour QWC2")
os.makedirs('/app/qwc2/attachments', exist_ok=True)
os.makedirs('/app/qwc2/config', exist_ok=True)
os.makedirs('/app/qwc2/config-in', exist_ok=True)
os.makedirs('/app/qwc2/legends', exist_ok=True)
os.makedirs('/app/qwc2/pg_services', exist_ok=True)
os.makedirs('/app/qwc2/qgs-resources', exist_ok=True)
os.makedirs('/app/qwc2/qwc2', exist_ok=True)
os.makedirs('/app/qwc2/solr', exist_ok=True)

# Préparation Dépôt plugins QGIS
print("Préparation des dossiers pour le dépôt des plugins QGIS")
qgis_plugins_path = '/app/qgis-plugins-repo/plugins'
plugin_customcatalog_repo = 'QGIS_CustomCatalog'
plugin_customcatalog_path = os.path.join(qgis_plugins_path, 'custom_catalog.zip')
plugin_projectpublisher_repo = 'QGIS_Project_Publisher'
plugin_projectpublisher_path = os.path.join(qgis_plugins_path, 'project_publisher.zip')
os.makedirs(qgis_plugins_path, exist_ok=True)


def download_plugin(repo_name, plugin_path):
    git_data = requests.get('https://api.github.com/repos/naub1n/' + repo_name + '/releases/latest')
    plugin_url = git_data.json()['assets'][0]['browser_download_url']

    with open(plugin_path, "wb") as file:
        content = requests.get(plugin_url, stream=True).content
        file.write(content)


download_plugin(plugin_customcatalog_repo, plugin_customcatalog_path)
download_plugin(plugin_projectpublisher_repo, plugin_projectpublisher_path)