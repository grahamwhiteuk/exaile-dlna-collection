DLNA Collection plugin for Exaile
=================================

This plugin allows Exaile to browse the music from DLNA media servers.
It allows user to connect to a media server, and upon connection,
searches the server for audio tracks. The discovered audio tracks are
then organized into virtual Exaile collection, from which they can be
browsed and added to Exaile's queue or playlist.

The plugin implements only a browser, i.e., the collection of the audio
tracks from the media server via the GUPnP/GUPnpAV library. The actual
playback is handled entirely by Exaile's ability to stream from HTTP
locations.


Requirements:
-------------

- Exaile
- GIR bindings for GUPnP library
- GIR bindings for GUPnPAV library


Installation:
-------------

The plugin can be installed by copying the ```dlna-collection``` folder
from ```plugins``` to the plugin folder of your Exaile installation.

The ```DLNA Collection``` plugin should then be listed under ```Media Sources```
in the Plugins list.


Usage:
------

Enabling the plugin will add a ```Connect to DLNA...``` item menu
under ```Tools```, where the discovered DLNA media servers will be
listed.

Clicking on the server entry will connect to the server and open new
collection panel that is populated once discovery of audio tracks is
completed. From there, the tracks can be added to queue or a playlist.

The plugin supports notifications about server-side changes; a rescan
of media share is typically performed five seconds after the last
update notification from a server. In case you wish to trigger manual
rescan, hold Shift key and click on the ```Refresh collection view```
button at the top of the collection panel.

To disconnect from the share, click the ```Disconnect``` button at the
top of the collection panel. Note that closing the collection panel
does not disconnect from the share, and that the closed panel can
be re-opend by ```View -> Panels``` menu.


Tested with:
------------

- rygel 0.36.1
- minidlna 1.1.6


Known issues:
-------------

- Adding a track from media server to the playlist and playing it for the
  first time causes the tree view in collection panel to collapse its
  entries.

  This is because when tracks are imported into the virtual collection,
  their tags are populated from properties returned by the DLNA server.
  Once the track is actually played, the tags are updated from the
  stream. This update triggers refresh of the tags in the tree-view,
  which in turn causes the view itself to be updated and collapsed.

  As such, this happens every time when a track from media server is
  played for the first time.
