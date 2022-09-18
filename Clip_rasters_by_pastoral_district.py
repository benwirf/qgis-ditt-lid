from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterMultipleLayers
from qgis.core import QgsProcessingParameterFolderDestination
from qgis.core import QgsProcessingFeatureSourceDefinition
from qgis.core import QgsFeatureRequest
import processing
import os


class ClipRastersByPastoralDistrict(QgsProcessingAlgorithm):
    
    # Pastoral districts vector
    DISTRICTS = 'DISTRICTS' # Vector Polygons
    
    # Input rasters
    GROWTH_PROBABILITY_INPUT = 'GROWTH_PROBABILITY_INPUT'
    PERCENTILE_GROWTH_INPUTS = 'PERCENTILE_GROWTH_INPUTS' # Multiple layers (3, 6, 12, 24 mnths)
    TSDM_INPUT = 'TSDM_INPUT'
    TSDM_PCNT_INPUT = 'TSDM_PCNT_INPUT'
    
    # output directories
    GROWTH_PROBABILITY_OUPUT = 'GROWTH_PROBABILITY_OUPUT'
    PERCENTILE_GROWTH_OUPUT = 'PERCENTILE_GROWTH_OUPUT'
    TSDM_OUPUT = 'TSDM_OUPUT' # Directory

    def initAlgorithm(self, config=None):
        # Alg inputs
        self.addParameter(QgsProcessingParameterVectorLayer(self.DISTRICTS, 'Pastoral districts', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer(self.GROWTH_PROBABILITY_INPUT, 'Input growth probability'))
        self.addParameter(QgsProcessingParameterMultipleLayers(self.PERCENTILE_GROWTH_INPUTS, 'Inputs growth percent', QgsProcessing.TypeRaster))
        self.addParameter(QgsProcessingParameterRasterLayer(self.TSDM_INPUT, 'Input TSDM'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.TSDM_PCNT_INPUT, 'Input TSDM percent'))
        # Alg outputs
        self.addParameter(QgsProcessingParameterFolderDestination(self.GROWTH_PROBABILITY_OUPUT, 'Output growth probability'))
        self.addParameter(QgsProcessingParameterFolderDestination(self.PERCENTILE_GROWTH_OUPUT, 'Output growth percent'))
        self.addParameter(QgsProcessingParameterFolderDestination(self.TSDM_OUPUT, 'Output TSDM'))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        mask_vector = self.parameterAsVectorLayer(parameters, self.DISTRICTS, context)
        
        pcnt_growth_layers = self.parameterAsLayerList(parameters, self.PERCENTILE_GROWTH_INPUTS, context)
        
        growth_prob_folder = parameters[self.GROWTH_PROBABILITY_OUPUT]
        pcnt_growth_folder = parameters[self.PERCENTILE_GROWTH_OUPUT]
        tsdm_folder = parameters[self.TSDM_OUPUT]
        
        raster_count = len(pcnt_growth_layers) + 3
        district_count = mask_vector.featureCount()
        steps = district_count*raster_count
        
        feedback = QgsProcessingMultiStepFeedback(steps, model_feedback)
        
        step = 1
        
        results = {}
        outputs = {}
        
        for feat in mask_vector.getFeatures():
            # Clip AussieGRASS rasters by districts
            mask_vector.selectByIds([feat.id()])
            district_name = feat['NAME'].title()# Format upper case to title case e.g. "BARKLY" -> "Barkly"
            
            # Clip Growth Probability map by districts
            growth_prob_out_path = os.path.join(growth_prob_folder, f'{district_name}_GROWTHPROB.img')
            growth_prob_params = {
                    'INPUT': parameters[self.GROWTH_PROBABILITY_INPUT],
                    'MASK':QgsProcessingFeatureSourceDefinition(mask_vector.source(), selectedFeaturesOnly=True, featureLimit=-1, geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid),
                    'SOURCE_CRS':None,
                    'TARGET_CRS':None,
                    'NODATA':-999,
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
                    'OUTPUT':growth_prob_out_path
                    }
            feedback.setCurrentStep(step)
            step+=1
            outputs[f'growth_prob_{district_name}'] = processing.run("gdal:cliprasterbymasklayer", growth_prob_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'growth_prob_{district_name}'] = outputs[f'growth_prob_{district_name}']['OUTPUT']
################################################################################
            # Clip Percentile Growth maps by district
            for raster_lyr in pcnt_growth_layers:
                month_part = raster_lyr.source().split('.')[1]
                pcnt_growth_out_path = os.path.join(pcnt_growth_folder, f'{district_name}-{month_part}.img')
                # PARAMS HERE FOR CLIPPING EACH MONTH OF PCNT GROWTH
                pcnt_growth_params = {
                    'INPUT': raster_lyr,
                    'MASK':QgsProcessingFeatureSourceDefinition(mask_vector.source(), selectedFeaturesOnly=True, featureLimit=-1, geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid),
                    'SOURCE_CRS':None,
                    'TARGET_CRS':None,
                    'NODATA':-999,
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
                    'OUTPUT':pcnt_growth_out_path
                }
                feedback.setCurrentStep(step)
                step+=1
                outputs[f'growth_pcnt_{district_name}'] = processing.run("gdal:cliprasterbymasklayer", pcnt_growth_params, context=context, feedback=feedback, is_child_algorithm=True)
                results[f'growth_pcnt_{district_name}'] = outputs[f'growth_pcnt_{district_name}']['OUTPUT']
            
################################################################################
            # Clip TSDM rasters by District
            # First tsdm.int...
            tsdm_out_path = os.path.join(tsdm_folder, f'{district_name}_TSDM.img')
            tsdm_params = {
                    'INPUT': parameters[self.TSDM_INPUT],
                    'MASK':QgsProcessingFeatureSourceDefinition(mask_vector.source(), selectedFeaturesOnly=True, featureLimit=-1, geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid),
                    'SOURCE_CRS':None,
                    'TARGET_CRS':None,
                    'NODATA':-999,
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
                    'OUTPUT':tsdm_out_path
                    }
                    
            feedback.setCurrentStep(step)
            step+=1
            outputs[f'tsdm_{district_name}'] = processing.run("gdal:cliprasterbymasklayer", tsdm_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'tsdm_{district_name}'] = outputs[f'tsdm_{district_name}']['OUTPUT']
            
            # Now tsdm.pcnt...
            tsdm_pcnt_out_path = os.path.join(tsdm_folder, f'{district_name}_TSDMPCNT.img')

            tsdm_pcnt_params = {
                    'INPUT': parameters[self.TSDM_PCNT_INPUT],
                    'MASK':QgsProcessingFeatureSourceDefinition(mask_vector.source(), selectedFeaturesOnly=True, featureLimit=-1, geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid),
                    'SOURCE_CRS':None,
                    'TARGET_CRS':None,
                    'NODATA':-999,
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
                    'OUTPUT':tsdm_pcnt_out_path
                    }
            
            feedback.setCurrentStep(step)
            step+=1
            outputs[f'tsdm_pcnt_{district_name}'] = processing.run("gdal:cliprasterbymasklayer", tsdm_pcnt_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'tsdm_pcnt_{district_name}'] = outputs[f'tsdm_pcnt_{district_name}']['OUTPUT']
            
        return results
#        return results

    def name(self):
        return 'Clip_rasters_by_pastoral_district'

    def displayName(self):
        return 'Clip rasters by pastoral district'
        
    def shortHelpString(self):
        return "Clips Growth Probability, Growth Percentile, TSDM & TSDM Percentile\
        rasters from AussieGRASS to pastoral districts for report maps."

    def group(self):
        return 'Feed Outlook'

    def groupId(self):
        return 'Feed_outlook'

    def createInstance(self):
        return ClipRastersByPastoralDistrict()