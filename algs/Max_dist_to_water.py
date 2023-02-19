from qgis.PyQt.QtCore import QCoreApplication, QVariant, QDir
from qgis.PyQt.QtGui import QIcon
from qgis.core import (QgsFeatureRequest,
                        QgsFeature,
                        QgsFields,
                        QgsField,
                        QgsProcessing,
                        QgsProcessingAlgorithm,
                        QgsProcessingParameterFeatureSource,
                        QgsProcessingParameterField,
                        QgsProcessingParameterFolderDestination,
                        QgsProcessingParameterBoolean,
                        QgsProcessingMultiStepFeedback,
                        QgsVectorLayer,
                        QgsRasterLayer,
                        QgsWkbTypes,
                        QgsProcessingParameterNumber,
                        QgsProcessingOutputMultipleLayers,
                        QgsProcessingException,
                        QgsProcessingContext,
                        QgsGradientColorRamp,
                        QgsSingleBandPseudoColorRenderer,
                        QgsColorRampShader,
                        QgsMapLayerType)

from osgeo import gdal
from pathlib import Path
import os
import re
import math
import processing
                       
class MaxDistToWater(QgsProcessingAlgorithm):
    PADDOCKS = 'PADDOCKS'
    PADDOCK_NAME_FIELD = 'PADDOCK_NAME_FIELD'
    WATER_POINTS = 'WATER_POINTS'
    OUTPUT_RESOLUTION = 'OUTPUT_RESOLUTION'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'
    CREATE_REPORT = 'CREATE_REPORT'
    OUTPUT_LAYERS = 'OUTPUT_LAYERS'
    LOAD_OUTPUTS = 'LOAD_OUTPUTS'
    
    GLOBAL_MAXIMUM_DTW = None
    
    LAYERS_TO_LOAD = []

 
    def __init__(self):
        super().__init__()
 
    def name(self):
        return "waterproximity"
     
         
    def displayName(self):
        return "Water proximity"
 
    def group(self):
        return "Analysis"
 
    def groupId(self):
        return "analysis"
        
    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "../icons/mdtw_icon.png"))
 
    def shortHelpString(self):
        return "Calculates maximum distance to water for each paddock\
                in an input polygon layer based on water points from\
                an input point layer.<br>Input layers with different CRS settings\
                are handled as follows: if only one input layer is projected\
                the geographic layer will be transformed to the other's projected\
                CRS. If both input layers use geographic coordinates, they will both be\
                transformed to EPSG:9473 GDA 2020/ Australian Albers.\
                <br>Outputs are a proximity raster generated for each paddock\
                and an optional spreadsheet report.\
                If the option to load and style output rasters is selected, the\
                resulting layers will be added to the current project in a group\
                called 'water proximity'. An interpolated gradient style will be\
                applied to each raster, based on the maximum distance to water\
                for all paddocks."
 
    def helpUrl(self):
        return "https://qgis.org"
         
    def createInstance(self):
        return type(self)()
   
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.PADDOCKS,
            "Input paddocks layer",
            [QgsProcessing.TypeVectorPolygon]))
            
        self.addParameter(QgsProcessingParameterField(
            self.PADDOCK_NAME_FIELD,
            "Paddock name field (output names will be generic if not selected)",
            parentLayerParameterName=self.PADDOCKS,
            type=QgsProcessingParameterField.String,
            optional=True))
            
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.WATER_POINTS,
            "Input water points layer",
            [QgsProcessing.TypeVectorPoint]))
            
        self.addParameter(QgsProcessingParameterNumber(
            self.OUTPUT_RESOLUTION,
            "Pixel size (resolution) for output proximity rasters",
            defaultValue=25,
            minValue=5.0,
            maxValue=100.0))
            
        self.addParameter(QgsProcessingParameterBoolean(
            self.CREATE_REPORT,
            "Create report spreadsheet?",
            defaultValue=True))
            
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_FOLDER,
            "Folder for output files"))
        
        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_OUTPUTS,
            "Load and style output rasters?",
            defaultValue=False))
        
        '''
        Prime suspect (output param) in case of crash/freeze- remove this first
        '''
        self.addOutput(QgsProcessingOutputMultipleLayers(
            self.OUTPUT_LAYERS,
            "Output layers"))
 
    def processAlgorithm(self, parameters, context, model_feedback):
        results = {}
        outputs = {}
        
        source_paddocks = self.parameterAsSource(parameters, self.PADDOCKS, context)
        # list of field names...
        fields = self.parameterAsFields(parameters, self.PADDOCK_NAME_FIELD, context)
        if fields:
            paddock_name_field = fields[0]
            pdk_name_fld_idx = source_paddocks.fields().lookupField(paddock_name_field)
            pdk_attribute_subset = [pdk_name_fld_idx]
        else:
            paddock_name_field = None
            pdk_attribute_subset = []
            
        source_waterpoints = self.parameterAsSource(parameters, self.WATER_POINTS, context)
        output_resolution = self.parameterAsInt(parameters, self.OUTPUT_RESOLUTION, context)
        export_report = self.parameterAsBool(parameters, self.CREATE_REPORT, context)
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        load_outputs = self.parameterAsBool(parameters, self.LOAD_OUTPUTS, context)
        
        if not QDir().mkpath(output_folder):
            raise QgsProcessingException('Failed to create output directory')
            return {}
        
        for ft in source_paddocks.getFeatures():
            if not ft.geometry().isGeosValid():
                raise QgsProcessingException(f"Feature in layer: {source_paddocks.sourceName()} with id: {ft.id()} has invalid geometry")
                return {}
        
        #############Transform either or both input layer/s if geographic#############
        #I won't fully trust the logic in this block until I test it thoroughly...
        #hence, if something isn't working- start debugging here.
        
        # paddocks projected but waterpoints geographic
        if not source_paddocks.sourceCrs().isGeographic() and source_waterpoints.sourceCrs().isGeographic():
            crs = source_paddocks.sourceCrs()
            prepared_paddocks = source_paddocks.materialize(QgsFeatureRequest().setSubsetOfAttributes(pdk_attribute_subset))
            prepared_waterpoints = source_waterpoints.materialize(QgsFeatureRequest().setSubsetOfAttributes([]).setDestinationCrs(crs, context.transformContext()))
        # water points projected but paddocks geographic
        elif source_paddocks.sourceCrs().isGeographic() and not source_waterpoints.sourceCrs().isGeographic():
            crs = source_waterpoints.sourceCrs()
            prepared_paddocks = source_paddocks.materialize(QgsFeatureRequest().setSubsetOfAttributes(pdk_attribute_subset).setDestinationCrs(crs, context.transformContext()))
            prepared_waterpoints = source_waterpoints.materialize(QgsFeatureRequest().setSubsetOfAttributes([]))
        # both inputs geographic (we 'transform' to epsg:9473 GDA202 Australian Albers)
        elif source_paddocks.sourceCrs().isGeographic() and source_waterpoints.sourceCrs().isGeographic():
            crs = QgsCoordinateReferenceSystem('epsg:9473')
            prepared_paddocks = source_paddocks.materialize(QgsFeatureRequest().setSubsetOfAttributes(pdk_attribute_subset).setDestinationCrs(crs, context.transformContext()))
            prepared_waterpoints = source_waterpoints.materialize(QgsFeatureRequest().setSubsetOfAttributes([]).setDestinationCrs(crs, context.transformContext()))
        # both inputs are projected
        else:
            # projected input crs are different (we 'transform' waterpoints to paddocks crs)
            if source_paddocks.sourceCrs() != source_waterpoints.sourceCrs():
                crs = source_paddocks.sourceCrs()
                prepared_waterpoints = source_waterpoints.materialize(QgsFeatureRequest().setSubsetOfAttributes([]).setDestinationCrs(crs, context.transformContext()))
                prepared_paddocks = source_paddocks.materialize(QgsFeatureRequest().setSubsetOfAttributes(pdk_attribute_subset))
            # both projected input crs are the same
            else:
                crs = source_paddocks.sourceCrs()
                prepared_paddocks = source_paddocks.materialize(QgsFeatureRequest().setSubsetOfAttributes(pdk_attribute_subset))
                prepared_waterpoints = source_waterpoints.materialize(QgsFeatureRequest().setSubsetOfAttributes([]))
            
        ########################################################################
        
        ###Calculate number of paddocks containing at least one waterpoint######
        analyzed_paddocks = [ft for ft in prepared_paddocks.getFeatures() if [f for f in prepared_waterpoints.getFeatures() if f.geometry().intersects(ft.geometry())]]
#        model_feedback.pushInfo(repr(analyzed_paddocks))
        ########################################################################
        steps = (len(analyzed_paddocks)*3)+1
        feedback = QgsProcessingMultiStepFeedback(steps, model_feedback)
        step = 1
        
        if feedback.isCanceled():
            return {}
        
        outputLayers = []
        
        info_map = {}# Used to store the info create the xlsx report
        
        maximums = []# will append max of each paddock, then find global max
        
        # Iterate over each paddock
        for i, paddock in enumerate(prepared_paddocks.getFeatures()):
            # Simple spatial query to retrieve water points within each paddock
            waterpoint_feats = [f for f in prepared_waterpoints.getFeatures() if f.geometry().intersects(paddock.geometry())]
#            model_feedback.pushInfo(repr(waterpoint_feats))
            if not waterpoint_feats:
                continue
            paddock_info = []# will be added to info_map dict as value against paddock name key
            
            if paddock_name_field:
                pdk_name = paddock[paddock_name_field].replace("'", "")
                paddock_name = re.sub('[^a-zA-Z0-9]+', '_', pdk_name)
            else:
                paddock_name = f'Paddock_{i}'
            
            paddock_info.append(paddock_name)
            paddock_info.append(paddock.geometry().area()/10000)# area in hectares
            paddock_info.append(len(waterpoint_feats))
            model_feedback.pushInfo(repr(crs))
            # Create a temporary layer to hold waterpoint features which fall within each paddock
            tmp_lyr = QgsVectorLayer(f'Point?crs={crs.authid()}', '', 'memory')
            tmp_lyr.dataProvider().addFeatures(waterpoint_feats)
            
            ############################################################################
            # Rasterise temporary waterpoint layer to create a binary raster where pixel value
            # is 1 at water locations and 0 everywhere else
            raster_extent = paddock.geometry().boundingBox()
            xmin = raster_extent.xMinimum()
            xmax = raster_extent.xMaximum()
            ymin = raster_extent.yMinimum()
            ymax = raster_extent.yMaximum()
            
            extent_string = f'{xmin},{xmax},{ymin},{ymax} [{tmp_lyr.crs().authid()}]'
            #extent_string = '670539.640100000,674839.662800000,8101017.562800000,8103145.602500000 [EPSG:28352]'
            
            rasterize_params = {'INPUT':tmp_lyr,
                                'FIELD':'',
                                'BURN':1,
                                'USE_Z':False,
                                'UNITS':1,
                                'WIDTH':output_resolution,
                                'HEIGHT':output_resolution,
                                'EXTENT':extent_string,
                                'NODATA':-1,
                                'OPTIONS':'',
                                'DATA_TYPE':0,
                                'INIT':0,
                                'INVERT':False,
                                'EXTRA':'',
                                'OUTPUT':'TEMPORARY_OUTPUT'}
            
            feedback.setCurrentStep(step)
            step+=1
            outputs[f'rasterized_{paddock_name}'] = processing.run("gdal:rasterize", rasterize_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'rasterized_{paddock_name}'] = outputs[f'rasterized_{paddock_name}']['OUTPUT']
            #####################################################################################
            # Calculate Proximity Raster for each waterpoint binary raster...
            proximity_params = {'INPUT':results[f'rasterized_{paddock_name}'],
                                'BAND':1,
                                'VALUES':'1',
                                'UNITS':0,
                                'MAX_DISTANCE':0,
                                'REPLACE':0,
                                'NODATA':0,
                                'OPTIONS':'',
                                'EXTRA':'',
                                'DATA_TYPE':5,
                                'OUTPUT':'TEMPORARY_OUTPUT'}
                                
            feedback.setCurrentStep(step)
            step+=1
            outputs[f'proximity_{paddock_name}'] = processing.run("gdal:proximity", proximity_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'proximity_{paddock_name}'] = outputs[f'proximity_{paddock_name}']['OUTPUT']
            ############################################################################
            #*Use materialize()
            paddock_layer_subset = prepared_paddocks.materialize(QgsFeatureRequest(paddock.id()))
            
            clipped_path = os.path.join(output_folder, f'{paddock_name}.tif')
            
            clip_params = {'INPUT':results[f'proximity_{paddock_name}'],
                            'MASK':paddock_layer_subset,
                            'SOURCE_CRS':None,
                            'TARGET_CRS':None,
                            'NODATA':-9999,
                            'ALPHA_BAND':False,
                            'CROP_TO_CUTLINE':True,
                            'KEEP_RESOLUTION':False,
                            'SET_RESOLUTION':False,
                            'X_RESOLUTION':None,
                            'Y_RESOLUTION':None,
                            'MULTITHREADING':False,
                            'OPTIONS':'',
                            'DATA_TYPE':0,
                            'EXTRA':'',
                            'OUTPUT':clipped_path}

            feedback.setCurrentStep(step)
            step+=1
            outputLayers.append(clipped_path)
            outputs[f'clipped_{paddock_name}'] = processing.run("gdal:cliprasterbymasklayer", clip_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'clipped_{paddock_name}'] = outputs[f'clipped_{paddock_name}']['OUTPUT']
            result_raster = gdal.Open(results[f'clipped_{paddock_name}'])
            b1_stats = result_raster.GetRasterBand(1).GetStatistics(0, 1)
#            max = result_raster.dataProvider().bandStatistics(1).maximumValue# in meters
            local_max = b1_stats[1]
            maximums.append(local_max)
            paddock_info.append(round(local_max/1000, 5))
            info_map[paddock_name] = paddock_info
            result_raster = None
#            model_feedback.pushInfo(f'PADDOCK INFO >>>{repr(info_map)}')            
            # calculate global maximum (max of all paddock maxima)
            flt_max = max(maximums) # will be a long float
            
        #Outside loop
        self.GLOBAL_MAXIMUM_DTW = math.ceil(flt_max)# this will be maximum value used for renderer classification
        #############Load and style output rasters if requested############
        if load_outputs:
            for f_path in outputLayers:
                file_name = Path(f_path).stem
                rl = QgsRasterLayer(f_path, file_name, 'gdal')
                if rl.isValid():
                    self.LAYERS_TO_LOAD.append(rl)

        ####################Create XLSX report###########################
        # check if user requested to export report spreadsheet
        if export_report:
            #Export report to spreadsheet
            options = QgsVectorLayer.LayerOptions()
            options.loadDefaultStyle=False
            report_lyr = QgsVectorLayer('Point', 'Table', 'memory', options)
            flds = QgsFields()
            flds_to_add = [QgsField('Paddock Name', QVariant.String, len=254),
                        QgsField('Area Ha', QVariant.Double, len=10, prec=3),
                        QgsField('No. Waterpoints', QVariant.Int),
                        QgsField('Max Dist to Water (km)', QVariant.Double, len=10, prec=3)]
            for f in flds_to_add:
                flds.append(f)
            report_lyr.dataProvider().addAttributes(flds)
            report_lyr.updateFields()

            feedback.setCurrentStep(step)
            step+=1
            
            if not report_lyr.isValid():
                raise QgsProcessingException("Could not create output report")
                        
            # make sure temporary report layer is valid
            if report_lyr.isValid():
                for pdk_name, atts_list in info_map.items():
                    feat = QgsFeature(report_lyr.fields())
                    atts = [pdk_name, atts_list[1], atts_list[2], atts_list[3]]
                    feat.setAttributes(atts)
                    report_lyr.dataProvider().addFeatures([feat])
                    
                    report_path = os.path.join(output_folder, 'Max_dist_to_water.xlsx')
                
                export_params = {'LAYERS':[report_lyr],
                                    'USE_ALIAS':False,
                                    'FORMATTED_VALUES':False,
                                    'OUTPUT':report_path,
                                    'OVERWRITE':False}
                                                    
                outputs['Report_spreadsheet'] = processing.run("native:exporttospreadsheet", export_params, context=context, feedback=feedback, is_child_algorithm=True)
                results['Report_spreadsheet'] = outputs['Report_spreadsheet']['OUTPUT']
                
                if load_outputs:
                    uri = f'{report_path}|layername=Table'
                    rep_lyr = QgsVectorLayer(uri, 'Report_Table', 'ogr')
                    if rep_lyr.isValid():
                        self.LAYERS_TO_LOAD.append(rep_lyr)
                    
        results[self.OUTPUT_LAYERS] = outputLayers
        return results
        
    def postProcessAlgorithm(self, context, feedback):
        max_dtw = self.GLOBAL_MAXIMUM_DTW
        if self.LAYERS_TO_LOAD:
            project = context.project()
            group_name = 'Water proximity'
            root_group = project.layerTreeRoot()
            if not root_group.findGroup(group_name):
                root_group.insertGroup(0, group_name)
            group1 = root_group.findGroup(group_name)
            
            for lyr in self.LAYERS_TO_LOAD:
                if lyr.type() == QgsMapLayerType.RasterLayer:
                    props = {'color1': '1,133,113,255',
                            'color2': '166,97,26,255',
                            'discrete': '0',
                            'rampType': 'gradient',
                            'stops': '0.25;128,205,193,255:0.5;245,245,245,255:0.75;223,194,125,255'}

                    color_ramp = QgsGradientColorRamp.create(props)
                    renderer = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 1)
                    renderer.setClassificationMin(0)
                    renderer.setClassificationMax(max_dtw)
                    renderer.createShader(color_ramp, QgsColorRampShader.Interpolated, QgsColorRampShader.EqualInterval, 5)# Don't use Continuous
                    lyr.setRenderer(renderer)
                    lyr.triggerRepaint()
                    if group1:
                        project.addMapLayer(lyr, False)
                        group1.addLayer(lyr)
                            
            for lyr in self.LAYERS_TO_LOAD:
                if lyr.type() == QgsMapLayerType.VectorLayer:
                    if group1:
                        project.addMapLayer(lyr, False)
                        group1.insertLayer(0, lyr)
                        
            self.LAYERS_TO_LOAD.clear()
                            
##############################################################################
