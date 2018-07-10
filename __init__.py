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


import weakref

import gi

gi.require_version('GUPnP', '1.0')
gi.require_version('GUPnPAV', '1.0')

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import GUPnP
from gi.repository import GUPnPAV

import xl.collection
import xl.event
import xl.trax
import xl.providers

import xlgui.panel.collection
import xlgui.widgets.menu

import logging

from gettext import gettext as _


logger = logging.getLogger(__name__)

class DlnaLibraryPanel (xlgui.panel.collection.CollectionPanel):
    def __init__ (self, parent, library):
        self.name = library.library_name

        self.net_collection = xl.collection.Collection(self.name)
        self.net_collection.add_library(library)

        xlgui.panel.collection.CollectionPanel.__init__(self, parent, self.net_collection,
                                 self.name, _show_collection_empty_message=False,
                                 label=self.name)

        library.connect("contents-changed", lambda *args: self.refresh())

    def __del__ (self):
        logger.info("DLNA Library Panel destroyed!")

    @xl.common.threaded
    def refresh (self):
        logger.info("DLNA Library Panel: refresh")

        # Since we don't use a ProgressManager/Thingy, we have to call these w/out
        # a ScanThread
        self.net_collection.rescan_libraries()
        GObject.idle_add(self._refresh_tags_in_tree)


class DlnaLibrary (xl.collection.Library, GObject.GObject):
    __gsignals__ = {
        'contents-changed': (GObject.SignalFlags.RUN_LAST, None, ())
    }

    def __init__ (self, media_server):
        GObject.GObject.__init__(self)

        # Initialize xl.collection.Library
        location = "dlna://%s" % (media_server.get_udn())
        xl.collection.Library.__init__(self, location)

        # Store library name
        self.library_name = media_server.get_friendly_name()

        # Get server's content directory
        self.__content_directory = media_server.get_service('urn:schemas-upnp-org:service:ContentDirectory')

        # Subscribe to update notifications
        weak_self = weakref.ref(self)
        self.__content_directory.add_notify("SystemUpdateID", str, lambda *args: weak_self().on_system_update_id(*args))
        self.__content_directory.set_subscribed(True)

        self.__ignore_id_update = True # Ignore initial ID update
        self.__last_update_id = None
        self.__update_timeout_id = None

        # Tracks
        self.__all_tracks = []
        self.__num_all_tracks = 0

    def __del__ (self):
        logger.info("DLNA Library destroyed!")

    def on_system_update_id (self, content_directory, variable, value):
        logger.info("DLNA Library: system updated IDs!")

        # Ignore initial ID update
        if self.__ignore_id_update:
            self.__ignore_id_update = False
            self.__last_update_id = value
            return

        # Require the update ID to differ from the previous one
        if self.__last_update_id is not None and self.__last_update_id == value:
            return

        # Schedule referesh; according to spec, the system update ID
        # event is moderated at maximum rate of 0.5 Hz (once every
        # two seconds). So we wait 5 seconds before running the update
        if self.__update_timeout_id is not None:
            GLib.source_remove(self.__update_timeout_id)

        weak_self = weakref.ref(self)
        self.__update_timeout_id = GLib.timeout_add_seconds(5, lambda *args: weak_self().on_system_update_id_timeout())

    def on_system_update_id_timeout (self):
        logger.info("DLNA Library: update timeout!")

        self.emit("contents-changed")

        self.__update_timeout_id = None
        return False


    def on_didl_object_available (self, parser, didl_object):
        """Called when DIDL-Lite parser parses a DIDL object"""

        # Process only audio items
        if not didl_object.get_upnp_class().startswith('object.item.audioItem'):
            return

        # Create track with primary URI
        resources = didl_object.get_resources()

        uri = resources[0].get_uri()
        track = xl.trax.Track(uri, scan=False)

        # Set up metadata
        artist = didl_object.get_artist()
        if artist is not None:
            track.set_tag_raw('artist', [ artist ], notify_changed=False)

        title = didl_object.get_title()
        if title is not None:
            track.set_tag_raw('title', [ title ], notify_changed=False)

        album = didl_object.get_album()
        if title is not None:
            track.set_tag_raw('album', [ album ], notify_changed=False)

        track_number = didl_object.get_track_number()
        if track_number is not None:
            track.set_tag_raw('tracknumber', [ u'%d' % (track_number) ], notify_changed=False)

        date = didl_object.get_date()
        if date is not None:
            tokens = date.split('-')
            track.set_tag_raw('year', [ tokens[0] ], notify_changed=False)

        # Append
        self.__all_tracks.append(track)

    def rescan (self, notify_interval=None, force_update=False):
        if self.collection is None:
            return True

        if self.scanning:
            return

        logger.info('Scanning library!')
        self.scanning = True

        # Get all tracks...
        self.collection.remove_tracks(self.__all_tracks)
        self.__all_tracks = []

        # Issue a search - we can use the synchronous variant, because
        # we are being called in a thread anyway...
        MAX_REQUEST_SIZE = 64

        start_index = 0
        request_size = MAX_REQUEST_SIZE

        weak_self = weakref.ref(self)

        parser = GUPnPAV.DIDLLiteParser.new()
        parser.connect("object-available", lambda *args: weak_self().on_didl_object_available(*args))

        while True:
            # Search from start index
            (status, out_values) = self.__content_directory.send_action_list("Search",
                ('ContainerID', 'SearchCriteria', 'Filter', 'StartingIndex', 'RequestedCount', 'SortCriteria'),
                ('0', 'upnp:class derivedfrom "object.item.audioItem"', '*', start_index, request_size, ''),
                ('Result', 'NumberReturned', 'TotalMatches'),
                (str, int, int)
            )

            didl_xml = out_values[0]
            number_returned = out_values[1]
            total_matches = out_values[2]

            logger.info('Retreieved %d music items!' % (number_returned))

            # Parse the returned DIDL
            if number_returned > 0:
                parser.parse_didl(didl_xml)

            # Do we have to retrieve more?
            # NOTE: some implementations (e.g., rygel) return 0 total
            # matches; in such cases, we try again until we receive zero
            # matches.
            start_index = start_index + number_returned
            remaining = total_matches - start_index

            if (remaining > 0 or total_matches == 0) and number_returned != 0:
                if remaining > 0:
                    request_size = min(remaining, MAX_REQUEST_SIZE)
                else:
                    request_size = MAX_REQUEST_SIZE
            else:
                logger.info('Retreieved all music items!')
                break

        # Add parsed tracks to collection
        count = len(self.__all_tracks)
        self.collection.add_tracks(self.__all_tracks)

        if notify_interval is not None:
            xl.event.log_event('tracks_scanned', self, count)

        # Cleanup
        self.scanning = False
        self.__num_all_tracks = len(self.__all_tracks)
        #self.__all_tracks = []

    # Needs to be overriden because default location walks over the
    # location
    def _count_files (self):
        """Needs to be overriden because default implementation attempts
           to walks over the location."""
        return self.__num_all_tracks


class DlnaManager (GObject.GObject):
    __gsignals__ = {
        'connect-to-server': (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING, ))
    }

    def __init__ (self, exaile, menu):
        GObject.GObject.__init__(self)

        self.__context_manager = None
        self.__control_point = None

        self.__exaile = exaile

        self.__media_servers = {}
        self.__panels = {}

        # Menu UI
        self.__menu = menu

        weak_self = weakref.ref(self) # Create a weak reference to pass to the item's callback
        self.__menu.add_item(xlgui.widgets.menu.simple_menu_item('rescan', [], _('Rescan...'), callback=lambda *args: weak_self().rescan()))
        self.__menu.add_item(xlgui.widgets.menu.simple_separator('sep', ['rescan']))

        # Create GUPnP context manager
        self.__context_manager = GUPnP.ContextManager.create(0)
        self.__context_manager.connect("context-available", weak_self().on_context_available)
        self.__context_manager.rescan_control_points()

        self.connect('connect-to-server', lambda o,u: weak_self().on_connect_to_server(u))

    def __del__ (self):
        """Overriden to track object's lifetime."""
        logger.info("DLNA Manager destroyed!")

    def shutdown (self):
        self.__exaile = None
        self.__context_manager = None
        self.__control_point = None

        #self.__media_servers = {}

    def on_context_available (self, context_manager, context):
        """Called when GUPnP context becomes available."""

        weak_self = weakref.ref(self) # Create a weak reference to self to pass on to signal connections

        # Create control point that monitors appearance and disappearance
        # of media servers
        control_point = GUPnP.ControlPoint.new(context, "urn:schemas-upnp-org:device:MediaServer:1")
        control_point.connect("device-proxy-available", lambda *args: weak_self().on_server_proxy_available(*args))
        control_point.connect("device-proxy-unavailable", lambda *args: weak_self().on_server_proxy_unavailable(*args))

        control_point.set_active(True)

        # Let context manager manage the control point
        context_manager.manage_control_point(control_point)

        # Store reference
        self.__control_point = control_point


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
        if self.__context_manager is not None:
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
        for (friendly_name, udn) in servers:
            self.new_server_menu_item(friendly_name, udn)


    def clear_menu_items (self):
        """Removes all menu items."""

        if self.__menu:
            for item in self.__menu._items:
                if item.name == 'rescan' or item.name == 'sep':
                    continue
                self.__menu.remove_item(item)

    def new_server_menu_item (self, name, udn):
        """Adds a new server menu item."""

        weak_self = weakref.ref(self)

        logger.info("Adding menu %s: %s", name, udn)
        if self.__menu:
            menu_item = xlgui.widgets.menu.simple_menu_item(udn, ['sep'], name, callback=lambda *args: weak_self().on_server_menu_entry_clicked(udn))
            self.__menu.add_item(menu_item)

    def on_server_menu_entry_clicked (self, udn):
        """Called when user clicks on a server menu item."""

        logger.info("Clicked on server entry: {0}".format(udn))

        GObject.idle_add(self.emit, "connect-to-server", udn)


    def on_connect_to_server (self, udn):
        """Connection request"""

        if udn in self.__panels:
            logger.info("Panel already opened!")
            return

        # Create library
        library = DlnaLibrary(self.__media_servers[udn])

        # Create new panel
        panel = DlnaLibraryPanel(self.__exaile.gui.main.window, library)

        panel.refresh() # threaded/async
        xl.providers.register('main-panel', panel)

        self.__panels[udn] = panel


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
            self.__manager.shutdown()
            self.__manager = None

        self.__exaile = None

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
