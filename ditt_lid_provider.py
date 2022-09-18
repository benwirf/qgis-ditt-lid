# -*- coding: utf-8 -*-

"""
/***************************************************************************
 LID
                                 A QGIS processing plugin

    A collection of scripts for quarterly feed outlook report
    
        begin                : September 2022
        copyright            : (C) 2022 by Ben Wirf
        email                : ben.wirf@gmail.com
 ***************************************************************************/
/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Ben Wirf'
__date__ = '2022-09-11'
__copyright__ = '(C) 2022 by Ben Wirf'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
from PyQt5.QtGui import QIcon
from qgis.core import QgsProcessingProvider
from .Clip_rasters_by_pastoral_district import ClipRastersByPastoralDistrict
from .Fire_risk_summary import FireRiskSummary
from .Pasture_growth_graphs import PastureGrowthGraphs
from .Pasture_growth_spreadsheet import PastureGrowthSpreadsheet
from .Percentage_burnt_by_district import PercentBurntByDistrict
from .Total_growth_summary import TotalGrowthSummary

iconPath = os.path.dirname(__file__)


class DittLidProvider(QgsProcessingProvider):

    def __init__(self):
        QgsProcessingProvider.__init__(self)

    def load(self):
        self.refreshAlgorithms()
        return True

    def unload(self):
        """
        Unloads the provider. Any tear-down steps required by the provider
        should be implemented here.
        """
        pass

    def isActive(self):
        return True

    def loadAlgorithms(self):
        """
        Loads all algorithms belonging to this provider.
        """
        # Load algorithms
        self.alglist = [ClipRastersByPastoralDistrict(),
                        FireRiskSummary(),
                        PastureGrowthGraphs(),
                        PastureGrowthSpreadsheet(),
                        PercentBurntByDistrict(),
                        TotalGrowthSummary()]

        for alg in self.alglist:
            self.addAlgorithm(alg)

    def icon(self):
        return QIcon(os.path.join(iconPath, "ntg-logo.png"))

    def id(self):
        """
        Returns the unique provider id, used for identifying the provider. This
        string should be a unique, short, character only string, eg "qgis" or
        "gdal". This string should not be localised.
        """
        return 'ditt-lid'

    def name(self):
        """
        Returns the provider name, which is used to describe the provider
        within the GUI.
        This string should be short (e.g. "Lastools") and localised.
        """
        return 'Livestock Industries'

    def longName(self):
        """
        Returns the a longer version of the provider name, which can include
        extra details such as version numbers. E.g. "Lastools LIDAR tools
        (version 2.2.1)". This string should be localised. The default
        implementation returns the same string as name().
        """
        return self.name()