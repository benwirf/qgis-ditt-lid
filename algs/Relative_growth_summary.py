from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (QgsVectorLayer,
                        QgsField,
                        QgsFeature,
                        QgsProcessing,
                        QgsProcessingException,
                        QgsProcessingAlgorithm,
                        QgsProcessingParameterRasterLayer,
                        QgsProcessingParameterFeatureSource,
                        QgsProcessingParameterField,
                        QgsProcessingParameterFileDestination,
                        QgsProcessingMultiStepFeedback)

from osgeo import gdal
import processing
import os
                       
class RelativeGrowthSummary(QgsProcessingAlgorithm):
    PERCENTILE_GROWTH_RASTER = 'PERCENTILE_GROWTH_RASTER'
    DISTRICT_LAYER = 'DISTRICT_LAYER'
    DISTRICT_NAME_FIELD = 'DISTRICT_NAME_FIELD'
    OUTPUT_XLSX = 'OUTPUT_XSLX'
 
    def __init__(self):
        super().__init__()
 
    def name(self):
        return "Relative_growth_summary"
         
    def displayName(self):
        return "Relative growth summary"
 
    def group(self):
        return "Feed Outlook"
 
    def groupId(self):
        return "Feed_outlook"
        
    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "../icons/growth_pcnt_icon.png"))
 
    def shortHelpString(self):
        return "Count pixels in 7 classes for each pastoral district\
        using an input percentile growth raster and a pastoral district vector layer.\
        results are written to an Excel spreadsheet."
 
    def helpUrl(self):
        return "https://qgis.org"
         
    def createInstance(self):
        return type(self)()
   
    def initAlgorithm(self, config=None):
        
        self.addParameter(QgsProcessingParameterRasterLayer(self.PERCENTILE_GROWTH_RASTER, "Percentile growth raster"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.DISTRICT_LAYER, "Pastoral districts", [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(self.DISTRICT_NAME_FIELD,
                                                    "Field containing district name",
                                                    parentLayerParameterName=self.DISTRICT_LAYER,
                                                    type=QgsProcessingParameterField.String))
        self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT_XLSX, 'Percentile growth summary spreadsheet', 'Microsoft Excel (*.xlsx);;Open Document Spreadsheet (*.ods)'))
 
    def processAlgorithm(self, parameters, context, model_feedback):
        results = {}
        outputs = {}
        
        percentile_growth_raster = self.parameterAsRasterLayer(parameters, self.PERCENTILE_GROWTH_RASTER, context)
        districts = self.parameterAsSource(parameters, self.DISTRICT_LAYER, context)
        district_name_field = self.parameterAsString(parameters, self.DISTRICT_NAME_FIELD, context)
        destination_spreadsheet = self.parameterAsString(parameters, self.OUTPUT_XLSX, context)
        
        #################Create temporary copy of district layer###############
        temp_districts = QgsVectorLayer(f'polygon?&crs={districts.sourceCrs().authid()}', 'Temp_Districts', 'memory')
        temp_districts.dataProvider().addAttributes(districts.fields())
        temp_districts.updateFields()
        for f in districts.getFeatures():
            feat = QgsFeature()
            feat.setGeometry(f.geometry())
            feat.setAttributes(f.attributes())
            temp_districts.dataProvider().addFeatures([feat])
            
        ##Create temporary layer to hold counts/ percentages for each district##
        pcnt_growth_temp = QgsVectorLayer('point', 'Relative Growth Summary', 'memory')
        
        pcnt_growth_temp.dataProvider().addAttributes([
            QgsField('District', QVariant.String),
            QgsField('Extremely_low_count', QVariant.Int),
            QgsField('Well_below_average_count', QVariant.Int),
            QgsField('Below_average_count', QVariant.Int),
            QgsField('Average_count', QVariant.Int),
            QgsField('Above_average_count', QVariant.Int),
            QgsField('Well_above_average_count', QVariant.Int),
            QgsField('Extremely_high_count', QVariant.Int),
            QgsField('Extremely low %', QVariant.Double),
            QgsField('Well below average %', QVariant.Double),
            QgsField('Below average %', QVariant.Double),
            QgsField('Average %', QVariant.Double),
            QgsField('Above average %', QVariant.Double),
            QgsField('Well above average %', QVariant.Double),
            QgsField('Extremely high %', QVariant.Double),
            QgsField('Check_Sum', QVariant.Int)
        ])
        pcnt_growth_temp.updateFields()
        
        #######################################################################
        steps = districts.featureCount()+1
        feedback = QgsProcessingMultiStepFeedback(steps, model_feedback)
        step = 1
        #######################################################################
        
        district_names = [f[district_name_field] for f in temp_districts.getFeatures()]
        
        for district_name in district_names:
            # filter district layer to current distict name
            filtered_district = temp_districts.setSubsetString(f'"{district_name_field}" LIKE \'{district_name}\'')
            if not filtered_district:
                feedback.pushDebugInfo('Unable to filter districts to create mask layer')
                continue
            # clip relative growth raster to district (no_data -999)
            mask_params = {'INPUT':percentile_growth_raster,
                'MASK':temp_districts,
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
                'DATA_TYPE':2,
                'EXTRA':'',
                'OUTPUT':'TEMPORARY_OUTPUT'}

            feedback.setCurrentStep(step)
            step+=1
            
            outputs[f'clipped_to_{district_name}'] = processing.run("gdal:cliprasterbymasklayer", mask_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'clipped_to_{district_name}'] = outputs[f'clipped_to_{district_name}']['OUTPUT']
            # run percentile_growth_counts and add results as feature to pcnt_growth_temp
            ds = gdal.Open(results[f'clipped_to_{district_name}'])
            ds_as_array = ds.ReadAsArray()
            all_counts = self.percentile_growth_counts(ds_as_array)
            feat = QgsFeature(pcnt_growth_temp.fields())
            feat.setAttributes([district_name,
                                int(all_counts[0]),#extremeley low count
                                int(all_counts[1]),#well below average count
                                int(all_counts[2]),#below average count
                                int(all_counts[3]),#average count
                                int(all_counts[4]),#above average count
                                int(all_counts[5]),#well above average count
                                int(all_counts[6]),#extremely high count
                                round(float(all_counts[7]), 3),#extremeley low pcnt
                                round(float(all_counts[8]), 3),#well below average pcnt
                                round(float(all_counts[9]), 3),#below average pcnt
                                round(float(all_counts[10]), 3),#average pcnt
                                round(float(all_counts[11]), 3),#above average pcnt
                                round(float(all_counts[12]), 3),#well above average pcnt
                                round(float(all_counts[13]), 3),#extremely high pcnt
                                round(float(all_counts[14]), 3)])#check sum pcnt
                                
            feature_added = pcnt_growth_temp.dataProvider().addFeatures([feat])
            if feature_added[0] is True:
                feedback.pushDebugInfo(f'District row successfully added: {repr(feature_added[0])}')
            elif feature_added[0] is False:
                feedback.pushWarning(repr(pcnt_growth_temp.dataProvider().lastError()))
            ds = None
        # save pcnt_growth_temp to output spreadsheet
        save_2_xlsx_params = {'LAYERS':[pcnt_growth_temp],
            'USE_ALIAS':False,
            'FORMATTED_VALUES':False,
            'OUTPUT':destination_spreadsheet,
            'OVERWRITE':True}

        feedback.setCurrentStep(step)
        step+=1
        
        outputs['summary_spreadsheet'] = processing.run("native:exporttospreadsheet", save_2_xlsx_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['summary_spreadsheet'] = outputs['summary_spreadsheet']['OUTPUT']
        #**************************************************************************************

        return results
                
                
    def percentile_growth_counts(self, arr):
        # get pixel counts for growth category bins
        extremely_low_count = ((arr > 0)&(arr <= 10)).sum()
        well_below_average_count = ((arr > 10)&(arr <= 20)).sum()
        below_average_count = ((arr > 20)&(arr <= 30)).sum()
        average_count = ((arr > 30)&(arr <= 70)).sum()
        above_average_count = ((arr > 70)&(arr <= 80)).sum()
        well_above_average_count = ((arr > 80)&(arr <= 90)).sum()
        extremely_high_count = ((arr > 90)&(arr <= 100)).sum()
        
        # get pixel counts for seasonally low growth, fire scars & water bodies (not included in total)
        seasonally_low_growth_count = (arr == 255).sum()
        water_count = (arr == 254).sum()
        fire_scar_count = (arr == 253).sum()
        # get no data count (also excluded from total)
        no_data_count = (arr == -999).sum()
        
        # get total count of relevant pixels
        total_valid_pixel_count = sum([extremely_low_count,
                                        well_below_average_count,
                                        below_average_count,
                                        average_count,
                                        above_average_count,
                                        well_above_average_count,
                                        extremely_high_count])
        
        # get each category as a percentage of the total
        extremely_low_pcnt = extremely_low_count/total_valid_pixel_count*100
        well_below_average_pcnt = well_below_average_count/total_valid_pixel_count*100
        below_average_pcnt = below_average_count/total_valid_pixel_count*100
        average_pcnt = average_count/total_valid_pixel_count*100
        above_average_pcnt = above_average_count/total_valid_pixel_count*100
        well_above_average_pcnt = well_above_average_count/total_valid_pixel_count*100
        extremely_high_pcnt = extremely_high_count/total_valid_pixel_count*100
        
        # check that sum of percentages add up to 100
        percent_check_sum = sum([extremely_low_pcnt,
                                well_below_average_pcnt,
                                below_average_pcnt,
                                average_pcnt,
                                above_average_pcnt,
                                well_above_average_pcnt,
                                extremely_high_pcnt])
                                
        # return counts, percentages and check sum
        return (extremely_low_count,
                well_below_average_count,
                below_average_count,
                average_count,
                above_average_count,
                well_above_average_count,
                extremely_high_count,
                extremely_low_pcnt,
                well_below_average_pcnt,
                below_average_pcnt,
                average_pcnt,
                above_average_pcnt,
                well_above_average_pcnt,
                extremely_high_pcnt,
                percent_check_sum)
                