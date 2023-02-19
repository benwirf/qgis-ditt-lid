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

                       
class FireRiskSummary(QgsProcessingAlgorithm):
    FIRE_RISK = 'FIRE_RISK'
    DISTRICTS = 'DISTRICTS'
    
    XL_SUMMARY = 'XL_SUMMARY'
 
    def __init__(self):
        super().__init__()
 
    def name(self):
        return "Fire_risk_summary"
         
    def displayName(self):
        return "Fire risk summary"
 
    def group(self):
        return "Feed Outlook"
 
    def groupId(self):
        return "Feed_outlook"

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "../icons/fire_risk_icon.png"))
 
    def shortHelpString(self):
        return "Creates an Excel Sheet containing counts and percentages of pixels\
        in low, moderate and high classes for each pastoral district"
 
    def helpUrl(self):
        return "https://qgis.org"
         
    def createInstance(self):
        return type(self)()
   
    def initAlgorithm(self, config=None):
        
        self.addParameter(QgsProcessingParameterRasterLayer(self.FIRE_RISK, 'AussieGRASS Fire Risk raster'))
        self.addParameter(QgsProcessingParameterVectorLayer(self.DISTRICTS, 'Pastoral Districts layer', [QgsProcessing.TypeVectorPolygon]))
            
        self.addParameter(QgsProcessingParameterFileDestination(self.XL_SUMMARY, 'Fire Risk summary spreadsheet', 'Microsoft Excel (*.xlsx);;Open Document Spreadsheet (*.ods)'))
 
    def processAlgorithm(self, parameters, context, model_feedback):

        results = {}
        outputs = {}
        
        fire_risk = self.parameterAsRasterLayer(parameters, self.FIRE_RISK, context)
        districts = self.parameterAsVectorLayer(parameters, self.DISTRICTS, context)
#        districts = QgsVectorLayer(d)
        
        dest_spreadsheet = parameters[self.XL_SUMMARY]
        
        steps = 12
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
        
        fire_risk_temp = QgsVectorLayer('Point', 'Fire Risk Summary', 'memory')
        fire_risk_temp.dataProvider().addAttributes([
            QgsField('District', QVariant.String),
            QgsField('Low_count', QVariant.Int),
            QgsField('Moderate_count', QVariant.Int),
            QgsField('High_count', QVariant.Int),
            QgsField('Low_percent', QVariant.Double),
            QgsField('Moderate_percent', QVariant.Double),
            QgsField('High_percent', QVariant.Double),
            QgsField('Check Sum', QVariant.Int)
        ])
        fire_risk_temp.updateFields()
        
        for district_name in district_names:
            
            temp_districts.setSubsetString(f""""DISTRICT" LIKE '{district_name}'""")
            
            mask_params = {'INPUT':fire_risk,
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
            counts = self.fire_risk_counts(raster1)
            feat = QgsFeature()
            feat.setAttributes([
                district_name,
                int(counts[0]),
                int(counts[1]),
                int(counts[2]),
                round(float(counts[3]), 5),
                round(float(counts[4]), 5),
                round(float(counts[5]), 5),
                int(counts[6])
                ])
            add = fire_risk_temp.dataProvider().addFeature(feat)

        temp_layers.append(fire_risk_temp)

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
        
        
    def fire_risk_counts(self, raster):
        low_count = ((raster > 0)&(raster <= 20)).sum()
        moderate_count = ((raster > 20)&(raster <= 30)).sum()
        high_count = ((raster > 30)&(raster <= 40)).sum()
        firescar_count = (raster == 253).sum()
        water_count = (raster == 254).sum()
        no_data_count = (raster == 0).sum()
        
        total_risk_classes = sum([low_count, moderate_count, high_count])
        
        low_pcnt = low_count/total_risk_classes*100
        moderate_pcnt = moderate_count/total_risk_classes*100
        high_pcnt = high_count/total_risk_classes*100
        
        check_sum = sum([low_pcnt, moderate_pcnt, high_pcnt])

        return [low_count, moderate_count, high_count, low_pcnt, moderate_pcnt, high_pcnt, check_sum]