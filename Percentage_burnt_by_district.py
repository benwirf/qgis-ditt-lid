from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsField, QgsFeature,
                        QgsProcessing, QgsProcessingAlgorithm,
                        QgsProcessingParameterFeatureSource,
                        QgsProcessingParameterVectorLayer,
                        QgsProcessingParameterFileDestination,
                        QgsVectorLayer,
                        QgsProcessingMultiStepFeedback)

import processing


class PercentBurntByDistrict(QgsProcessingAlgorithm):
    PASTORAL_DISTRICTS = 'PASTORAL_DISTRICTS'
    INPUT_FIRESCARS = 'INPUT_FIRESCARS'
    OUTPUT_XLSX = 'OUTPUT_XLSX'
 
    def __init__(self):
        super().__init__()
 
    def name(self):
        return "Percent_burnt_by_district"
         
    def displayName(self):
        return "Percent burnt by district"
 
    def group(self):
        return "Feed Outlook"

    def groupId(self):
        return "Feed_outlook"
 
    def shortHelpString(self):
        return "Calculate percentage of each pastoral district burnt and ouput \
        an Excel Spreadsheet containing a sheet each for financial and calendar year"
 
    def helpUrl(self):
        return "https://qgis.org"
         
    def createInstance(self):
        return type(self)()
   
    def initAlgorithm(self, config=None):
        
        self.addParameter(QgsProcessingParameterVectorLayer(self.PASTORAL_DISTRICTS, 'Pastoral Districts layer', [QgsProcessing.TypeVectorPolygon]))
        
        self.addParameter(QgsProcessingParameterVectorLayer(self.INPUT_FIRESCARS, 'NAFI Firescar layer', [QgsProcessing.TypeVectorPolygon]))
            
        self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT_XLSX, 'Output Firescar Spreadsheet', 'Microsoft Excel (*.xlsx);;Open Document Spreadsheet (*.ods)'))

 
    def processAlgorithm(self, parameters, context, model_feedback):
        
        results = {}
        outputs = {}
        
        districts = self.parameterAsVectorLayer(parameters, self.PASTORAL_DISTRICTS, context)
        
        input_fs = self.parameterAsVectorLayer(parameters, self.INPUT_FIRESCARS, context)
        
        dest_xlsx = parameters[self.OUTPUT_XLSX]
        
        steps = 4
        feedback = QgsProcessingMultiStepFeedback(steps, model_feedback)
        step = 1
        
        fix_geom_params = {
                        'INPUT':input_fs,
                        'OUTPUT':'TEMPORARY_OUTPUT'
                        }

        feedback.setCurrentStep(step)
        step+=1
        outputs['fixed_geoms'] = processing.run('native:fixgeometries', fix_geom_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['fixed_geoms'] = outputs['fixed_geoms']['OUTPUT']
        
        fs_lyr = context.getMapLayer(results['fixed_geoms'])

        fs_lyr.setSubsetString('"month" > 6')

        # Run overlap analysis on firescar layer with filter (since June- start of financial year)
        overlap_params = {
                        'INPUT':districts,
                        'LAYERS':[fs_lyr],
                        'OUTPUT':'TEMPORARY_OUTPUT'
                        }

        feedback.setCurrentStep(step)
        step+=1
        outputs['overlap_fy'] = processing.run('native:calculatevectoroverlaps', overlap_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['overlap_fy'] = outputs['overlap_fy']['OUTPUT']

        pcnt_fy_lyr = context.getMapLayer(results['overlap_fy'])
        
        # Copy rows from overlap analysis ouput to a temporary layer
        temp_lyr_fy = QgsVectorLayer('Point', 'Area Burnt Summary Financial Year', 'memory')
        temp_lyr_fy.dataProvider().addAttributes([
            QgsField('DISTRICT', QVariant.String),
            QgsField('DISTRICT AREA (KM2)', QVariant.Double),
            QgsField('AREA BURNT (KM2)', QVariant.Double),
            QgsField('PERCENTAGE BURNT', QVariant.Double)
        ])
        temp_lyr_fy.updateFields()
        
        for f in pcnt_fy_lyr.getFeatures():
            feat = QgsFeature()
            feat.setAttributes([
                f['DISTRICT'],
                f['AREA_KM2'],
                round(f['Fixed geometries_area']/1000000, 5),
                round(f['Fixed geometries_pc'], 5)
                ])
            temp_lyr_fy.dataProvider().addFeatures([feat])
        
        # Run overlap analysis on firescar layer with no filter (all months since Jan- calendar year)
        fs_lyr.setSubsetString('')
        
        overlap_params = {
                        'INPUT':districts,
                        'LAYERS':[fs_lyr],
                        'OUTPUT':'TEMPORARY_OUTPUT'
                        }

        feedback.setCurrentStep(step)
        step+=1
        outputs['overlap_cy'] = processing.run('native:calculatevectoroverlaps', overlap_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['overlap_cy'] = outputs['overlap_cy']['OUTPUT']
        
        pcnt_cy_lyr = context.getMapLayer(results['overlap_cy'])

        # Copy rows from overlap analysis ouput to a temporary layer
        temp_lyr_cy = QgsVectorLayer('Point', 'Area Burnt Summary Calendar Year', 'memory')
        temp_lyr_cy.dataProvider().addAttributes([
            QgsField('DISTRICT', QVariant.String),
            QgsField('DISTRICT AREA (KM2)', QVariant.Double),
            QgsField('AREA BURNT (KM2)', QVariant.Double),
            QgsField('PERCENTAGE BURNT', QVariant.Double)
        ])
        temp_lyr_fy.updateFields()
        
        for f in pcnt_cy_lyr.getFeatures():
            feat = QgsFeature()
            feat.setAttributes([
                f['DISTRICT'],
                f['AREA_KM2'],
                round(f['Fixed geometries_area']/1000000, 5),
                round(f['Fixed geometries_pc'], 5)
                ])
            temp_lyr_cy.dataProvider().addFeatures([feat])
        
        ####################################################################################
        save_2_xlsx_params = {'LAYERS': [temp_lyr_fy, temp_lyr_cy],
            'USE_ALIAS':False,
            'FORMATTED_VALUES':False,
            'OUTPUT':dest_xlsx,
            'OVERWRITE':True}
            
        feedback.setCurrentStep(step)
        step+=1
        outputs['pcnt_burnt_summary'] = processing.run("native:exporttospreadsheet", save_2_xlsx_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['pcnt_burnt_summary'] = outputs['pcnt_burnt_summary']['OUTPUT']
        #######################################################################################
        return results
