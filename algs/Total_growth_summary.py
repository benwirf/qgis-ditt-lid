from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsField, QgsFeature, QgsProcessing, QgsFeature,
                        QgsProcessingAlgorithm, QgsProcessingParameterFile,
                        QgsProcessingParameterVectorLayer, QgsVectorLayer,
                        QgsProcessingParameterFileDestination,
                        QgsProcessingMultiStepFeedback)

from osgeo import gdalnumeric
import processing
import os
                       
class TotalGrowthSummary(QgsProcessingAlgorithm):
    INPUT_FOLDER = 'INPUT_FOLDER'
    DISTRICT_LAYER = 'DISTRICT_LAYER'
    OUTPUT_XLSX = 'OUTPUT_XSLX'
 
    def __init__(self):
        super().__init__()
 
    def name(self):
        return "Total_growth_summary"
         
    def displayName(self):
        return "Total growth summary"
 
    def group(self):
        return "Feed Outlook"
 
    def groupId(self):
        return "Feed_outlook"
 
    def shortHelpString(self):
        return "Stack monthly growth rasters for current financial year \
        and count pixels in 4 classes for each pastoral district"
 
    def helpUrl(self):
        return "https://qgis.org"
         
    def createInstance(self):
        return type(self)()
   
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(self.INPUT_FOLDER, 'Financial Year growth rasters', behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterVectorLayer(self.DISTRICT_LAYER, 'Pastoral Districts', [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT_XLSX, 'Total growth summary spreadsheet', 'Microsoft Excel (*.xlsx);;Open Document Spreadsheet (*.ods)'))
 
    def processAlgorithm(self, parameters, context, model_feedback):
        
        results = {}
        outputs = {}
        
        monthly_growth_folder = self.parameterAsString(parameters, self.INPUT_FOLDER, context)
        districts = self.parameterAsVectorLayer(parameters, self.DISTRICT_LAYER, context)
        destination_spreadsheet = parameters[self.OUTPUT_XLSX]
        ####################################################################
        regions = {'Barkly': 'southern',
            'Darwin': 'northern',
            'Gulf': 'northern',
            'Katherine': 'northern',
            'Northern Alice Springs': 'southern',
            'Plenty': 'southern',
            'Roper': 'northern',
            'Southern Alice Springs': 'southern',
            'Sturt Plateau': 'northern',
            'Tennant Creek': 'southern',
            'V.R.D.': 'northern',
            'Victoria River': 'northern'}
        
        ###Create temporary copy of district layer#########################
        temp_districts = QgsVectorLayer(f'polygon?&crs={districts.crs().authid()}', 'Temp_Districts', 'memory')
        temp_districts.dataProvider().addAttributes(districts.fields())
        temp_districts.updateFields()
        for f in districts.getFeatures():
            feat = QgsFeature()
            feat.setGeometry(f.geometry())
            feat.setAttributes(f.attributes())
            temp_districts.dataProvider().addFeatures([feat])
        ####################################################################
        
        input_rasters = []

        for file in os.scandir(monthly_growth_folder):
            if file.name.split('.')[-1] == 'img':
                raster_path = os.path.join(monthly_growth_folder, file.name)
                input_rasters.append(raster_path)
                
        steps = 13
        feedback = QgsProcessingMultiStepFeedback(steps, model_feedback)
        step = 1
        
        cell_sum_params = {
                        'INPUT': input_rasters,
                        'STATISTIC':0,
                        'IGNORE_NODATA':True,
                        'REFERENCE_LAYER':input_rasters[0],
                        'OUTPUT_NODATA_VALUE':-9999,
                        'OUTPUT':'TEMPORARY_OUTPUT'
                        }
        
        feedback.setCurrentStep(step)
        step+=1
        outputs['total_growth_raster'] = processing.run('native:cellstatistics', cell_sum_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['total_growth_raster'] = outputs['total_growth_raster']['OUTPUT']
        
        district_names = [f['DISTRICT'] for f in temp_districts.getFeatures()]
        
        total_growth_temp = QgsVectorLayer('Point', 'Total Growth Summary', 'memory')
        total_growth_temp.dataProvider().addAttributes([
            QgsField('District', QVariant.String),
            QgsField('Low_count', QVariant.Int),
            QgsField('Low_moderate_count', QVariant.Int),
            QgsField('Moderate_count', QVariant.Int),
            QgsField('High_count', QVariant.Int),
            QgsField('Low_percent', QVariant.Double),
            QgsField('Low_moderate_percent', QVariant.Double),
            QgsField('Moderate_percent', QVariant.Double),
            QgsField('High_percent', QVariant.Double),
            QgsField('Check_Sum', QVariant.Int)
        ])
        total_growth_temp.updateFields()
        
        for district_name in district_names:
            
            temp_districts.setSubsetString(f""""DISTRICT" LIKE '{district_name}'""")
            
            mask_params = {'INPUT':results['total_growth_raster'],
                'MASK':temp_districts,
                'SOURCE_CRS':None,
                'TARGET_CRS':None,
                'NODATA':None,
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
                'OUTPUT':'TEMPORARY_OUTPUT'}
            
            feedback.setCurrentStep(step)
            step+=1
            outputs[f'clipped_to_{district_name}'] = processing.run("gdal:cliprasterbymasklayer", mask_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'clipped_to_{district_name}'] = outputs[f'clipped_to_{district_name}']['OUTPUT']
            
            raster1 = gdalnumeric.LoadFile(results[f'clipped_to_{district_name}'])
            region = regions[district_name]
            count_results = self.total_growth_counts(raster1, region)
            feat = QgsFeature()
            feat.setAttributes([
                    district_name,
                    int(count_results[0]),
                    int(count_results[1]),
                    int(count_results[2]),
                    int(count_results[3]),
                    float(count_results[4]),
                    float(count_results[5]),
                    float(count_results[6]),
                    float(count_results[7]),
                    int(count_results[8])
                ])
            total_growth_temp.dataProvider().addFeatures([feat])
        
        save_2_xlsx_params = {'LAYERS':[total_growth_temp],
            'USE_ALIAS':False,
            'FORMATTED_VALUES':False,
            'OUTPUT':destination_spreadsheet,
            'OVERWRITE':True}

        feedback.setCurrentStep(step)
        step+=1
        outputs['summary_spreadsheet'] = processing.run("native:exporttospreadsheet", save_2_xlsx_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['summary_spreadsheet'] = outputs['summary_spreadsheet']['OUTPUT']

        return results

##############################################################################
        
    def total_growth_counts(self, raster, region):
        if region == 'northern':
            # Northern Districts
            low_count = ((raster > 0)&(raster <= 1000)).sum()
            low_moderate_count = ((raster > 1000)&(raster <= 2000)).sum()
            moderate_count = ((raster > 2000)&(raster <= 3000)).sum()
            high_count = (raster > 3000).sum()
            no_data_count = (raster == 0).sum()

        elif region == 'southern':
            # Southern Districts
            low_count = ((raster > 0)&(raster <= 250)).sum()
            low_moderate_count = ((raster > 250)&(raster <= 500)).sum()
            moderate_count = ((raster > 500)&(raster <= 1000)).sum()
            high_count = (raster > 1000).sum()
            no_data_count = (raster == 0).sum()

        total_pixel_count = sum([low_count, low_moderate_count, moderate_count, high_count, no_data_count])
        total_pixel_count_greater_than_zero = sum([low_count, low_moderate_count, moderate_count, high_count])

        low_percent = low_count/total_pixel_count_greater_than_zero*100
        low_moderate_percent = low_moderate_count/total_pixel_count_greater_than_zero*100
        moderate_percent = moderate_count/total_pixel_count_greater_than_zero*100
        high_percent = high_count/total_pixel_count_greater_than_zero*100
        
        check_sum = sum([low_percent, low_moderate_percent, moderate_percent, high_percent])
        
        return [low_count,
                low_moderate_count,
                moderate_count, 
                high_count,
                low_percent,
                low_moderate_percent,
                moderate_percent,
                high_percent,
                check_sum]
    ##############################################################################
        