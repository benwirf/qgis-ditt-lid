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
 This script initializes the plugin, making it known to QGIS.
"""

__author__ = 'Ben Wirf'
__date__ = '2022-09-11'
__copyright__ = '(C) 2022 by Ben Wirf'


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load DittLidPlugin class from file ditt_lid.py.
    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .ditt_lid import DittLidPlugin
    return DittLidPlugin()