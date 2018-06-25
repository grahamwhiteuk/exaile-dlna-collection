#  Copyright (C) 2018 Rok Mandeljc
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#


import xl
import xlgui

from gettext import gettext as _


class DlnaLibraryPlugin (object):
    """The exaile plugin."""

    __exaile = None

    def enable (self, exaile):
        """Enable plugin."""

        self.__exaile = exaile

    def teardown (self, exaile):
        """Shutdown plugin."""

    def disable (self, exaile):
        """Disable plugin."""
        self.teardown(exaile)

        # Remove the menu item
        for item in xl.providers.get('menubar-tools-menu'):
            if item.name == 'dlna':
                xl.providers.unregister('menubar-tools-menu', item)
                break


    def on_gui_loaded (self):
        """GUI setup."""

        # Add menu item
        menu_ = xlgui.widgets.menu.Menu(None)

        xl.providers.register('menubar-tools-menu',  xlgui.widgets.menu.simple_separator('plugin-sep', ['track-properties']))

        item = xlgui.widgets.menu.simple_menu_item('dlna', ['plugin-sep'], _('Connect to DLNA...'), submenu=menu_)
        xl.providers.register('menubar-tools-menu', item)


plugin_class = DlnaLibraryPlugin
