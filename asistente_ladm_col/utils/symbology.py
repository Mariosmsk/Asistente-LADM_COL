# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              Asistente LADM_COL
                             --------------------
        begin                : 2018-04-16
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
import os.path

from qgis.core import (
    QgsFeatureRenderer,
    QgsAbstractVectorLayerLabeling,
    QgsReadWriteContext
)
from qgis.PyQt.QtCore import QObject, pyqtSignal, QFile, QIODevice
from qgis.PyQt.QtXml import QDomDocument

from ..config.translator import QGIS_LANG
from ..config.general_config import (
    STYLES_DIR
)
from ..config.symbology import (
    LAYER_QML_STYLE,
    ERROR_LAYER,
    CUSTOM_ERROR_LAYERS
)

class SymbologyUtils(QObject):

    layer_symbology_changed = pyqtSignal(str) # layer id

    def __init__(self):
        QObject.__init__(self)

    def set_layer_style_from_qml(self, layer, is_error_layer=False, emit=False):
        qml_name = None
        if is_error_layer:
            if layer.name() in CUSTOM_ERROR_LAYERS:
                # Symbology is selected according to the language
                qml_name = CUSTOM_ERROR_LAYERS[layer.name()][QGIS_LANG]
            else:
                qml_name = LAYER_QML_STYLE[ERROR_LAYER][layer.geometryType()]
        else:
            if layer.name() in LAYER_QML_STYLE:
                qml_name = LAYER_QML_STYLE[layer.name()][layer.geometryType()]

        if qml_name is not None:
            renderer, labeling = self.get_style_from_qml(qml_name)
            if renderer:
                layer.setRenderer(renderer)
                if emit:
                    self.layer_symbology_changed.emit(layer.id())
            if labeling:
                layer.setLabeling(labeling)
                layer.setLabelsEnabled(True)

    def get_style_from_qml(self, qml_name):
        renderer = None
        labeling = None

        style_path = os.path.join(STYLES_DIR, qml_name + '.qml')
        file = QFile(style_path)
        if not file.open(QIODevice.ReadOnly | QIODevice.Text):
            print("Unable to read style file from", style_path)

        doc = QDomDocument()
        doc.setContent(file)
        file.close()
        doc_elem = doc.documentElement()

        nodes = doc_elem.elementsByTagName("renderer-v2")
        if nodes.count():
            renderer_elem = nodes.at(0).toElement()
            renderer = QgsFeatureRenderer.load(renderer_elem, QgsReadWriteContext())

        nodes = doc_elem.elementsByTagName("labeling")
        if nodes.count():
            labeling_elem = nodes.at(0).toElement()
            labeling = QgsAbstractVectorLayerLabeling.create(labeling_elem, QgsReadWriteContext())

        return (renderer, labeling)
