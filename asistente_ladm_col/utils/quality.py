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
from qgis.PyQt.QtCore import (QObject,
                              QCoreApplication,
                              QVariant,
                              QSettings)
from qgis.core import (Qgis,
                       QgsField,
                       QgsGeometry,
                       QgsPointXY,
                       QgsProcessingFeedback,
                       QgsProject,
                       QgsSpatialIndex,
                       QgsVectorLayer,
                       QgsVectorLayerUtils,
                       QgsWkbTypes,
                       QgsFeatureRequest,
                       QgsRectangle)

import processing
from .project_generator_utils import ProjectGeneratorUtils
from ..config.general_config import (DEFAULT_EPSG,
                                     DEFAULT_TOO_LONG_BOUNDARY_SEGMENTS_TOLERANCE,
                                     DEFAULT_USE_ROADS_VALUE,
                                     TranslatableConfigStrings)
from ..config.table_mapping_config import (BOUNDARY_POINT_TABLE,
                                           BOUNDARY_TABLE,
                                           BUILDING_TABLE,
                                           CONTROL_POINT_TABLE,
                                           ID_FIELD,
                                           POINT_BFS_TABLE_BOUNDARY_FIELD,
                                           POINT_BOUNDARY_FACE_STRING_TABLE,
                                           POINTSOURCE_TABLE_BOUNDARYPOINT_FIELD,
                                           PLOT_TABLE,
                                           RIGHT_OF_WAY_TABLE,
                                           SURVEY_POINT_TABLE)


class QualityUtils(QObject):

    def __init__(self, qgis_utils):
        QObject.__init__(self)
        self.qgis_utils = qgis_utils
        self.project_generator_utils = ProjectGeneratorUtils()
        self.translatable_config_strings = TranslatableConfigStrings()

    def check_overlapping_points(self, db, point_layer_name):
        """
        Shows which points are overlapping
        :param db: db connection instance
        :param entity: points layer
        :return:
        """
        features = []
        point_layer = self.qgis_utils.get_layer(db, point_layer_name, load=True)

        if point_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Table {} not found in DB! {}").format(point_layer_name, db.get_description()),
                Qgis.Warning)
            return

        if point_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                   "There are no points in layer '{}' to check for overlaps!").format(point_layer_name), Qgis.Info)
            return

        error_layer_name = ''
        if point_layer_name == BOUNDARY_POINT_TABLE:
            error_layer_name = self.translatable_config_strings.CHECK_OVERLAPS_IN_BOUNDARY_POINTS
        elif point_layer_name == CONTROL_POINT_TABLE:
            error_layer_name = self.translatable_config_strings.CHECK_OVERLAPS_IN_CONTROL_POINTS

        error_layer = QgsVectorLayer("Point?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     error_layer_name, "memory")
        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField("point_count", QVariant.Int), QgsField("intersecting_ids", QVariant.String) ])
        error_layer.updateFields()

        overlapping = self.qgis_utils.geometry.get_overlapping_points(point_layer)
        flat_overlapping = [id for items in overlapping for id in items]  # Build a flat list of ids

        t_ids = {f.id(): f[ID_FIELD] for f in point_layer.getFeatures(flat_overlapping)}

        for items in overlapping:
            # We need a feature geometry, pick the first id to get it
            feature = point_layer.getFeature(items[0])
            point = feature.geometry()
            new_feature = QgsVectorLayerUtils().createFeature(
                error_layer,
                point,
                {0: len(items), 1: ", ".join([str(t_ids[i]) for i in items])})
            features.append(new_feature)

        error_layer.dataProvider().addFeatures(features)

        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "A memory layer with {} overlapping points in '{}' has been added to the map!").format(
                    added_layer.featureCount(), point_layer_name), Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no overlapping points in layer '{}'!").format(point_layer_name), Qgis.Info)

    def check_plots_covered_by_boundaries(self, db):
        res_layers = self.qgis_utils.get_layers(db, {
            PLOT_TABLE: {'name': PLOT_TABLE, 'geometry': QgsWkbTypes.PolygonGeometry},
            BOUNDARY_TABLE: {'name': BOUNDARY_TABLE, 'geometry': None}
        }, load=True)

        plot_layer = res_layers[PLOT_TABLE]
        boundary_layer = res_layers[BOUNDARY_TABLE]

        if plot_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "Layer {} not found in DB! {}").format(
                        PLOT_TABLE, db.get_description()), Qgis.Warning)
            return

        if boundary_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "Layer {} not found in DB! {}").format(
                        BOUNDARY_TABLE, db.get_description()), Qgis.Warning)
            return

        if plot_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no plots to check 'plots should be covered by boundaries'."),
                Qgis.Info)
            return

        error_layer = QgsVectorLayer("MultiLineString?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     self.translatable_config_strings.CHECK_PLOTS_COVERED_BY_BOUNDARIES,
                                     "memory")

        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField('plot_id', QVariant.Int)])
        error_layer.updateFields()

        features = []
        differences = self.qgis_utils.geometry.difference_plot_boundary(plot_layer, boundary_layer)

        if differences is not None:
            for difference in differences:
                new_feature = QgsVectorLayerUtils().createFeature(
                    error_layer,
                    difference['geometry'],
                    {0: difference['id']})
                features.append(new_feature)

            error_layer.dataProvider().addFeatures(features)

            if error_layer.featureCount() > 0:
                added_layer = self.add_error_layer(error_layer)

                self.qgis_utils.message_emitted.emit(
                    QCoreApplication.translate("QGISUtils",
                        "A memory layer with {} plot lines not covered by boundaries has been added to the map!").format(
                        added_layer.featureCount()), Qgis.Info)
            else:
                self.qgis_utils.message_emitted.emit(
                    QCoreApplication.translate("QGISUtils",
                        "All Plot lines are covered by Boundaries!"), Qgis.Info)

    def check_boundary_points_covered_by_boundary_nodes(self, db):
        res_layers = self.qgis_utils.get_layers(db, {
            BOUNDARY_TABLE: {'name': BOUNDARY_TABLE, 'geometry': None},
            BOUNDARY_POINT_TABLE: {'name': BOUNDARY_POINT_TABLE, 'geometry': None}}, load=True)

        boundary_layer = res_layers[BOUNDARY_TABLE]
        boundary_point_layer = res_layers[BOUNDARY_POINT_TABLE]

        if boundary_point_layer is None:
            self.qgis_utils.message_emitted.emit(
            QCoreApplication.translate("QGISUtils",
            "Layer {} not found in DB! {}").format(
            BOUNDARY_POINT_TABLE, db.get_description()), Qgis.Warning)
            return

        if boundary_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "Layer {} not found in DB! {}").format(
                    BOUNDARY_TABLE, db.get_description()), Qgis.Warning)
            return

        if boundary_point_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no boundary points to check 'boundary points should be covered by boundary nodes'."),
                Qgis.Info)
            return

        error_layer = QgsVectorLayer("Point?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     self.translatable_config_strings.CHECK_BOUNDARY_POINTS_COVERED_BY_BOUNDARY_NODES,
                                     "memory")

        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField('point_boundary_id', QVariant.Int)])
        error_layer.updateFields()

        features = []
        points_selected = self.qgis_utils.geometry.get_boundary_points_not_covered_by_boundary_nodes(boundary_point_layer, boundary_layer)

        for point_selected in points_selected:
            new_feature = QgsVectorLayerUtils().createFeature(
                error_layer,
                point_selected.geometry(),
                {0: point_selected[ID_FIELD]})
            features.append(new_feature)

        error_layer.dataProvider().addFeatures(features)

        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "A memory layer with {} boundary points not covered by boundary nodes has been added to the map!").format(
                    added_layer.featureCount()), Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "All boundary points are covered by boundary nodes!"), Qgis.Info)

    def check_boundaries_covered_by_plots(self, db):
        res_layers = self.qgis_utils.get_layers(db, {
            PLOT_TABLE: {'name': PLOT_TABLE, 'geometry': QgsWkbTypes.PolygonGeometry},
            BOUNDARY_TABLE: {'name': BOUNDARY_TABLE, 'geometry': None}
        }, load=True)

        plot_layer = res_layers[PLOT_TABLE]
        boundary_layer = res_layers[BOUNDARY_TABLE]

        if plot_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "Layer {} not found in DB! {}").format(
                        PLOT_TABLE, db.get_description()), Qgis.Warning)
            return

        if boundary_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "Layer {} not found in DB! {}").format(
                        BOUNDARY_TABLE, db.get_description()), Qgis.Warning)
            return

        if boundary_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no boundaries to check 'boundaries should be covered by plots'."),
                Qgis.Info)
            return

        error_layer = QgsVectorLayer("MultiLineString?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     self.translatable_config_strings.CHECK_BOUNDARIES_COVERED_BY_PLOTS,
                                     "memory")

        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField('boundary_id', QVariant.Int)])
        error_layer.updateFields()

        features = []
        differences = self.qgis_utils.geometry.difference_boundary_plot(boundary_layer, plot_layer)

        if differences is not None:
            for difference in differences:
                new_feature = QgsVectorLayerUtils().createFeature(
                    error_layer,
                    difference['geometry'],
                    {0: difference['id']})
                features.append(new_feature)

            error_layer.dataProvider().addFeatures(features)

            if error_layer.featureCount() > 0:
                added_layer = self.add_error_layer(error_layer)

                self.qgis_utils.message_emitted.emit(
                    QCoreApplication.translate("QGISUtils",
                        "A memory layer with {} boundaries not covered by plot lines has been added to the map!").format(
                        added_layer.featureCount()), Qgis.Info)
            else:
                self.qgis_utils.message_emitted.emit(
                    QCoreApplication.translate("QGISUtils",
                        "All Boundaries are covered by Plot lines!"), Qgis.Info)

    def check_overlapping_polygons(self, db, polygon_layer_name):
        polygon_layer = self.qgis_utils.get_layer(db, polygon_layer_name, QgsWkbTypes.PolygonGeometry, load=True)

        if polygon_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Table {} not found in DB! {}").format(polygon_layer_name, db.get_description()),
                Qgis.Warning)
            return

        error_layer_name = ''
        if polygon_layer_name == PLOT_TABLE:
            error_layer_name = self.translatable_config_strings.CHECK_OVERLAPS_IN_PLOTS
        elif polygon_layer_name == BUILDING_TABLE:
            error_layer_name = self.translatable_config_strings.CHECK_OVERLAPS_IN_BUILDINGS
        elif polygon_layer_name == RIGHT_OF_WAY_TABLE:
            error_layer_name = self.translatable_config_strings.CHECK_OVERLAPS_IN_RIGHTS_OF_WAY

        error_layer = QgsVectorLayer("Polygon?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     error_layer_name, "memory")
        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField("polygon_id", QVariant.Int),
                                     QgsField("overlapping_ids", QVariant.String),
                                     QgsField("count_parts", QVariant.Int)])
        error_layer.updateFields()

        if QgsWkbTypes.isMultiType(polygon_layer.wkbType()) and \
            polygon_layer.geometryType() == QgsWkbTypes.PolygonGeometry:
            polygon_layer = processing.run("native:multiparttosingleparts",
                                           {'INPUT': polygon_layer, 'OUTPUT': 'memory:'})['OUTPUT']

        overlapping = self.qgis_utils.geometry.get_overlapping_polygons(polygon_layer)

        flat_overlapping = [id for items in overlapping for id in items]  # Build a flat list of ids
        flat_overlapping = list(set(flat_overlapping))  # unique values

        if type(polygon_layer) == QgsVectorLayer: # A string might come from processing for empty layers
            t_ids = {f.id(): f[ID_FIELD] for f in polygon_layer.getFeatures() if f.id() in flat_overlapping}

        features = []

        for overlapping_item in overlapping:
            polygon_id_field = overlapping_item[0]
            overlapping_id_field = overlapping_item[1]
            polygon_intersection = self.qgis_utils.geometry.get_intersection_polygons(polygon_layer, polygon_id_field, overlapping_id_field)

            if polygon_intersection is not None:
                new_feature = QgsVectorLayerUtils().createFeature(
                    error_layer,
                    polygon_intersection,
                    {0: t_ids[polygon_id_field],
                     1: t_ids[overlapping_id_field],
                     2: len(polygon_intersection.asMultiPolygon()) if polygon_intersection.isMultipart() else 1})

                features.append(new_feature)

        error_layer.dataProvider().addFeatures(features)

        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "A memory layer with {} overlapping polygons in layer '{}' has been added to the map!").format(
                    added_layer.featureCount(), polygon_layer_name), Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "There are no overlapping polygons in layer '{}'!").format(
                    polygon_layer_name), Qgis.Info)

    def check_overlaps_in_boundaries(self, db):
        boundary_layer = self.qgis_utils.get_layer(db, BOUNDARY_TABLE, load=True)

        if boundary_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "Table {} not found in DB! {}").format(
                        BOUNDARY_TABLE, db.get_description()), Qgis.Warning)
            return

        overlapping = self.qgis_utils.geometry.get_overlapping_lines(boundary_layer)
        if overlapping is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                   "There are no boundaries to check for overlaps!"), Qgis.Info)
            return

        error_point_layer = overlapping['native:saveselectedfeatures_3:Intersected_Points']
        error_line_layer = overlapping['native:saveselectedfeatures_2:Intersected_Lines']
        if type(error_point_layer) is QgsVectorLayer:
            error_point_layer.setName("{} (point intersections)".format(
                self.translatable_config_strings.CHECK_OVERLAPS_IN_BOUNDARIES
            ))
        if type(error_line_layer) is QgsVectorLayer:
            error_line_layer.setName("{} (line intersections)".format(
                self.translatable_config_strings.CHECK_OVERLAPS_IN_BOUNDARIES
            ))

        if (type(error_point_layer) is not QgsVectorLayer and \
           type(error_line_layer) is not QgsVectorLayer) or \
           (error_point_layer.featureCount() == 0 and \
           error_line_layer.featureCount() == 0):

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no overlapping boundaries."), Qgis.Info)
        else:
            msg = ''

            if type(error_point_layer) is QgsVectorLayer and error_point_layer.featureCount() > 0:
                added_point_layer = self.add_error_layer(error_point_layer)
                msg = QCoreApplication.translate("QGISUtils",
                    "A memory layer with {} overlapping boundaries (point intersections) has been added to the map.").format(added_point_layer.featureCount())

            if type(error_line_layer) is QgsVectorLayer and error_line_layer.featureCount() > 0:
                added_line_layer = self.add_error_layer(error_line_layer)
                msg = QCoreApplication.translate("QGISUtils",
                    "A memory layer with {} overlapping boundaries (line intersections) has been added to the map.").format(added_line_layer.featureCount())

            if type(error_point_layer) is QgsVectorLayer and \
               type(error_line_layer) is QgsVectorLayer and \
               error_point_layer.featureCount() > 0 and \
               error_line_layer.featureCount() > 0:
                msg = QCoreApplication.translate("QGISUtils",
                    "Two memory layers with overlapping boundaries ({} point intersections and {} line intersections) have been added to the map.").format(added_point_layer.featureCount(), added_line_layer.featureCount())

            self.qgis_utils.message_emitted.emit(msg, Qgis.Info)

    def check_boundaries_are_not_split(self, db):
        """
        An split boundary is an incomplete boundary because it is connected to
        a single boundary and therefore, they don't represent a change in
        boundary (colindancia).
        """
        features = []
        boundary_layer = self.qgis_utils.get_layer(db, BOUNDARY_TABLE, load=True)

        if boundary_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "Layer {} not found in DB! {}").format(
                        BOUNDARY_TABLE, db.get_description()), Qgis.Warning)
            return

        if boundary_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                   "There are no boundaries to check 'boundaries should not be split'!"), Qgis.Info)
            return

        wrong_boundaries = self.qgis_utils.geometry.get_boundaries_connected_to_single_boundary(boundary_layer)

        if wrong_boundaries is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no wrong boundaries!"), Qgis.Info)
            return

        error_layer = QgsVectorLayer("LineString?crs=EPSG:{}".format(DEFAULT_EPSG),
                        self.translatable_config_strings.CHECK_BOUNDARIES_ARE_NOT_SPLIT,
                        "memory")
        pr = error_layer.dataProvider()
        pr.addAttributes([QgsField("boundary_id", QVariant.Int)])
        error_layer.updateFields()

        for feature in wrong_boundaries:
            new_feature = QgsVectorLayerUtils().createFeature(error_layer, feature.geometry(),
                                                              {0: feature[ID_FIELD]})
            features.append(new_feature)

        error_layer.dataProvider().addFeatures(features)
        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "A memory layer with {} wrong boundaries has been added to the map!").format(added_layer.featureCount()),
                Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no wrong boundaries."),
                Qgis.Info)

    def check_too_long_segments(self, db):
        tolerance = int(QSettings().value('Asistente-LADM_COL/quality/too_long_tolerance', DEFAULT_TOO_LONG_BOUNDARY_SEGMENTS_TOLERANCE)) # meters
        features = []
        boundary_layer = self.qgis_utils.get_layer(db, BOUNDARY_TABLE, load=True)

        if boundary_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Table {} not found in the DB! {}").format(BOUNDARY_TABLE, db.get_description()),
                Qgis.Warning)
            return

        if boundary_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                   "There are no boundaries to check for too long segments!"), Qgis.Info)
            return

        error_layer = QgsVectorLayer("LineString?crs=EPSG:{}".format(DEFAULT_EPSG),
                        self.translatable_config_strings.CHECK_TOO_LONG_BOUNDARY_SEGMENTS,
                        "memory")
        pr = error_layer.dataProvider()
        pr.addAttributes([QgsField("boundary_id", QVariant.Int),
                          QgsField("distance", QVariant.Double)])
        error_layer.updateFields()

        for feature in boundary_layer.getFeatures():
            lines = feature.geometry()
            if lines.isMultipart():
                for part in range(lines.constGet().numGeometries()):
                    line = lines.constGet().geometryN(part)
                    segments_info = self.qgis_utils.geometry.get_too_long_segments_from_simple_line(line, tolerance)
                    for segment_info in segments_info:
                        new_feature = QgsVectorLayerUtils().createFeature(error_layer, segment_info[0], {0:feature.id(), 1:segment_info[1]})
                        features.append(new_feature)
            else:
                segments_info = self.qgis_utils.geometry.get_too_long_segments_from_simple_line(lines.constGet(), tolerance)
                for segment_info in segments_info:
                    new_feature = QgsVectorLayerUtils().createFeature(error_layer, segment_info[0], {0:feature.id(), 1:segment_info[1]})
                    features.append(new_feature)

        error_layer.dataProvider().addFeatures(features)
        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "A memory layer with {} boundary segments longer than {}m. has been added to the map!").format(added_layer.featureCount(), tolerance),
                Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "All boundary segments are within the length tolerance for segments ({}m.)!").format(tolerance),
                Qgis.Info)

    def check_missing_boundary_points_in_boundaries(self, db):
        res_layers = self.qgis_utils.get_layers(db, {
            BOUNDARY_POINT_TABLE: {'name': BOUNDARY_POINT_TABLE, 'geometry': None},
            POINT_BOUNDARY_FACE_STRING_TABLE: {'name': POINT_BOUNDARY_FACE_STRING_TABLE, 'geometry': None},
            BOUNDARY_TABLE: {'name': BOUNDARY_TABLE, 'geometry': None}}, load=True)

        boundary_point_layer = res_layers[BOUNDARY_POINT_TABLE]
        boundary_layer = res_layers[BOUNDARY_TABLE]
        point_ccl_table = res_layers[POINT_BOUNDARY_FACE_STRING_TABLE]

        if boundary_point_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Table {} not found in DB! {}").format(BOUNDARY_POINT_TABLE, db.get_description()),
                Qgis.Warning)
            return

        if boundary_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Table {} not found in DB! {}").format(BOUNDARY_TABLE, db.get_description()),
                Qgis.Warning)
            return

        if boundary_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no boundaries to check 'missing boundary points in boundaries'."),
                Qgis.Info)
            return

        if point_ccl_table is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Table {} not found in DB! {}").format(
                    POINT_BOUNDARY_FACE_STRING_TABLE, db.get_description()), Qgis.Warning)
            return

        error_layer = QgsVectorLayer("Point?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     self.translatable_config_strings.CHECK_MISSING_BOUNDARY_POINTS_IN_BOUNDARIES,
                                     "memory")
        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField('boundary_point_id', QVariant.Int),
                                     QgsField('boundary_id', QVariant.Int),
                                     QgsField('error_type', QVariant.String)])

        error_layer.updateFields()

        # check missing points
        missing_points = self.get_missing_boundary_points_in_boundaries(boundary_point_layer, boundary_layer)

        new_features = list()
        for key, point_list in missing_points.items():
            for point in point_list:
                new_feature = QgsVectorLayerUtils().createFeature(
                    error_layer,
                    point,
                    {
                        0: None,
                        1: key,
                        2: QCoreApplication.translate("QGISUtils", "Missing boundary point in boundary")})
                new_features.append(new_feature)

        dic_points_ccl = dict()
        for feature_point_ccl in point_ccl_table.getFeatures():
            key = "{}-{}".format(feature_point_ccl[POINTSOURCE_TABLE_BOUNDARYPOINT_FIELD], feature_point_ccl[POINT_BFS_TABLE_BOUNDARY_FIELD])
            if key in dic_points_ccl:
                dic_points_ccl[key] += 1
            else:
                dic_points_ccl.update({key:1})

        # verify that the relation between boundary point and boundary is registered in the topology table
        points_selected = self.qgis_utils.geometry.join_boundary_points_with_boundary_discard_nonmatching(boundary_point_layer, boundary_layer)

        for point_selected in points_selected:
            boundary_point_id = point_selected[ID_FIELD]
            boundary_id = point_selected['{}_2'.format(ID_FIELD)]
            key_query = "{}-{}".format(boundary_point_id, boundary_id)

            if key_query in dic_points_ccl:
                if dic_points_ccl[key_query] > 1:
                    new_features.append(QgsVectorLayerUtils().createFeature(error_layer, point_selected.geometry(),
                        {0: boundary_point_id,
                         1: boundary_id,
                         2: QCoreApplication.translate("QGISUtils", "Relation found more than once in the PointBFS table")}))
            else:
                new_features.append(QgsVectorLayerUtils().createFeature(error_layer, point_selected.geometry(),
                    {0: boundary_point_id,
                     1: boundary_id,
                     2: QCoreApplication.translate("QGISUtils", "Relation not found in the PointBFS table")}))
        data_provider.addFeatures(new_features)

        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "A memory layer with {} boundary vertices with no associated boundary points or with boundary points wrongly registered in the PointBFS table been added to the map!").format(added_layer.featureCount()), Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no missing boundary points in boundaries."), Qgis.Info)

    def check_missing_survey_points_in_buildings(self, db):
        """
        Not used anymore but kept for reference.
        """
        res_layers = self.qgis_utils.get_layers(db, {
            SURVEY_POINT_TABLE: {'name': SURVEY_POINT_TABLE, 'geometry': None},
            BUILDING_TABLE: {'name': BUILDING_TABLE, 'geometry': QgsWkbTypes.PolygonGeometry}}, load=True)

        survey_point_layer = res_layers[SURVEY_POINT_TABLE]
        building_layer = res_layers[BUILDING_TABLE]

        if survey_point_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Table {} not found in DB! {}").format(SURVEY_POINT_TABLE, db.get_description()),
                Qgis.Warning)
            return

        if building_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Table {} not found in DB! {}").format(BUILDING_TABLE, db.get_description()),
                Qgis.Warning)
            return

        if building_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no buildings to check 'missing survey points in buildings'."),
                Qgis.Info)
            return

        error_layer = QgsVectorLayer("Point?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     QCoreApplication.translate("QGISUtils", "Missing survey points in buildings"),
                                     "memory")
        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField("building_id", QVariant.Int)])
        error_layer.updateFields()

        missing_points = self.get_missing_boundary_points_in_boundaries(survey_point_layer, building_layer)

        new_features = list()
        for key, point_list in missing_points.items():
            for point in point_list:
                new_feature = QgsVectorLayerUtils().createFeature(error_layer, point, {0: key})
                new_features.append(new_feature)

        data_provider.addFeatures(new_features)

        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "A memory layer with {} building vertices with no associated survey points has been added to the map!").format(added_layer.featureCount()), Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no missing survey points in buildings."), Qgis.Info)

    def check_dangles_in_boundaries(self, db):
        boundary_layer = self.qgis_utils.get_layer(db, BOUNDARY_TABLE, load=True)

        if boundary_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Table {} not found in the DB! {}").format(BOUNDARY_TABLE, db.get_description()),
                Qgis.Warning)
            return

        if boundary_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no boundaries to check for dangles."),
                Qgis.Info)
            return

        error_layer = QgsVectorLayer("Point?crs=EPSG:{}".format(DEFAULT_EPSG),
                            self.translatable_config_strings.CHECK_DANGLES_IN_BOUNDARIES,
                            "memory")
        pr = error_layer.dataProvider()
        pr.addAttributes([QgsField("boundary_id", QVariant.Int)])
        error_layer.updateFields()

        end_points, dangle_ids = self.get_dangle_ids(boundary_layer)

        new_features = []
        for dangle in end_points.getFeatures(dangle_ids):
            new_feature = QgsVectorLayerUtils().createFeature(end_points, dangle.geometry(), {0: dangle[ID_FIELD]})
            new_features.append(new_feature)

        error_layer.dataProvider().addFeatures(new_features)

        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "A memory layer with {} boundary dangles has been added to the map!").format(added_layer.featureCount()),
                Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Boundaries have no dangles!"),
                Qgis.Info)

    def get_missing_boundary_points_in_boundaries(self, boundary_point_layer, boundary_layer):
        res = dict()

        feedback = QgsProcessingFeedback()
        extracted_vertices = processing.run("native:extractvertices", {'INPUT':boundary_layer,'OUTPUT':'memory:'}, feedback=feedback)
        extracted_vertices_layer = extracted_vertices['OUTPUT']

        # From vertices layer, get points with no overlap
        overlapping_points = self.qgis_utils.geometry.get_overlapping_points(extracted_vertices_layer)

        extracted_vertices_ids = [feature.id() for feature in extracted_vertices_layer.getFeatures()]

        # Unpack list of lists into single list
        overlapping_point_ids = [item for sublist in overlapping_points for item in sublist]

        # Unpack list of lists into single list selecting only the first point
        # per list. That means, discard overlapping points, and only keep one
        cleaned_point_ids = [sublist[0] for sublist in overlapping_points]

        # All vertices (even duplicated, due to the alg we use), minus all
        # overlapping ids, plus only one of the overlapping ids
        # This gets a list of all vertex ids with no duplicates
        no_duplicate_ids = list(set(extracted_vertices_ids) - set(overlapping_point_ids)) + cleaned_point_ids

        if boundary_point_layer.featureCount() == 0:
            # Return all extracted and cleaned vertices
            for feature in extracted_vertices_layer.getFeatures(no_duplicate_ids):
                if feature[ID_FIELD] in res:
                    res[feature[ID_FIELD]].append(feature.geometry())
                else:
                    res[feature[ID_FIELD]] = [feature.geometry()]

            return res

        index = QgsSpatialIndex(boundary_point_layer.getFeatures(QgsFeatureRequest().setSubsetOfAttributes([])), feedback)

        for feature in extracted_vertices_layer.getFeatures(no_duplicate_ids):
            if feature.hasGeometry():
                geom = feature.geometry()
                diff_geom = QgsGeometry(geom)

                # Use a custom bbox to include very near but not exactly equal points
                point_vert = {'x': diff_geom.asPoint().x(), 'y': diff_geom.asPoint().y()}
                bbox = QgsRectangle(
                    QgsPointXY(point_vert['x'] - 0.0001, point_vert['y'] - 0.0001),
                    QgsPointXY(point_vert['x'] + 0.0001, point_vert['y'] + 0.0001)
                )
                intersects = index.intersects(bbox)

                if not intersects:
                    if feature[ID_FIELD] in res:
                        res[feature[ID_FIELD]].append(diff_geom)
                    else:
                        res[feature[ID_FIELD]] = [diff_geom]
        return res

    def check_right_of_way_overlaps_buildings(self, db):
        res_layers = self.qgis_utils.get_layers(db, {
            RIGHT_OF_WAY_TABLE: {'name': RIGHT_OF_WAY_TABLE, 'geometry': QgsWkbTypes.PolygonGeometry},
            BUILDING_TABLE: {'name': BUILDING_TABLE, 'geometry': QgsWkbTypes.PolygonGeometry}}, load=True)

        right_of_way_layer = res_layers[RIGHT_OF_WAY_TABLE]
        building_layer = res_layers[BUILDING_TABLE]

        if right_of_way_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "Table {} not found in DB! {}").format(RIGHT_OF_WAY_TABLE,
                    db.get_description()),
                Qgis.Warning)
            return

        if building_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                    "Table {} not found in DB! {}").format(BUILDING_TABLE,
                    db.get_description()),
                Qgis.Warning)
            return

        if right_of_way_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                   "There are no Right of Way features to check 'Right of Way should not overlap buildings'."),
                Qgis.Info)
            return

        if building_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                   "There are no buildings to check 'Right of Way should not overlap buildings'."),
                Qgis.Info)
            return

        error_layer = QgsVectorLayer("MultiPolygon?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     self.translatable_config_strings.CHECK_RIGHT_OF_WAY_OVERLAPS_BUILDINGS,
                                     "memory")
        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField("right_of_way_id", QVariant.Int)])
        data_provider.addAttributes([QgsField("building_id", QVariant.Int)])
        error_layer.updateFields()

        ids, overlapping_polygons = self.qgis_utils.geometry.get_inner_intersections_between_polygons(right_of_way_layer, building_layer)

        if overlapping_polygons is not None:
            new_features = list()
            for key, polygon in zip(ids, overlapping_polygons.asGeometryCollection()):
                new_feature = QgsVectorLayerUtils().createFeature(error_layer, polygon, {0: key[0], 1: key[1]}) # right_of_way_id, building_id
                new_features.append(new_feature)

            data_provider.addFeatures(new_features)

        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "A memory layer with {} Right of Way-Building overlaps has been added to the map!").format(
                    added_layer.featureCount()), Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no Right of Way-Building overlaps."), Qgis.Info)

    def check_gaps_in_plots(self, db):
        use_roads = bool(QSettings().value('Asistente-LADM_COL/quality/use_roads', DEFAULT_USE_ROADS_VALUE, bool))
        plot_layer = self.qgis_utils.get_layer(db, PLOT_TABLE, QgsWkbTypes.PolygonGeometry, True)

        if plot_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Layer {} not found in DB! {}").format(PLOT_TABLE,
                                                                                  db.get_description()),
                Qgis.Warning)
            return

        if plot_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no Plot features to check 'Plot should not have gaps'."),
                Qgis.Info)
            return

        error_layer = QgsVectorLayer("MultiPolygon?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     self.translatable_config_strings.CHECK_GAPS_IN_PLOTS,
                                     "memory")
        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField("id", QVariant.Int)])
        error_layer.updateFields()

        gaps = self.qgis_utils.geometry.get_gaps_in_polygon_layer(plot_layer, use_roads)

        if gaps is not None:
            new_features = list()
            for geom, id in zip(gaps, range(0, len(gaps))):
                feature = QgsVectorLayerUtils().createFeature(error_layer, geom, {0: id})
                new_features.append(feature)

            data_provider.addFeatures(new_features)

        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "A memory layer with {} gaps in layer Plots has been added to the map!").format(
                    added_layer.featureCount()), Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no gaps in layer Plot."), Qgis.Info)

    def check_multiparts_in_right_of_way(self, db):
        right_of_way_layer = self.qgis_utils.get_layer(db, RIGHT_OF_WAY_TABLE, QgsWkbTypes.PolygonGeometry, True)

        if right_of_way_layer is None:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "Layer {} not found in DB! {}").format(RIGHT_OF_WAY_TABLE,
                                                                                  db.get_description()),
                Qgis.Warning)
            return

        if right_of_way_layer.featureCount() == 0:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no Right Of Way features to check 'Right Of Way should not have Multipart geometries'."),
                Qgis.Info)
            return

        error_layer = QgsVectorLayer("Polygon?crs=EPSG:{}".format(DEFAULT_EPSG),
                                     self.translatable_config_strings.CHECK_MULTIPART_IN_RIGHT_OF_WAY,
                                     "memory")
        data_provider = error_layer.dataProvider()
        data_provider.addAttributes([QgsField("original_id", QVariant.Int)])
        error_layer.updateFields()

        multi_parts, ids = self.qgis_utils.geometry.get_multipart_geoms(right_of_way_layer)

        if multi_parts is not None:
            new_features = list()
            for geom, id in zip(multi_parts, ids):
                feature = QgsVectorLayerUtils().createFeature(error_layer, geom, {0: id})
                new_features.append(feature)

            data_provider.addFeatures(new_features)

        if error_layer.featureCount() > 0:
            added_layer = self.add_error_layer(error_layer)

            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "A memory layer with {} multipart geometries in layer Right Of Way has been added to the map!").format(
                    added_layer.featureCount()), Qgis.Info)
        else:
            self.qgis_utils.message_emitted.emit(
                QCoreApplication.translate("QGISUtils",
                                           "There are no multipart geometries in layer Right Of Way."), Qgis.Info)

    def get_dangle_ids(self, boundary_layer):
        # 1. Run extract specific vertices
        # 2. Call to get_overlapping_points
        # 3. Obtain dangle ids (those not present in overlapping points result)
        res = processing.run("qgis:extractspecificvertices", {
                'INPUT': boundary_layer,
                'VERTICES': '0,-1', # First and last
                'OUTPUT': 'memory:'
            },
            feedback=QgsProcessingFeedback()
        )
        end_points = res['OUTPUT']

        end_point_ids = [point.id() for point in end_points.getFeatures()]
        overlapping_points = self.qgis_utils.geometry.get_overlapping_points(end_points)

        # Unpack list of lists into single list
        overlapping_point_ids = [item for sublist in overlapping_points for item in sublist]

        return (end_points, list(set(end_point_ids) - set(overlapping_point_ids)))

    def add_error_layer(self, error_layer):
        group = self.qgis_utils.get_error_layers_group()

        # Check if layer is loaded and remove it
        layers = group.findLayers()
        for layer in layers:
            if layer.name() == error_layer.name():
                group.removeLayer(layer.layer())
                break

        added_layer = QgsProject.instance().addMapLayer(error_layer, False)
        index = self.project_generator_utils.get_suggested_index_for_layer(added_layer, group)
        added_layer = group.insertLayer(index, added_layer).layer()
        self.qgis_utils.symbology.set_layer_style_from_qml(added_layer, is_error_layer=True)
        return added_layer
