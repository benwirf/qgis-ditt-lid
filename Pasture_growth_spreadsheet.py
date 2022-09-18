
from qgis.PyQt.QtCore import QCoreApplication, QVariant, Qt
from qgis.core import (QgsProcessing, QgsProcessingAlgorithm, QgsProcessingParameterString,
                    QgsProcessingParameterVectorLayer, QgsProcessingParameterEnum,
                    QgsProcessingParameterFileDestination, QgsProcessingParameterFile,
                    QgsProcessingMultiStepFeedback, QgsVectorLayer, QgsField,
                    QgsFeature, QgsMessageLog)
import processing
import os
import datetime

                  
class PastureGrowthSpreadsheet(QgsProcessingAlgorithm):
    INDIR = 'INDIR'
    DISTRICTS = 'DISTRICTS'
    FY = 'FY'
    OUTPUT_XL = 'OUTPUT_XL'
    
    msg_log = QgsMessageLog()
        
    financial_yrs = []
 
    def __init__(self):
        super().__init__()
 
    def name(self):
        return "Pasture_growth_spreadsheet"
         
    def displayName(self):
        return "Pasture growth spreadsheet"
 
    def group(self):
        return "Feed Outlook"
 
    def groupId(self):
        return "Feed_outlook"
 
    def shortHelpString(self):
        return "Creates Excel Spreadsheet for stacked, median monthly growth for each pastoral district by FY"
 
    def helpUrl(self):
        return "https://qgis.org"
         
    def createInstance(self):
        return type(self)()
   
    def initAlgorithm(self, config=None):
        self.financial_yrs.clear()
        self.addParameter(QgsProcessingParameterFile(self.INDIR, 'Monthly Growth Source Directory', behavior=QgsProcessingParameterFile.Folder))        
        self.addParameter(QgsProcessingParameterVectorLayer(self.DISTRICTS, 'Pastoral districts', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        ###Construct list of current + 4 previous financial years to add as options to enum dropdown
        cdt = datetime.datetime.now()
        current_yr = cdt.year
        current_mnth = cdt.month
        if current_mnth>6:
            financial_year = f'{current_yr}-{current_yr+1} FY'
        elif current_month<=6:
            financial_year = f'{current_yr-1}-{current_yr} FY'
        self.financial_yrs.append(financial_year)
        self.financial_yrs.append(f'{str(int(financial_year.split("-")[0])-1)}-{str(int(financial_year.split("-")[1][:4])-1)} FY')
        self.financial_yrs.append(f'{str(int(financial_year.split("-")[0])-2)}-{str(int(financial_year.split("-")[1][:4])-2)} FY')
        self.financial_yrs.append(f'{str(int(financial_year.split("-")[0])-3)}-{str(int(financial_year.split("-")[1][:4])-3)} FY')
        self.financial_yrs.append(f'{str(int(financial_year.split("-")[0])-4)}-{str(int(financial_year.split("-")[1][:4])-4)} FY')
        
        self.addParameter(QgsProcessingParameterEnum(self.FY, 'Financial Year', self.financial_yrs, defaultValue=self.financial_yrs[0]))
        self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT_XL, 'Output District Spreadsheet', 'Microsoft Excel (*.xlsx);;Open Document Spreadsheet (*.ods)'))
 
    def processAlgorithm(self, parameters, context, model_feedback):
        results = {}
        outputs = {}
        
        growth_folder_path = self.parameterAsString(parameters, self.INDIR, context)
        
        district_layer = self.parameterAsVectorLayer(parameters, self.DISTRICTS, context)
        
        fy_enum = self.parameterAsEnum(parameters, 'FY', context) # Returns index of selected option
        fy = self.financial_yrs[fy_enum] # Get string of selected option by index
        
        months = ['January', 'February',  'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

        northern_district_medians = {'Darwin': 2010, 'Katherine': 2097, 'Victoria River': 1842, 'Sturt Plateau': 2031, 'Roper': 2215, 'Gulf': 2083}
        southern_district_medians = {'Barkly': 664, 'Tennant Creek': 288, 'Northern Alice Springs': 495, 'Plenty': 328, 'Southern Alice Springs': 232}
###################################################################################################
        fy_folders = []

        fy_folders.append((f"{int(fy.split(' ')[0].split('-')[0])-2}-{int(fy.split(' ')[0].split('-')[1])-2} FY"))
        fy_folders.append((f"{int(fy.split(' ')[0].split('-')[0])-1}-{int(fy.split(' ')[0].split('-')[1])-1} FY"))
        fy_folders.append(fy)

        all_districts = list(northern_district_medians.keys()) + list(southern_district_medians.keys())

        district_results = [list() for i in range(11)]
        ############################################################################################
        # Number of processing steps will be sum of all .img files in all 3 folders
        # Addition nested loop required to get count of all input files *is there a better way???
        steps = 0
        for fy_folder in fy_folders:
            fyear = fy_folder.split(' ')[0]
            dir_path = os.path.join(growth_folder_path, fy_folder)
            file_count = [file for file in os.scandir(dir_path) if file.name.split('.')[-1] == 'img']
            if len(file_count) == 1:
                steps += len(file_count)# Just zonal stats will be run (1 alg)
            else:
                steps += len(file_count)*2 # Cell stats (sum) and zonal stats will be run (2 algs)
        steps += 12 # number of districts (1 step for each district) + export to xlsx alg
        self.msg_log.logMessage(f'Calculated Steps {steps}')
        feedback = QgsProcessingMultiStepFeedback(steps, model_feedback)
        step = 1
        ###########################################################################################
        #TODO: set (increment) step, feedback, child alg etc. for each processing call
        for fy_folder in fy_folders:
            fyear = fy_folder.split(' ')[0]
            raw_inputs = []
            dir_path = os.path.join(growth_folder_path, fy_folder)
            for file in os.scandir(dir_path):
                if file.name.split('.')[-1] == 'img':
                    raster_path = os.path.join(dir_path, file.name)
                    raw_inputs.append(raster_path)
            # os.scandir() does not return files in directory order...
            # we need to return a sorted (yyyymm) version of the input list e.g. [202107, 202108, 202109] etc.
            inputs = sorted(raw_inputs)
            for i in range(len(inputs)):
                ##########Get calendar year and month###################
                calendar_yr = inputs[i].split('/')[-1].split('.')[0][:4]
                mnth_digit = inputs[i].split('/')[-1].split('.')[0][-2:]
                mnth_name = months[int(mnth_digit)-1]
                ########################################################
                # add next input to stack on each iteration e.g. [1], [1,2], [1,2,3] etc
                rstack = inputs[:i+1]
                if len(rstack) == 1:
                    # just run zonal stats on single input
                    zonal_stats_params = {'INPUT':district_layer,
                                'INPUT_RASTER':rstack[0],
                                'RASTER_BAND':1,
                                'COLUMN_PREFIX':'_',
                                'STATISTICS':[2,3],
                                'OUTPUT':'TEMPORARY_OUTPUT'}
                    
                    feedback.setCurrentStep(step)
                    step+=1
                    outputs['stats'] = processing.run("native:zonalstatisticsfb", zonal_stats_params, context=context, feedback=feedback, is_child_algorithm=True)
                    results['stats'] = outputs['stats']['OUTPUT']

                elif len(rstack) > 1:
                    # run cell stats to sum pixels of rasters in rstack, then zonal stats for mean & median for each district
                    cell_stat_params = {'INPUT':rstack,
                            'STATISTIC':0,
                            'IGNORE_NODATA':True,
                            'REFERENCE_LAYER':rstack[0],
                            'OUTPUT_NODATA_VALUE':-9999,
                            'OUTPUT':'TEMPORARY_OUTPUT'}
                    
                    feedback.setCurrentStep(step)
                    step+=1
                    outputs['cell_sum'] = processing.run("native:cellstatistics", cell_stat_params)
                    results['cell_sum'] = outputs['cell_sum']['OUTPUT']
                    
                    zonal_stats_params = {'INPUT':district_layer,
                                'INPUT_RASTER':results['cell_sum'],
                                'RASTER_BAND':1,
                                'COLUMN_PREFIX':'_',
                                'STATISTICS':[2,3],
                                'OUTPUT':'TEMPORARY_OUTPUT'}

                    feedback.setCurrentStep(step)
                    step+=1
                    outputs['stats'] = processing.run("native:zonalstatisticsfb", zonal_stats_params, context=context, feedback=feedback, is_child_algorithm=True)
                    results['stats'] = outputs['stats']['OUTPUT']
                    
                for f in context.getMapLayer(results['stats']).getFeatures():
                    for i, district in enumerate(all_districts):
                        if f['DISTRICT'] == district or (district == 'Victoria River' and f['DISTRICT'] == 'V.R.D.'):
                            if district in northern_district_medians.keys():
                                long_term_median = northern_district_medians[district]
                            elif district in southern_district_medians.keys():
                                long_term_median = southern_district_medians[district]
                            # Write all column values as a row/feature attributes
                            district_results[i].append([fyear, calendar_yr, mnth_name, f['DISTRICT'], f['_mean'], long_term_median, f['_median']])
        
            
        output_layers = []
                    
        for district_result in district_results:
            district_name = district_result[0][3]
            layer = QgsVectorLayer('Point', district_name, 'memory')
            layer.dataProvider().addAttributes([
                QgsField('Financial_year', QVariant.String),
                QgsField('Calendar_year', QVariant.String),
                QgsField('Month', QVariant.String),
                QgsField('District', QVariant.String),
                QgsField('Cumulative_mean', QVariant.Double),
                QgsField('Long_term_median', QVariant.Int),
                QgsField('Cumulative_median', QVariant.Double)
            ])

            for row in district_result:
                feat = QgsFeature()
                feat.setAttributes(row)
                layer.dataProvider().addFeatures([feat])
                layer.updateFeature(feat)
            
            output_layers.append(layer)
            feedback.setCurrentStep(step)
            step+=1
            
        # Export layers to spreadsheet

        save_2_xls_params = {'LAYERS': output_layers,
            'USE_ALIAS':False,
            'FORMATTED_VALUES':False,
            'OUTPUT':parameters[self.OUTPUT_XL],
            'OVERWRITE':True}
        
        feedback.setCurrentStep(step)
        step+=2 # Make up unaccounted for discrepancy (Calculated steps is one more than completed steps)??
        outputs['xlsx'] = processing.run("native:exporttospreadsheet", save_2_xls_params)
        results['xlsx'] = outputs['xlsx']['OUTPUT']
        self.msg_log.logMessage(f'Completed Steps: {step}')
##################################################################################################
        return results

        