# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              Asistente LADM_COL
                                 Piloto UAECD
                             --------------------
        begin                : 2017-12-18
        git sha              : :%H$
        copyright            : (C) 2017, 2018 by Germán Carrillo (BSF Swissphoto)
                               (C) 2017, 2018 by Jonathan Albarracín (UAECD)
        email                : gcarrillo@linuxmail.org
                               jonyfido@gmail.com
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
import datetime
import qgis
import processing

from qgis.core import (
    QgsVectorLayerUtils,
    QgsField,
    QgsProcessingFeedback,
    Qgis,
    QgsApplication
)
from qgis.PyQt.QtCore import QVariant

from asistente_ladm_col.utils.qgis_utils import QGISUtils

INPUT_DB_PATH = '/docs/tr/ai/insumos/uaecd/Capas_Sector_Piloto/GDB_Piloto.gpkg'
INPUT_DB_PATH_CARTO_REF = '/docs/tr/ai/insumos/uaecd/Capas_Sector_Piloto/GDB_Carto_REF.gpkg'
REFACTORED_DB_PATH = '/docs/tr/ai/productos/uaecd/resultados_intermedios/refactored_{}.gpkg'.format(datetime.datetime.now().strftime("%y%m%d_%H%M%S"))

# PostgreSQL connection to schema with a LADM_COL model
OUTPUT_DB_NAME = 'test'
OUTPUT_DB_SCHEMA = 'uaecd_ladm_col_09'
OUTPUT_DB_USER = 'postgres'
OUTPUT_DB_PASSWORD = 'postgres'

log = QgsApplication.messageLog()
log_group_name = 'Script ETL UAECD'

# Asistente-LADM_COL plugin is a prerrequisite
asistente_ladm_col = QGISUtils()
log.logMessage("Using Refactored DB {}".format(REFACTORED_DB_PATH), log_group_name, Qgis.Info)

def refactor_and_copy_paste(params_refactor, input_uri, output_layer_name):
    """
    Run refactor field algorithm with the given mapping and appends the output
    features to output_layer
    """
    feedback = QgsProcessingFeedback()
    res = processing.run("qgis:refactorfields", params_refactor, feedback=feedback)

    input_layer = None
    if input_uri == 'memory':
        input_layer = res['OUTPUT']
    else:
        input_layer = QgsVectorLayer(input_uri, "r_input_layer", "ogr")

    if input_layer is None or not input_layer.isValid():
        log.logMessage("Layer '{}' is not valid! Stopping...".format(input_uri), log_group_name, Qgis.Critical)
        return

    output_layer = get_ladm_col_layer(output_layer_name)
    if not output_layer.isValid():
        log.logMessage("Layer {} is not valid! Stopping...".format(output_layer.name()), log_group_name, Qgis.Critical)
        return

    # Append refactored features to output_layer
    copy_paste_features(input_layer, output_layer)

def copy_paste_features(input_layer, output_layer):
    # Define a mapping between input and target layer
    input_layer.selectAll()
    iface.copySelectionToClipboard(input_layer)
    output_layer.startEditing()
    iface.pasteFromClipboard(output_layer)
    output_layer.commitChanges()
    log.logMessage("INFO: {} features successfully copied to layer {}!".format(input_layer.featureCount(), output_layer.name()), log_group_name, Qgis.Info)

    # mapping = dict()
    # for target_idx in output_layer.fields().allAttributesList():
    #     target_field = output_layer.fields().field(target_idx)
    #     input_idx = input_layer.fields().indexOf(target_field.name())
    #     if input_idx != -1 and target_field.name() != 't_id':
    #         mapping[target_idx] = input_idx
    #
    # # Copy and Paste
    # new_features = []
    # for in_feature in input_layer.getFeatures():
    #     attrs = {target_idx: in_feature[input_idx] for target_idx, input_idx in mapping.items()}
    #     new_feature = QgsVectorLayerUtils().createFeature(output_layer, in_feature.geometry(), attrs)
    #     new_features.append(new_feature)
    #
    # res, foo = output_layer.dataProvider().addFeatures(new_features)
    # if res:
    #     print("INFO: {} features successfully copied to layer {}!".format(len(new_features), output_layer.name()))
    # else:
    #     print("ERROR: Error copying {} features from {} to {}!!!".format(len(new_features), input_layer.name(), output_layer.name()))
    #     print("       Field mapping: {}".format(mapping))
    #     print("       Input layer info:")
    #     print("           Is valid: {}".format(input_layer.isValid()))
    #     print("           Num Feat: {}".format(input_layer.featureCount()))
    #     print("           Source: {}".format(input_layer.source()))
    #     print("       Output layer info:")
    #     print("           Is valid: {}".format(output_layer.isValid()))
    #     print("           Num Feat: {}".format(output_layer.featureCount()))
    #     print("           Source: {}".format(output_layer.source()))

def get_ladm_col_layer(layer_name):
    """
    Get a layer from the LADM_COL database by name
    """
    db = asistente_ladm_col.get_db_connection()
    output_uri = db.get_uri_for_layer(layer_name)[1]
    return QgsVectorLayer(output_uri, layer_name, "postgres")

def fix_geometries(layer_name, input_db_path=INPUT_DB_PATH):
    params = {
        'INPUT' : '{input_db_path}|layername={layer_name}'.format(input_db_path=input_db_path, layer_name=layer_name),
        'OUTPUT' : 'ogr:dbname=\'{input_db_path}\' table="{layer_name}_fixed" (geom) sql='.format(input_db_path=input_db_path, layer_name=layer_name)
    }
    feedback = QgsProcessingFeedback()
    processing.run("native:fixgeometries", params, feedback=feedback)
    log.logMessage("Geometries from layer {} successfully fixed!".format(layer_name), log_group_name, Qgis.Info)

def initialize_connection():
    dict_conn = dict()
    dict_conn['host'] = 'localhost'
    dict_conn['port'] = '5432'
    dict_conn['database'] = OUTPUT_DB_NAME
    dict_conn['schema'] = OUTPUT_DB_SCHEMA
    dict_conn['user'] = OUTPUT_DB_USER
    dict_conn['password'] = OUTPUT_DB_PASSWORD
    asistente_ladm_col.set_db_connection('pg', dict_conn)

def llenar_punto_lindero():
    params_refactor_punto_lindero = {
        'FIELDS_MAPPING' : [
            {'length': -1, 'precision': 0, 'expression': '"t_id"', 'name': 't_id', 'type': 4},
            {'length': 255, 'precision': -1, 'expression': "'Acuerdo'", 'name': 'acuerdo', 'type': 10},
            {'length': 255, 'precision': -1, 'expression': "'Bien_Definido'", 'name': 'definicion_punto', 'type': 10},
            {'length': 255, 'precision': -1, 'expression': '"descripcion_punto"', 'name': 'descripcion_punto', 'type': 10},
            {'length': -1, 'precision': 0, 'expression': '"exactitud_vertical"', 'name': 'exactitud_vertical', 'type': 2},
            {'length': -1, 'precision': 0, 'expression': '12', 'name': 'exactitud_horizontal', 'type': 2},
            {'length': -1, 'precision': -1, 'expression': '"confiabilidad"', 'name': 'confiabilidad', 'type': 1},
            {'length': 10, 'precision': -1, 'expression': '"nombre_punto"', 'name': 'nombre_punto', 'type': 10},
            {'length': 255, 'precision': -1, 'expression': '"posicion_interpolacion"', 'name': 'posicion_interpolacion', 'type': 10},
            {'length': 255, 'precision': -1, 'expression': "'Otros'", 'name': 'monumentacion', 'type': 10},
            {'length': 255, 'precision': -1, 'expression': "'Catastro'", 'name': 'puntotipo', 'type': 10},
            {'length': 255, 'precision': -1, 'expression': "'UAECD_Punto_Lindero'", 'name': 'p_espacio_de_nombres', 'type': 10},
            {'length': 255, 'precision': -1, 'expression': '"fid"', 'name': 'p_local_id', 'type': 10},
            {'length': -1, 'precision': 0, 'expression': '"ue_la_unidadespacial"', 'name': 'ue_la_unidadespacial', 'type': 4},
            {'length': -1, 'precision': 0, 'expression': '"ue_terreno"', 'name': 'ue_terreno', 'type': 4},
            {'length': -1, 'precision': 0, 'expression': '"ue_la_espaciojuridicoredservicios"', 'name': 'ue_la_espaciojuridicoredservicios', 'type': 4},
            {'length': -1, 'precision': 0, 'expression': '"ue_la_espaciojuridicounidadedificacion"', 'name': 'ue_la_espaciojuridicounidadedificacion', 'type': 4},
            {'length': -1, 'precision': 0, 'expression': '"ue_servidumbrepaso"', 'name': 'ue_servidumbrepaso', 'type': 4},
            {'length': -1, 'precision': 0, 'expression': '"ue_unidadconstruccion"', 'name': 'ue_unidadconstruccion', 'type': 4},
            {'length': -1, 'precision': 0, 'expression': '"ue_construccion"', 'name': 'ue_construccion', 'type': 4},
            {'length': -1, 'precision': -1, 'expression': 'now()', 'name': 'comienzo_vida_util_version', 'type': 16},
            {'length': -1, 'precision': -1, 'expression': '"fin_vida_util_version"', 'name': 'fin_vida_util_version', 'type': 16}
        ],
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_punto_lindero" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH),
        'INPUT' : '{input_db_path}|layername=Vertices_Lot'.format(input_db_path=INPUT_DB_PATH)
    }

    input_uri = '{refactored_db_path}|layername=R_punto_lindero'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_punto_lindero, input_uri, "puntolindero")

def llenar_lindero():
    # Lindero
    params_refactor_lindero = {
        'INPUT' : '{input_db_path}|layername=PLot'.format(input_db_path=INPUT_DB_PATH),
        'FIELDS_MAPPING' : [
            {'name': 't_id', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"t_id"'},
            {'name': 'longitud', 'type': 6, 'length': 6, 'precision': 1, 'expression': '"PELDISTANC"'},
            {'name': 'localizacion_textual', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"localizacion_textual"'},
            {'name': 'ccl_espacio_de_nombres', 'type': 10, 'length': 255, 'precision': -1, 'expression': "'UAECD_Lindero'"},
            {'name': 'ccl_local_id', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"fid"'},
            {'name': 'comienzo_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': 'now()'},
            {'name': 'fin_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': '"fin_vida_util_version"'}
        ],
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_lindero" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH)
    }

    input_uri = '{refactored_db_path}|layername=R_lindero'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_lindero, input_uri, "lindero")

def llenar_terreno():
    # Terreno
    params_refactor_terreno = {
        'INPUT' : '{input_db_path}|layername=Lote_fixed'.format(input_db_path=INPUT_DB_PATH),
        'FIELDS_MAPPING' : [
            {'name': 't_id', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"t_id"'},
            {'name': 'area_registral', 'type': 6, 'length': 15, 'precision': 1, 'expression': '"AREA_TERRENO"'},
            {'name': 'area_calculada', 'type': 6, 'length': 15, 'precision': 1, 'expression': '"SHAPE_Area"'},
            {'name': 'avaluo_terreno', 'type': 6, 'length': 13, 'precision': 1, 'expression': '"AV_TERRENO"'},
            {'name': 'dimension', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"dimension"'},
            {'name': 'etiqueta', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"etiqueta"'},
            {'name': 'relacion_superficie', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"relacion_superficie"'},
            {'name': 'su_espacio_de_nombres', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"u_nombres"'},
            {'name': 'su_local_id', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"Cod_LOTE"'},
            {'name': 'nivel', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"nivel"'},
            {'name': 'uej2_la_unidadespacial', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_la_unidadespacial"'},
            {'name': 'uej2_servidumbrepaso', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_servidumbrepaso"'},
            {'name': 'uej2_terreno', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_terreno"'},
            {'name': 'uej2_la_espaciojuridicoredservicios', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_la_espaciojuridicoredservicios"'},
            {'name': 'uej2_la_espaciojuridicounidadedificacion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_la_espaciojuridicounidadedificacion"'},
            {'name': 'uej2_construccion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_construccion"'},
            {'name': 'uej2_unidadconstruccion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_unidadconstruccion"'},
            {'name': 'comienzo_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': 'now()'},
            {'name': 'fin_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': '"fin_vida_util_version"'},
            {'name': 'punto_referencia', 'type': 10, 'length': -1, 'precision': -1, 'expression': '"punto_referencia"'}
        ],
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_terreno" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH)
    }

    input_uri = '{refactored_db_path}|layername=R_terreno'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_terreno, input_uri, "terreno")

def llenar_tablas_de_topologia():
    # PuntoCCL, MasCCL, Menos
    db = asistente_ladm_col.get_db_connection()
    asistente_ladm_col.fill_topology_table_pointbfs(db, use_selection=False)
    asistente_ladm_col.fill_topology_tables_morebfs_less(db, use_selection=False)

def llenar_predio():
    # Predio
    params_refactor_predio = {
        'INPUT' : '{input_db_path}|layername=Pred_Identificador'.format(input_db_path=INPUT_DB_PATH),
        'FIELDS_MAPPING' : [
            {'name': 't_id', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"t_id"'},
            {'name': 'departamento', 'type': 10, 'length': 2, 'precision': -1, 'expression': "'11'"},
            {'name': 'municipio', 'type': 10, 'length': 3, 'precision': -1, 'expression': "'001'"},
            {'name': 'zona', 'type': 10, 'length': 2, 'precision': -1, 'expression': "'01'"},
            {'name': 'nupre', 'type': 10, 'length': 20, 'precision': -1, 'expression': '"CHIP"'},
            {'name': 'fmi', 'type': 10, 'length': 20, 'precision': -1, 'expression': '"MATRICULA"'},
            {'name': 'numero_predial', 'type': 10, 'length': 30, 'precision': -1, 'expression': '"NUMERO_PREDIAL_NAL"'},
            {'name': 'numero_predial_anterior', 'type': 10, 'length': 20, 'precision': -1, 'expression': '"numero_predial_anterior"'},
            {'name': 'avaluo_predio', 'type': 6, 'length': 13, 'precision': 1, 'expression': '"VALOR_AVALUO"'},
            {'name': 'nombre', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"DIRECCION_REAL"'},
            {'name': 'tipo', 'type': 10, 'length': 255, 'precision': -1, 'expression': "'Unidad_Propiedad_Basica'"},
            {'name': 'u_espacio_de_nombres', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"u_nombres"'},
            {'name': 'u_local_id', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"CHIP"'},
            {'name': 'comienzo_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': 'now()'},
            {'name': 'fin_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': '"fin_vida_util_version"'}
        ],
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_predio" sql='.format(refactored_db_path=REFACTORED_DB_PATH)
    }

    input_uri = '{refactored_db_path}|layername=R_predio'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_predio, input_uri, "predio")

def llenar_uebaunit_terreno_predio():
    # Relación Terreno-Predio (Necesita una tabla fuente de paso, en la UAECD tienen CHIP vs. COD LOTE)

    # Predio: dict = {CHIP : t_id}
    layer_predio = get_ladm_col_layer("predio")
    it_predio = layer_predio.getFeatures()
    dict_predio = {feat_predio['nupre']: feat_predio['t_id'] for feat_predio in it_predio}

    # Terreno: dict = {COD_LOTE : t_id}
    layer_terreno = get_ladm_col_layer("terreno")
    it_terreno = layer_terreno.getFeatures()
    dict_terreno = {feat_terreno['su_local_id']: feat_terreno['t_id'] for feat_terreno in it_terreno}

    # Get uebaunit
    table_uebaunit = get_ladm_col_layer("uebaunit")
    rows = list()

    # Iterar tabla fuente de paso buscando CHIP y COD_LOTE en dicts Predio y Terreno
    uri_association_table = '{}|layername={}'.format(INPUT_DB_PATH, 'Pred_Identificador')
    terreno_predio = QgsVectorLayer(uri_association_table, 'terreno_predio', 'ogr')

    for f in terreno_predio.getFeatures():
        cod_lote = f['Cod_LOTE']
        chip = f['CHIP']
        new_row = QgsVectorLayerUtils().createFeature(table_uebaunit)

        if cod_lote in dict_terreno and chip in dict_predio:
            new_row.setAttribute("ue_terreno", dict_terreno[cod_lote])
            new_row.setAttribute("baunit_predio", dict_predio[chip])
            rows.append(new_row)
        else:
            log.logMessage("COD_LOTE-CHIP NOT FOUND in llenar_uebaunit {}-{}".format(cod_lote, chip), log_group_name, Qgis.Warning)

    # Llenar uebaunit
    log.logMessage("{} rows added to uebaunit!!!".format(len(rows)), log_group_name, Qgis.Info)
    table_uebaunit.dataProvider().addFeatures(rows)

def llenar_construccion(layer_name):
    # Construccion
    params_refactor_construccion = {
        'INPUT' : '{input_db_path}|layername={input_layer_name}'.format(input_db_path=INPUT_DB_PATH, input_layer_name=layer_name),
        'FIELDS_MAPPING' : [
            {'name': 't_id', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"t_id"'},
            {'name': 'avaluo_construccion', 'type': 6, 'length': 13, 'precision': 1, 'expression': '"AVTotal_CONSTRUC"'},
            {'name': 'tipo', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"tipo"'},
            {'name': 'dimension', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"dimension"'},
            {'name': 'etiqueta', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"etiqueta"'},
            {'name': 'relacion_superficie', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"relacion_superficie"'},
            {'name': 'su_espacio_de_nombres', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"u_nombres"'},
            {'name': 'su_local_id', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"Cod_LOTE"'},
            {'name': 'nivel', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"nivel"'},
            {'name': 'uej2_la_unidadespacial', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_la_unidadespacial"'},
            {'name': 'uej2_servidumbrepaso', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_servidumbrepaso"'},
            {'name': 'uej2_terreno', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_terreno"'},
            {'name': 'uej2_la_espaciojuridicoredservicios', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_la_espaciojuridicoredservicios"'},
            {'name': 'uej2_la_espaciojuridicounidadedificacion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_la_espaciojuridicounidadedificacion"'},
            {'name': 'uej2_construccion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_construccion"'},
            {'name': 'uej2_unidadconstruccion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_unidadconstruccion"'},
            {'name': 'comienzo_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': 'now()'},
            {'name': 'fin_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': '"fin_vida_util_version"'},
            {'name': 'punto_referencia', 'type': 10, 'length': -1, 'precision': -1, 'expression': '"punto_referencia"'}
        ],
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_construccion" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH)
    }

    input_uri = '{refactored_db_path}|layername=R_construccion'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_construccion, input_uri, "construccion")

def llenar_uebaunit_construccion_predio():
    # Relación Construccion-Predio (Necesitaría una tabla fuente de paso, pero
    # tenemos relación Construcción-Terreno (local_ids) y ya hemos relacionado
    # Terreno-Predio)

    # Construccion dict: {COD_LOTE : t_id}
    layer_construccion = get_ladm_col_layer("construccion")
    dict_construccion = {feat_construccion['su_local_id']: feat_construccion['t_id'] for feat_construccion in layer_construccion.getFeatures()}

    # Terreno: dict = {COD_LOTE : {'t_id':t_id, 'ns':su_espacio_de_nombres}
    layer_terreno = get_ladm_col_layer("terreno")
    dict_terreno = {feat_terreno['su_local_id']: {'t_id':feat_terreno['t_id'], 'ns':feat_terreno['su_espacio_de_nombres']} for feat_terreno in layer_terreno.getFeatures()}

    # Get Predio
    table_predio = get_ladm_col_layer("predio")

    # Get uebaunit
    table_uebaunit = get_ladm_col_layer("uebaunit")
    rows = list()

    # Iterar sobre construcciones buscando el t_id de terreno correspondiente
    # y luego de uebanit extraer el t_id de predio
    for cod_lote, cons_t_id in dict_construccion.items():
        if cod_lote in dict_terreno:
            terreno_t_id = dict_terreno[cod_lote]['t_id']
            terreno_ns = dict_terreno[cod_lote]['ns']
            it_table_uebaunit = table_uebaunit.getFeatures("\"ue_terreno\" = '{}'".format(terreno_t_id))

            for f_table_uebaunit in it_table_uebaunit:
                if terreno_ns == 'UAECD_Terreno_MJ_Matriz':
                    # Estamos en MJ, debemos omitir de las parejas cons-predio
                    # la que le corresponde al terreno. Sabemos cuál omitir
                    # porque está marcado en la tabla predio.
                    it_table_predio = table_predio.getFeatures("\"t_id\" = '{}'".format(f_table_uebaunit['baunit_predio']))
                    f_table_predio = QgsFeature()
                    it_table_predio.nextFeature(f_table_predio)

                    if f_table_predio.isValid():
                        if f_table_predio['u_espacio_de_nombres'] == 'UAECD_Predio_MJ_Matriz':
                            # Llegamos al predio relacionado con terreno y no con
                            # construcción, este lo omitimos en la relación
                            continue

                new_row = QgsVectorLayerUtils().createFeature(table_uebaunit)
                new_row.setAttribute('ue_construccion', cons_t_id)
                new_row.setAttribute('baunit_predio', f_table_uebaunit['baunit_predio'])
                rows.append(new_row)
        else:
            log.logMessage("COD_LOTE NOT FOUND in llenar_uebaunit_construccion_predio: {}".format(cod_lote), log_group_name, Qgis.Warning)

    # Llenar uebaunit
    table_uebaunit.dataProvider().addFeatures(rows)
    log.logMessage("{} rows (construccion-predio) added to uebaunit!!!".format(len(rows)), log_group_name, Qgis.Info)

def llenar_unidad_construccion(tipo='nph'):
    # Cada tipo de predio en la UAECD tiene su particularidad, entonces se
    # divide por casos (PH, NPH y Mejora)
    if tipo == 'nph':
        layer_name = 'Und_Cons_NPH_fixed'
        refactored_layer = 'R_unidadconstruccion_nph'
    elif tipo == 'ph':
        layer_name = 'Und_Cons_PH'
        refactored_layer = 'R_unidadconstruccion_ph'
    elif tipo == 'mj':
        layer_name = 'Und_Cons_MJ'
        refactored_layer = 'R_unidadconstruccion_mj'

    params_refactor_unidad_construccion = {
        'INPUT' : '{input_db_path}|layername={layer_name}'.format(input_db_path=INPUT_DB_PATH, layer_name=layer_name),
        'FIELDS_MAPPING' : [
            {'name': 't_id', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"t_id"'},
            {'name': 'avaluo_unidad_construccion', 'type': 6, 'length': 15, 'precision': 1, 'expression': '"AV_Und_CONS"'},
            {'name': 'numero_pisos', 'type': 2, 'length': -1, 'precision': 0, 'expression': '"MAX_CONELEVACI"'},
            {'name': 'tipo_construccion', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"tipo_construccion"'},
            {'name': 'area_construida', 'type': 6, 'length': 15, 'precision': 1, 'expression': '"Area_UND_CONS"'},
            {'name': 'area_privada_construida', 'type': 6, 'length': 15, 'precision': 1, 'expression': '"area_privada_construida"'},
            {'name': 'construccion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"Cod_CONS"'}, # This value will be updated in the next step...
            {'name': 'tipo', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"tipo"'},
            {'name': 'dimension', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"dimension"'},
            {'name': 'etiqueta', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"etiqueta"'},
            {'name': 'relacion_superficie', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"relacion_superficie"'},
            {'name': 'su_espacio_de_nombres', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"u_nombres"'},
            {'name': 'su_local_id', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"Cod_CONS"'},
            {'name': 'nivel', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"nivel"'},
            {'name': 'uej2_la_unidadespacial', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_la_unidadespacial"'},
            {'name': 'uej2_servidumbrepaso', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_servidumbrepaso"'},
            {'name': 'uej2_terreno', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_terreno"'},
            {'name': 'uej2_la_espaciojuridicoredservicios', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_la_espaciojuridicoredservicios"'},
            {'name': 'uej2_la_espaciojuridicounidadedificacion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_la_espaciojuridicounidadedificacion"'},
            {'name': 'uej2_construccion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_construccion"'},
            {'name': 'uej2_unidadconstruccion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"uej2_unidadconstruccion"'},
            {'name': 'comienzo_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': 'now()'},
            {'name': 'fin_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': '"fin_vida_util_version"'},
            {'name': 'punto_referencia', 'type': 10, 'length': -1, 'precision': -1, 'expression': '"punto_referencia"'}
        ],
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="{refactored_layer}" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH, refactored_layer=refactored_layer)
    }

    feedback = QgsProcessingFeedback()
    processing.run("qgis:refactorfields", params_refactor_unidad_construccion, feedback=feedback)
    input_uri = '{refactored_db_path}|layername={refactored_layer}'.format(refactored_db_path=REFACTORED_DB_PATH, refactored_layer=refactored_layer)
    input_layer = QgsVectorLayer(input_uri, "r_input_layer", "ogr")

    layer_construccion = get_ladm_col_layer("construccion")
    output_unidad_construccion = get_ladm_col_layer("unidadconstruccion")

    # Llenar relacion unidad_construccion - construccion en capa refactored
    features_unidad_construccion = [f for f in input_layer.getFeatures()]
    attrMap = {}
    idx_construccion = input_layer.fields().indexFromName('construccion')

    for f in features_unidad_construccion:
        it_construccion = layer_construccion.getFeatures('"su_local_id"=\'{}\''.format(f['su_local_id'][:12]))
        f_construccion = QgsFeature()
        it_construccion.nextFeature(f_construccion)

        if f_construccion.isValid():
            attrs = {idx_construccion: f_construccion['t_id']}
            attrMap[f.id()] = attrs
        else:
            log.logMessage("Construccion not found in llenar_unidad_construccion: {}".format(f['su_local_id']), log_group_name, Qgis.Info)

    input_layer.dataProvider().changeAttributeValues(attrMap)
    input_layer.reload()

    # Finalmente, copiar refactored en capa unidad construccion
    copy_paste_features(input_layer, output_unidad_construccion)

def llenar_uebaunit_unidad_construccion_predio(tipo='nph'):
    # Relación Unidad_construccion-Predio
    # En la tabla insumo tenemos la pareja Cod_CONS-CHIP, por medio de ella
    # llegamos a t_id unidadconstrucción y t_id predio

    # Unidadconstruccion dict: {COD_CONS : t_id}
    layer_unidadconstruccion = get_ladm_col_layer("unidadconstruccion")
    dict_unidadconstruccion = {feat_unidadconstruccion['su_local_id']: feat_unidadconstruccion['t_id'] for feat_unidadconstruccion in layer_unidadconstruccion.getFeatures()}

    # Und_Cons: dict = {COD_Cons : CHIP}
    if tipo == 'nph':
        layer_name = 'Und_Cons_NPH_fixed'
    elif tipo == 'ph':
        # Como para PH se generó un polígono consolidado para UndCons, no podemos
        # usar la tabla UndCons_PH (109 registros) sino tenemos que usar
        # Pred_Identificador que tiene la relación de cada unidad con su predio
        # 6645 registros de PH. En otras palabras, MJ y NPH tienen 1:1 con predio,
        # pero PH 1:M, por haber consolidado las unidades de cons en una sola.
        layer_name = 'Pred_Identificador'
    elif tipo == 'mj':
        layer_name = 'Und_Cons_MJ'

    source_layer_uri = '{input_db_path}|layername={layer_name}'.format(input_db_path=INPUT_DB_PATH, layer_name=layer_name)
    source_layer = QgsVectorLayer(source_layer_uri, "r_input_layer", "ogr")
    dict_source = dict()
    if tipo == 'ph': # 1:M
        for feat_source in source_layer.getFeatures("\"u_nombres\" = 'UAECD_Predio_PH'"):
            if feat_source['Cod_LOTE'] not in dict_source:
                dict_source[feat_source['Cod_LOTE']] = [feat_source['CHIP']]
            else:
                dict_source[feat_source['Cod_LOTE']].append(feat_source['CHIP'])
    else: # 1:1
        dict_source = {feat_source['Cod_CONS']: feat_source['CHIP'] for feat_source in source_layer.getFeatures()}

    # Predio:
    table_predio = get_ladm_col_layer("predio")

    # Get uebaunit
    table_uebaunit = get_ladm_col_layer("uebaunit")
    rows = list()

    # Iterar sobre unidades de construcciones buscando llegar a predio vía el GPKG de origen
    for cod_cons, und_cons_t_id in dict_unidadconstruccion.items():
        if tipo == 'ph':
            cod_cons = cod_cons[:12] # Solo necesitamos Cod_LOTE para PH

        if cod_cons in dict_source:
            source_chips = dict_source[cod_cons]
            if type(source_chips) != list: # Make MJ y NPH chips a list of 1 element
                source_chips = [source_chips]

            for source_chip in source_chips:
                it_table_predio = table_predio.getFeatures("\"nupre\" = '{}'".format(source_chip))
                f_table_predio = QgsFeature()
                it_table_predio.nextFeature(f_table_predio)

                if f_table_predio.isValid():
                    new_row = QgsVectorLayerUtils().createFeature(table_uebaunit)
                    new_row.setAttribute('ue_unidadconstruccion', und_cons_t_id)
                    new_row.setAttribute('baunit_predio', f_table_predio['t_id'])
                    rows.append(new_row)
        else:
            #print("WARNING: COD_CONS NOT FOUND in llenar_uebaunit_unidad_construccion_predio:", cod_cons)
            pass # Muchos mensajes...

    # Llenar uebaunit
    table_uebaunit.dataProvider().addFeatures(rows)
    log.logMessage("{} rows (unidadconstruccion-predio) added to uebaunit!!!".format(len(rows)), log_group_name, Qgis.Info)

def llenar_interesado_natural():
    # Interesado Natural
    params_refactor_interesado_natural = {
        'INPUT' : '{input_db_path}|layername=Interesado_Natural'.format(input_db_path=INPUT_DB_PATH),
        'FIELDS_MAPPING' : [
            {'name': 't_id', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"t_id"'},
            {'name': 'documento_identidad', 'type': 10, 'length': 10, 'precision': -1, 'expression': '"documento_identidad"'},
            {'name': 'tipo_documento', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"tipo_documento"'},
            {'name': 'organo_emisor', 'type': 10, 'length': 20, 'precision': -1, 'expression': '"organo_emisor"'},
            {'name': 'fecha_emision', 'type': 14, 'length': -1, 'precision': -1, 'expression': '"fecha_emision"'},
            {'name': 'primer_apellido', 'type': 10, 'length': 50, 'precision': -1, 'expression': '"primer_apellido"'},
            {'name': 'primer_nombre', 'type': 10, 'length': 50, 'precision': -1, 'expression': '"primer_nombre"'},
            {'name': 'segundo_apellido', 'type': 10, 'length': 50, 'precision': -1, 'expression': '"segundo_apellido"'},
            {'name': 'segundo_nombre', 'type': 10, 'length': 50, 'precision': -1, 'expression': '"segundo_nombre"'},
            {'name': 'genero', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"genero"'},
            {'name': 'nombre', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"nombre"'},
            {'name': 'tipo', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"TIPO_interesado"'},
            {'name': 'p_espacio_de_nombres', 'type': 10, 'length': 255, 'precision': -1, 'expression': "'UAECD_Interesado_Natural'"},
            {'name': 'p_local_id', 'type': 10, 'length': 255, 'precision': -1, 'expression': '"OBJECTID"'},
            {'name': 'agrupacion', 'type': 4, 'length': -1, 'precision': 0, 'expression': '"agrupacion"'},
            {'name': 'comienzo_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': 'now()'},
            {'name': 'fin_vida_util_version', 'type': 16, 'length': -1, 'precision': -1, 'expression': '"fin_vida_util_version"'}
        ],
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_interesado_natural" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH)
    }

    input_uri_interesado_natural = '{refactored_db_path}|layername=R_interesado_natural'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_interesado_natural, input_uri_interesado_natural, "interesado_natural")

def llenar_interesado_juridico():
    # Interesado Juridico
    params_refactor_interesado_juridico = {
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_interesado_juridico" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH),
        'INPUT' : '{input_db_path}|layername=Interesado_Juridico'.format(input_db_path=INPUT_DB_PATH),
        'FIELDS_MAPPING' : [
            {'type': 4, 'precision': 0, 'name': 't_id', 'expression': '"t_id"', 'length': -1},
            {'type': 10, 'precision': -1, 'name': 'numero_nit', 'expression': '"numero_nit"', 'length': 20},
            {'type': 10, 'precision': -1, 'name': 'razon_social', 'expression': '"razon_social"', 'length': 100},
            {'type': 10, 'precision': -1, 'name': 'nombre', 'expression': '"nombre"', 'length': 255},
            {'type': 10, 'precision': -1, 'name': 'tipo', 'expression': '"TIPO"', 'length': 255},
            {'type': 10, 'precision': -1, 'name': 'p_espacio_de_nombres', 'expression': "'UAECD_Interesado_Juridico'", 'length': 255},
            {'type': 10, 'precision': -1, 'name': 'p_local_id', 'expression': '"OBJECTID"', 'length': 255},
            {'type': 16, 'precision': -1, 'name': 'comienzo_vida_util_version', 'expression': 'now()', 'length': -1},
            {'type': 16, 'precision': -1, 'name': 'fin_vida_util_version', 'expression': '"fin_vida_util_version"', 'length': -1}
        ]
    }

    input_uri_interesado_juridico = '{refactored_db_path}|layername=R_interesado_juridico'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_interesado_juridico, input_uri_interesado_juridico, "interesado_juridico")

def llenar_col_derecho(tipo='interesado_natural'):
    # Relación Interesado-Derecho (Necesita una tabla fuente de paso)

    # Predio: dict = {CHIP: t_id}
    layer_predio = get_ladm_col_layer("predio")
    it_predio = layer_predio.getFeatures()
    dict_predio = {feat_predio['nupre']: feat_predio['t_id'] for feat_predio in it_predio}

    # Interesado: dict = {numero_documento : t_id}
    if tipo == 'interesado_juridico':
        association_table_name = 'Maestra_Juridicos'
        ladm_attribute = "interesado_interesado_juridico"
        table_interesado = get_ladm_col_layer('interesado_juridico')
        it_interesado = table_interesado.getFeatures()
        dict_interesado = {feat_interesado['numero_nit']: feat_interesado['t_id'] for feat_interesado in it_interesado}
    else:
        association_table_name = 'Maestra_Naturales'
        ladm_attribute = "interesado_interesado_natural"
        table_interesado = get_ladm_col_layer('interesado_natural')
        it_interesado = table_interesado.getFeatures()
        dict_interesado = {feat_interesado['documento_identidad']: feat_interesado['t_id'] for feat_interesado in it_interesado}

    # Get col_derecho
    table_col_derecho = get_ladm_col_layer("col_derecho")
    asistente_ladm_col.configureAutomaticField(table_col_derecho, "comienzo_vida_util_version", "now()")
    espacio_de_nombres = 'UAECD_Col_Derecho_Natural' if tipo == 'interesado_natural' else 'UAECD_Col_Derecho_Juridico'
    asistente_ladm_col.configureAutomaticField(table_col_derecho, "r_espacio_de_nombres", "'{}'".format(espacio_de_nombres))
    rows = list()

    # Iterar tabla fuente de paso buscando CHIP y COD_LOTE en dicts Predio y Terreno
    uri_association_table = '{}|layername={}'.format(INPUT_DB_PATH, association_table_name)
    predio_interesado = QgsVectorLayer(uri_association_table, 'predio_interesado', 'ogr')

    for f in predio_interesado.getFeatures():
        numero_documento = str(int(f['documento_identidad']))
        chip = f['chip']
        col_derecho_tipo = f['Col_DerechoTipo']
        r_local_id = f['OBJECTID'] # We had to do this because an automatic field with @row_number didn't work
        new_row = QgsVectorLayerUtils().createFeature(table_col_derecho)

        if numero_documento in dict_interesado and chip in dict_predio:
            new_row.setAttribute(ladm_attribute, dict_interesado[numero_documento])
            new_row.setAttribute("unidad_predio", dict_predio[chip])
            new_row.setAttribute("tipo", col_derecho_tipo)
            new_row.setAttribute("r_local_id", r_local_id)
            rows.append(new_row)
        else:
            log.logMessage("NOT FOUND NUM_DOCUMENTO-CHIP in llenar_col_derecho {}-{}".format(numero_documento, chip), log_group_name, Qgis.Info)

    # Llenar col_derecho
    res = table_col_derecho.dataProvider().addFeatures(rows)
    if res[0]:
        log.logMessage("{} rows added to col_derecho!!!".format(len(rows)), log_group_name, Qgis.Info)
    else:
        log.logMessage("There was an error adding {} rows to col_derecho...".format(len(rows)), log_group_name, Qgis.Critical)

def llenar_fuente_administrativa(tipo='interesado_natural'):
    # Hay dos tablas 'maestras', una para int Jurídicos, otra para Naturales
    # Se usa el local_id para luego asociar la fuente al derecho
    # Como ese local_id no es único para Jurídicos y Naturales, se usa la
    # combinación con el namespace oara la identificación de cada registro
    namespace = 'UAECD_fuente_administrativa_juridico' if tipo == 'interesado_juridico' else 'UAECD_fuente_administrativa_natural'
    refactored_layer = 'R_col_fuente_administrativa_juridico' if tipo == 'interesado_juridico' else 'R_col_fuente_administrativa_natural'
    layer_name = "Maestra_Juridicos" if tipo == 'interesado_juridico' else 'Maestra_Naturales'

    params_refactor_fuente_administrativa = {
        'FIELDS_MAPPING' : [
            {'name': 't_id', 'precision': 0, 'expression': '"t_id"', 'type': 4, 'length': -1},
            {'name': 'texto', 'precision': -1, 'expression': '"texto"', 'type': 10, 'length': 255},
            {'name': 'tipo', 'precision': -1, 'expression': '"Col_FuenteAdministrativa"', 'type': 10, 'length': 255},
            {'name': 'codigo_registral_transaccion', 'precision': -1, 'expression': '"codigo_registral_transaccion"', 'type': 10, 'length': 3},
            {'name': 'fecha_aceptacion', 'precision': -1, 'expression': '"fecha_aceptacion"', 'type': 16, 'length': -1},
            {'name': 'estado_disponibilidad', 'precision': -1, 'expression': "'Disponible'", 'type': 10, 'length': 255},
            {'name': 'sello_inicio_validez', 'precision': -1, 'expression': '"sello_inicio_validez"', 'type': 16, 'length': -1},
            {'name': 'tipo_principal', 'precision': -1, 'expression': '"tipo_principal"', 'type': 10, 'length': 255},
            {'name': 'fecha_grabacion', 'precision': -1, 'expression': '"fecha_grabacion"', 'type': 16, 'length': -1},
            {'name': 'fecha_entrega', 'precision': -1, 'expression': '"fecha_entrega"', 'type': 16, 'length': -1},
            {'name': 's_espacio_de_nombres', 'precision': -1, 'expression': "'{namespace}'".format(namespace=namespace), 'type': 10, 'length': 255},
            {'name': 's_local_id', 'precision': -1, 'expression': '"OBJECTID"', 'type': 10, 'length': 255},
            {'name': 'oficialidad', 'precision': -1, 'expression': '"oficialidad"', 'type': 1, 'length': -1}
        ],
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="{refactored_layer}" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH, refactored_layer=refactored_layer),
        'INPUT' : '{input_db_path}|layername={layer_name}'.format(input_db_path=INPUT_DB_PATH, layer_name=layer_name)
    }

    input_uri_col_fte_adminis = '{refactored_db_path}|layername={refactored_layer}'.format(refactored_db_path=REFACTORED_DB_PATH, refactored_layer=refactored_layer)
    refactor_and_copy_paste(params_refactor_fuente_administrativa, input_uri_col_fte_adminis, "col_fuenteadministrativa")

def llenar_rrr_fuente():
    output_col_derecho = get_ladm_col_layer("col_derecho")
    output_col_fuente_administrativa = get_ladm_col_layer("col_fuenteadministrativa")
    output_rrr_fuente = get_ladm_col_layer("rrrfuente")

    features_col_derecho = [f for f in output_col_derecho.getFeatures()]
    features = []

    for f in features_col_derecho:
        # Match col_derecho and col_fuenteadministrativa by local_id - namespace
        namespace = 'UAECD_fuente_administrativa_juridico' if f['r_espacio_de_nombres'] == 'UAECD_Col_Derecho_Juridico' else 'UAECD_fuente_administrativa_natural'
        it_col_fuente_administrativa = output_col_fuente_administrativa.getFeatures('"s_local_id"=\'{}\' AND "s_espacio_de_nombres"=\'{}\''.format(f['r_local_id'], namespace))
        f_col_fuente_administrativa = QgsFeature()
        it_col_fuente_administrativa.nextFeature(f_col_fuente_administrativa)

        if f_col_fuente_administrativa.isValid():
            feature = QgsVectorLayerUtils().createFeature(output_rrr_fuente)
            feature.setAttribute('rrr_col_derecho', f['t_id'])
            feature.setAttribute('rfuente', f_col_fuente_administrativa['t_id'])
            features.append(feature)
        else:
            log.logMessage("Col_derecho local id not found in fuente administrativa in llenar_rrr_fuente {}-{}".format(f['r_local_id'], f['r_espacio_de_nombres']), log_group_name, Qgis.Warning)

    output_rrr_fuente.dataProvider().addFeatures(features)
    log.logMessage("{} features successfully added to rrr_fuente!".format(len(features)), log_group_name, Qgis.Info)


################################################################################
################################################################################
################################################################################

def llenar_avaluos__predio_matriz_ph():
    # First we need to add a temporal column to store COD_LOTE and be able to
    # do joins to fill avaluopredio
    output_predio_matriz_ph = get_ladm_col_layer("predio_matriz_ph")
    if output_predio_matriz_ph.dataProvider().fields().indexFromName('tmp_cod_lote') == -1:
        output_predio_matriz_ph.dataProvider().addAttributes([QgsField('tmp_cod_lote', QVariant.String)])

    output_predio_matriz_ph.reload()

    if output_predio_matriz_ph.dataProvider().fields().indexFromName('tmp_cod_lote') == -1:
        log.logMessage("FIELD tmp_cod_lote DOES NOT EXIST!!! Create it before running llenar_avaluos__predio_matriz_ph()...", log_group_name, Qgis.Critical)
        return

    params_refactor_predio_matriz_ph = {
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_predio_matriz_ph" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH),
        'FIELDS_MAPPING' : [
            {'type': 4, 'precision': 0, 'expression': '"t_id"', 'length': -1, 'name': 't_id'},
            {'type': 2, 'precision': 0, 'expression': 'IF ("ETAPA_NUMERO" = \'\', NULL, "ETAPA_NUMERO")', 'length': -1, 'name': 'num_etapas'},
            {'type': 2, 'precision': 0, 'expression': '"num_interiores"', 'length': -1, 'name': 'num_interiores'},
            {'type': 2, 'precision': 0, 'expression': '"num_torres"', 'length': -1, 'name': 'num_torres'},
            {'type': 2, 'precision': 0, 'expression': '"PISOS"', 'length': -1, 'name': 'num_pisos_por_torre'},
            {'type': 2, 'precision': 0, 'expression': '"NUMERO_UNIDADES"', 'length': -1, 'name': 'num_unidades_privadas'},
            {'type': 10, 'precision': -1, 'expression': '"tipologia_constructiva_copropiedad"', 'length': 20, 'name': 'tipologia_constructiva_copropiedad'},
            {'type': 14, 'precision': -1, 'expression': "concat('01-01-', anio_construccion)", 'length': -1, 'name': 'anio_construccion_etapa'},
            {'type': 10, 'precision': -1, 'expression': '"Estado_Conservacion_Copropiedad"', 'length': 255, 'name': 'estado_conservacion_copropiedad'},
            {'type': 10, 'precision': -1, 'expression': '"materiales_construccion_areas_comunes"', 'length': 100, 'name': 'materiales_construccion_areas_comunes'},
            {'type': 10, 'precision': -1, 'expression': '"disenio_funcionalidad_copropiedad"', 'length': 100, 'name': 'disenio_funcionalidad_copropiedad'},
            {'type': 10, 'precision': -1, 'expression': '"COD_LOTE"', 'length': -1, 'name': 'tmp_cod_lote'}
        ],
        'INPUT' : '{input_db_path}|layername=Predio_Matriz_PH'.format(input_db_path=INPUT_DB_PATH)
    }

    input_uri = '{refactored_db_path}|layername=R_predio_matriz_ph'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_predio_matriz_ph, input_uri, output_predio_matriz_ph.name())

def llenar_avaluos__predio():
    # First we need to add a temporal column to store NUPRE (CHIP) and be able
    # to do joins to fill avaluopredio
    output_predio = get_ladm_col_layer("avaluos_v2_2_1avaluos_predio")
    if output_predio.dataProvider().fields().indexFromName('tmp_chip') == -1:
        output_predio.dataProvider().addAttributes([QgsField('tmp_chip', QVariant.String)])

    output_predio.reload()

    if output_predio.dataProvider().fields().indexFromName('tmp_chip') == -1:
        log.logMessage("FIELD tmp_chip DOES NOT EXIST!!! Create it before running llenar_avaluos__predio()...", log_group_name, Qgis.Info)
        return

    # table_predio: Catastro_Registro.predio
    # table_source: Pred_Identificador, GPKG de la UAECD
    # table_target: Avaluos.predio (avaluos_v2_2_1avaluos_predio)
    # table_matriz_ph: Predio_Matriz_PH (requerida para relacionar predios PH a su matriz PH)
    table_predio = get_ladm_col_layer("predio")
    table_source = QgsVectorLayer('{input_db_path}|layername=Pred_Identificador'.format(input_db_path=INPUT_DB_PATH), "table_source", "ogr")
    table_target = get_ladm_col_layer("avaluos_v2_2_1avaluos_predio")
    table_predio = get_ladm_col_layer("predio_matriz_ph")

    features_predio = [f for f in table_predio.getFeatures()]
    features = []
    for f in features_predio:
        it_table_source = table_source.getFeatures("\"CHIP\" = '{}'".format(f['nupre']))
        f_table_source = QgsFeature()
        it_table_source.nextFeature(f_table_source)

        it_table_matriz_ph = table_matriz_ph.getFeatures("\"tmp_cod_lote\" = '{}'".format(f_table_source['Cod_LOTE']))
        f_table_matriz_ph = QgsFeature()
        it_table_matriz_ph.nextFeature(f_table_matriz_ph)

        if f_table_source.isValid():
            feature = QgsVectorLayerUtils().createFeature(table_target)
            feature.setAttribute('tmp_chip', f['nupre'])
            if f_table_matriz_ph.isValid(): # Not all predios are PH
                feature.setAttribute('avpredmatrizph', f_table_matriz_ph['t_id'])

            feature.setAttribute('area_calculada_plano_local', f_table_source['AREA_TERRENO'])
            feature.setAttribute('aprovechamiento', 'Aprov_Optimo')
            feature.setAttribute('disponibilidad_agua', 'A_Acueducto_Mpio')
            feature.setAttribute('obra_al_interior', 'No_Posee')
            feature.setAttribute('cercania_hitos', 'Cercano')
            feature.setAttribute('capa_vegetal', 'Sin_Cobert_Vegetal')
            feature.setAttribute('pendiente', 'Plano')
            feature.setAttribute('frente', f_table_source['FRENTE'])
            feature.setAttribute('fondo', f_table_source['FONDO'])
            features.append(feature)
        else:
           pass

    table_target.dataProvider().addFeatures(features)

def llenar_avaluos__avaluopredio():
    # Asociación entre avalúos.predio y catastro_registro.predio
    # Para ello se usa el campo temporal tmp_chip de la capa avaluos.predio

    # table_predio_cr: predio (Catastro-Registro)
    # table_predio_av: avaluos_predio (Avaluos)
    # table_target: tabla de paso 1:1 avaluopredio
    table_predio_cr = get_ladm_col_layer("predio")
    table_predio_av = get_ladm_col_layer("avaluos_v2_2_1avaluos_predio")
    table_target = get_ladm_col_layer("avaluopredio")

    features_predio_av = [f for f in table_predio_av.getFeatures()]
    features = []
    for f in features_predio_av:
        it_table_predio_cr = table_predio_cr.getFeatures("\"nupre\" = '{}'".format(f['tmp_chip']))
        f_table_predio_cr = QgsFeature()
        it_table_predio_cr.nextFeature(f_table_predio_cr)
        if f_table_predio_cr.isValid():
            feature = QgsVectorLayerUtils().createFeature(table_target)
            feature.setAttribute('apredio', f['t_id'])
            feature.setAttribute('predio', f_table_predio_cr['t_id'])

            features.append(feature)
        else:
           pass

    table_target.dataProvider().addFeatures(features)

def remover_campos_temporales_de_asociacion_avaluos():
    # En llenar_avaluos__predio_matriz_ph y llenar_avaluos__predio creamos
    # campos temporales para poder asociar datos. Aquí los removemos.
    predio_matriz_ph = get_ladm_col_layer("predio_matriz_ph")
    idx_tmp_field = predio_matriz_ph.dataProvider().fields().indexFromName('tmp_cod_lote')
    if idx_tmp_field != -1:
        predio_matriz_ph.dataProvider().deleteAttributes([idx_tmp_field])
        predio_matriz_ph.updateFields()

    avaluos_predio = get_ladm_col_layer("avaluos_v2_2_1avaluos_predio")
    idx_tmp_field = avaluos_predio.dataProvider().fields().indexFromName('tmp_chip')
    if idx_tmp_field != -1:
        avaluos_predio.dataProvider().deleteAttributes([idx_tmp_field])
        avaluos_predio.updateFields()

def llenar_avaluos__construccion(tipo='nph'):
    # layer_cr_construccion: Catastro_Registro.Construccion
    # table_source: GPKG Source (construccion)
    # table_target: Table in LADM where to paste features to (Avaluos_Construccion)
    layer_cr_construccion = get_ladm_col_layer("construccion")
    table_target = get_ladm_col_layer("avaluos_v2_2_1avaluos_construccion")

    if tipo == 'nph':
        source_uri = '{input_db_path}|layername=Construccion_NPH_fixed'.format(input_db_path=INPUT_DB_PATH)
    elif tipo == 'ph':
        source_uri = '{input_db_path}|layername=Construccion_PH'.format(input_db_path=INPUT_DB_PATH)
    elif tipo == 'mj':
        source_uri = '{input_db_path}|layername=Construccion_MJ'.format(input_db_path=INPUT_DB_PATH)

    table_source = QgsVectorLayer(source_uri, "table_source", "ogr")

    features_source = [f for f in table_source.getFeatures()]
    features = []
    for f in features_source:
        # Get corresponding feature in CR.Construccion
        it_cr_construccion = layer_cr_construccion.getFeatures("\"su_local_id\" = '{}'".format(f['Cod_LOTE']))
        f_cr_construccion = QgsFeature()
        it_cr_construccion.nextFeature(f_cr_construccion)

        if f_cr_construccion.isValid():
            feature = QgsVectorLayerUtils().createFeature(table_target)
            feature.setAttribute('cons', f_cr_construccion['t_id'])
            feature.setAttribute('numero_pisos', f['MAX_NUM_PISOS'])

            features.append(feature)
        else:
            log.logMessage("Cod_LOTE not found in CR.Construccion {}".format(f['Cod_LOTE']), log_group_name, Qgis.Warning)

    table_target.dataProvider().addFeatures(features)

def llenar_avaluos__unidad_construccion(tipo='nph'):
    # layer_cr_unidad_construccion: CR.unidadconstruccion
    # table_source: GPKG Layer Und_Cons_PH, MJ, NPH
    # table_target: Avaluos.unidad_construccion
    layer_cr_unidad_construccion = get_ladm_col_layer("unidadconstruccion")
    table_target = get_ladm_col_layer("unidad_construccion")

    if tipo == 'nph':
        source_uri = '{input_db_path}|layername=Und_Cons_NPH_fixed'.format(input_db_path=INPUT_DB_PATH)
    elif tipo == 'ph':
        source_uri = '{input_db_path}|layername=Und_Cons_PH'.format(input_db_path=INPUT_DB_PATH)
    elif tipo == 'mj':
        source_uri = '{input_db_path}|layername=Und_Cons_MJ'.format(input_db_path=INPUT_DB_PATH)

    table_source = QgsVectorLayer(source_uri, "table_source", "ogr")

    features_cr_unidad_construccion = [f for f in layer_cr_unidad_construccion.getFeatures()]
    features = []
    for f in features_cr_unidad_construccion:
        it_table_source = table_source.getFeatures("\"Cod_CONS\" = '{}'".format(f['su_local_id']))
        f_table_source = QgsFeature()
        it_table_source.nextFeature(f_table_source)

        if f_table_source.isValid():
            feature = QgsVectorLayerUtils().createFeature(table_target)
            feature.setAttribute('ucons', f['t_id'])
            feature.setAttribute('numero_total_pisos', f_table_source['MAX_NUM_PISOS'])
            feature.setAttribute('acceso', 'Escaleras_Electricas') # Should be optional!
            feature.setAttribute('nivel_de_acceso', f_table_source['nivel_acceso'])
            feature.setAttribute('actividad_econo', 'definirPilotos')
            feature.setAttribute('destino_econo', 'Definir_Operador')
            feature.setAttribute('estilo', 'Tradicional')
            feature.setAttribute('anio_construction', "'01-01-{}'".format(int(f_table_source['VETUSTEZ'])))
            feature.setAttribute('construction_tipo', 'Convencional')
            feature.setAttribute('estado_conservacion', f_table_source['ESTADO_CONSERVA'])
            feature.setAttribute('funcionalidad', f_table_source['funcionalidad'])
            feature.setAttribute('material', 'Definir_Pilotos')
            feature.setAttribute('puntuacion', f_table_source['PUNTAJE'])
            feature.setAttribute('tipologia', f_table_source['Tipologia'])
            features.append(feature)
        else:
           pass

    table_target.dataProvider().addFeatures(features)

def llenar_avaluos__calificacion_unidad_construccion():
    # layer_cr_unidad_construccion: Catastro_Registro.UnidadConstruccion
    # layer_av_unidad_construccion: Avaluos.Unidad_Construccion
    # table_source: GPKG Source Cal_Und_construccion
    # table_target: Table in LADM where to paste features to (Avaluos_Calificacion_Unidad_Construccion)
    layer_cr_unidad_construccion = get_ladm_col_layer("unidadconstruccion")
    layer_av_unidad_construccion = get_ladm_col_layer("unidad_construccion")
    table_source = QgsVectorLayer('{input_db_path}|layername=Cal_Und_construccion'.format(input_db_path=INPUT_DB_PATH), "table_source", "ogr")
    table_target = get_ladm_col_layer("calificacion_unidad_construccion")

    features_source = [f for f in table_source.getFeatures()]
    features = []
    for f in features_source:
        # Get corresponding feature in CR.UnidadConstruccion
        it_cr_unidad_construccion = layer_cr_unidad_construccion.getFeatures("\"su_local_id\" = '{}'".format(f['COD_CONS_MODIF']))
        f_cr_unidad_construccion = QgsFeature()
        it_cr_unidad_construccion.nextFeature(f_cr_unidad_construccion)
        if f_cr_unidad_construccion.isValid():

            # Get corresponding feature in Av.Unidad_Construccion
            it_av_unidad_construccion = layer_av_unidad_construccion.getFeatures("\"ucons\" = {}".format(f_cr_unidad_construccion['t_id']))
            f_av_unidad_construccion = QgsFeature()
            it_av_unidad_construccion.nextFeature(f_av_unidad_construccion)
            if f_av_unidad_construccion.isValid():
                feature = QgsVectorLayerUtils().createFeature(table_target)
                feature.setAttribute('fichapredio', f_av_unidad_construccion['t_id'])

                feature.setAttribute('tipo_calificar', f['USO_UC'])
                feature.setAttribute('armazon', f['Armazon_MD'])
                feature.setAttribute('puntos_armazon', f['puntos_armazon'] if f['puntos_armazon'] > 0 else None)  # Ranges not allowing 0!
                feature.setAttribute('muros', f['Muros_MD'])
                feature.setAttribute('puntos_muro', f['puntos_muro'] if f['puntos_muro'] > 0 else None)
                feature.setAttribute('cubierta', f['Cubierta_MD'])
                feature.setAttribute('puntos_cubierta', f['puntos_cubierta'] if f['puntos_muro'] > 0 else None)
                feature.setAttribute('conservacion_cubierta', f['Coserva_Cubierta_MD'])
                feature.setAttribute('puntos_cubierta_conservacion', f['puntos_cubierta_conservacion'] if f['puntos_cubierta_conservacion'] > 0 else None)
                feature.setAttribute('sub_total_estructura', f['sub_total_estructura'])
                feature.setAttribute('fachada', f['Fachada_MD'])
                feature.setAttribute('puntos_fachada', f['puntos_fachada'] if f['puntos_fachada'] > 0 else None)
                feature.setAttribute('cubrimiento_muros', f['Cubrimiento_Muros_MD'])
                feature.setAttribute('puntos_cubrimiento_muros', f['puntos_cubrimiento_muros'] if f['puntos_cubrimiento_muros'] > 0 else None)
                feature.setAttribute('piso', f['Pisos_MD'])
                feature.setAttribute('puntos_piso', f['puntos_piso'] if f['puntos_piso'] > 0 else None)
                feature.setAttribute('conservacion_acabados', f['Conserva_Acabados_MD'])
                feature.setAttribute('puntos_conservacion_acabados', f['puntos_conservacion_acabados'] if f['puntos_conservacion_acabados'] > 0 else None)
                feature.setAttribute('sub_total_acabados', f['sub_total_acabados'])
                feature.setAttribute('tamanio_banio', f['Tamano_Bano_MD'])
                feature.setAttribute('puntos_tamanio_banio', f['puntos_tamanio_banio'] if f['puntos_tamanio_banio'] > 0 else None)
                feature.setAttribute('enchape_banio', f['Enchape_Bano_MD'])
                feature.setAttribute('puntos_enchape_banio', f['puntos_enchape_banio'] if f['puntos_enchape_banio'] > 0 else None)
                feature.setAttribute('mobiliario_banio', f['Mobiliario_Bano_MD'])
                feature.setAttribute('puntos_mobiliario_banio', f['puntos_mobiliario_banio'] if f['puntos_mobiliario_banio'] > 0 else None)
                feature.setAttribute('conservacion_banio', f['Conserva_Bano_MD'])
                feature.setAttribute('puntos_conservacion_banio', f['puntos_conservacion_banio'] if f['puntos_conservacion_banio'] > 0 else None)
                feature.setAttribute('sub_total_banio', f['sub_total_banio'])
                feature.setAttribute('tamanio_cocina', f['Tamano_Cocina_MD'])
                feature.setAttribute('puntos_tamanio_cocina', f['puntos_tamanio_cocina'] if f['puntos_tamanio_cocina'] > 0 else None)
                feature.setAttribute('enchape_cocina', f['Enchape_Cocina_MD'])
                feature.setAttribute('puntos_enchape_cocina', f['puntos_enchape_cocina'] if f['puntos_enchape_cocina'] > 0 else None)
                feature.setAttribute('mobiliario_cocina', f['Mobiliario_Cocina_MD'])
                feature.setAttribute('puntos_mobiliario_cocina', f['puntos_mobiliario_cocina'] if f['puntos_mobiliario_cocina'] > 0 else None)
                feature.setAttribute('conservacion_cocina', f['Conserva_Cocina_MD'])
                feature.setAttribute('puntos_conservacion_cocina', f['puntos_conservacion_cocina'] if f['puntos_conservacion_cocina'] > 0 else None)
                feature.setAttribute('sub_total_cocina', f['sub_total_cocina'])
                feature.setAttribute('total_residencial_y_comercial', f['total_RyC'] if f['total_RyC'] > 0 else None)
                feature.setAttribute('cerchas', f['Comple_Industria_MD'])
                feature.setAttribute('puntos_cerchas', f['puntos_comple_industria'] if int(f['puntos_comple_industria'] or 0) > 0 else None)
                feature.setAttribute('total_industrial', f['total_industrial'] if f['total_industrial'] > 0 else None)

                features.append(feature)
            else:
                log.logMessage("Unidad de Construcción id not found in Av.Unidad_Construccion {}".format(f_cr_unidad_construccion['t_id']), log_group_name, Qgis.Warning)
        else:
            log.logMessage("COD_LOTE not found in CR.Unidad_Construccion: {}".format(f['COD_LOTE']), log_group_name, Qgis.Warning)

    table_target.dataProvider().addFeatures(features)

def llenar_avaluos__zhf():
    params_refactor_zhf = {
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_zhf" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH),
        'INPUT' : '{input_db_path}|layername=ZHF_009116_fixed'.format(input_db_path=INPUT_DB_PATH_CARTO_REF),
        'FIELDS_MAPPING' : [
            {'type': 4, 'name': 't_id', 'length': -1, 'precision': 0, 'expression': '"t_id"'},
            {'type': 10, 'name': 'identificador', 'length': 20, 'precision': -1, 'expression': '"ZHF_IDENTI"'}
        ]
    }

    input_uri = '{refactored_db_path}|layername=R_zhf'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_zhf, input_uri, "zona_homogenea_fisica")

def llenar_avaluos__zhg():
    params_refactor_zhg = {
        'OUTPUT' : 'ogr:dbname="{refactored_db_path}" table="R_zhg" (geom) sql='.format(refactored_db_path=REFACTORED_DB_PATH),
        'INPUT' : '{input_db_path}|layername=ZHG_009116'.format(input_db_path=INPUT_DB_PATH_CARTO_REF),
        'FIELDS_MAPPING' : [
            {'type': 4, 'name': 't_id', 'length': -1, 'precision': 0, 'expression': '"t_id"'},
            {'type': 10, 'name': 'identificador', 'length': 20, 'precision': -1, 'expression': '"ZHG_IDENTI"'},
            {'type': 2, 'name': 'valor', 'length': -1, 'precision': 0, 'expression': '"ZHGVM2TERR"'}
        ]
    }

    input_uri = '{refactored_db_path}|layername=R_zhg'.format(refactored_db_path=REFACTORED_DB_PATH)
    refactor_and_copy_paste(params_refactor_zhg, input_uri, "zona_homogenea_geoeconomica")


################################################################################
################################################################################
################################################################################

def llenar_ficha__predio_ficha():
    # First we need to add a temporal column to store CHIP and be able to
    # join predio and fill predioficha_predio
    predio_ficha = get_ladm_col_layer("predio_ficha")
    if predio_ficha.dataProvider().fields().indexFromName('tmp_chip') == -1:
        predio_ficha.dataProvider().addAttributes([QgsField('tmp_chip', QVariant.String)])

    predio_ficha.reload()

    if predio_ficha.dataProvider().fields().indexFromName('tmp_chip') == -1:
        log.logMessage("FIELD tmp_chip DOES NOT EXIST!!! Create it before running llenar_ficha__predio_ficha()...", log_group_name, Qgis.Info)
        return

    params_refactor_predio_ficha = {
        'INPUT' : '{input_db_path}|layername=predio_ficha'.format(input_db_path=INPUT_DB_PATH),
        'FIELDS_MAPPING' : [
            {'name': 't_id', 'precision': 0, 'expression': '"t_id"', 'type': 4, 'length': -1},
            {'name': 'clase_suelo_pot', 'precision': -1, 'expression': '"clase_suelo_pot"', 'type': 10, 'length': 255},
            {'name': 'categoria_suelo_pot', 'precision': -1, 'expression': '"categoria_suelo_pot"', 'type': 10, 'length': 255},
            {'name': 'actividad_economica', 'precision': -1, 'expression': '"actividad_economica"', 'type': 10, 'length': 255},
            {'name': 'derecho_fmi', 'precision': -1, 'expression': '"derecho_fmi"', 'type': 10, 'length': 255},
            {'name': 'inscrito_rupta', 'precision': -1, 'expression': '"inscrito_rupta"', 'type': 1, 'length': -1},
            {'name': 'fecha_medida_rupta', 'precision': -1, 'expression': '"fecha_medida_rupta"', 'type': 14, 'length': -1},
            {'name': 'anotacion_fmi_rupta', 'precision': -1, 'expression': 'false', 'type': 1, 'length': -1},
            {'name': 'inscrito_proteccion_colectiva', 'precision': -1, 'expression': '"inscrito_proteccion_colectiva"', 'type': 1, 'length': -1},
            {'name': 'fecha_proteccion_colectiva', 'precision': -1, 'expression': '"fecha_proteccion_colectiva"', 'type': 14, 'length': -1},
            {'name': 'anotacion_fmi_proteccion_colectiva', 'precision': -1, 'expression': 'false', 'type': 1, 'length': -1},
            {'name': 'incrito_proteccion_ley1448', 'precision': -1, 'expression': '"incrito_proteccion_ley1448"', 'type': 1, 'length': -1},
            {'name': 'fecha_proteccion_ley1448', 'precision': -1, 'expression': '"fecha_proteccion_ley1448"', 'type': 14, 'length': -1},
            {'name': 'anotacion_fmi_ley1448', 'precision': -1, 'expression': 'false', 'type': 1, 'length': -1},
            {'name': 'inscripcion_urt', 'precision': -1, 'expression': '"inscripcion_urt"', 'type': 1, 'length': -1},
            {'name': 'fecha_inscripcion_urt', 'precision': -1, 'expression': '"fecha_inscripcion_urt"', 'type': 14, 'length': -1},
            {'name': 'anotacion_fmi_urt', 'precision': -1, 'expression': 'false', 'type': 1, 'length': -1},
            {'name': 'observaciones', 'precision': -1, 'expression': '"observaciones"', 'type': 10, 'length': 255},
            {'name': 'nombre_quien_atendio', 'precision': -1, 'expression': '"nombre_quien_atendio"', 'type': 10, 'length': 40},
            {'name': 'numero_documento_quien_atendio', 'precision': -1, 'expression': '"numero_documento_quien_atendio"', 'type': 10, 'length': 10},
            {'name': 'categoria_quien_atendio', 'precision': -1, 'expression': '"categoria_quien_atendio"', 'type': 10, 'length': 255},
            {'name': 'tipo_documento_quien_atendio', 'precision': -1, 'expression': '"tipo_documento_quien_atendio"', 'type': 10, 'length': 255},
            {'name': 'nombre_encuestador', 'precision': -1, 'expression': '"nombre_encuestador"', 'type': 10, 'length': 40},
            {'name': 'numero_documento_encuestador', 'precision': -1, 'expression': '"numero_documento_encuestador"', 'type': 10, 'length': 10},
            {'name': 'tipo_documento_encuestador', 'precision': -1, 'expression': '"tipo_documento_encuestador"', 'type': 10, 'length': 255},
            {'name': 'fecha_visita_predial', 'precision': -1, 'expression': 'if("fecha_visita_predial" IS NULL, NULL, concat(right("fecha_visita_predial",4), \'-\', substr("fecha_visita_predial",4,2),\'-\',left("fecha_visita_predial",2)))', 'type': 14, 'length': -1},
            {'name': 'predio_tipo', 'precision': -1, 'expression': '"predio_tipo_MD"', 'type': 10, 'length': 255},
            {'name': 'tipo_predio_publico', 'precision': -1, 'expression': '"tipo_predio_publico"', 'type': 10, 'length': 255},
            {'name': 'estrato', 'precision': -1, 'expression': 'concat(\'Estrato_\',to_int("CODIGO_ESTRATO"))', 'type': 10, 'length': 255},
            {'name': 'formalidad', 'precision': -1, 'expression': '"formalidad"', 'type': 1, 'length': -1},
            {'name': 'estado_nupre', 'precision': -1, 'expression': '"estado_nupre"', 'type': 10, 'length': 255},
            {'name': 'vigencia_fiscal', 'precision': -1, 'expression': "concat('01-01-',vigencia_fiscal)", 'type': 14, 'length': -1},
            {'name': 'sector', 'precision': -1, 'expression': '"sector_MD"', 'type': 10, 'length': 2},
            {'name': 'localidad_comuna', 'precision': -1, 'expression': '"localidad_comuna"', 'type': 10, 'length': 2},
            {'name': 'barrio', 'precision': -1, 'expression': '"barrio_MD"', 'type': 10, 'length': 2},
            {'name': 'manzana_vereda', 'precision': -1, 'expression': '"manzana_vereda"', 'type': 10, 'length': 4},
            {'name': 'terreno', 'precision': -1, 'expression': '"terreno_MD"', 'type': 10, 'length': 4},
            {'name': 'condicion_propiedad', 'precision': -1, 'expression': '"condicion_propiedad"', 'type': 10, 'length': 1},
            {'name': 'edificio', 'precision': -1, 'expression': '"edificio"', 'type': 10, 'length': 2},
            {'name': 'piso', 'precision': -1, 'expression': '"piso_MD"', 'type': 10, 'length': 2},
            {'name': 'unidad', 'precision': -1, 'expression': '"unidad_MD"', 'type': 10, 'length': 4},
            {'name': 'tmp_chip', 'precision': -1, 'expression': '"CHIP"', 'type': 10, 'length': -1}
        ],
        'OUTPUT' : 'memory:'
    }

    refactor_and_copy_paste(params_refactor_predio_ficha, 'memory', predio_ficha.name())

def llenar_ficha__predioficha_predio():
    # table_cr_predio: Catastro_Registro.Predio
    # table_ficha__predio_ficha: LADM_COL ficha predio_ficha
    # association_table: LADM_COL ficha predioficha_predio
    table_cr_predio = get_ladm_col_layer("predio")
    table_ficha__predio_ficha = get_ladm_col_layer("predio_ficha")
    association_table = get_ladm_col_layer("predioficha_predio")

    features_source = [f for f in table_ficha__predio_ficha.getFeatures()]
    features = []
    for f in features_source:
        # Get corresponding feature in CR.Predio
        it_cr_predio = table_cr_predio.getFeatures("\"nupre\" = '{}'".format(f['tmp_chip']))
        f_cr_predio = QgsFeature()
        it_cr_predio.nextFeature(f_cr_predio)

        if f_cr_predio.isValid():
            feature = QgsVectorLayerUtils().createFeature(association_table)
            feature.setAttribute('crpredio', f_cr_predio['t_id'])
            feature.setAttribute('fichapredio', f['t_id'])

            features.append(feature)
        else:
            log.logMessage("CHIP not found in CR.predio {}".format(f['tmp_chip']), log_group_name, Qgis.Warning)

    association_table.dataProvider().addFeatures(features)

def llenar_ficha__nucleo_familiar():
    #table_predio_ficha: Ficha
    #table_predio: Catastro_Registro
    #table_col_derecho: catastro_Registro
    #table_interesado_natural: Catastro_Registro
    #table_interesado_juridico: Catastro_Registro
    #table_target: Table in LADM where to paste features to (Ficha_NucleoFamiliar)
    table_predio_ficha = get_ladm_col_layer("predio_ficha")
    table_predio = get_ladm_col_layer("predio")
    table_col_derecho = get_ladm_col_layer("col_derecho")
    table_interesado_natural = get_ladm_col_layer("interesado_natural")
    table_interesado_juridico = get_ladm_col_layer("interesado_juridico")
    table_target = get_ladm_col_layer("nucleofamiliar")

    dict_int_natural = {f["t_id"]: f for f in table_interesado_natural.getFeatures()}
    dict_int_juridico = {f["t_id"]: f for f in table_interesado_juridico.getFeatures()}

    features_predio_ficha = [f for f in table_predio_ficha.getFeatures()]
    features = []
    for f in features_predio_ficha:
        # Get corresponding feature in CR.predio
        it_cr_predio = table_predio.getFeatures("\"nupre\" = '{}'".format(f['tmp_chip']))
        f_cr_predio = QgsFeature()
        it_cr_predio.nextFeature(f_cr_predio)

        if f_cr_predio.isValid():
            # Get corresponding features in CR.Col_derecho
            features_cr_col_derecho = table_col_derecho.getFeatures("\"unidad_predio\" = {}".format(f_cr_predio['t_id']))
            for f_cr_col_derecho in features_cr_col_derecho:
                if f_cr_col_derecho.isValid():
                    int_natural = f_cr_col_derecho['interesado_interesado_natural']
                    int_juridico = f_cr_col_derecho['interesado_interesado_juridico']
                    feature = QgsVectorLayerUtils().createFeature(table_target)

                    if int_natural != NULL:
                        # Get corresponding feature in CR.interesado_natural
                        if int_natural in dict_int_natural:
                            f_cr_interesado_natural = dict_int_natural[int_natural]

                            if f_cr_interesado_natural.isValid():
                                feature.setAttribute('documento_identidad', f_cr_interesado_natural['documento_identidad'][:10]) # Field should support more chars
                                feature.setAttribute('tipo_documento', f_cr_interesado_natural['tipo_documento'])
                                p_n = f_cr_interesado_natural['primer_nombre']
                                s_n = f_cr_interesado_natural['segundo_nombre']
                                p_a = f_cr_interesado_natural['primer_apellido']
                                s_a = f_cr_interesado_natural['segundo_apellido']
                                feature.setAttribute('primer_nombre', p_n[:20] if p_n != NULL else NULL)
                                feature.setAttribute('segundo_nombre', s_n[:20] if s_n != NULL else NULL)
                                feature.setAttribute('primer_apellido', p_a[:20] if p_a != NULL else NULL)
                                feature.setAttribute('segundo_apellido', s_a[:20] if s_a != NULL else NULL)
                                feature.setAttribute('genero', f_cr_interesado_natural['genero'])

                    elif int_juridico != NULL:
                        # Get corresponding feature in CR.interesado_juridico
                        if int_juridico in dict_int_juridico:
                            f_cr_interesado_juridico = dict_int_juridico[int_juridico]

                            if f_cr_interesado_juridico.isValid():
                                feature.setAttribute('documento_identidad', f_cr_interesado_juridico['numero_nit'][:10]) # Field should support more chars
                                feature.setAttribute('tipo_documento', 'NIT')

                    feature.setAttribute('fichapredio', f['t_id'])
                    if feature['documento_identidad'] != NULL:
                        features.append(feature)

                else:
                    pass
        else:
            log.logMessage("CHIP not found in CR.Col_derecho: {}".format(f_cr_predio['t_id']), log_group_name, Qgis.Info)

    res = table_target.dataProvider().addFeatures(features)
    if res[0]:
        log.logMessage("{} features saved into Nucleo Familiar!".format(len(features)), log_group_name, Qgis.Info)

def llenar_ficha__investigacion_de_mercado():
    # layer_ficha__predio_ficha: Ficha.Predio_Ficha
    # table_source: GPKG Source (InvestigacionMercado)
    # table_target: Table in LADM where to paste features to (Ficha_Investigacion_Mercado)
    layer_predio_ficha = get_ladm_col_layer("predio_ficha")
    table_target = get_ladm_col_layer("investigacionmercado")

    table_source = QgsVectorLayer('{input_db_path}|layername=InvestigacionMercado'.format(input_db_path=INPUT_DB_PATH), "table_source", "ogr")

    features_source = [f for f in table_source.getFeatures()]
    features = []
    for f in features_source:
        # Get corresponding feature in Ficha.Predio_Ficha
        it_predio_ficha = layer_predio_ficha.getFeatures("\"tmp_chip\" = '{}'".format(f['CHIP']))
        f_predio_ficha = QgsFeature()
        it_predio_ficha.nextFeature(f_predio_ficha)

        if f_predio_ficha.isValid():
            feature = QgsVectorLayerUtils().createFeature(table_target)
            feature.setAttribute('fichapredio', f_predio_ficha['t_id'])
            feature.setAttribute('tipo_oferta', f['Tipo_Oferta'])
            feature.setAttribute('disponible_mercado', f['Disponible_Mercado'])
            feature.setAttribute('valor', f['Valor'])
            feature.setAttribute('nombre_oferente', f['Nombre_Oferente'])
            feature.setAttribute('telefono_contacto_oferente', f['Telefono_Contacto_Oferente'])
            feature.setAttribute('observaciones', f['Observaciones'])

            features.append(feature)
        else:
            log.logMessage("CHIP not found in FICHA.Predio_Ficha {}".format(f['CHIP']), log_group_name, Qgis.Info)

    res = table_target.dataProvider().addFeatures(features)
    if res[0]:
        log.logMessage("{} features saved into Investigación de Mercado!".format(len(features)), log_group_name, Qgis.Info)

def remover_campos_temporales_de_asociacion_ficha():
    # En llenar_ficha__predio_ficha creamos campo temporal para poder asociar
    # datos. Aquí lo removemos.
    predio_ficha = get_ladm_col_layer("predio_ficha")
    idx_tmp_field = predio_ficha.dataProvider().fields().indexFromName('tmp_chip')
    if idx_tmp_field != -1:
        predio_ficha.dataProvider().deleteAttributes([idx_tmp_field])
        predio_ficha.updateFields()

################################################################################
initialize_connection()

################################################################################
#                      MODELO CATASTRO-REGISTRO NÚCLEO
################################################################################
# Pre-processing
fix_geometries('Lote')
fix_geometries('Construccion_NPH')
fix_geometries('Und_Cons_NPH')

llenar_punto_lindero()
llenar_lindero()
llenar_terreno() # First fix the source layer (with 'Fix Geometries' algorithm)
llenar_tablas_de_topologia()
llenar_predio()
llenar_uebaunit_terreno_predio()
llenar_construccion('Construccion_NPH_fixed') # First fix source layer geometries
llenar_construccion('Construccion_PH')
llenar_construccion('Construccion_MJ')
llenar_uebaunit_construccion_predio()
llenar_unidad_construccion('nph') # First fix source layer geometries
llenar_unidad_construccion('ph')
llenar_unidad_construccion('mj')
llenar_uebaunit_unidad_construccion_predio('nph')
llenar_uebaunit_unidad_construccion_predio('ph')
llenar_uebaunit_unidad_construccion_predio('mj')
llenar_interesado_natural()
llenar_interesado_juridico()
llenar_col_derecho('interesado_natural')
llenar_col_derecho('interesado_juridico')
llenar_fuente_administrativa('interesado_juridico')
llenar_fuente_administrativa('interesado_natural')
llenar_rrr_fuente()

################################################################################
#                                MODELO AVALÚOS
################################################################################
# Pre-processing
fix_geometries('ZHF_009116', INPUT_DB_PATH_CARTO_REF)

llenar_avaluos__predio_matriz_ph()
llenar_avaluos__predio()
llenar_avaluos__avaluopredio()
remover_campos_temporales_de_asociacion_avaluos()
llenar_avaluos__construccion('nph')
llenar_avaluos__construccion('ph')
llenar_avaluos__construccion('mj')
llenar_avaluos__unidad_construccion('nph')
llenar_avaluos__unidad_construccion('ph')
llenar_avaluos__unidad_construccion('mj')
llenar_avaluos__calificacion_unidad_construccion()
llenar_avaluos__zhf()
llenar_avaluos__zhg()

################################################################################
#                                MODELO FICHA
################################################################################

llenar_ficha__predio_ficha()
llenar_ficha__predioficha_predio()
llenar_ficha__nucleo_familiar()
llenar_ficha__investigacion_de_mercado()
remover_campos_temporales_de_asociacion_ficha()
