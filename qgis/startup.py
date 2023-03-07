import os
import json
import pyplugin_installer
import re
import configparser

from qgis.core import (QgsSettings, QgsApplication, QgsAuthMethodConfig, QgsExpressionContextUtils,
                       QgsMessageLog, Qgis)
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface
from pyplugin_installer.installer_data import repositories, plugins, reposGroup


class StartupDSIUN:
    def __init__(self):

        #### Variables à paramètrer ####
        self.repo_dsiun_name = "Dépôt DSIUN"
        self.repo_dsiun_url = "http://geoplugins-dev.lesagencesdeleau.eu"
        self.plugin_project_publisher = 'project_publisher'
        self.plugin_custom_catalog = 'custom_catalog'
        self.catalog_dsiun_name = 'Catalogue DSIUN'
        self.catalog_dsiun_link = "http://github"
        self.auth_id = "dsiun01"
        self.auth_conf_name = "Authentification individuelle Windows des Agences de l'eau"
        self.profile_dsiun = "DSIUN"
        self.default_profile_message = "Vous utilisez le profil par défaut. Privilégiez le profil DSIUN."
        self.qgis_version_dsiun = 32214
        self.qgis_bad_version_message = "Vous utilisez une version (%s) non gérée par la DSIUN (%s). Le paramètrage ne sera pas appliqué."
        #################################

        self.plugins_dsiun = [self.plugin_project_publisher,
                              self.plugin_custom_catalog]
        self.pyplugin_inst = pyplugin_installer.instance()
        self.plugins_data = pyplugin_installer.installer_data.plugins
        self.profile_name = None
        # Un bug dans userProfileManager() dans les versions inférieures à 3.30.0 ne permet pas d'interagir correctement
        # avec les profils utilisateurs : https://github.com/qgis/QGIS/issues/48337
        self.qgis_min_version_profile = 33000
        self.p_mgr = iface.userProfileManager()
        self.auth_mgr = QgsApplication.authManager()
        self.current_v = Qgis.QGIS_VERSION_INT

        self.current_profile_path = None
        self.profiles_path = None
        self.config_profiles_path = None
        self.qgis_profile_path = None
        self.config_profile_path = None
        self.cc_config_path = None

        self.qt_auth_dlg = QtWidgets.QDialog(None)
        self.qt_auth_login = QtWidgets.QLineEdit(self.qt_auth_dlg)
        self.qt_auth_pass = QtWidgets.QLineEdit(self.qt_auth_dlg)

    def start(self):
        self.get_paths()
        if self.check_version():
            if self.profile_name == self.profile_dsiun:
                self.check_repo()
                self.install_plugins()
                self.get_catalog_config()
                self.check_auth_cfg()
                self.check_profil()
            else:
                self.check_profil()

            if self.profile_name == 'default':
                iface.messageBar().pushMessage(self.default_profile_message, level=Qgis.Info, duration=10)

    def log(self, log_message, log_level):
        QgsMessageLog.logMessage(log_message, 'Startup DSIUN', level=log_level, notifyUser=False)

    def check_repo(self):
        self.log("Vérification de la présence du dépôt DSIUN ...", Qgis.Info)
        try:
            settings = QgsSettings()
            settings.beginGroup(reposGroup)
            repos_name = self.repo_dsiun_name
            repos_url = self.repo_dsiun_url
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

    def get_catalog_config(self):
        self.log("Paramétrage du catalogue des AE ...", Qgis.Info)
        try:
            # Vérification de la disponibilité du plugin
            if self.plugin_custom_catalog in self.plugins_data.all().keys():
                # Vérification de son installation
                if self.plugins_data.all()[self.plugin_custom_catalog]['installed']:
                    # Récupération de la configuration actuelle
                    if os.path.exists(self.cc_config_path):
                        with open(self.cc_config_path, 'r') as f:
                            catalog_settings = json.load(f)

                        # Suppression du catalog par défaut
                        for index, catalog in enumerate(catalog_settings['catalogs']):
                            if catalog['name'] == 'CatalogExample':
                                self.log("Suppression du catalogue par défaut", Qgis.Info)
                                del catalog_settings['catalogs'][index]
                                break

                        if not any(catalog.get('name', None) == self.catalog_dsiun_name for catalog in
                                   catalog_settings['catalogs']):
                            self.log("Catalogue DSIUN absent - ajout du catalogue", Qgis.Info)
                            catalog_settings['catalogs'].append(
                                {
                                    "name": self.catalog_dsiun_name,
                                    "type": "json",
                                    "link": "",
                                    "qgisauthconfigid": ""
                                })

                        with open(self.cc_config_path, 'w') as json_file:
                            json.dump(catalog_settings, json_file, indent=2)

                        self.log("Paramétrage du catalogue - OK", Qgis.Info)
                    else:
                        self.log("Le chemin vers le fichier de configuration n'existe pas : %s" % str(self.cc_config_path), Qgis.Warning)
                else:
                    self.log("Le plugin %s n'est pas installé" % str(self.plugin_custom_catalog), Qgis.Warning)
            else:
                self.log("Le plugin %s n'est pas disponible" % str(self.plugin_custom_catalog), Qgis.Warning)
        except Exception as e:
            self.log("Erreur lors du paramétrage du catalogue : %s" % str(e), Qgis.Critical)

    def check_auth_cfg(self):
        self.log("Vérification de la configuration d'authentification des AE ...", Qgis.Info)
        try:
            ids = self.auth_mgr.availableAuthMethodConfigs().keys()
            if self.auth_id in ids:
                self.log("La configuration est déjà présente", Qgis.Info)
                return
            else:
                self.log("Ajout de la configuration d'authentification %s" % str(self.auth_id), Qgis.Info)

                # Définition du mot de passe par l'utilisateur
                self.qt_auth_dlg.setWindowTitle("Indiquer votre login et mdp Windows")
                layout = QtWidgets.QVBoxLayout(self.qt_auth_dlg)
                self.qt_auth_login.setText(QgsExpressionContextUtils.globalScope().variable('user_account_name'))
                self.qt_auth_pass.setEchoMode(QtWidgets.QLineEdit.Password)
                button_save = QtWidgets.QPushButton('Enregistrer', self.qt_auth_dlg)
                button_save.clicked.connect(self.button_save_clicked)
                layout.addWidget(self.qt_auth_login)
                layout.addWidget(self.qt_auth_pass)
                layout.addWidget(button_save)
                self.qt_auth_dlg.setLayout(layout)
                self.qt_auth_dlg.setWindowModality(Qt.WindowModal)
                self.qt_auth_dlg.exec_()

            self.log("Vérification de la configuration d'authentification - OK", Qgis.Info)
        except Exception as e:
            self.log("Erreur lors de la vérification de la configuration d'authentification : %s" % str(e), Qgis.Critical)

    def button_save_clicked(self):
        config = QgsAuthMethodConfig()
        config.setId(self.auth_id)
        config.setName(self.auth_conf_name)
        config.setConfig('username', self.qt_auth_login.text())
        config.setConfig('password', self.qt_auth_pass.text())
        config.setMethod("Basic")
        assert config.isValid()
        # Ajout de la configuration d'authentification DSIUN
        self.auth_mgr.storeAuthenticationConfig(config)
        self.qt_auth_dlg.accept()

    def check_profil(self):
        self.log("Vérification du profile par défaut ...", Qgis.Info)
        try:
            if not self.profile_exists(self.profile_dsiun):
                self.log("Création du profile %s" % self.profile_dsiun, Qgis.Info)
                if self.current_v >= self.qgis_min_version_profile:
                    self.p_mgr.createUserProfile(self.profile_dsiun)
                else:
                    self.log("Utilisation de la méthode pour les versions inférieures à %s" %
                             self.qgis_min_version_profile, Qgis.Info)
                    # Création du dossier du profile et du fichier de configuration vide
                    os.makedirs(self.qgis_profile_path, exist_ok=True)
                    with open(self.config_profile_path, mode='w'):
                        pass

                # Demande à l'utilisateur d'ouvrir le profile de la DSIUN
                msg_box = QtWidgets.QMessageBox()
                msg_box.setText("Le profile DSIUN a été créé.\n" +
                                "Souhaitez-vous basculer sur le profile DSIUN?")
                msg_box.setStandardButtons(QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Yes)
                open_new_profil = msg_box.exec()
                if open_new_profil == QtWidgets.QMessageBox.Yes:
                    self.p_mgr.loadUserProfile(self.profile_dsiun)
                    QgsApplication.exit() #Ne marche pas !

            # Vérification du profile par défaut
            if not self.p_mgr.defaultProfileName == self.profile_dsiun:
                self.set_default_profile(self.profile_dsiun)

            self.log("Vérification du profil par défaut - OK", Qgis.Info)
        except Exception as e:
            self.log("Erreur lors de la vérification du profil par défaut : %s" % str(e), Qgis.Critical)

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
                                           level=Qgis.Warning, duration=3)
            self.log(self.qgis_bad_version_message % (self.current_v, self.qgis_version_dsiun), Qgis.Warning)
            return False

    def get_paths(self):
        self.current_profile_path = QgsApplication.qgisSettingsDirPath().replace('\\', '/')
        self.profiles_path = re.search("(.*?profiles/)", self.current_profile_path).group(1)
        self.config_profiles_path = os.path.join(self.profiles_path, 'profiles.ini')
        self.qgis_profile_path = os.path.join(self.profiles_path, self.profile_dsiun + '/QGIS')
        self.config_profile_path = os.path.join(self.qgis_profile_path, 'QGIS3.ini').replace('\\', '/')
        self.cc_config_path = os.path.join(self.current_profile_path,
                                           'python/plugins/' + self.plugin_custom_catalog + '/conf/settings.json')

    def get_current_profile_name(self):
        # Les versions inférieures de QGIS ont un bug sur la gestion des profiles
        if self.current_v >= self.qgis_min_version_profile:
            profile = self.p_mgr.userProfile()
            self.profile_name = profile.name()
        else:
            self.log("Utilisation de la méthode pour les versions inférieures à %s" %
                     self.qgis_min_version_profile, Qgis.Info)
            self.profile_name = re.search("profiles/(.*?)/", self.current_profile_path).group(1)

    def profile_exists(self, profile_name):
        if self.current_v >= self.qgis_min_version_profile:
            return self.p_mgr.profileExists(profile_name)

        else:
            return profile_name in os.listdir(self.profiles_path)



# Lancement de la procédure
startup = StartupDSIUN()
startup.start()
