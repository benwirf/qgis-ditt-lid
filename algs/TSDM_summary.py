from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (QgsVectorLayer, QgsField, QgsFeature,
                        QgsProcessing, QgsProcessingAlgorithm,
                        QgsProcessingParameterRasterLayer,
                        QgsProcessingParameterVectorLayer,
                        QgsProcessingParameterFileDestination,
                        QgsProcessingMultiStepFeedback)

from osgeo import gdalnumeric
import processing
import os

                       
class TSDMSummary(QgsProcessingAlgorithm):
    TSDM = 'TSDM'
    TSDM_PCNT = 'TSDM_PCNT'
    DISTRICTS = 'DISTRICTS'
    
    XL_SUMMARY = 'XL_SUMMARY'
 
    def __init__(self):
        super().__init__()
 
    def name(self):
        return "TSDM_summary"
         
    def displayName(self):
        return "TSDM summary"
 
    def group(self):
        return "Feed Outlook"
 
    def groupId(self):
        return "Feed_outlook"
        
    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "../icons/tsdm_icon.png"))
 
    def shortHelpString(self):
        return "Creates an Excel Workbook containing 2 sheets with counts and percentages of pixels\
        for each pastoral district. One with low, low-moderate, moderate and high classes for TSDM,\
        and one with below average, average and above average for TSDM percentile."
 
    def helpUrl(self):
        return "https://qgis.org"
         
    def createInstance(self):
        return type(self)()
   
    def initAlgorithm(self, config=None):
        
        self.addParameter(QgsProcessingParameterRasterLayer(self.TSDM, 'AussieGRASS TSDM raster'))
        self.addParameter(QgsProcessingParameterRasterLayer(self.TSDM_PCNT, 'AussieGRASS TSDM Percentile raster'))
        self.addParameter(QgsProcessingParameterVectorLayer(self.DISTRICTS, 'Pastoral Districts layer', [QgsProcessing.TypeVectorPolygon]))
            
        self.addParameter(QgsProcessingParameterFileDestination(self.XL_SUMMARY, 'TSDM summary spreadsheet', 'Microsoft Excel (*.xlsx);;Open Document Spreadsheet (*.ods)'))
 
    def processAlgorithm(self, parameters, context, model_feedback):

        results = {}
        outputs = {}
        
        tsdm = self.parameterAsRasterLayer(parameters, self.TSDM, context)
        tsdm_pcnt = self.parameterAsRasterLayer(parameters, self.TSDM_PCNT, context)
        districts = self.parameterAsVectorLayer(parameters, self.DISTRICTS, context)
        dest_spreadsheet = parameters[self.XL_SUMMARY]
    
    ############################################################################
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
    ############################################################################
    
        steps = 23
        feedback = QgsProcessingMultiStepFeedback(steps, model_feedback)
        step = 1
        
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
        
        temp_layers = []
        
        district_names = [f['DISTRICT'] for f in temp_districts.getFeatures()]
        
        tsdm_temp = QgsVectorLayer('Point', 'TSDM Summary', 'memory')
        tsdm_temp.dataProvider().addAttributes([
            QgsField('District', QVariant.String),
            QgsField('Low_count', QVariant.Int),
            QgsField('Low_moderate_count', QVariant.Int),
            QgsField('Moderate_count', QVariant.Int),
            QgsField('High_count', QVariant.Int),
            QgsField('Low_percent', QVariant.Double),
            QgsField('Low_moderate_percent', QVariant.Double),
            QgsField('Moderate_percent', QVariant.Double),
            QgsField('High_percent', QVariant.Double),
            QgsField('Check_Sum', QVariant.Int)])
        tsdm_temp.updateFields()
        
        tsdm_pcnt_temp = QgsVectorLayer('Point', 'TSDM Percentile Summary', 'memory')
        tsdm_pcnt_temp.dataProvider().addAttributes([
            QgsField('District', QVariant.String),
            QgsField('Below_average_count', QVariant.Int),
            QgsField('Average_count', QVariant.Int),
            QgsField('Above_average_count', QVariant.Int),
            QgsField('Below_average_percent', QVariant.Double),
            QgsField('Average_percent', QVariant.Double),
            QgsField('Above_average_percent', QVariant.Double),
            QgsField('Check_Sum', QVariant.Int)])
        tsdm_pcnt_temp.updateFields()
                
        for district_name in district_names:
            
            temp_districts.setSubsetString(f""""DISTRICT" LIKE '{district_name}'""")
            
            ######## Clip tsdm (total) raster to filtered district layer########
            mask1_params = {'INPUT':tsdm,
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
            outputs[f'tsdm_clipped_to_{district_name}'] = processing.run("gdal:cliprasterbymasklayer", mask1_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'tsdm_clipped_to_{district_name}'] = outputs[f'tsdm_clipped_to_{district_name}']['OUTPUT']
            
            ###Save TSDM (total) counts to tempory layer
            region = regions[district_name]
            raster_1 = gdalnumeric.LoadFile(results[f'tsdm_clipped_to_{district_name}'])
            counts_1 = self.tsdm_counts(raster_1, region)
            feat1 = QgsFeature()
            feat1.setAttributes([
                district_name,
                int(counts_1[0]),
                int(counts_1[1]),
                int(counts_1[2]),
                int(counts_1[3]),
                round(float(counts_1[4]), 5),
                round(float(counts_1[5]), 5),
                round(float(counts_1[6]), 5),
                round(float(counts_1[7]), 5),
                int(round(counts_1[8], 0))
                ])
            add1 = tsdm_temp.dataProvider().addFeature(feat1)
            
            ######## Clip tsdm (percentile) raster to filtered district layer########
            mask2_params = {'INPUT':tsdm_pcnt,
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
            outputs[f'tsdm_pcnt_clipped_to_{district_name}'] = processing.run("gdal:cliprasterbymasklayer", mask2_params, context=context, feedback=feedback, is_child_algorithm=True)
            results[f'tsdm_pcnt_clipped_to_{district_name}'] = outputs[f'tsdm_pcnt_clipped_to_{district_name}']['OUTPUT']
                        
            ###Save TSDM (percentile) counts to tempory layer
            raster_2 = gdalnumeric.LoadFile(results[f'tsdm_pcnt_clipped_to_{district_name}'])
            counts_2 = self.tsdm_percentile_counts(raster_2)
            feat2 = QgsFeature()
            feat2.setAttributes([
                district_name,
                int(counts_2[0]),
                int(counts_2[1]),
                int(counts_2[2]),
                round(float(counts_2[3]), 5),
                round(float(counts_2[4]), 5),
                round(float(counts_2[5]), 5),
                int(round(counts_2[6], 0))
                ])
            add2 = tsdm_pcnt_temp.dataProvider().addFeature(feat2)
        ########################################################################
        temp_layers.append(tsdm_temp)
        temp_layers.append(tsdm_pcnt_temp)
                
        save_2_xlsx_params = {'LAYERS':temp_layers,
            'USE_ALIAS':False,
            'FORMATTED_VALUES':False,
            'OUTPUT':dest_spreadsheet,
            'OVERWRITE':True}
        
        feedback.setCurrentStep(step)
        step+=1
        outputs['summary_spreadsheet'] = processing.run("native:exporttospreadsheet", save_2_xlsx_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['summary_spreadsheet'] = outputs['summary_spreadsheet']['OUTPUT']
        
        return results
    
    #############Methods which return counts and percentages##################
        
    def tsdm_counts(self, raster, region):
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
    
    
    def tsdm_percentile_counts(self, raster):
        below_average_count = ((raster > 0)&(raster <= 30)).sum()
        average_count = ((raster > 30)&(raster <= 70)).sum()
        above_average_count = ((raster > 70)&(raster <= 100)).sum()
        firescar_count = (raster == 253).sum()
        water_count = (raster == 254).sum()
        no_data_count = (raster == 0).sum()
        
        total_tsdm_pcnt_classes = sum([below_average_count, average_count, above_average_count])
        
        below_average_pcnt = below_average_count/total_tsdm_pcnt_classes*100
        average_pcnt = average_count/total_tsdm_pcnt_classes*100
        above_average_pcnt = above_average_count/total_tsdm_pcnt_classes*100
        
        check_sum = sum([below_average_pcnt, average_pcnt, above_average_pcnt])
        
        return [below_average_count,
                average_count,
                above_average_count,
                below_average_pcnt,
                average_pcnt,
                above_average_pcnt,
                check_sum]
        
