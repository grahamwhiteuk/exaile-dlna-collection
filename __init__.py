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


import gi
gi.require_version('GUPnP', '1.0')
from gi.repository import GUPnP

import xl
import xlgui

import logging

from gettext import gettext as _


logger = logging.getLogger(__name__)

class DlnaManager (object):
    def __init__ (self, exaile, menu):
        self.__control_point = None

        self.__media_servers = {}

        # Menu UI
        self.__menu = menu

        self.__menu.add_item(xlgui.widgets.menu.simple_menu_item('rescan', [], _('Rescan...'), callback=self.rescan))
        self.__menu.add_item(xlgui.widgets.menu.simple_separator('sep', ['rescan']))

        # Create GUPnP context manager
        self.__context_manager = GUPnP.ContextManager.create(0)
        self.__context_manager.connect("context-available", self.on_context_available)
        self.__context_manager.rescan_control_points()

    def on_context_available (self, context_manager, context):
        """Called when GUPnP context becomes available."""

        # Create control point that monitors appearance and disappearance
        # of media servers
        self.__control_point = GUPnP.ControlPoint.new(context, "urn:schemas-upnp-org:device:MediaServer:1")
        self.__control_point.connect("device-proxy-available", self.on_server_proxy_available);
        self.__control_point.connect("device-proxy-unavailable", self.on_server_proxy_unavailable);

        self.__control_point.set_active(True)

        # Let context manager manage the control point
        context_manager.manage_control_point(self.__control_point)

    def on_server_proxy_available (self, control_point, media_server):
        """Called when a Media Server becomes available."""
        udn = media_server.get_udn()
        friendly_name = media_server.get_friendly_name()

        logger.info("DLNA Media Server available: '{0}', '{1}'".format(udn, friendly_name))

        # Store the media server
        if udn in self.__media_servers:
            return

        self.__media_servers[udn] = media_server

        # Rebuild menu items list
        self.rebuild_server_menu_items()


    def on_server_proxy_unavailable (self, control_point, media_server):
        """Called when a Media Server becomes unavailable."""
        udn = media_server.get_udn()

        logger.info("DLNA Media Server unavailable: '{0}''".format(udn))

        if udn in self.__media_servers:
            del self.__media_servers[udn]

            self.rebuild_server_menu_items()

    def rescan (self, *_args):
        """Rescan for DLNA media servers."""

        logger.info("Manual rescan!")

        # Trigger rescan of control points
        self.__context_manager.rescan_control_points()


    def rebuild_server_menu_items (self):
        """Rebuilds the list of menu items for available servers."""

        # Clear all
        self.clear_menu_items()

        # Build server list...
        servers = []

        for udn, media_server in self.__media_servers.items():
            friendly_name = media_server.get_friendly_name()
            servers.append(( friendly_name, udn ))

        # ... and sort it by friendly name
        #servers = sorted(servers, key=lambda server: server[0].lower())

        # Add items
        for server in servers:
            self.new_server_menu_item(server[0], server[1])


    def clear_menu_items (self):
        """Removes all menu items."""

        if self.__menu:
            for item in self.__menu._items:
                if item.name == 'rescan' or item.name == 'sep':
                    continue
                self.__menu.remove_item(item)

    def new_server_menu_item (self, name, udn):
        """Adds a new server menu item."""

        logger.info("Adding menu %s: %s", name, udn)
        if self.__menu:
            menu_item = xlgui.widgets.menu.simple_menu_item(udn, ['sep'], name, callback=lambda *_x: self.on_server_menu_entry_clicked(udn))
            self.__menu.add_item(menu_item)

    def on_server_menu_entry_clicked (self, udn):
        """Called when user clicks on a server menu item."""

        logger.info("Clicked on server entry: {0}".format(udn))


class DlnaLibraryPlugin (object):
    """The exaile plugin."""

    __exaile = None
    __manager = None

    def enable (self, exaile):
        """Enable plugin."""

        self.__exaile = exaile

    def teardown (self, exaile):
        """Shutdown plugin."""

        if self.__manager is not None:
            self.__manager = None

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
        menu = xlgui.widgets.menu.Menu(None)

        xl.providers.register('menubar-tools-menu',  xlgui.widgets.menu.simple_separator('plugin-sep', ['track-properties']))

        item = xlgui.widgets.menu.simple_menu_item('dlna', ['plugin-sep'], _('Connect to DLNA...'), submenu=menu)
        xl.providers.register('menubar-tools-menu', item)

        # Create the UPnP manager
        self.__manager = DlnaManager(self.__exaile, menu)


plugin_class = DlnaLibraryPlugin
