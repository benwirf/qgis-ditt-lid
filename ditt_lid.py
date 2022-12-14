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
import sys
import inspect

from qgis.core import QgsProcessingAlgorithm, QgsApplication
from .ditt_lid_provider import DittLidProvider

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]

if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)


class DittLidPlugin(object):

    def __init__(self):
        self.provider = DittLidProvider()

    def initGui(self):
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)