
# Script qui sera lancé au démarrage de QGIS 
# Son chemin d'accès est à déclarer dans la variable d'environnement PYQGIS_STARTUP

import requests
import os

appdata_path = os.getenv('APPDATA')
qgisdata_path = os.path.join(appdata_path, 'QGIS/QGIS3')

script_url = "https://raw.githubusercontent.com/naub1n/lade_dsiun_sig/developpement/qgis/startup.py"
script_dest = os.path.join(qgisdata_path, 'startup.py')

resp = requests.get(script_url, verify=False)

with open(script_dest, "wb") as f:
    f.write(resp.content)
