import os
import json
import pyplugin_installer
import re
import configparser
import requests
import pkg_resources

from qgis.core import (QgsSettings, QgsApplication, QgsAuthMethodConfig, QgsExpressionContextUtils,
                       QgsMessageLog, Qgis, QgsProviderRegistry, QgsDataSourceUri, QgsUserProfileManager)
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface
from pyplugin_installer.installer_data import repositories, plugins, reposGroup


class StartupDSIUN:
    def __init__(self):

        #### Variables à paramétrer ####
        self.conf_url = "https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/developpement/qgis/startup_parameters.json"
        self.default_profile_message = "Vous utilisez le profil par défaut. Privilégiez le profil DSIUN."
        self.qgis_bad_version_message = "Vous utilisez une version (%s) non gérée par la DSIUN (%s). Le paramètrage ne sera pas appliqué."

        #################################

        self.pyplugin_inst = pyplugin_installer.instance()
        self.plugins_data = pyplugin_installer.installer_data.plugins
        # Un bug dans userProfileManager() dans les versions inférieures à 3.30.0 ne permet pas d'interagir correctement
        # avec les profils utilisateurs : https://github.com/qgis/QGIS/issues/48337
        self.qgis_min_version_profile = 33000
        self.auth_mgr = QgsApplication.authManager()
        self.current_v = Qgis.QGIS_VERSION_INT
        self.user_domain = os.environ.get("userdomain", "").lower()

        if self.current_v >= self.qgis_min_version_profile:
            self.p_mgr = iface.userProfileManager()
        else:
            self.p_mgr = QgsUserProfileManager()

        self.current_profile_path = None
        self.profiles_path = None
        self.config_profiles_path = None

        # Préparation des chemins vers les dossiers ou fichiers de config qgis
        self.get_paths()
        # Lecture du fichier de configuration
        self.global_config = self.get_global_config()
        self.env_config = self.read_conf(self.global_config)
        # à nettoyer et améliorer :
        config = self.env_config
        # Initialisation de certains paramètres
        self.plugin_project_publisher = 'project_publisher'
        self.plugin_custom_catalog = 'custom_catalog'
        self.catalogs = config.get("catalogs", [])
        self.auth_configs = config.get("authentications", [])
        self.profile_dsiun = config.get("profile_name", "")
        self.qgis_version_dsiun = config.get("qgis", {}).get("dsiun_version", "")
        self.plugins_dsiun = config.get("plugins", {}).get("plugins_names", [])
        self.database_connections = config.get("db_connections", [])
        self.current_env = config.get("env_name", "")

    def get_global_config(self):
        self.log("Lecture de la configuration globale.", Qgis.Info)
        try:
            conf_url = self.conf_url
            resp = requests.get(conf_url, verify=False)
            config = resp.json()

            return config

        except Exception as e:
            self.log("Erreur lors de la lecture de la configuration globale: %s" % str(e), Qgis.Critical)

            return {}

    def read_conf(self, config):
        self.log("Lecture de la configuration de l'environnement.", Qgis.Info)
        env_config = {}
        current_profile = self.get_current_profile_name()
        for key, environment in enumerate(config.get("environments", [])):
            if environment.get("env_name", "") == "production":
                env_prod_key = key

            if environment.get("profile_name", "") == current_profile:
                env_config = environment
                env_name = environment.get("env_name", "")

        if not env_config:
            self.log("profil '%s' inconnu, utilisation de la configuration de production" % current_profile,
                     Qgis.Warning)
            env_config = config.get("environments", [])[env_prod_key]
        else:
            self.log("Utilisation de la configuration '%s'" % env_name, Qgis.Info)

        return env_config

    def start(self):
        if self.check_json():
            profiles = []
            for env in self.global_config.get("environments", []):
                profiles.append(env.get("profile_name", ""))

            if self.check_version():
                profile_name = self.get_current_profile_name()
                if profile_name in profiles:
                    self.check_repo()
                    self.install_plugins()
                    self.get_catalog_config()
                    self.check_auth_cfg()
                    self.add_connections()
                    self.check_profiles()
                else:
                    self.check_profiles()

                if profile_name == 'default':
                    iface.messageBar().pushMessage(self.default_profile_message, level=Qgis.Info, duration=10)

    def log(self, log_message, log_level):
        QgsMessageLog.logMessage(log_message, 'Startup DSIUN', level=log_level, notifyUser=False)

    def check_repo(self):
        repos_name = self.env_config.get("plugins", {}).get("repo_name", "")
        repos_url = self.env_config.get("plugins", {}).get("repo_url", "")
        if repos_name and repos_url:
            self.log("Vérification de la présence du dépôt DSIUN ...", Qgis.Info)
            try:
                settings = QgsSettings()
                settings.beginGroup(reposGroup)
                if repos_name in repositories.all():
                    settings.remove(repos_name)
                # add to settings
                settings.setValue(repos_name + "/url", repos_url)
                settings.setValue(repos_name + "/authcfg", None)
                settings.setValue(repos_name + "/enabled", True)
                # refresh lists and populate widgets
                plugins.removeRepository(repos_name)
                self.pyplugin_inst.reloadAndExportData()
                self.log("Ajout/Remplacement du dépôt - OK", Qgis.Info)
            except Exception as e:
                self.log("Erreur lors de la l'ajout/le remplacement du dépôt : %s" % str(e), Qgis.Critical)

    def install_plugins(self):
        self.log("Vérification des plugins requis ...", Qgis.Info)
        try:
            available_plugins_keys = self.plugins_data.all().keys()
            upgradable_plugins_keys = self.plugins_data.allUpgradeable().keys()

            errors = False

            for plugin_dsiun in self.plugins_dsiun:

                if plugin_dsiun in available_plugins_keys:

                    is_installed = self.plugins_data.all()[plugin_dsiun]['installed']
                    is_upgradable = plugin_dsiun in upgradable_plugins_keys

                    if not is_installed or is_upgradable:
                        self.log("Installation/Mise à jour du paquet %s" % str(plugin_dsiun), Qgis.Info)
                        self.pyplugin_inst.installPlugin(plugin_dsiun)
                    else:
                        self.log("Le paquet %s est installé et à jour" % str(plugin_dsiun), Qgis.Info)
                else:
                    errors = True
                    self.log("Le paquet %s est indisponible" % str(plugin_dsiun), Qgis.Critical)

            if not errors:
                self.log("Vérification des plugins - OK", Qgis.Info)
        except Exception as e:
            self.log("Erreur lors l'installation ou les mise à jour des plugins : %s" % str(e), Qgis.Critical)

    def get_current_customcatalog_settings(self):
        s = QgsSettings()
        s.beginGroup("CustomCatalog/catalogs")

        catalogs = []
        for key in s.childGroups():
            catalog = {
                "name": s.value("%s/name" % key, ""),
                "type": s.value("%s/type" % key, ""),
                "link": s.value("%s/link" % key, ""),
                "qgisauthconfigid": s.value("%s/qgisauthconfigid" % key, "")
            }
            catalogs.append(catalog)

        settings = {"catalogs": catalogs}

        return settings

    def save_customcatalog_settings(self, settings):
        s = QgsSettings()
        s.beginGroup("CustomCatalog")
        s.remove("CustomCatalog/catalogs")

        for key, catalog in enumerate(settings.get("catalogs", [])):
            s.setValue("catalogs/%s/name" % key, catalog.get("name", ""))
            s.setValue("catalogs/%s/type" % key, catalog.get("type", ""))
            s.setValue("catalogs/%s/link" % key, catalog.get("link", ""))
            s.setValue("catalogs/%s/qgisauthconfigid" % key, catalog.get("qgisauthconfigid", ""))

    def get_catalog_config(self):
        self.log("Paramétrage du catalogue des AE ...", Qgis.Info)
        try:
            plugin_name = self.plugin_custom_catalog
            # Vérification de la disponibilité du plugin
            if plugin_name in self.plugins_data.all().keys():
                # Vérification de son installation
                if self.plugins_data.all()[plugin_name]['installed']:
                    catalog_settings = self.get_current_customcatalog_settings()

                    # Suppression du catalog par défaut
                    for index, catalog in enumerate(catalog_settings['catalogs']):
                        if catalog['name'] == 'CatalogExample':
                            self.log("Suppression du catalogue par défaut", Qgis.Info)
                            del catalog_settings['catalogs'][index]
                            break

                    for catalog in self.catalogs:
                        new_catalog_name = catalog.get("name", "")
                        new_catalog_data = {
                            "name": new_catalog_name,
                            "type": catalog.get("type", ""),
                            "link": catalog.get("link", ""),
                            "qgisauthconfigid": catalog.get("qgisauthconfigid", "")
                        }
                        if not any(local_catalog.get('name', None) == new_catalog_name for local_catalog in
                                   catalog_settings['catalogs']):
                            self.log("Catalogue '%s' absent - ajout du catalogue" % new_catalog_name, Qgis.Info)
                            catalog_settings['catalogs'].append(new_catalog_data)
                        else:
                            self.log("Mise à jour du catalogue '%s'." % new_catalog_name, Qgis.Info)
                            for key, local_catalog in enumerate(catalog_settings['catalogs']):
                                if local_catalog.get("name", "") == new_catalog_name:
                                    catalog_settings['catalogs'][key] = new_catalog_data

                    self.save_customcatalog_settings(catalog_settings)

                    self.log("Paramétrage du catalogue - OK", Qgis.Info)
                else:
                    self.log("Le plugin %s n'est pas installé" % str(plugin_name), Qgis.Warning)
            else:
                self.log("Le plugin %s n'est pas disponible" % str(plugin_name), Qgis.Warning)
        except Exception as e:
            self.log("Erreur lors du paramétrage du catalogue : %s" % str(e), Qgis.Critical)

    def check_auth_cfg(self):
        self.log("Vérification de la configuration d'authentification des AE ...", Qgis.Info)
        try:

            ids = self.auth_mgr.availableAuthMethodConfigs().keys()

            for auth_config in self.auth_configs:
                self.auth_id = auth_config.get("id", "")
                self.auth_conf_name = auth_config.get("name", "")
                auth_user = auth_config.get("user", "")
                auth_pass = auth_config.get("pass", "")
                auth_domains = [x.lower() for x in auth_config.get("domains", [])]

                if self.user_domain in auth_domains or "all" in auth_domains:
                    if self.auth_id in ids:
                        self.log("La configuration %s est déjà présente" % str(self.auth_id), Qgis.Info)

                    else:
                        self.log("Ajout de la configuration d'authentification %s" % str(self.auth_id), Qgis.Info)

                        if auth_user and auth_pass:
                            self.save_auth_config(self.auth_id, self.auth_conf_name, auth_user, auth_pass)

                            continue

                        else:
                            self.qt_auth_dlg = QtWidgets.QDialog(None)
                            self.qt_auth_dlg.setFixedWidth(450)
                            self.qt_auth_dlg.setWindowTitle("Indiquer votre login et mdp")

                            self.qt_auth_login = QtWidgets.QLineEdit(self.qt_auth_dlg)
                            self.qt_auth_login.setPlaceholderText("Identifiant")

                            if self.auth_id in ["dsiun01"]:
                                self.qt_auth_login.setText(
                                    QgsExpressionContextUtils.globalScope().variable('user_account_name'))

                            if auth_user:
                                self.qt_auth_login.setText(auth_user)

                            self.qt_auth_pass = QtWidgets.QLineEdit(self.qt_auth_dlg)
                            self.qt_auth_pass.setEchoMode(QtWidgets.QLineEdit.Password)
                            self.qt_auth_pass.setPlaceholderText("Mot de passe (laisser vide si inconnu)")

                            if auth_pass:
                                self.qt_auth_pass.setText(auth_pass)

                            self.qt_info_env = QtWidgets.QLabel(self.qt_auth_dlg)

                            self.qt_info_auth_conf_name = QtWidgets.QLabel(self.qt_auth_dlg)

                            self.qt_info_env.setText("Environnement : %s" % self.current_env)

                            self.qt_info_auth_conf_name.setText("Nom : %s" % self.auth_conf_name)

                            button_save = QtWidgets.QPushButton('Enregistrer', self.qt_auth_dlg)
                            button_save.clicked.connect(self.button_save_clicked)

                            layout = QtWidgets.QVBoxLayout(self.qt_auth_dlg)
                            layout.addWidget(self.qt_info_env)
                            layout.addWidget(self.qt_info_auth_conf_name)
                            layout.addWidget(self.qt_auth_login)
                            layout.addWidget(self.qt_auth_pass)
                            layout.addWidget(button_save)

                            self.qt_auth_dlg.setLayout(layout)
                            self.qt_auth_dlg.setWindowModality(Qt.WindowModal)
                            self.qt_auth_dlg.exec_()

            self.log("Vérification de la configuration des authentifications - OK", Qgis.Info)
        except Exception as e:
            self.log("Erreur lors de la vérification de la configuration d'authentification : %s" % str(e),
                     Qgis.Critical)

    def button_save_clicked(self):
        self.save_auth_config(self.auth_id, self.auth_conf_name, self.qt_auth_login.text(), self.qt_auth_pass.text())
        self.qt_auth_dlg.accept()

    def save_auth_config(self, auth_id, name, user, password):
        config = QgsAuthMethodConfig()
        config.setId(auth_id)
        config.setName(name)
        config.setConfig('username', user)
        config.setConfig('password', password)
        config.setMethod("Basic")
        assert config.isValid()

        self.auth_mgr.storeAuthenticationConfig(config)

    def check_profiles(self):
        self.log("Vérification des profiles ...", Qgis.Info)
        try:
            for env in self.global_config.get("environments", []):
                profile = env.get("profile_name", "")
                is_default_profile = env.get("profile_default", False)

                qgis_profile_path = os.path.join(self.profiles_path, profile + '/QGIS')
                config_profile_path = os.path.join(qgis_profile_path, 'QGIS3.ini').replace('\\', '/')

                if not self.profile_exists(profile):
                    self.log("Création du profile %s" % profile, Qgis.Info)
                    if self.current_v >= self.qgis_min_version_profile:
                        self.p_mgr.createUserProfile(profile)
                    else:
                        self.log("Utilisation de la méthode pour les versions inférieures à %s" %
                                 self.qgis_min_version_profile, Qgis.Info)
                        # Création du dossier du profil et du fichier de configuration vide
                        os.makedirs(qgis_profile_path, exist_ok=True)
                        with open(config_profile_path, mode='w'):
                            pass

                    if is_default_profile:
                        # Demande à l'utilisateur d'ouvrir le profile de la DSIUN
                        msg_box = QtWidgets.QMessageBox()
                        msg_box.setText("Le profile %s a été créé.\n" % profile +
                                        "Souhaitez-vous basculer sur ce profil?")
                        msg_box.setStandardButtons(QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Yes)
                        open_new_profil = msg_box.exec()
                        if open_new_profil == QtWidgets.QMessageBox.Yes:
                            self.p_mgr.loadUserProfile(profile)
                            # Ne fonctionne pas :
                            os._exit(0)

                # Vérification du profil par défaut
                if is_default_profile:
                    if not self.p_mgr.defaultProfileName == profile:
                        self.set_default_profile(profile)

            self.log("Vérification des profiles - OK", Qgis.Info)
        except Exception as e:
            self.log("Erreur lors de la vérification des profiles : %s" % str(e), Qgis.Critical)

    def set_default_profile(self, profile_name):
        self.log("Paramétrage du profile par défaut ...", Qgis.Info)
        try:
            if self.current_v >= self.qgis_min_version_profile:
                self.p_mgr.setDefaultProfileName(profile_name)
            else:
                self.log("Utilisation de la méthode pour les versions inférieures à %s" %
                         self.qgis_min_version_profile, Qgis.Info)
                config = configparser.ConfigParser()
                config.read(self.config_profiles_path)
                config['core']['defaultProfile'] = profile_name
                with open(self.config_profiles_path, 'w') as configfile:
                    config.write(configfile, space_around_delimiters=False)

            self.log("%s devient le profile par défaut" % profile_name, Qgis.Info)
        except Exception as e:
            self.log("Impossible de définir '%s' en tant que profil par défaut : %s" % (str(profile_name), str(e)),
                     Qgis.Critical)

    def check_version(self):
        self.log("Vérification de la version de QGIS ...", Qgis.Info)
        if self.current_v == self.qgis_version_dsiun:
            self.get_current_profile_name()
            return True
        else:
            iface.messageBar().pushMessage(self.qgis_bad_version_message % (self.current_v, self.qgis_version_dsiun),
                                           level=Qgis.Warning, duration=10)
            self.log(self.qgis_bad_version_message % (self.current_v, self.qgis_version_dsiun), Qgis.Warning)
            return False

    def get_paths(self):
        self.current_profile_path = QgsApplication.qgisSettingsDirPath().replace('\\', '/')
        self.profiles_path = re.search("(.*?profiles/)", self.current_profile_path).group(1)
        self.config_profiles_path = os.path.join(self.profiles_path, 'profiles.ini')

    def get_current_profile_name(self):
        # Les versions inférieures de QGIS ont un bug sur la gestion des profils
        if self.current_v >= self.qgis_min_version_profile:
            profile = self.p_mgr.userProfile()
            profile_name = profile.name()
        else:
            profile_name = re.search("profiles/(.*?)/", self.current_profile_path).group(1)

        return profile_name

    def profile_exists(self, profile_name):
        if self.current_v >= self.qgis_min_version_profile:
            return self.p_mgr.profileExists(profile_name)

        else:
            return profile_name in os.listdir(self.profiles_path)

    def add_connections(self):
        self.log("Vérification de la présence des connections aux BDD.", Qgis.Info)
        for cnx in self.database_connections:
            cnx_provider = cnx.get("qgis_provider", "")
            cnx_name = cnx.get("name", "")
            cnx_host = cnx.get("host", "")
            cnx_port = cnx.get("port", "")
            cnx_dbname = cnx.get("dbname", "")
            cnx_auth_id = cnx.get("auth_id", "")
            cnx_domains = [x.lower() for x in cnx.get("domains", [])]

            if self.user_domain in cnx_domains or "all" in cnx_domains:
                try:
                    provider = QgsProviderRegistry.instance().providerMetadata(cnx_provider)
                    uri = QgsDataSourceUri()
                    uri.setConnection(aHost=cnx_host,
                                      aPort=cnx_port,
                                      aDatabase=cnx_dbname,
                                      aUsername=None,
                                      aPassword=None,
                                      authConfigId=cnx_auth_id)
                    self.log("Ajout/Restauration de la connection '%s'." % cnx_name, Qgis.Info)
                    new_conn = provider.createConnection(uri.uri(expandAuthConfig=False), {})
                    # La connexion est ajoutée si inexistante ou remplacée si elle existe déjà
                    provider.saveConnection(new_conn, cnx_name)
                except Exception as e:
                    self.log("Erreur lors de la l'ajout de la connexion '%s' : %s" % (cnx_name, str(e)), Qgis.Critical)

    def check_json(self):
        try:
            self.install_python_package("jsonschema")
            import jsonschema

        except Exception as e:
            msg = "Impossible d'installer les paquets python : %s" % str(e)
            self.log(msg, Qgis.Critical)
            return False

        schema_conf_url = self.global_config.get('$schema',
                                                 'https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/developpement/qgis/startup_parameters_schema.json')

        try:
            r = requests.get(schema_conf_url,
                             headers={'Accept': 'application/json'})
            schema = r.json()

        except Exception as e:
            msg = "Impossible de lire l'URL du schéma : %s" % str(e)
            self.log(msg, Qgis.Critical)
            return False

        if schema:
            try:
                jsonschema.validate(self.global_config, schema)
                self.log("Configuration JSON validée", Qgis.Info)
                return True

            except Exception as valid_err:
                msg = "La configuration JSON n'est pas valide:\n%s" % str(valid_err)
                self.log(msg, Qgis.Critical)
                return False

        else:
            self.log("Le schéma de validation est vide - Validation ignorée", Qgis.Warning)
            return True

    def install_python_package(self, package_name):
        installed_packages = pkg_resources.working_set
        installed_packages_list = sorted([i.key for i in installed_packages])
        if package_name not in installed_packages_list:
            self.log("Installation de %s" % package_name, Qgis.Info)
            import subprocess
            osgeo4w_env_path = os.path.join(os.getenv('OSGEO4W_ROOT'), 'OSGeo4W.bat')
            subprocess.check_call(['call', osgeo4w_env_path, ';',
                                   'python.exe', '-m', 'pip', 'install', '--upgrade', 'pip'], shell=True)
            subprocess.check_call(['call', osgeo4w_env_path, ';',
                                   'python.exe', '-m', 'pip', 'install', package_name], shell=True)


# Lancement de la procédure
startup = StartupDSIUN()
startup.start()
