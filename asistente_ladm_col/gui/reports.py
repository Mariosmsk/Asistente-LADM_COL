# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              Asistente LADM_COL
                             --------------------
        begin                : 2018-10-17
        git sha              : :%H$
        copyright            : (C) 2018 by Germán Carrillo (BSF Swissphoto)
        email                : gcarrillo@linuxmail.org
 ***************************************************************************/
/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License v3.0 as          *
 *   published by the Free Software Foundation.                            *
 *                                                                         *
 ***************************************************************************/
"""
import os
import locale
import functools
import shutil
import zipfile
import json
import stat
import tempfile
import time

from qgis.core import (QgsGeometry, QgsLineString, QgsDefaultValue, QgsProject,
                       QgsWkbTypes, QgsVectorLayerUtils, QgsDataSourceUri, Qgis,
                       QgsSpatialIndex, QgsVectorLayer, QgsMultiLineString,
                       QgsField,
                       QgsMapLayer,
                       QgsPointXY, QgsNetworkContentFetcherTask,
                       QgsMultiPoint, QgsMultiLineString, QgsGeometryCollection,
                       QgsApplication, QgsProcessingFeedback, QgsRelation,
                       QgsExpressionContextUtils, QgsEditorWidgetSetup,
                       QgsLayerTreeGroup, QgsApplication)
from qgis.PyQt.QtCore import (
    Qt,
    QObject,
    pyqtSignal,
    QCoreApplication,
    QVariant,
    QSettings,
    QLocale,
    QUrl,
    QFile,
    QProcess,
    QEventLoop,
    QIODevice
)
from qgis.PyQt.QtWidgets import QDialog, QFileDialog, QProgressBar

from ..utils.qt_utils import OverrideCursor
from ..utils.symbology import SymbologyUtils
from ..utils.geometry import GeometryUtils
from .dlg_topological_edition import LayersForTopologicalEdition

from ..config.general_config import (
    TEST_SERVER,
    PLUGIN_NAME
)
from ..config.table_mapping_config import (
    ID_FIELD,
    PLOT_TABLE
)

class ReportGenerator():
    def __init__(self, qgis_utils):
        self.qgis_utils = qgis_utils
        self.encoding = locale.getlocale()[1]
        self.log = QgsApplication.messageLog()
        self.LOG_TAB = 'Anexo_17'
        self._downloading = False

    def validate_bin_exists(self, path):
        if os.path.exists(path):
            return True
        else:
            print("Prerequisite wasn't found")
            return False

    def stderr_ready(self, proc):
        text = bytes(proc.readAllStandardError()).decode(self.encoding)
    #    if not self.__done_pattern:
    #        if self.dataImport:
    #            self.__done_pattern = re.compile(r"Info: \.\.\.import done")
    #        else:
    #            self.__done_pattern = re.compile(r"Info: \.\.\.done")
    #    if self.__done_pattern.search(text):
    #        self.__result = Importer.SUCCESS
        #print("err", text)
        self.log.logMessage(text, self.LOG_TAB, Qgis.Critical)

    def stdout_ready(self, proc):
        text = bytes(proc.readAllStandardOutput()).decode(self.encoding)
        #print("out", text)
        self.log.logMessage(text, self.LOG_TAB, Qgis.Info)

    def update_yaml_config(self, db, config_path):
        text = ''
        qgs_uri = QgsDataSourceUri(db.uri)

        with open(os.path.join(config_path, 'config_template.yaml')) as f:
            text = f.read()
            text = text.format(
                '{}',
                DB_USER = qgs_uri.username(),
                DB_PASSWORD = qgs_uri.password(),
                DB_HOST = qgs_uri.host(),
                DB_PORT = qgs_uri.port(),
                DB_NAME = qgs_uri.database()
            )
        new_file_path = os.path.join(config_path, self.get_tmp_filename('yaml_config', 'yaml'))

        with open(new_file_path, 'w') as new_yaml:
            new_yaml.write(text)

        return new_file_path

    def get_layer_geojson(self, db, layer_name, plot_id):
        if layer_name == 'terreno':
            return db.get_annex17_plot_data(plot_id)
        else:
            return db.get_annex17_point_data(plot_id)

    def update_json_data(self, db, json_spec_file, plot_id, tmp_dir):
        json_data = dict()
        with open(json_spec_file) as f:
            json_data = json.load(f)

        json_data['attributes']['id'] = plot_id
        json_data['attributes']['datasetName'] = db.schema
        layers = json_data['attributes']['map']['layers']
        for layer in layers:
            layer['geoJson'] = self.get_layer_geojson(db, layer['name'], plot_id)

        #print(json_data)

        new_json_file_path = os.path.join(tmp_dir, self.get_tmp_filename('json_data_{}'.format(plot_id), 'json'))
        with open(new_json_file_path, 'w') as new_json:
            new_json.write(json.dumps(json_data))

        return new_json_file_path

    def get_tmp_dir(self, create_random=True):
        if create_random:
            return tempfile.mkdtemp()

        return tempfile.gettempdir()

    def get_tmp_filename(self, basename, extension='gpkg'):
        return "{}_{}.{}".format(basename, str(time.time()).replace(".",""), extension)

    def get_java_path_from_project_generator(self):
        settings = QSettings()
        path = settings.value('QgsProjectGenerator/ili2db/JavaPath')
        java_path = os.path.dirname(os.path.dirname(path or ''))
        return java_path

    def generate_report(self, db, button):
        # Check if mapfish and Jasper are installed, otherwise show where to
        # download them from and return
        base_path = os.path.join(os.path.expanduser('~'), 'Asistente-LADM_COL', 'impresion')
        bin_path = os.path.join(base_path, 'bin')
        if not self.validate_bin_exists(bin_path):
            self.qgis_utils.message_with_button_download_report_dependency_emitted.emit(
                QCoreApplication.translate("ReportGenerator",
                   "The dependency library to generate reports is not installed. Click on the button to download and install it."))
            return

        # Check if JAVA_HOME path is set, otherwise use path from project Generator
        if 'JAVA_HOME' not in os.environ:
            java_path = self.get_java_path_from_project_generator()
            if not java_path:
                self.qgis_utils.message_emitted.emit(
                    QCoreApplication.translate("ReportGenerator",
                                               "Please set JAVA_HOME path in Project Generator Settings or in Environmental Variables for your OS"),
                    Qgis.Warning)
                return
            else:
                os.environ["JAVA_HOME"] = java_path
                self.log.logMessage("The JAVA_HOME path have been set using Project Generator Settings for reports", PLUGIN_NAME, Qgis.Info)



        plot_layer = self.qgis_utils.get_layer(db, PLOT_TABLE, QgsWkbTypes.PolygonGeometry, load=True)
        if plot_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("ReportGenerator",
                                           "Layer 'Plot' not found in DB! {}").format(db.get_description()),
                Qgis.Warning)
            return

        selected_plots = plot_layer.selectedFeatures()
        if not selected_plots:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("ReportGenerator",
                                           "To generate reports, first select at least a plot!"),
                Qgis.Warning)
            return

        # Where to store the reports?
        previous_folder = QSettings().value("Asistente-LADM_COL/reports/save_into_dir", ".")
        save_into_folder = QFileDialog.getExistingDirectory(
                        None,
                        QCoreApplication.translate("ReportGenerator", "Select a folder to save the reports to be generated"),
                        previous_folder)
        if not save_into_folder:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("ReportGenerator",
                    "You need to select a folder where to save the reports before continuing."),
                Qgis.Warning)
            return
        QSettings().setValue("Asistente-LADM_COL/reports/save_into_dir", save_into_folder)

        config_path = os.path.join(base_path, 'ANT')
        json_spec_file = os.path.join(config_path, 'spec_json_file.json')

        script_name = ''
        if os.name == 'posix':
            script_name = 'print'
        elif os.name == 'nt':
            script_name = 'print.bat'

        script_path = os.path.join(bin_path, script_name)
        if not os.path.isfile(script_path):
            print("### SCRIPT FILE WASN'T FOUND")
            return

        button.setEnabled(False)

        # Update config file
        yaml_config_path = self.update_yaml_config(db, config_path)
        print("CONFIG FILE:", yaml_config_path)

        total = len(selected_plots)
        step = 0
        count = 0
        tmp_dir = self.get_tmp_dir()

        # Progress bar setup
        progress = QProgressBar()
        if total == 1:
            progress.setRange(0, 0)
        else:
            progress.setRange(0, 100)
        progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.qgis_utils.create_progress_message_bar_emitted.emit(
            QCoreApplication.translate("ReportGenerator", "Generating {} report{}...").format(total, '' if total == 1 else 's'),
            progress)

        for selected_plot in selected_plots:
            plot_id = selected_plot[ID_FIELD]

            # Generate data file
            json_file = self.update_json_data(db, json_spec_file, plot_id, tmp_dir)
            print("JSON FILE:", json_file)

            # Run sh/bat passing config and data files
            proc = QProcess()
            proc.readyReadStandardError.connect(
                functools.partial(self.stderr_ready, proc=proc))
            proc.readyReadStandardOutput.connect(
                functools.partial(self.stdout_ready, proc=proc))

            current_report_path = os.path.join(save_into_folder, 'anexo_17_{}.pdf'.format(plot_id))
            proc.start(script_path, ['-config', yaml_config_path, '-spec', json_file, '-output', current_report_path])

            if not proc.waitForStarted():
                # Grant execution permissions
                os.chmod(script_path, stat.S_IXOTH | stat.S_IXGRP | stat.S_IXUSR | stat.S_IRUSR | stat.S_IRGRP)
                proc.start(script_path, ['-config', yaml_config_path, '-spec', json_file, '-output', current_report_path])

            if not proc.waitForStarted():
                proc = None
                print("### COULDN'T EXECUTE SCRIPT TO GENERATE REPORT...")
            else:
                loop = QEventLoop()
                proc.finished.connect(loop.exit)
                loop.exec()

                print(plot_id, ':', proc.exitCode())
                if proc.exitCode() == 0:
                    count += 1

                step += 1
                progress.setValue(step * 100 / total)

        os.remove(yaml_config_path)
        button.setEnabled(True)
        self.qgis_utils.clear_message_bar_emitted.emit()

        if total == count:
            if total == 1:
                msg = QCoreApplication.translate("ReportGenerator", "The report <a href='file://{}'>anexo_17_{}.pdf</a> was successfully generated!").format(save_into_folder, plot_id)
            else:
                msg = QCoreApplication.translate("ReportGenerator", "All reports were successfully generated in folder <a href='file://{path}'>{path}</a>!").format(path=save_into_folder)

            self.qgis_utils.message_with_duration_emitted.emit(msg, Qgis.Success, 0)
        else:
            if total == 1:
                msg = QCoreApplication.translate("ReportGenerator", "The report for plot {} couldn't be generated! See QGIS log (tab 'Anexo_17') for details.").format(plot_id)
            else:
                if count == 0:
                    msg = QCoreApplication.translate("ReportGenerator", "No report could be generated! See QGIS log (tab 'Anexo_17') for details.")
                else:
                    msg = QCoreApplication.translate("ReportGenerator", "At least one report couldn't be generated! See QGIS log (tab 'Anexo_17') for details. Go to <a href='file://{path}'>{path}</a> to see the reports that were generated.").format(path=save_into_folder)

            self.qgis_utils.message_with_duration_emitted.emit(msg, Qgis.Warning, 0)


    def save_dependency_file(self, fetcher_task):
        if fetcher_task.reply() is not None:
            tmp_file = tempfile.mktemp()
            out_file = QFile(tmp_file)
            out_file.open(QIODevice.WriteOnly)
            out_file.write(fetcher_task.reply().readAll())
            out_file.close()

            dependency_base_path = os.path.join(os.path.expanduser('~'), 'Asistente-LADM_COL')
            if not os.path.exists(dependency_base_path):
                os.makedirs(dependency_base_path)

            print(dependency_base_path)

            try:
                with zipfile.ZipFile(tmp_file, "r") as zip_ref:
                    zip_ref.extractall(dependency_base_path)

            except zipfile.BadZipFile as e:
                self.qgis_utils.message_with_duration_emitted.emit(
                    QCoreApplication.translate("ReportGenerator", "There was an error with the download. The downloaded file is invalid."),
                    Qgis.Warning,
                    0)
            else:
                self.qgis_utils.message_with_duration_emitted.emit(
                    QCoreApplication.translate("ReportGenerator", "The dependency to generate reports is properly installed! Select plots and click again the button in the toolbar to generate reports."),
                    Qgis.Info,
                    0)

            try:
                os.remove(tmp_file)
            except:
                pass

        self._downloading = False

    def download_report_dependency(self):
        self.qgis_utils.clear_message_bar_emitted.emit()
        if not self._downloading:
            if self.qgis_utils.is_connected(TEST_SERVER):
                self._downloading = True
                url = 'https://owncloud.proadmintierra.info/owncloud/index.php/s/mrUcc2ugGJoB8pk/download'
                fetcher_task = QgsNetworkContentFetcherTask(QUrl(url))
                fetcher_task.fetched.connect(functools.partial(self.save_dependency_file, fetcher_task))
                QgsApplication.taskManager().addTask(fetcher_task)
            else:
                self.qgis_utils.message_emitted.emit(
                    QCoreApplication.translate("AboutDialog", "There was a problem connecting to Internet."),
                    Qgis.Warning)
                self._downloading = False
        else:
            print("Already downloading report dependency...")
