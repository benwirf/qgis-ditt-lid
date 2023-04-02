from processing.gui.wrappers import WidgetWrapper
from qgis.PyQt.QtCore import QCoreApplication, QVariant, QDir, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (QWidget,
                                QLabel,
                                QLineEdit,
                                QPushButton,
                                QVBoxLayout,
                                QHBoxLayout,
                                QCheckBox,
                                QFileDialog)

from qgis.core import (NULL,
                        QgsVectorLayer,
                        QgsField,
                        QgsFeature,
                        QgsFeatureSink,
                        QgsFeatureRequest,
                        QgsProcessing,
                        QgsProcessingAlgorithm,
                        QgsProcessingParameterFeatureSource,
                        QgsProcessingParameterField,
                        QgsProcessingParameterBoolean,
                        QgsProcessingParameterEnum,
                        QgsProcessingParameterDefinition,
                        QgsProcessingParameterFolderDestination,
                        QgsProcessingParameterMatrix,
                        QgsProcessingOutputMultipleLayers,
                        QgsProcessingMultiStepFeedback,
                        QgsSpatialIndex,
                        QgsGeometry,
                        QgsProcessingException,
                        QgsCoordinateTransform,
                        QgsCoordinateReferenceSystem,
                        QgsDistanceArea,
                        QgsUnitTypes)

from pathlib import Path

import processing

import os
                       
class ExtractLandTypes(QgsProcessingAlgorithm):
    LAND_TYPES = 'LAND_TYPES'# Vector polygon
    OUTPUT_FIELDS = 'OUTPUT_FIELDS'# Fields to copy to output land type layers
    UNIT_FIELD = 'UNIT_FIELD'# Field containing unique map unit/land unit
    PADDOCKS = 'PADDOCKS'# Vector polygon
    PADDOCK_NAME_FIELD = 'PADDOCK_NAME_FIELD'
    WATERPOINTS = 'WATERPOINTS'# Vector point
    DISSOLVE_PADDOCKS = 'DISSOLVE_PADDOCKS'# Boolean
    WATERED_AREAS = 'WATERED_AREAS'# Enum
    AREA_METHOD = 'AREA_METHOD'# Enum
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'# destination folder
    LOAD_OUTPUTS = 'LOAD_OUTPUTS'# Boolean
    OUTPUT_LAYERS = 'OUTPUT_LAYERS'
    OUTPUT_FORMAT = 'OUTPUT_FORMAT'
    OUTPUT_XLSX = 'OUTPUT_XSLX'# Location for output xlsx. If empty, use output folder *Custom param widget
    
    WA_DISTANCES = ['3km', '5km']
    AREA_METHODS = ['Ellipsoidal', 'Planar']
    FORMATS = ['gpkg', 'shp', 'json', 'kml', 'kmz']
    
    # Will be populated with output layer paths if user selects 'Load Outputs'
    layers_to_load = []
    
    # Distance Area instance used to measure ellipsoidal areas
    da = QgsDistanceArea()
 
    def __init__(self):
        super().__init__()
 
    def name(self):
        return "extractlandtypes"
         
    def displayName(self):
        return "Extract Land Types"
 
    def group(self):
        return "Analysis"
 
    def groupId(self):
        return "analysis"
        
    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "../icons/land_type_icon.png"))
 
    def shortHelpString(self):
        return "Extract and calculate land system/unit areas for property, paddock and watered areas\
                If the input paddock layer is in a projected CRS, the other input layers and\
                outputs will be transformed to match. If the input paddock layer is in a\
                geographic CRS, all layers will be projected to EPSG:9473 GDA 2020/ Australian Albers.\
                An output report spreadsheet can also optionally be exported"
 
    def helpUrl(self):
        return "https://qgis.org"
         
    def createInstance(self):
        return type(self)()
        
    def checkParameterValues(self, parameters, context):
        if (parameters[self.WATERPOINTS] and not parameters[self.WATERED_AREAS]) or (not parameters[self.WATERPOINTS] and parameters[self.WATERED_AREAS]):
            return (False, 'Water points and watered area inputs are incompatible. Specify both or neither.')
        return (True, '')
           
    def initAlgorithm(self, config=None):
        
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.LAND_TYPES,
            "Land types layer (e.g. land systems/ units)",
            [QgsProcessing.TypeVectorPolygon],
            optional=False))
            
        self.addParameter(QgsProcessingParameterField(
            self.OUTPUT_FIELDS,
            "Fields to copy to output layers",
            parentLayerParameterName=self.LAND_TYPES,
            allowMultiple=True))
            
        self.addParameter(QgsProcessingParameterField(
            self.UNIT_FIELD,
            "Field containing unique map unit/ land unit names",
            parentLayerParameterName=self.LAND_TYPES,
            type=QgsProcessingParameterField.String))
            
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.PADDOCKS,
            "Property paddocks layer",
            [QgsProcessing.TypeVectorPolygon],
            optional=False))
            
        self.addParameter(QgsProcessingParameterField(
            self.PADDOCK_NAME_FIELD,
            "Field containing paddock names",
            parentLayerParameterName=self.PADDOCKS,
            type=QgsProcessingParameterField.String))

        self.addParameter(QgsProcessingParameterFeatureSource(
            self.WATERPOINTS,
            "Property waterpoints layer",
            [QgsProcessing.TypeVectorPoint],
            optional=True))
            
        self.addParameter(QgsProcessingParameterBoolean(
            self.DISSOLVE_PADDOCKS,
            "Include calculation for whole property (paddocks dissolved)?",
            defaultValue=False))
            
        self.addParameter(QgsProcessingParameterEnum(
            self.WATERED_AREAS,
            "Include watered areas?",
            self.WA_DISTANCES,
            allowMultiple=True,
            optional=True))
            
        self.parameterDefinition(self.WATERED_AREAS).setMetadata({
            'widget_wrapper': {
                'useCheckBoxes': True,
                'columns': 2}})
                
        self.addParameter(QgsProcessingParameterEnum(
            self.AREA_METHOD,
            "Area calculation method",
            self.AREA_METHODS,
            defaultValue=0))
            
        self.parameterDefinition(self.AREA_METHOD).setMetadata({
            'widget_wrapper': {
                'useCheckBoxes': True,
                'columns': 2}})
        
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_FOLDER,
            "Folder for output files"))
                        
        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_OUTPUTS,
            "Load output vector layers on completion?",
            defaultValue=False))
            
        self.addParameter(QgsProcessingParameterEnum(
            self.OUTPUT_FORMAT,
            "Output file format for vector layers",
            self.FORMATS,
            allowMultiple=False,
            defaultValue=self.FORMATS[0],
            optional=False))
        
        output_spreadsheet_params = (QgsProcessingParameterMatrix(self.OUTPUT_XLSX, 'Output spreadsheet parameters', optional=True))
        output_spreadsheet_params.setMetadata({'widget_wrapper': {'class': CustomParametersWidgetWrapper}})
        self.addParameter(output_spreadsheet_params)
        '''
        Prime suspect (output param) in case of crash/freeze- remove this first
        '''
        self.addOutput(QgsProcessingOutputMultipleLayers(
            self.OUTPUT_LAYERS,
            "Output layers"))
        
    def processAlgorithm(self, parameters, context, model_feedback):
        results = {}
        outputs = {}
        
        # Will be populated with generated vector layers. If user wants to export a spreadsheet,
        # these layers will be used as inputs for save to spreadsheet algorithm.
        # This list will also be added to the results dict as the value of the self.OUTPUT_LAYERS key
        output_layers = []
 
        source_land_types = self.parameterAsSource(parameters, self.LAND_TYPES, context)
        output_fields = self.parameterAsFields(parameters, self.OUTPUT_FIELDS, context)
        unit_fields = self.parameterAsFields(parameters, self.UNIT_FIELD, context)
        source_paddocks = self.parameterAsSource(parameters, self.PADDOCKS, context)
        paddock_name_field = self.parameterAsFields(parameters, self.PADDOCK_NAME_FIELD, context)[0]
        source_waterpoints = self.parameterAsSource(parameters, self.WATERPOINTS, context)
        dissolve_paddocks = self.parameterAsBool(parameters, self.DISSOLVE_PADDOCKS, context)
        watered_areas = self.parameterAsEnums(parameters, self.WATERED_AREAS, context)
        area_method = self.parameterAsEnum(parameters, self.AREA_METHOD, context)
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        load_outputs = self.parameterAsBool(parameters, self.LOAD_OUTPUTS, context)
        output_format = self.parameterAsEnum(parameters, self.OUTPUT_FORMAT, context)
        parsed_spreadsheet_params = self.parameterAsMatrix(parameters, self.OUTPUT_XLSX, context)
        export_spreadsheet = parsed_spreadsheet_params[0]# Boolean
        output_spreadsheet_path = parsed_spreadsheet_params[1]# String
        
        ###*******Calculate processing steps in advance*******###
        if dissolve_paddocks and len(watered_areas) == 2 and export_spreadsheet:
            steps = 8
        if dissolve_paddocks and len(watered_areas) == 2 and not export_spreadsheet:
            steps = 7
        if dissolve_paddocks and len(watered_areas) == 1 and export_spreadsheet:
            steps = 6
        if dissolve_paddocks and len(watered_areas) == 1 and not export_spreadsheet:
            steps = 5
        if dissolve_paddocks and len(watered_areas) == 0 and not export_spreadsheet:
            steps = 3
        if not dissolve_paddocks and len(watered_areas) == 2 and export_spreadsheet:
            steps = 5
        if not dissolve_paddocks and len(watered_areas) == 2 and not export_spreadsheet:
            steps = 4
        if not dissolve_paddocks and len(watered_areas) == 1 and export_spreadsheet:
            steps = 4
        if not dissolve_paddocks and len(watered_areas) == 1 and not export_spreadsheet:
            steps = 3
        if not dissolve_paddocks and len(watered_areas) == 0 and export_spreadsheet:
            steps = 3
        if not dissolve_paddocks and len(watered_areas) == 0 and not export_spreadsheet:
            steps = 2
        
        feedback = QgsProcessingMultiStepFeedback(steps, model_feedback)
        
        current_step = 1
        
        if feedback.isCanceled():
            return {}
        ###***************************************************###
        
        # Used to calculate land type areas if user selects ellipsoidal method
        da = QgsDistanceArea()
        
        # creates output destination folder
        if not QDir().mkpath(output_folder):
            raise QgsProcessingException('Failed to create output directory')
            return {}
        
        # Check CRS of paddock layer and transform to epsg:9473 if geographic
        src_crs = source_paddocks.sourceCrs()
        if src_crs.isGeographic():
            dest_crs = QgsCoordinateReferenceSystem('epsg:9473')# Transform to GDA2020 Albers (projected)
        else:
            dest_crs = src_crs
        
        # Create a QgsSpatialIndex from land type layer
        land_types_index = QgsSpatialIndex(source_land_types.getFeatures())
        
        # Create a single geometry object comprising all property paddocks
        all_pdks = QgsGeometry.unaryUnion([f.geometry() for f in source_paddocks.getFeatures()])
        
        # Construct a feature request of land types intersecting the property extent
        req = land_types_index.intersects(self.transformedGeom(all_pdks, source_paddocks.sourceCrs(), source_land_types.sourceCrs(), context.transformContext()).boundingBox())
        
        # Construct list of field indexes from output field names
        output_field_indexes = [source_land_types.fields().lookupField(fld) for fld in output_fields]
        
        # create temporary, transformed copy of land types with features intersecting property bounding box
        # We also filter land type attributes to selected output fields by chaining method calls
        local_land_types_projected = source_land_types.materialize(QgsFeatureRequest(req).setSubsetOfAttributes(output_field_indexes).setDestinationCrs(dest_crs, context.transformContext()))
        
        feedback.setCurrentStep(current_step)
        current_step+=1
        # Dissolve land types by the land unit/ map unit field
        local_land_types_projected_dissolved = processing.run("native:dissolve",
                                                                {'INPUT':local_land_types_projected,
                                                                'FIELD':unit_fields,
                                                                'OUTPUT':'TEMPORARY_OUTPUT'},
                                                                context=context,
                                                                feedback=feedback,
                                                                is_child_algorithm=True)
        
        outputs['local_land_types_projected_dissolved'] = local_land_types_projected_dissolved
        results['local_land_types_projected_dissolved'] = local_land_types_projected_dissolved['OUTPUT']
        lltpd_temp_result = context.getMapLayer(local_land_types_projected_dissolved['OUTPUT'])
        

        # Check if user selected option to calculate for whole property...
        if dissolve_paddocks:
            all_pdks_projected = self.transformedGeom(all_pdks, src_crs, dest_crs, context.transformContext()).makeValid()
            plt_path = os.path.join(output_folder, f'Property_land_types.{self.FORMATS[output_format]}')
            property_land_types_temp = QgsVectorLayer(f'Polygon?crs={dest_crs.authid()}', 'Property_land_types', 'memory')
            property_land_types_temp.dataProvider().addAttributes([fld for fld in source_land_types.fields() if fld.name() in output_fields])
            property_land_types_temp.dataProvider().addAttributes([QgsField('Area_m2', QVariant.Double, prec=3),
                                                                    QgsField('Area_ha', QVariant.Double, prec=3),
                                                                    QgsField('Area_km2', QVariant.Double, prec=5),
                                                                    QgsField('Percent', QVariant.Double, prec=2)])
            property_land_types_temp.updateFields()
            for ft in lltpd_temp_result.getFeatures():
                if ft.geometry().intersects(all_pdks_projected):
                    prop_ix = ft.geometry().intersection(all_pdks_projected)
                    prop_lt_feat = QgsFeature(property_land_types_temp.fields())
                    prop_lt_feat.setGeometry(prop_ix)
                    prop_atts = ft.attributes()
                    prop_area_atts = self.returnLandTypeAttributesForGeometry(prop_ix,
                                                                                all_pdks_projected,
                                                                                property_land_types_temp.sourceCrs(),
                                                                                area_method,
                                                                                context=context)
                    prop_atts.append(prop_area_atts[0])# area m2
                    prop_atts.append(prop_area_atts[1])# area ha
                    prop_atts.append(prop_area_atts[2])# area km2
                    prop_atts.append(prop_area_atts[3])# pcnt
                    prop_lt_feat.setAttributes(prop_atts)
                    property_land_types_temp.dataProvider().addFeatures([prop_lt_feat])
            if property_land_types_temp.isValid():
                    feedback.setCurrentStep(current_step)
                    current_step+=1
                    plt_result = processing.run("native:savefeatures",
                                                {'INPUT':property_land_types_temp,
                                                'OUTPUT':plt_path},
                                                context=context,
                                                feedback=feedback,
                                                is_child_algorithm=True)
                    
                    outputs['plt_result'] = plt_result
                    results['plt_result'] = plt_result['OUTPUT']
                    # Append path to output_layers list which will be used as inputs for export to spreadsheet
                    output_layers.append(plt_path)
                    if load_outputs:
                        self.layers_to_load.append(plt_path)
        
        # Extract land types and calculate areas for each paddock
        pdk_lt_path = os.path.join(output_folder, f'Paddock_land_types.{self.FORMATS[output_format]}')
        paddock_land_types_temp = QgsVectorLayer(f'Polygon?crs={dest_crs.authid()}', 'Paddock_land_types', 'memory')
        paddock_land_types_temp.dataProvider().addAttributes([QgsField('Paddock', QVariant.String)])
        paddock_land_types_temp.dataProvider().addAttributes([fld for fld in source_land_types.fields() if fld.name() in output_fields])
        paddock_land_types_temp.dataProvider().addAttributes([QgsField('Area_m2', QVariant.Double, prec=3),
                                                                QgsField('Area_ha', QVariant.Double, prec=3),
                                                                QgsField('Area_km2', QVariant.Double, prec=5),
                                                                QgsField('Percent', QVariant.Double, prec=2)])
        paddock_land_types_temp.updateFields()
        
        for pdk_ft in source_paddocks.getFeatures():
            pdk_geom = self.transformedGeom(pdk_ft.geometry(), src_crs, dest_crs, context.transformContext())
            for lt_ft in lltpd_temp_result.getFeatures():
                if lt_ft.geometry().intersects(pdk_geom):
                    pdk_ix = lt_ft.geometry().intersection(pdk_geom)
                    pdk_lt_feat = QgsFeature(paddock_land_types_temp.fields())
                    pdk_lt_feat.setGeometry(pdk_ix)
                    pdk_lt_atts = ['Un-named paddock' if pdk_ft[paddock_name_field] == NULL else pdk_ft[paddock_name_field]]#*************
                    for a in lt_ft.attributes():
                        pdk_lt_atts.append(a)
                    pdk_area_atts = self.returnLandTypeAttributesForGeometry(pdk_ix,
                                                                            pdk_geom,
                                                                            paddock_land_types_temp.sourceCrs(),
                                                                            area_method,
                                                                            context=context)
                    pdk_lt_atts.append(pdk_area_atts[0])# area m2
                    pdk_lt_atts.append(pdk_area_atts[1])# area ha
                    pdk_lt_atts.append(pdk_area_atts[2])# area km2
                    pdk_lt_atts.append(pdk_area_atts[3])# pcnt
                    pdk_lt_feat.setAttributes(pdk_lt_atts)
                    paddock_land_types_temp.dataProvider().addFeatures([pdk_lt_feat])
                    
        if paddock_land_types_temp.isValid():
            feedback.setCurrentStep(current_step)
            current_step+=1
            pdk_lt_result = processing.run("native:savefeatures",
                                        {'INPUT':paddock_land_types_temp,
                                        'OUTPUT':pdk_lt_path},
                                        context=context,
                                        feedback=feedback,
                                        is_child_algorithm=True)
                                        
            outputs['pdk_lt_result'] = pdk_lt_result
            results['pdk_lt_result'] = pdk_lt_result['OUTPUT']
            # Append path to output_layers list which will be used as inputs for export to spreadsheet
            output_layers.append(pdk_lt_path)
            if load_outputs:
                self.layers_to_load.append(pdk_lt_path)
        
        
        # Check if user selected to calculate land types for watered areas
        if source_waterpoints:
            waterpoints_projected = source_waterpoints.materialize(QgsFeatureRequest().setDestinationCrs(dest_crs, context.transformContext()))
            if 0 in watered_areas:
                # User wants 3km watered area land types
                buffers_3k = [ft.geometry().buffer(3000, 25) for ft in waterpoints_projected.getFeatures()]
                # Dissolve 3km buffers
                buffers_3k_dissolved = QgsGeometry.unaryUnion(buffers_3k)
                # Check if user selected option to calculate for whole property...
                if dissolve_paddocks:
                    prop_3k_wa = buffers_3k_dissolved.intersection(all_pdks_projected)
                    prop_3k_wa_lt_path = os.path.join(output_folder, f'Property_3km_WA_land_types.{self.FORMATS[output_format]}')
                    prop_3k_wa_land_types_temp = QgsVectorLayer(f'Polygon?crs={dest_crs.authid()}', 'Property_3km_WA_land_types', 'memory')
                    prop_3k_wa_land_types_temp.dataProvider().addAttributes([fld for fld in source_land_types.fields() if fld.name() in output_fields])
                    prop_3k_wa_land_types_temp.dataProvider().addAttributes([QgsField('Area_m2', QVariant.Double, prec=3),
                                                                            QgsField('Area_ha', QVariant.Double, prec=3),
                                                                            QgsField('Area_km2', QVariant.Double, prec=5),
                                                                            QgsField('Percent', QVariant.Double, prec=2)])
                    prop_3k_wa_land_types_temp.updateFields()
                    for ft in lltpd_temp_result.getFeatures():
                        if ft.geometry().intersects(prop_3k_wa):
                            prop_3k_wa_land_types_ix = ft.geometry().intersection(prop_3k_wa)
                            prop_3k_wa_lt_feat = QgsFeature(property_land_types_temp.fields())
                            prop_3k_wa_lt_feat.setGeometry(prop_3k_wa_land_types_ix)
                            prop_3k_wa_atts = ft.attributes()
                            prop_3k_wa_area_atts = self.returnLandTypeAttributesForGeometry(prop_3k_wa_land_types_ix,
                                                                                        prop_3k_wa,
                                                                                        prop_3k_wa_land_types_temp.sourceCrs(),
                                                                                        area_method,
                                                                                        context=context)
                            prop_3k_wa_atts.append(prop_3k_wa_area_atts[0])# area m2
                            prop_3k_wa_atts.append(prop_3k_wa_area_atts[1])# area ha
                            prop_3k_wa_atts.append(prop_3k_wa_area_atts[2])# area km2
                            prop_3k_wa_atts.append(prop_3k_wa_area_atts[3])# pcnt
                            prop_3k_wa_lt_feat.setAttributes(prop_3k_wa_atts)
                            prop_3k_wa_land_types_temp.dataProvider().addFeatures([prop_3k_wa_lt_feat])
                    if prop_3k_wa_land_types_temp.isValid():
                        feedback.setCurrentStep(current_step)
                        current_step+=1
                        prop_3k_wa_lt_result = processing.run("native:savefeatures",
                                                                {'INPUT':prop_3k_wa_land_types_temp,
                                                                'OUTPUT':prop_3k_wa_lt_path},
                                                                context=context,
                                                                feedback=feedback,
                                                                is_child_algorithm=True)
                                                                
                        outputs['prop_3k_wa_lt_result'] = prop_3k_wa_lt_result
                        results['prop_3k_wa_lt_result'] = prop_3k_wa_lt_result['OUTPUT']
                        # Append path to output_layers list which will be used as inputs for export to spreadsheet
                        output_layers.append(prop_3k_wa_lt_path)
                        if load_outputs:
                            self.layers_to_load.append(prop_3k_wa_lt_path)
                # Now calculate land types for 3km buffers per paddock
                #--For each paddock, get intersection of paddock and dissolved 3km WA,
                #--Then, for each land type, get the intersection with the paddock watered area
                #-- and calculate the areas and add a feature to the temp output layer
                pdk_3k_wa_lt_path = os.path.join(output_folder, f'Paddock_3km_WA_land_types.{self.FORMATS[output_format]}')
                pdk_3k_wa_land_types_temp = QgsVectorLayer(f'Polygon?crs={dest_crs.authid()}', 'Paddock_3km_WA_land_types', 'memory')
                pdk_3k_wa_land_types_temp.dataProvider().addAttributes([QgsField('Paddock', QVariant.String)])
                pdk_3k_wa_land_types_temp.dataProvider().addAttributes([fld for fld in source_land_types.fields() if fld.name() in output_fields])
                pdk_3k_wa_land_types_temp.dataProvider().addAttributes([QgsField('Area_m2', QVariant.Double, prec=3),
                                                                        QgsField('Area_ha', QVariant.Double, prec=3),
                                                                        QgsField('Area_km2', QVariant.Double, prec=5),
                                                                        QgsField('Percent', QVariant.Double, prec=2)])
                pdk_3k_wa_land_types_temp.updateFields()
                for pdk_ft in source_paddocks.getFeatures():
                    pdk_geom = self.transformedGeom(pdk_ft.geometry(), src_crs, dest_crs, context.transformContext())
                    pdk_3km_wa_geom = buffers_3k_dissolved.intersection(pdk_geom)
                    for lt_ft in lltpd_temp_result.getFeatures():
                        if lt_ft.geometry().intersects(pdk_3km_wa_geom):
                            #*Test...
                            #feedback.pushDebugInfo('Heyyy, intersection found')
                            #*
                            pdk_3km_wa_ix = lt_ft.geometry().intersection(pdk_3km_wa_geom)
                            pdk_3km_wa_lt_feat = QgsFeature(pdk_3k_wa_land_types_temp.fields())
                            pdk_3km_wa_lt_feat.setGeometry(pdk_3km_wa_ix)
                            pdk_3km_wa_lt_atts = ['Un-named paddock' if pdk_ft[paddock_name_field] == NULL else pdk_ft[paddock_name_field]]
                            for a in lt_ft.attributes():
                                pdk_3km_wa_lt_atts.append(a)
                            pdk_3km_wa_area_atts = self.returnLandTypeAttributesForGeometry(pdk_3km_wa_ix,
                                                                                    pdk_3km_wa_geom,
                                                                                    paddock_land_types_temp.sourceCrs(),
                                                                                    area_method,
                                                                                    context=context)
                            pdk_3km_wa_lt_atts.append(pdk_3km_wa_area_atts[0])# area m2
                            pdk_3km_wa_lt_atts.append(pdk_3km_wa_area_atts[1])# area ha
                            pdk_3km_wa_lt_atts.append(pdk_3km_wa_area_atts[2])# area km2
                            pdk_3km_wa_lt_atts.append(pdk_3km_wa_area_atts[3])# pcnt
                            pdk_3km_wa_lt_feat.setAttributes(pdk_3km_wa_lt_atts)
                            feature_added = pdk_3k_wa_land_types_temp.dataProvider().addFeatures([pdk_3km_wa_lt_feat])
                            #*Test...
#                            feedback.pushDebugInfo(repr(feature_added[0]))
#                            feedback.pushDebugInfo(repr(pdk_3k_wa_land_types_temp.dataProvider().lastError()))
                            #*
                if pdk_3k_wa_land_types_temp.isValid():
                    feedback.setCurrentStep(current_step)
                    current_step+=1
                    pdk_3km_wa_lt_result = processing.run("native:savefeatures",
                                                {'INPUT':pdk_3k_wa_land_types_temp,
                                                'OUTPUT':pdk_3k_wa_lt_path},
                                                context=context,
                                                feedback=feedback,
                                                is_child_algorithm=True)
                                                
                    outputs['pdk_3km_wa_lt_result'] = pdk_3km_wa_lt_result
                    results['pdk_3km_wa_lt_result'] = pdk_3km_wa_lt_result['OUTPUT']
                    # Append path to output_layers list which will be used as inputs for export to spreadsheet
                    output_layers.append(pdk_3k_wa_lt_path)
                    if load_outputs:
                        self.layers_to_load.append(pdk_3k_wa_lt_path)
#*********************************************************************************************************************
            if 1 in watered_areas:
                # User wants 5km watered area land types
                buffers_5k = [ft.geometry().buffer(5000, 25) for ft in waterpoints_projected.getFeatures()]
                # Dissolve 5km buffers
                buffers_5k_dissolved = QgsGeometry.unaryUnion(buffers_5k)
                # Check if user selected option to calculate for whole property...
                if dissolve_paddocks:
                    prop_5k_wa = buffers_5k_dissolved.intersection(all_pdks_projected)
                    prop_5k_wa_lt_path = os.path.join(output_folder, f'Property_5km_WA_land_types.{self.FORMATS[output_format]}')
                    prop_5k_wa_land_types_temp = QgsVectorLayer(f'Polygon?crs={dest_crs.authid()}', 'Property_5km_WA_land_types', 'memory')
                    prop_5k_wa_land_types_temp.dataProvider().addAttributes([fld for fld in source_land_types.fields() if fld.name() in output_fields])
                    prop_5k_wa_land_types_temp.dataProvider().addAttributes([QgsField('Area_m2', QVariant.Double, prec=3),
                                                                            QgsField('Area_ha', QVariant.Double, prec=3),
                                                                            QgsField('Area_km2', QVariant.Double, prec=5),
                                                                            QgsField('Percent', QVariant.Double, prec=2)])
                    prop_5k_wa_land_types_temp.updateFields()
                    for ft in lltpd_temp_result.getFeatures():
                        if ft.geometry().intersects(prop_5k_wa):
                            prop_5k_wa_land_types_ix = ft.geometry().intersection(prop_5k_wa)
                            prop_5k_wa_lt_feat = QgsFeature(property_land_types_temp.fields())
                            prop_5k_wa_lt_feat.setGeometry(prop_5k_wa_land_types_ix)
                            prop_5k_wa_atts = ft.attributes()
                            prop_5k_wa_area_atts = self.returnLandTypeAttributesForGeometry(prop_5k_wa_land_types_ix,
                                                                                        prop_5k_wa,
                                                                                        prop_5k_wa_land_types_temp.sourceCrs(),
                                                                                        area_method,
                                                                                        context=context)
                            prop_5k_wa_atts.append(prop_5k_wa_area_atts[0])# area m2
                            prop_5k_wa_atts.append(prop_5k_wa_area_atts[1])# area ha
                            prop_5k_wa_atts.append(prop_5k_wa_area_atts[2])# area km2
                            prop_5k_wa_atts.append(prop_5k_wa_area_atts[3])# pcnt
                            prop_5k_wa_lt_feat.setAttributes(prop_5k_wa_atts)
                            prop_5k_wa_land_types_temp.dataProvider().addFeatures([prop_5k_wa_lt_feat])
                    if prop_5k_wa_land_types_temp.isValid():
                        feedback.setCurrentStep(current_step)
                        current_step+=1
                        prop_5k_wa_lt_result = processing.run("native:savefeatures",
                                                                {'INPUT':prop_5k_wa_land_types_temp,
                                                                'OUTPUT':prop_5k_wa_lt_path},
                                                                context=context,
                                                                feedback=feedback,
                                                                is_child_algorithm=True)
                                                                
                        outputs['prop_5k_wa_lt_result'] = prop_5k_wa_lt_result
                        results['prop_5k_wa_lt_result'] = prop_5k_wa_lt_result['OUTPUT']
                        # Append path to output_layers list which will be used as inputs for export to spreadsheet
                        output_layers.append(prop_5k_wa_lt_path)
                        if load_outputs:
                            self.layers_to_load.append(prop_5k_wa_lt_path)
                # Now calculate land types for 5km buffers per paddock
                #--For each paddock, get intersection of paddock and dissolved 5km WA,
                #--Then, for each land type, get the intersection with the paddock watered area
                #-- and calculate the areas and add a feature to the temp output layer
                pdk_5k_wa_lt_path = os.path.join(output_folder, f'Paddock_5km_WA_land_types.{self.FORMATS[output_format]}')
                pdk_5k_wa_land_types_temp = QgsVectorLayer(f'Polygon?crs={dest_crs.authid()}', 'Paddock_5km_WA_land_types', 'memory')
                pdk_5k_wa_land_types_temp.dataProvider().addAttributes([QgsField('Paddock', QVariant.String)])
                pdk_5k_wa_land_types_temp.dataProvider().addAttributes([fld for fld in source_land_types.fields() if fld.name() in output_fields])
                pdk_5k_wa_land_types_temp.dataProvider().addAttributes([QgsField('Area_m2', QVariant.Double, prec=3),
                                                                        QgsField('Area_ha', QVariant.Double, prec=3),
                                                                        QgsField('Area_km2', QVariant.Double, prec=5),
                                                                        QgsField('Percent', QVariant.Double, prec=2)])
                pdk_5k_wa_land_types_temp.updateFields()
                for pdk_ft in source_paddocks.getFeatures():
                    pdk_geom = self.transformedGeom(pdk_ft.geometry(), src_crs, dest_crs, context.transformContext())
                    pdk_5km_wa_geom = buffers_5k_dissolved.intersection(pdk_geom)
                    for lt_ft in lltpd_temp_result.getFeatures():
                        if lt_ft.geometry().intersects(pdk_5km_wa_geom):
                            #*Test...
                            #feedback.pushDebugInfo('Intersection found')
                            #*
                            pdk_5km_wa_ix = lt_ft.geometry().intersection(pdk_5km_wa_geom)
                            pdk_5km_wa_lt_feat = QgsFeature(pdk_5k_wa_land_types_temp.fields())
                            pdk_5km_wa_lt_feat.setGeometry(pdk_5km_wa_ix)
                            pdk_5km_wa_lt_atts = ['Un-named paddock' if pdk_ft[paddock_name_field] == NULL else pdk_ft[paddock_name_field]]
                            for a in lt_ft.attributes():
                                pdk_5km_wa_lt_atts.append(a)
                            pdk_5km_wa_area_atts = self.returnLandTypeAttributesForGeometry(pdk_5km_wa_ix,
                                                                                    pdk_5km_wa_geom,
                                                                                    paddock_land_types_temp.sourceCrs(),
                                                                                    area_method,
                                                                                    context=context)
                            pdk_5km_wa_lt_atts.append(pdk_5km_wa_area_atts[0])# area m2
                            pdk_5km_wa_lt_atts.append(pdk_5km_wa_area_atts[1])# area ha
                            pdk_5km_wa_lt_atts.append(pdk_5km_wa_area_atts[2])# area km2
                            pdk_5km_wa_lt_atts.append(pdk_5km_wa_area_atts[3])# pcnt
                            pdk_5km_wa_lt_feat.setAttributes(pdk_5km_wa_lt_atts)
                            feature_added = pdk_5k_wa_land_types_temp.dataProvider().addFeatures([pdk_5km_wa_lt_feat])
                            #*Test...
#                            feedback.pushDebugInfo(repr(feature_added[0]))
#                            feedback.pushDebugInfo(repr(pdk_5k_wa_land_types_temp.dataProvider().lastError()))
                            #*
                if pdk_5k_wa_land_types_temp.isValid():
                    feedback.setCurrentStep(current_step)
                    current_step+=1
                    pdk_5km_wa_lt_result = processing.run("native:savefeatures",
                                                {'INPUT':pdk_5k_wa_land_types_temp,
                                                'OUTPUT':pdk_5k_wa_lt_path},
                                                context=context,
                                                feedback=feedback,
                                                is_child_algorithm=True)
                                                
                    outputs['pdk_5km_wa_lt_result'] = pdk_5km_wa_lt_result
                    results['pdk_5km_wa_lt_result'] = pdk_5km_wa_lt_result['OUTPUT']
                    # Append path to output_layers list which will be used as inputs for export to spreadsheet
                    output_layers.append(pdk_5k_wa_lt_path)
                    if load_outputs:
                        self.layers_to_load.append(pdk_5k_wa_lt_path)
                            
        ####################Create XLSX report###########################
        #Export report to spreadsheet
        if export_spreadsheet:
            if output_spreadsheet_path == '':
                output_spreadsheet_path = os.path.join(output_folder, 'Land_types_summary.xlsx')
            
            feedback.setCurrentStep(current_step)
            current_step+=1
            export_params = {'LAYERS':output_layers,
                                'USE_ALIAS':False,
                                'FORMATTED_VALUES':False,
                                'OUTPUT':output_spreadsheet_path,
                                'OVERWRITE':False}

            outputs['Report_spreadsheet'] = processing.run("native:exporttospreadsheet",
                                                            export_params,
                                                            context=context,
                                                            feedback=feedback,
                                                            is_child_algorithm=True)
                            
            results['Report_spreadsheet'] = outputs['Report_spreadsheet']['OUTPUT']
        
        return results
        
        
    def postProcessAlgorithm(self, context, feedback):
        for uri in self.layers_to_load:
            lyr_name = Path(uri).stem
            ml = QgsVectorLayer(uri, lyr_name, 'ogr')
            context.project().addMapLayers([ml])
        self.layers_to_load.clear()
        return {}
        
    def transformedGeom(self, g, orig_crs, target_crs, transform_context):
        geom_copy = QgsGeometry().fromWkt(g.asWkt())
        if orig_crs != target_crs:
            xform = QgsCoordinateTransform(orig_crs, target_crs, transform_context)
            geom_copy.transform(xform)
        return geom_copy
        
    def returnLandTypeAttributesForGeometry(self, land_type_geom, pdk_geom, ellipsoidal_crs, calc_method, context=None):
        if calc_method == 1:# Planar
            plt_area_m2 = round(land_type_geom.area(), 3)
            plt_area_ha = round(land_type_geom.area()/10000, 3)
            plt_area_km2 = round(land_type_geom.area()/1000000, 5)
            plt_pcnt = (land_type_geom.area()/pdk_geom.area())*100
        elif calc_method == 0:# Ellipsoidal
            self.da.setSourceCrs(ellipsoidal_crs, context.transformContext())
            self.da.setEllipsoid(ellipsoidal_crs.ellipsoidAcronym())
            plt_area = self.da.measureArea(land_type_geom)
            plt_area_m2 = round(plt_area, 3)
            plt_area_ha = round(self.da.convertAreaMeasurement(plt_area, QgsUnitTypes.AreaHectares), 3)
            plt_area_km2 = round(self.da.convertAreaMeasurement(plt_area, QgsUnitTypes.AreaSquareKilometers), 5)
            plt_pcnt = (plt_area/self.da.measureArea(pdk_geom))*100
            
        return (plt_area_m2, plt_area_ha, plt_area_km2, plt_pcnt)


class CustomParametersWidgetWrapper(WidgetWrapper):
    def createWidget(self):
        self.spw = SpreadsheetParamsWidget()
        return self.spw
        
    def value(self):
        save_spreadsheet = self.spw.saveToSpreadsheet()
        save_location = self.spw.saveFilePath()
        return [save_spreadsheet, save_location]


class SpreadsheetParamsWidget(QWidget):
    def __init__(self):
        super(SpreadsheetParamsWidget, self).__init__()
        self.setGeometry(500, 500, 600, 300)
        self.layout = QVBoxLayout(self)
        self.output_xlsx_checkbox = QCheckBox('Create summary spreadsheet report? [will not be loaded on completetion]', self)
        self.output_xlsx_checkbox.stateChanged.connect(self.manageSaveWidget)
        self.output_lbl = QLabel('Land type summary spreadsheet. Leave empty to save to output folder', self)
        self.file_widget = SpreadsheetDestinationFileWidget(self)
        self.file_widget.setEnabled(False)
        self.layout.addWidget(self.output_xlsx_checkbox)
        self.layout.addStretch()
        self.layout.addWidget(self.output_lbl)
        self.layout.addWidget(self.file_widget)
        
    def manageSaveWidget(self):
        if self.output_xlsx_checkbox.checkState() == Qt.Unchecked:
            if self.file_widget.isEnabled():
                self.file_widget.setEnabled(False)
        else:
            if not self.file_widget.isEnabled():
                self.file_widget.setEnabled(True)
                
    def saveToSpreadsheet(self):
        return self.output_xlsx_checkbox.isChecked()
        
    def saveFilePath(self):
        #Will return '' if user leaves placeholder text
        return self.file_widget.file_save_widget.text()

        
class SpreadsheetDestinationFileWidget(QWidget):
    def __init__(self, parent):
        self.parent = parent
        super(SpreadsheetDestinationFileWidget, self).__init__()
        self.layout = QHBoxLayout(self)
        self.file_save_widget = QLineEdit('', self)
        self.file_save_widget.setPlaceholderText('Save to output folder')
        self.file_dialog_btn = QPushButton('\u2026', self)
        self.file_dialog_btn.setToolTip('Save to file location')
        self.file_dialog_btn.setMaximumWidth(30)
        self.file_dialog_btn.clicked.connect(self.setDestinationFilePath)
        self.layout.addWidget(self.file_save_widget)
        self.layout.addWidget(self.file_dialog_btn)

    def setDestinationFilePath(self):
        file_path = QFileDialog.getSaveFileName(None, 'Save output spreadsheet', '', filter='Microsoft Excel (*.xlsx);;Open Document Spreadsheet (*.ods)')
        self.file_save_widget.setText(file_path[0])
        