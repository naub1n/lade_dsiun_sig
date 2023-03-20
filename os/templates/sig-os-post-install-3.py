import os
import requests
import secrets
import string
import sys
import time
import shutil
import configparser

from python_on_whales import DockerClient
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from getpass import getpass


class DeploySIG:
    def __init__(self):
        self.read_config()

    def deploy(self):
        self.set_apps_dirs()
        self.get_config_data()
        self.deploy_portainer()
        self.portainer_add_env()
        self.portainer_set_ldap()
        self.prepare_traefik()
        self.get_certificats()
        self.deploy_traefik()
        self.prepare_qwc2()
        self.deploy_qwc2()
        self.init_db_qwc2()
        self.prepare_plugins_qgis()
        self.deploy_qgis_plugins_repo()
        self.print_recap()

    def update_cert(self):
        self.get_certificats()
        self.docker_restart('traefik')

    def set_apps_dirs(self):
        self.portainer_app_path = os.path.join(self.root_apps_dir, 'portainer')
        self.portainer_pass_file = os.path.join(self.portainer_app_path, '.portainer_admin_pass')
        self.traefik_providers_path = os.path.join(self.root_apps_dir, 'traefik/providers')
        self.traefik_certs_path = os.path.join(self.root_apps_dir, 'traefik/.certs')
        self.qwc_app_path = os.path.join(self.root_apps_dir, 'qwc2')
        self.qgis_plugins_path = os.path.join(self.root_apps_dir, 'qgis-plugins-repo/plugins')

    def read_config(self, git_branch='master'):
        response = requests.get('https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/%s/os/templates/sig-os-post-install-3-config.json' % git_branch)
        config = response.json()

        self.root_apps_dir = config['root_apps_dir']
        self.pfx_path = config['pfx_path']
        self.fullchain_path = config['fullchain_path']
        self.qwc2_subdirs = config['qwc2_subdirs']
        self.qwc2_pgs_path = os.path.join(self.root_apps_dir, 'qwc2/pg_services/pg_service.conf')
        self.git_sig_org = config['git_sig_org']
        self.git_sig_repo = config['git_sig_repo']
        self.plugin_customcatalog_org = config['plugin_customcatalog_org']
        self.plugin_customcatalog_repo = config['plugin_customcatalog_repo']
        self.plugin_projectpublisher_org = config['plugin_projectpublisher_org']
        self.plugin_projectpublisher_repo = config['plugin_projectpublisher_repo']
        self.env_data = config['env_data']

    def get_config_data(self):
        for key, data in self.env_data.items():
            print(f"{key}. {data['env']}")

        choice = input("Choisissez l'environnement de déploiement: ")
        while choice not in self.env_data:
            choice = input(f"Indiquez une des valeurs suivante: {', '.join(self.env_data)}: ")

        # Relecture de la configuration sur la bonne branche Git
        # Cela permet de tester la config en dev et int
        self.read_config(self.env_data[choice]['git_branch'])

        if choice == "4":
            self.portainer_host = input("Indiquez le hostname de Portainer à utiliser: ")
            self.git_branch = input("Indiquez le nom de la branche Git à utiliser: ")
            self.traefik_host = input("Indiquez le hostname de Traefik à utiliser: ")
            self.traefik_loglevel = 'ERROR'
        else:
            self.portainer_host = self.env_data[choice]['portainer']['host']
            self.traefik_host = self.env_data[choice]['traefik']['host']
            self.traefik_loglevel = self.env_data[choice]['traefik']['loglevel']
            self.git_branch = self.env_data[choice]['git_branch']

        self.app_env = self.env_data[choice]['env']
        self.app_config = self.env_data[choice]

    def set_portainer_pass(self):
        alphabet = string.ascii_letters + string.digits
        self.portainer_pass = ''.join(secrets.choice(alphabet) for i in range(20))

    def get_portainer_files(self):
        home_path = os.path.expanduser('~')
        portainer_stack_url = "https://raw.githubusercontent.com/%s/%s/%s/docker/standalone/portainer/portainer.yml" % \
                              (self.git_sig_org, self.git_sig_repo, self.git_branch)
        self.portainer_stack_file = os.path.join(home_path, "portainer.yml")
        self.portainer_env_file = os.path.join(home_path, "portainer.env")

        with open(self.portainer_stack_file, "wb") as file:
            content = requests.get(portainer_stack_url, stream=True).content
            file.write(content)

        with open(self.portainer_env_file, "w") as file:
            file.writelines("\n".join([
                'XDG_RUNTIME_DIR=%s' % os.getenv("XDG_RUNTIME_DIR"),
                'PORTAINER_HOST=%s' % self.portainer_host
            ]))

    def check_endpoint_exists(self, endpoint_name):
        endpoints_data = self.portainer_get_endpoints()
        exists = False
        for endpoint in endpoints_data:
            if endpoint['Name'] == endpoint_name:
                self.portainer_endpoint_id = endpoint['Id']
                exists = True

        return exists

    def deploy_portainer(self):
        self.get_portainer_files()

        if self.docker_compose_status('portainer')['exists']:
            print("ATTENTION : La stack Portainer existe déjà.")
            admin_pass = getpass("Indiquez le mot de passe du compte 'admin' (sinon laisser vide): ")
            if admin_pass:
                self.portainer_pass = admin_pass
                return
            else:
                erase = input("Souhaitez-vous réinitialiser Portainer ? : ")
                if erase.lower() in ['yes', 'y', 'oui', 'o']:
                    self.docker_compose_down('portainer', self.portainer_stack_file, self.portainer_env_file)
                    shutil.rmtree(self.portainer_app_path, ignore_errors=True)
                else:
                    print("ERREUR : Le déploiement ne peut pas se poursuivre sans mdp ou réinitialisation.")
                    sys.exit(1)

        self.set_portainer_pass()
        self.docker_deploy('portainer', self.portainer_stack_file, self.portainer_env_file)
        time.sleep(5)

        if self.docker_container_status('portainer') == 'running':
            response = requests.post('http://localhost:9000/api/users/admin/init',
                                     json={'Username': 'admin', 'Password': self.portainer_pass})
            if response.status_code == 200:
                print("Initialisation du mot de passe Portainer : OK")
            else:
                print("ERREUR : Initialisation du mot de passe Portainer : Erreur - code %s" % response.status_code)
        else:
            print("ERREUR : Le conteneur Portainer n'est pas démarré")

    def docker_deploy(self, stack_name, stack_file, env_file):
        docker = DockerClient(context='rootless',
                              compose_files=stack_file,
                              compose_env_file=env_file,
                              compose_project_name=stack_name)
        print("Déploiement de %s : " % stack_name)
        docker.compose.up(detach=True)

    def docker_restart(self, container_name):
        print("Redémarrage du container %s:" % container_name)
        docker = DockerClient(context='rootless')
        container = docker.container.list(filters={'name': container_name})[0]
        docker.container.restart(container)

    def docker_compose_down(self, stack_name, stack_file, env_file):
        docker = DockerClient(context='rootless',
                              compose_files=stack_file,
                              compose_env_file=env_file,
                              compose_project_name=stack_name)
        print("Suppression de %s : " % stack_name)
        docker.compose.down()


    def docker_container_status(self, container_name):
        docker = DockerClient(context='rootless')
        container = docker.container.list(filters={'name': container_name})[0]
        return container.state.status

    def docker_compose_status(self, compose_name):
        docker = DockerClient(context='rootless')
        compose_info = docker.compose.ls(all=True, filters={'name': compose_name})
        if compose_info:
            compose_info = compose_info[0]
            status = "created=%s, running=%s, restarting=%s, exited=%s, paused=%s, dead=%s" % (
                compose_info.created,
                compose_info.running,
                compose_info.restarting,
                compose_info.exited,
                compose_info.paused,
                compose_info.dead
            )
            exists = True
        else:
            status = "ERREUR : Stack non construite!"
            exists = False

        return {'exists': exists, 'status': status}

    def portainer_get_token(self):
        response = requests.post('http://localhost:9000/api/auth',
                                 json={'Username': 'admin', 'Password': self.portainer_pass})

        if response.status_code == 200:
            return response.json()['jwt']

    def portainer_get_endpoints(self):
        response = requests.get('http://localhost:9000/api/endpoints',
                                 headers={"Authorization": "Bearer %s" % self.portainer_get_token()})

        if response.status_code == 200:
            return response.json()

    def portainer_get_stacks(self):
        response = requests.get('http://localhost:9000/api/stacks',
                                 headers={"Authorization": "Bearer %s" % self.portainer_get_token()})

        if response.status_code == 200:
            return response.json()

    def portainer_add_env(self):
        endpoint_name = self.app_config['portainer'].get('endpoint_name', 'local')
        print("Ajout de l'endpoint '%s' dans Portainer" % endpoint_name)
        if not self.check_endpoint_exists(endpoint_name):
            response = requests.post('http://localhost:9000/api/endpoints',
                                     headers={"Authorization": "Bearer %s" % self.portainer_get_token()},
                                     data={'Name': endpoint_name, 'EndpointCreationType': '1'})

            if response.status_code == 200:
                self.portainer_endpoint_id = response.json()['Id']
            else:
                print("Erreur : La création de l'endpoint Portainer à échoué : %s" % response.text)
                self.portainer_endpoint_id = None
                sys.exit(1)
        else:
            print("L'endpoint '%s' existe déjà" % endpoint_name)

    def portainer_set_ldap(self):
        print("Ajout de l'authentification LDAP dans Portainer")
        portainer_cfg = self.app_config['portainer']
        endpoint_name = portainer_cfg.get('endpoint_name', 'local')
        if self.check_endpoint_exists(endpoint_name):
            response = requests.put('http://localhost:9000/api/settings',
                                     headers={"Authorization": "Bearer %s" % self.portainer_get_token()},
                                     json={
                                         "AuthenticationMethod": 2,
                                         "ldapsettings": {
                                             "AnonymousMode": False,
                                             "AutoCreateUsers": True,
                                             "Password": getpass("Indiquez la valeur de LDAP_BIND_USER_PASSWORD pour portainer: "),
                                             "ReaderDN": portainer_cfg.get('ldap_bind_user_dn', ''),
                                             "SearchSettings": [
                                                 {
                                                     "BaseDN": portainer_cfg.get('ldap_base_dn', ''),
                                                     "Filter": portainer_cfg.get('ldap_search_user_filter', ''),
                                                     "UserNameAttribute": portainer_cfg.get('ldap_search_user_attr', '')
                                                 }
                                             ],
                                             "URL": portainer_cfg.get('ldap_host', '') + ":" +
                                                    portainer_cfg.get('ldap_port', '')
                                         }
                                     })

            if response.status_code not in [200, 204]:
                print("ATTENTION : La configuration de l'authentification LDAP a échouée : %s" % str(response.text))

        else:
            print("ATTENTION : L'endpoint '%s' n'existe pas" % endpoint_name)

    def portainer_deploy_stack(self, stack_config, stack_name):
        stacks = self.portainer_get_stacks()
        for stack in stacks:
            if stack['Name'] == stack_name:
                print("Suppression de la stack %s existante via Portainer" % stack_name)
                stack_id = stack['Id']
                response = requests.delete('http://localhost:9000/api/stacks/%s' % stack_id,
                                           headers={"Authorization": "Bearer %s" % self.portainer_get_token()},
                                           params={'endpointId': self.portainer_endpoint_id})

                if response.status_code not in [200, 204]:
                    print("ERREUR : La suppression de la stack %s a échouée : %s" % (stack_name, response.text))

        # Si la stack n'a pas été supprimée par portainer (car non gérable), suppression via docker
        if self.docker_compose_status(stack_name)['exists']:
            print("Suppression de la stack %s existante via Docker" % stack_name)
            self.docker_compose_down(stack_name, [], None)

        if self.portainer_endpoint_id:
            print("Déploiement de la stack %s" % stack_name)
            response = requests.post('http://localhost:9000/api/stacks',
                                     headers={"Authorization": "Bearer %s" % self.portainer_get_token()},
                                     params={'type': 2, 'method': 'repository', 'endpointId': self.portainer_endpoint_id},
                                     json=stack_config)

            if response.status_code not in [200, 204]:
                print("ERREUR : Le déploiement de l'application a échoué - code %s : %s" % (response.status_code, response.text))

            else:
                # Mise à jour des droits sur la stack
                response_data = response.json()
                resource_id = response_data.get("ResourceControl", {}).get("Id", "")
                self.portainer_update_resource_control(resource_id)
        else:
            print("ERREUR : aucun endpoint défini.")
            sys.exit(1)

    def portainer_update_resource_control(self, resource_id):
        resource_control = {
            "administratorsOnly": False,
            "public": True
        }
        response = requests.put('http://localhost:9000/api/resource_controls/%s' % resource_id,
                                 headers={"Authorization": "Bearer %s" % self.portainer_get_token()},
                                 json=resource_control)

        if response.status_code not in [200, 204]:
            print("ERREUR : La modification du contrôle d'accès a échoué pour le ResourceId %s : %s" % (resource_id, response.text))

    def prepare_traefik(self):
        print("Mise en place des prérequis pour le déploiement de Traefik.")
        traefik_tls_file = os.path.join(self.traefik_providers_path, 'tls.yml')
        traefik_tls_url = "https://raw.githubusercontent.com/%s/%s/%s/docker/standalone/traefik/tls.yml" % \
                          (self.git_sig_org, self.git_sig_repo, self.git_branch)

        # Création du dossier qui contiendra le fichier tls.yml
        os.makedirs(self.traefik_providers_path, exist_ok=True)

        # Téléchargement du fichier tls.yml
        print("Téléchargement du fichier tls.yml dans %s" % self.traefik_providers_path)
        with open(traefik_tls_file, "wb") as file:
            content = requests.get(traefik_tls_url, stream=True).content
            file.write(content)

    def deploy_traefik(self):
        self.portainer_deploy_stack(self.get_traefik_stack_info(), 'traefik')

    def get_certificats(self):

        traefik_cert_path = os.path.join(self.traefik_certs_path, 'w_.lade-eu.cer')
        traefik_privatekey_path = os.path.join(self.traefik_certs_path, 'w_.lade-eu.key')
        traefik_fullcrt_path = os.path.join(self.traefik_certs_path, 'w_.lade-eu.crt')

        # Création du dossier qui contiendra le fichier tls.yml
        os.makedirs(self.traefik_certs_path, exist_ok=True)

        print("Préparation du certificats pour les connexions HTTPS")
        # Vérification de l'existence du fichier pfx
        if not os.path.exists(self.pfx_path):
            print("ATTENTION - Le fichier %s n'existe pas." % self.pfx_path)
            self.pfx_path = input("Indiquez le chemin complet vers le fichier de certificat .pfx: ")

        # Vérification de l'existence de la fullchain
        if not os.path.exists(self.fullchain_path):
            print("ATTENTION - Le fichier %s n'existe pas." % self.pfx_path)
            self.fullchain_path = input("Indiquez le chemin complet vers la fullchain: ")

        try:
            with open(self.pfx_path, 'rb') as pfx:
                private_key, cert, _ = load_key_and_certificates(
                    pfx.read(),
                    password=getpass("Indiquez le mot de passe du fichier .pfx: ").encode('UTF-8'),
                )

            with open(traefik_privatekey_path, 'wb') as file:
                _ = file.write(private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))

            with open(traefik_cert_path, 'wb') as file:
                _ = file.write(cert.public_bytes(Encoding.PEM))

            with open(self.fullchain_path, "r") as file:
                fullchain_data = file.read()

            with open(traefik_fullcrt_path, 'wb') as file:
                _ = file.write(cert.public_bytes(Encoding.PEM))
                _ = file.write(str.encode(fullchain_data))
        except Exception as e:
            print("ATTENTION : Impossible de générer le certificat : %s" % str(e))

    def prepare_qwc2(self):
        # Préparation QWC2
        print("Préparation des dossiers pour QWC2")
        for subdir in self.qwc2_subdirs:
            os.makedirs(os.path.join(self.qwc_app_path, subdir), exist_ok=True)

        print("Création du fichier de configuration pg_services.conf pour QWC2")
        config = configparser.ConfigParser()
        config['qwc_configdb'] = {
            'host': self.app_config['qwc2']['db_host'],
            'port': self.app_config['qwc2']['db_port'],
            'dbname': self.app_config['qwc2']['db_dbname'],
            'user': self.app_config['qwc2']['db_user'],
            'password': getpass("Indiquez le mot de passe du compte %s: " %
                                self.app_config['qwc2']['db_user']),
            'sslmode': 'disable'
        }
        with open(self.qwc2_pgs_path, 'w') as f:
            config.write(f, space_around_delimiters=False)

    def deploy_qwc2(self):
        self.portainer_deploy_stack(self.get_qwc2_stack_info(), 'qwc2')

    def init_db_qwc2(self):
        init_db = input("Souhaitez-vous initialiser les tables dans la BDD QWC2?: ")
        if init_db in ['yes', 'y', 'oui', 'o']:
            try:
                print("Initialisation des données dans la BDD QWC2")
                docker = DockerClient(context='rootless')
                docker.container.run(image="sourcepole/qwc-config-db:latest",
                                     command=['-c',
                                              'alembic revision -m "create sample table" && alembic upgrade head'],
                                     volumes=[(self.qwc2_pgs_path, '/root/.pg_service.conf', 'ro')],
                                     entrypoint='/bin/bash')
            except Exception as e:
                print("ATTENTION : Les tables de QWC2 n'ont pas pu être initialisées : \n %s" % str(e))

    def prepare_plugins_qgis(self):
        # Préparation Dépôt plugins QGIS
        print("Préparation des dossiers pour le dépôt des plugins QGIS")

        plugin_customcatalog_path = os.path.join(self.qgis_plugins_path, 'custom_catalog.zip')
        plugin_projectpublisher_path = os.path.join(self.qgis_plugins_path, 'project_publisher.zip')

        os.makedirs(self.qgis_plugins_path, exist_ok=True)

        self.download_plugin(self.plugin_customcatalog_org,
                             self.plugin_customcatalog_repo,
                             plugin_customcatalog_path)
        self.download_plugin(self.plugin_projectpublisher_org,
                             self.plugin_projectpublisher_repo,
                             plugin_projectpublisher_path)

    def deploy_qgis_plugins_repo(self):
        self.portainer_deploy_stack(self.get_qgis_plugins_repo_stack_info(), 'qgis_plugins_repo')

    def download_plugin(self, org_name, repo_name, plugin_path):
        try:
            git_url = 'https://api.github.com/repos/%s/%s/releases/latest' % (org_name, repo_name)
            git_data = requests.get(git_url)
            plugin_url = git_data.json()['assets'][0]['browser_download_url']

            with open(plugin_path, "wb") as file:
                content = requests.get(plugin_url, stream=True).content
                file.write(content)

        except Exception as e:
            print("ATTENTION : Un plugin n'a pas pu être téléchargé à partir de l'URL %s : \n %s \n %s" %
                  (git_url, str(e), git_data.json()))

    def print_recap(self):
        print("",
              "###########################################################",
              "#######                 Récapitulatif :             #######",
              "###########################################################",
              "Environnement : %s" % self.app_env,
              "Hostname Portainer : %s" % self.portainer_host,
              "Branche Git : %s" % self.git_branch,
              "Hostname Traefik : %s" % self.app_config['traefik']['host'],
              "Traefik LogLevel : %s" % self.app_config['traefik']['loglevel'],
              "MdP admin Portainer : %s" % self.portainer_pass,
              "Dossier des applications SIG : %s" % self.root_apps_dir,
              "Etat de la stack Portainer : %s" % self.docker_compose_status('portainer')['status'],
              "Etat de la stack Traefik : %s" % self.docker_compose_status('traefik')['status'],
              "Etat de la stack QWC2 : %s" % self.docker_compose_status('qwc2')['status'],
              "Etat de la stack QGIS Plugins Repo : %s" % self.docker_compose_status('qgis_plugins_repo')['status'],
              "###########################################################",
              "",
              sep=os.linesep)

    def set_stack_info(self, name, compose_file, env):
        stack_info = {"additionalFiles": [],
                      "autoUpdate": {
                          "interval": "5m",
                      },
                      "composeFile": compose_file,
                      "env": env,
                      "fromAppTemplate": False,
                      "name": name,
                      "repositoryAuthentication": False,
                      "repositoryPassword": "",
                      "repositoryReferenceName": "refs/heads/%s" % self.git_branch,
                      "repositoryURL": "https://github.com/%s/%s" % (self.git_sig_org, self.git_sig_repo),
                      "repositoryUsername": ""
                      }
        return stack_info

    def get_traefik_stack_info(self):
        traefik_env = [
            {
                "name": "TRAEFIK_HOST",
                "value": self.app_config['traefik']['host']
            },
            {
                "name": "TRAEFIK_LOGLEVEL",
                "value": self.app_config['traefik']['loglevel']
            },
            {
                "name": "XDG_RUNTIME_DIR",
                "value": os.getenv("XDG_RUNTIME_DIR")
            }
        ]
        traefik_stack_info = self.set_stack_info('traefik', 'docker/standalone/traefik/traefik.yml', traefik_env)

        return traefik_stack_info

    def get_qwc2_stack_info(self):
        # N.B. En mode rootless, les droits réels resteront sur le compte spécifique à docker et non root.
        qwc2_env = [
            {
                "name": "UID",
                "value": "root"
            },
            {
                "name": "GID",
                "value": "root"
            },
            {
                "name": "JWT_SECRET_KEY",
                "value": secrets.token_urlsafe(16)
            },
            {
                "name": "LDAP_HOST",
                "value": self.app_config['qwc2']['ldap_host']
            },
            {
                "name": "LDAP_PORT",
                "value": self.app_config['qwc2']['ldap_port']
            },
            {
                "name": "LDAP_BASE_DN",
                "value": self.app_config['qwc2']['ldap_base_dn']
            },
            {
                "name": "LDAP_BIND_USER_DN",
                "value": self.app_config['qwc2']['ldap_bind_user_dn']
            },
            {
                "name": "LDAP_BIND_USER_PASSWORD",
                "value": getpass("Indiquez la valeur de LDAP_BIND_USER_PASSWORD pour qwc2: ")

            },
            {
                "name": "TRAEFIK_QWC2_HOST_REGEX",
                "value": self.app_config['qwc2']['host_regex']
            },
            {
                "name": "QWC2_TENANT_URL_RE",
                "value": self.app_config['qwc2']['tenant_url_re']
            },
            {
                "name": "QWC2_FLASK_DEBUG",
                "value": self.app_config['qwc2']['flask_debug']
            }
        ]
        qwc2_stack_info = self.set_stack_info('qwc2', 'docker/standalone/qwc2/qwc2.yml', qwc2_env)

        return qwc2_stack_info

    def get_qgis_plugins_repo_stack_info(self):
        plugins_repo_env = [
            {
                "name": "UID",
                "value": str(os.getuid())
            },
            {
                "name": "GID",
                "value": str(os.getuid())
            },
            {
                "name": "PHPQGISREPOSITORY_VERSION",
                "value": self.app_config['plugins_repo']['phpqgisrepo_version']
            },
            {
                "name": "TRAEFIK_PHPQGISREPOSITORY_HOST",
                "value": self.app_config['plugins_repo']['host']
            }
        ]
        qgis_plugins_repo_stack_info = self.set_stack_info('qgis_plugins_repo',
                                                           'docker/standalone/qgis_plugins_repo/qgis_plugins_repo.yml',
                                                           plugins_repo_env)

        return qgis_plugins_repo_stack_info


sig = DeploySIG()


def deploy():
    sig.deploy()


def update_cert():
    sig.update_cert()


if __name__ == '__main__':
    globals()[sys.argv[1]]()
