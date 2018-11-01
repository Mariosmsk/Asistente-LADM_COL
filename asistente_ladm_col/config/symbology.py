from qgis.core import QgsWkbTypes

from .general_config import TranslatableConfigStrings
from .table_mapping_config import (
    BOUNDARY_TABLE,
    BOUNDARY_POINT_TABLE,
    CONTROL_POINT_TABLE,
    SURVEY_POINT_TABLE,
    PLOT_TABLE,
    BUILDING_TABLE,
    BUILDING_UNIT_TABLE,
    RIGHT_OF_WAY_TABLE
)
translatable_config_strings = TranslatableConfigStrings()
ERROR_LAYER = 'error_layer'

LAYER_QML_STYLE = {
    BOUNDARY_TABLE: {
        QgsWkbTypes.LineGeometry: 'style_boundary'
    },
    BOUNDARY_POINT_TABLE: {
        QgsWkbTypes.PointGeometry: 'style_boundary_point'
    },
    SURVEY_POINT_TABLE: {
        QgsWkbTypes.PointGeometry: 'style_survey_point'
    },
    CONTROL_POINT_TABLE: {
        QgsWkbTypes.PointGeometry: 'style_control_point'
    },
    PLOT_TABLE: {
        QgsWkbTypes.PointGeometry: 'style_plot_point',
        QgsWkbTypes.PolygonGeometry: 'style_plot_polygon'
    },
    BUILDING_TABLE: {
        QgsWkbTypes.PointGeometry: 'style_building_point',
        QgsWkbTypes.PolygonGeometry: 'style_building_25'
    },
    BUILDING_UNIT_TABLE: {
        QgsWkbTypes.PointGeometry: 'style_building_unit_point',
        QgsWkbTypes.PolygonGeometry: 'style_building_unit_25'
    },
    RIGHT_OF_WAY_TABLE: {
        QgsWkbTypes.PointGeometry: 'style_right_of_way_point',
        QgsWkbTypes.PolygonGeometry: 'style_right_of_way'
    },
    ERROR_LAYER: {
        QgsWkbTypes.PointGeometry: 'style_point_error',
        QgsWkbTypes.LineGeometry: 'style_line_error',
        QgsWkbTypes.PolygonGeometry: 'style_polygon_error'
    }
}

CUSTOM_ERROR_LAYERS = {
    translatable_config_strings.CHECK_BOUNDARIES_COVERED_BY_PLOTS: {
        'es': 'style_boundary_should_be_covered_by_plot_es',
        'en': 'style_boundary_should_be_covered_by_plot_en'
    },
    translatable_config_strings.CHECK_PLOTS_COVERED_BY_BOUNDARIES: {
        'es': 'style_plot_should_be_covered_by_boundary_es',
        'en': 'style_plot_should_be_covered_by_boundary_en'
    }
}