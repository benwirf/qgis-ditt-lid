from processing.gui.wrappers import WidgetWrapper
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import (QCoreApplication,
                                QVariant,
                                Qt)
                                
from qgis.PyQt.QtWidgets import (QWidget,
                                QLabel,
                                QListWidget,
                                QTableWidget,
                                QVBoxLayout,
                                QHBoxLayout,
                                QListWidgetItem,
                                QTableWidgetItem,
                                QCheckBox,
                                QRadioButton,
                                QDialog,
                                QTabWidget)
                                
from qgis.core import (QgsField,
                        QgsProject,
                        QgsProcessing,
                        QgsProcessingAlgorithm,
                        QgsProcessingParameterMatrix,
                        QgsProcessingParameterLayout,
                        QgsProcessingParameterBoolean,
                        QgsProcessingParameterEnum,
                        QgsMapLayerProxyModel,
                        QgsTableCell,
                        QgsLayoutItemManualTable,
                        QgsLayoutFrame,
                        QgsLayoutSize,
                        QgsRenderContext,
                        QgsCoordinateTransform,
                        QgsDistanceArea,
                        QgsCoordinateReferenceSystem,
                        QgsUnitTypes)
                        
from qgis.gui import QgsMapLayerComboBox

from qgis.utils import iface

import os
                       
class AddLayoutTable(QgsProcessingAlgorithm):
    INPUT_PARAMETERS = 'INPUT_PARAMETERS'
    LAYOUT = 'LAYOUT'
    ADD_SYMBOL_COLUMN = 'ADD_SYMBOL_COLUMN'
 
    def __init__(self):
        super().__init__()
 
    def name(self):
        return "addtabletolayout"
         
    def displayName(self):
        return "Add table to layout"
 
    def group(self):
        return "General"
 
    def groupId(self):
        return "general"
        
    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "../icons/table_icon.png"))
 
    def shortHelpString(self):
        return "Add a custom table of field values and derived attributes\
        to a print layout."
 
    def helpUrl(self):
        return "https://qgis.org"
         
    def createInstance(self):
        return type(self)()
        
    def flags(self):
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading
        
    def checkParameterValues(self, parameters, context):
        input_layer_name = parameters[self.INPUT_PARAMETERS][0]
        input_layer = context.project().mapLayersByName(input_layer_name)
        if not input_layer:
            return (False, 'Missing parameter value for Input layer')
        if input_layer[0].featureCount()>50:
            return(False, 'Input layer has more than 50 features; resulting\
                            table will be large! You may wish to dissolve\
                            input layer before proceeding.')
        if (input_layer[0].geometryType() != 2) and (parameters[self.INPUT_PARAMETERS][3]):
            return (False, 'Area values can only be calculated for polygon layers')
        return (True, '')
   
    def initAlgorithm(self, config=None):
        source_params = QgsProcessingParameterMatrix(self.INPUT_PARAMETERS, 'Input parameters')
        source_params.setMetadata({'widget_wrapper': {'class': CustomParametersWidgetWrapper}})
        self.addParameter(source_params)
        
        self.addParameter(QgsProcessingParameterLayout(self.LAYOUT, 'Print layout to add table'))
        
        self.addParameter(QgsProcessingParameterBoolean(self.ADD_SYMBOL_COLUMN, 'Add symbol color column?'))

    def processAlgorithm(self, parameters, context, feedback):
        # parse all input parameters***********************************
        source_param_array = self.parameterAsMatrix(parameters, self.INPUT_PARAMETERS, context)
        
        lyr_name = source_param_array[0]
        fld_arr = source_param_array[1]
        hdr_map = source_param_array[2]
        area_cols = source_param_array[3]
        area_method = source_param_array[4]
        
        layout_name = self.parameterAsString(parameters, self.LAYOUT, context)
        
        add_symbol_column = self.parameterAsBool(parameters, self.ADD_SYMBOL_COLUMN, context)
        #**************************************************************
        lyr = context.project().mapLayersByName(lyr_name)[0]
        
        header_strings = [hdr_map[k] for k in fld_arr]
        
        if area_cols:
            for h in area_cols:
                header_strings.append(h)
        
        header_row = [QgsTableCell(v) for v in header_strings]
        
        if add_symbol_column:
            header_row.insert(0, QgsTableCell('Symbol'))
        
        tbl_rows = [header_row]

        if add_symbol_column:
            canvas = iface.mapCanvas()
            settings = canvas.mapSettings()
            render_context = QgsRenderContext.fromMapSettings(settings)
            renderer = lyr.renderer()
            renderer.startRender(render_context, lyr.fields())
        
        if area_cols:
            da = QgsDistanceArea()
            da.setSourceCrs(lyr.sourceCrs(), context.transformContext())
            da.setEllipsoid(lyr.sourceCrs().ellipsoidAcronym())
        
        for i, f in enumerate(lyr.getFeatures()):
            #TODO: check for canceled by user and report feedback progress
            if feedback.isCanceled():
                break
            pcnt = (i+1)/lyr.featureCount()*100
            feedback.setProgress(pcnt)
            tbl_row = []
            if add_symbol_column:
                symbol = renderer.symbolForFeature(f, render_context)
                symbol_color = symbol.color()
                symbol_cell = QgsTableCell()
                symbol_cell.setBackgroundColor(symbol_color)
                tbl_row.append(symbol_cell)
            for fld in fld_arr:
                tbl_row.append(QgsTableCell(f[fld]))
            # Calculate area columns
            if area_cols:
                if 'Area m2' in area_cols:
                    if area_method == 'Ellipsoidal':
                        a = da.measureArea(f.geometry())
                        area_m2 = da.convertAreaMeasurement(a, QgsUnitTypes.AreaSquareMeters)
                    elif area_method == 'Planimetric':
                        geom = self.transform_geom(lyr, f.geometry())
                        area_m2 = geom.area()
                    tbl_row.append(QgsTableCell(str(round(area_m2, 2))))
                if 'Area Ha' in area_cols:
                    if area_method == 'Ellipsoidal':
                        a = da.measureArea(f.geometry())
                        area_ha = da.convertAreaMeasurement(a, QgsUnitTypes.AreaHectares)
                    elif area_method == 'Planimetric':
                        geom = self.transform_geom(lyr, f.geometry())
                        area_ha = geom.area()/10000
                    tbl_row.append(QgsTableCell(str(round(area_ha, 3))))
                if 'Area km2' in area_cols:
                    if area_method == 'Ellipsoidal':
                        a = da.measureArea(f.geometry())
                        area_km2 = da.convertAreaMeasurement(a, QgsUnitTypes.AreaSquareKilometers)
                    elif area_method == 'Planimetric':
                        geom = self.transform_geom(lyr, f.geometry())
                        area_km2 = geom.area()/1000000
                    tbl_row.append(QgsTableCell(str(round(area_km2, 5))))
            tbl_rows.append(tbl_row)
        
        if add_symbol_column:
            renderer.stopRender(render_context)
            
        l = context.project().layoutManager().layoutByName(layout_name)
        t = QgsLayoutItemManualTable.create(l)
        l.addMultiFrame(t)
        t.setTableContents(tbl_rows)

        # Base class for frame items, which form a layout multiframe item.
        frame = QgsLayoutFrame(l, t)
        frame.attemptResize(QgsLayoutSize(150, 100), True)
        t.addFrame(frame)

        l.refresh()
         
        return {'layer': lyr,
                'rows': tbl_rows,
                'layout': l}
    
    def postProcessAlgorithm(self, context, feedback):
        # hack to work around ?bug where, if algorithm returns the NoThreading flag,
        # the dialog reverts to the Parameters tab instead of showing the Log tab with results
        alg_dlg = [d for d in iface.mainWindow().findChildren(QDialog)if d.objectName() == 'QgsProcessingDialogBase' and d.isVisible()]
        tab_widg = alg_dlg[0].findChildren(QTabWidget)
        current_tab = tab_widg[0].currentIndex()
        if current_tab == 0:
            tab_widg[0].setCurrentIndex(1)
        return {}
        
    def transform_geom(self, vl, g):
        if vl.sourceCrs().isGeographic():
            xform = QgsCoordinateTransform(vl.sourceCrs(), QgsCoordinateReferenceSystem('epsg:9473'), QgsProject.instance())
            g.transform(xform)
        return g
        
class CustomParametersWidgetWrapper(WidgetWrapper):

    def createWidget(self):
        self.cpw = CustomParametersWidget()
        return self.cpw
        
    def value(self):
        self.lyr = self.cpw.getLayer()
        self.flds = self.cpw.getFields()
        self.col_hdrs = self.cpw.getLayoutTableHeaders()
        self.area_cols = self.cpw.getAreaColumns()
        self.area_method = self.cpw.getAreaMethod()
        return [self.lyr, self.flds, self.col_hdrs, self.area_cols, self.area_method]

        
class CustomParametersWidget(QWidget):
    def __init__(self):
        super(CustomParametersWidget, self).__init__()
        self.layout = QVBoxLayout(self)
        self.lyr_lbl = QLabel('Input layer', self)
        self.lyr_cb = QgsMapLayerComboBox(self)
        self.lyr_cb.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.lyr_cb.layerChanged.connect(self.populateListWidget)
        self.fld_lbl = QLabel("Fields to add as table columns", self)
        self.lw = QListWidget(self)
        self.lw.itemChanged.connect(self.fieldSelectionChanged)
        self.tbl_lbl = QLabel('Enter table column headers')
        self.tbl = QTableWidget(self)
        ##########################INSERT AREA CALC WIDGETS##################
        self.param_lbl = QLabel('Calculate area attributes (polygon layers only)', self)
        self.param_lbl.setMinimumWidth(175)
        self.param_lbl.setMinimumHeight(30)
        self.area_m2_chk = QCheckBox('Area m2', self)
        self.area_ha_chk = QCheckBox('Area Ha', self)
        self.area_km2_chk = QCheckBox('Area km2', self)
        self.ellipsoidal_rb = QRadioButton('Ellipsoidal', self)
        self.ellipsoidal_rb.setChecked(True)
        self.ellipsoidal_rb.setEnabled(False)
        self.planimetric_rb = QRadioButton('Planimetric', self)
        self.planimetric_rb.setEnabled(False)
        self.method_lbl = QLabel('Area calculation method:', self)
        self.method_lbl.setMinimumWidth(175)
        self.method_lbl.setMinimumHeight(10)
        self.cb_layout = QHBoxLayout(self)
        self.cb_layout.addWidget(self.area_m2_chk)
        self.cb_layout.addWidget(self.area_ha_chk)
        self.cb_layout.addWidget(self.area_km2_chk)
        self.rb_layout = QHBoxLayout(self)
        self.rb_layout.addWidget(self.ellipsoidal_rb)
        self.rb_layout.addWidget(self.planimetric_rb)
        #*******************************************

        self.layout.addWidget(self.lyr_lbl)
        self.layout.addWidget(self.lyr_cb)
        self.layout.addWidget(self.fld_lbl)
        self.layout.addWidget(self.lw)
        self.layout.addWidget(self.tbl_lbl)
        self.layout.addWidget(self.tbl)
        #*******************************************
        self.layout.addWidget(self.param_lbl)
        self.layout.addLayout(self.cb_layout)
        self.layout.addWidget(self.method_lbl)
        self.layout.addLayout(self.rb_layout)

        self.checkboxes = [self.area_m2_chk,
                            self.area_ha_chk,
                            self.area_km2_chk]
                            
        self.radiobuttons = [self.ellipsoidal_rb,
                            self.planimetric_rb]
        
        for cb in self.checkboxes:
                cb.stateChanged.connect(self.manageRadioButtons)
        ####################################################################

        self.populateListWidget()
        self.setUpTable()
        self.manageCheckBoxes()
        
        self.lyr_cb.layerChanged.connect(self.manageCheckBoxes)
        
    def manageCheckBoxes(self):
        if self.lyr_cb.currentLayer():
            if self.lyr_cb.currentLayer().geometryType() == 2:
                for cbox in self.checkboxes:
                    cbox.setEnabled(True)
        else:
            for cbox in self.checkboxes:
                cbox.setCheckState(Qt.Unchecked)
                cbox.setEnabled(False)
    
    def populateListWidget(self):
        self.lw.clear()
        current_lyr = self.lyr_cb.currentLayer()
        if not current_lyr:
            return
        list_items = [f.name() for f in current_lyr.fields()]
        if list:
            for fld in list_items:
                li = QListWidgetItem(fld)
                li.setFlags(li.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                li.setCheckState(Qt.Unchecked)
                self.lw.addItem(li)
        self.fieldSelectionChanged()
    
    def setUpTable(self):
        self.tbl.setColumnCount(2)
        self.tbl.setHorizontalHeaderLabels(['Field Name', 'Alias'])
        
    def fieldSelectionChanged(self):
        checked_items = [self.lw.item(i) for i in range(self.lw.count()) if self.lw.item(i).checkState() == Qt.Checked]
        self.tbl.setRowCount(len(checked_items))
        for current, item in enumerate(checked_items):
            tbl_item = QTableWidgetItem(item.text())
            self.tbl.setItem(current, 0, tbl_item)
            
    def getLayer(self):
        if not self.lyr_cb.currentLayer():
            return
        return self.lyr_cb.currentLayer().name()
        
    def getFields(self):
        return [self.lw.item(i).text() for i in range(self.lw.count()) if self.lw.item(i).checkState() == Qt.Checked]
        
    def getLayoutTableHeaders(self):
        header_map = {}
        for i in range(self.tbl.rowCount()):
            cell_1 = self.tbl.item(i, 0)
            if cell_1:
                fld_name = cell_1.text()
            else:
                fld_name = ''
            cell_2 = self.tbl.item(i, 1)
            if cell_2:
                fld_alias = cell_2.text()
            else:
                fld_alias = ''
            header_map[fld_name] = fld_alias
        return header_map
        
    def manageRadioButtons(self):
        if self.area_m2_chk.checkState() == Qt.Checked or self.area_ha_chk.checkState() == Qt.Checked or self.area_km2_chk.checkState() == Qt.Checked:
            self.ellipsoidal_rb.setEnabled(True)
            self.planimetric_rb.setEnabled(True)
        else:
            self.ellipsoidal_rb.setEnabled(False)
            self.planimetric_rb.setEnabled(False)
            
    def getAreaColumns(self):
        return [chk_box.text() for chk_box in self.checkboxes if chk_box.checkState() == Qt.Checked]
        
    def getAreaMethod(self):
        return [rad_btn.text() for rad_btn in self.radiobuttons if rad_btn.isChecked()][0]
        
    