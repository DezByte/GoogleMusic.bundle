#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
The clients module exposes the main user-facing interfaces of gmusicapi.
"""

import logging

import gmusicapi
from gmusicapi.exceptions import CallFailure
from gmusicapi.protocol import webclient
from gmusicapi.utils import utils
import gmusicapi.session


class _Base(object):
    """Factors out common client setup."""

    __metaclass__ = utils.DocstringInheritMeta

    num_clients = 0  # used to disambiguate loggers

    def __init__(self, logger_basename, debug_logging):
        """

        :param debug_logging: each Client has a ``logger`` member.
          The logger is named ``gmusicapi.<client class><client number>`` and
          will propogate to the ``gmusicapi`` root logger.

          If this param is ``True``, handlers will be configured to send
          this client's debug log output to disk,
          with warnings and above printed to stderr.
          `Appdirs <https://pypi.python.org/pypi/appdirs/1.2.0>`__
          ``user_log_dir`` is used by default. Users can run::

              from gmusicapi.utils import utils
              print utils.log_filepath

          to see the exact location on their system.

          If ``False``, no handlers will be configured;
          users must create their own handlers.

          Completely ignoring logging is dangerous and not recommended.
          The Google Music protocol can change at any time; if
          something were to go wrong, the logs would be necessary for
          recovery.
        """
        # this isn't correct if init is called more than once, so we log the
        # client name below to avoid confusion for people reading logs
        _Base.num_clients += 1

        logger_name = "gmusicapi.%s%s" % (logger_basename,
                                          _Base.num_clients)
        self.logger = logging.getLogger(logger_name)

        if debug_logging:
            utils.configure_debug_log_handlers(self.logger)

        self.logger.info("initialized")

    def _make_call(self, protocol, *args, **kwargs):
        """Returns the response of a protocol.Call.

        args/kwargs are passed to protocol.perform.

        CallFailure may be raised."""

        return protocol.perform(self.session, *args, **kwargs)

    def is_authenticated(self):
        """Returns ``True`` if the Api can make an authenticated request."""
        return self.session.is_authenticated

    def logout(self):
        """Forgets local authentication in this Api instance.
        Returns ``True`` on success."""

        self.session.logout()
        self.logger.info("logged out")
        return True

class Webclient(_Base):
    """Allows library management and streaming by posing as the
    music.google.com webclient.

    Uploading is not supported by this client (use the :class:`Musicmanager`
    to upload).
    """

    def __init__(self, debug_logging=True):
        self.session = gmusicapi.session.Webclient()

        super(Webclient, self).__init__(self.__class__.__name__, debug_logging)
        self.logout()

    def login(self, email, password):
        """Authenticates the webclient.
        Returns ``True`` on success, ``False`` on failure.

        :param email: eg ``'test@gmail.com'`` or just ``'test'``.
        :param password: password or app-specific password for 2-factor users.
          This is not stored locally, and is sent securely over SSL.

        Users of two-factor authentication will need to set an application-specific password
        to log in.
        """

        if not self.session.login(email, password):
            self.logger.info("failed to authenticate")
            return False

        self.logger.info("authenticated")

        return True

    def logout(self):
        return super(Webclient, self).logout()

    def change_playlist_name(self, playlist_id, new_name):
        """Changes the name of a playlist. Returns the changed id.

        :param playlist_id: id of the playlist to rename.
        :param new_title: desired title.
        """

        self._make_call(webclient.ChangePlaylistName, playlist_id, new_name)

        return playlist_id  # the call actually doesn't return anything.

    @utils.accept_singleton(dict)
    @utils.empty_arg_shortcircuit()
    def change_song_metadata(self, songs):
        """Changes the metadata for some :ref:`song dictionaries <songdict-format>`.
        Returns a list of the song ids changed.

        :param songs: a list of :ref:`song dictionaries <songdict-format>`,
          or a single :ref:`song dictionary <songdict-format>`.

        Generally, stick to these metadata keys:

        * ``rating``: set to 0 (no thumb), 1 (down thumb), or 5 (up thumb)
        * ``name``: use this instead of ``title``
        * ``album``
        * ``albumArtist``
        * ``artist``
        * ``composer``
        * ``disc``
        * ``genre``
        * ``playCount``
        * ``totalDiscs``
        * ``totalTracks``
        * ``track``
        * ``year``
        """

        res = self._make_call(webclient.ChangeSongMetadata, songs)

        return [s['id'] for s in res['songs']]

    def create_playlist(self, name):
        """Creates a new playlist. Returns the new playlist id.

        :param title: the title of the playlist to create.
        """

        return self._make_call(webclient.AddPlaylist, name)['id']

    def delete_playlist(self, playlist_id):
        """Deletes a playlist. Returns the deleted id.

        :param playlist_id: id of the playlist to delete.
        """

        res = self._make_call(webclient.DeletePlaylist, playlist_id)

        return res['deleteId']

    @utils.accept_singleton(basestring)
    @utils.empty_arg_shortcircuit()
    def delete_songs(self, song_ids):
        """Deletes songs from the entire library. Returns a list of deleted song ids.

        :param song_ids: a list of song ids, or a single song id.
        """

        res = self._make_call(webclient.DeleteSongs, song_ids)

        return res['deleteIds']

    def get_all_songs(self, incremental=False):
        """Returns a list of :ref:`song dictionaries <songdict-format>`.

        :param incremental: if True, return a generator that yields lists
          of at most 2500 :ref:`song dictionaries <songdict-format>`
          as they are retrieved from the server. This can be useful for
          presenting a loading bar to a user.
        """

        to_return = self._get_all_songs()

        if not incremental:
            to_return = [song for chunk in to_return for song in chunk]

        return to_return

    def _get_all_songs(self):
        """Return a generator of song chunks."""

        get_next_chunk = True
        lib_chunk = {'continuationToken': None}

        while get_next_chunk:
            lib_chunk = self._make_call(webclient.GetLibrarySongs,
                                        lib_chunk['continuationToken'])

            yield lib_chunk['playlist']  # list of songs of the chunk

            get_next_chunk = 'continuationToken' in lib_chunk

    def get_playlist_songs(self, playlist_id):
        """Returns a list of :ref:`song dictionaries <songdict-format>`,
        which include ``playlistEntryId`` keys for the given playlist.

        :param playlist_id: id of the playlist to load.

        This will return ``[]`` if the playlist id does not exist.
        """

        res = self._make_call(webclient.GetPlaylistSongs, playlist_id)
        return res['playlist']

    def get_all_playlist_ids(self, auto=True, user=True):
        """Returns a dictionary that maps playlist types to dictionaries.

        :param auto: create an ``'auto'`` subdictionary entry.
          Currently, this will just map to ``{}``; support for 'Shared with me' and
          'Google Play recommends' is on the way (
          `#102 <https://github.com/simon-weber/Unofficial-Google-Music-API/issues/102>`__).

          Other auto playlists are not stored on the server, but calculated by the client.
          See `this gist <https://gist.github.com/simon-weber/5007769>`__ for sample code for
          'Thumbs Up', 'Last Added', and 'Free and Purchased'.

        :param user: create a user ``'user'`` subdictionary entry for user-created playlists.
          This includes anything that appears on the left side 'Playlists' bar (notably, saved
          instant mixes).

        User playlist names will be unicode strings.

        Google Music allows multiple user playlists with the same name, so the ``'user'`` dictionary
        will map onto lists of ids. Here's an example response::

            {
                'auto':{},

                'user':{
                    u'Some Song Mix':[
                        u'14814747-efbf-4500-93a1-53291e7a5919'
                    ],

                    u'Two playlists have this name':[
                        u'c89078a6-0c35-4f53-88fe-21afdc51a414',
                        u'86c69009-ea5b-4474-bd2e-c0fe34ff5484'
                    ]
                }
            }

        There is currently no support for retrieving automatically-created instant mixes
        (see issue `#67 <https://github.com/simon-weber/Unofficial-Google-Music-API/issues/67>`__).

        """

        playlists = {}

        if auto:
            #playlists['auto'] = self._get_auto_playlists()
            playlists['auto'] = {}
        if user:
            res = self._make_call(webclient.GetPlaylistSongs, 'all')
            playlists['user'] = self._playlist_list_to_dict(res['playlists'])

        return playlists

    def _playlist_list_to_dict(self, pl_list):
        ret = {}

        for name, pid in ((p["title"], p["playlistId"]) for p in pl_list):
            if not name in ret:
                ret[name] = []
            ret[name].append(pid)

        return ret

    def _get_auto_playlists(self):
        """For auto playlists, returns a dictionary which maps autoplaylist name to id."""

        #Auto playlist ids are hardcoded in the wc javascript.
        #When testing, an incorrect name here will be caught.
        return {u'Thumbs up': u'auto-playlist-thumbs-up',
                u'Last added': u'auto-playlist-recent',
                u'Free and purchased': u'auto-playlist-promo'}

    def get_song_download_info(self, song_id):
        """Returns a tuple: ``('<url>', <download count>)``.

        :param song_id: a single song id.

        ``url`` will be ``None`` if the download limit is exceeded.

        GM allows 2 downloads per song. The download count may not always be accurate,
        and the 2 download limit seems to be loosely enforced.

        This call alone does not count towards a download -
        the count is incremented when ``url`` is retrieved.
        """

        #TODO the protocol expects a list of songs - could extend with accept_singleton
        info = self._make_call(webclient.GetDownloadInfo, [song_id])
        url = info.get('url')

        return (url, info["downloadCounts"][song_id])

    def get_stream_url(self, song_id):
        """Returns a url that points to a streamable version of this song.

        :param song_id: a single song id.

        While acquiring the url requires authentication, retreiving the
        url contents does not.

        However, there are limitation as to how the stream url can be used:
            * the url expires after about a minute
            * only one IP can be streaming music at once.
              Other attempts will get an http 403 with
              ``X-Rejected-Reason: ANOTHER_STREAM_BEING_PLAYED``.

        *This is only intended for streaming*. The streamed audio does not contain metadata.
        Use :func:`get_song_download_info` to download complete files with metadata.
        """

        res = self._make_call(webclient.GetStreamUrl, song_id)

        return res['url']

    def copy_playlist(self, playlist_id, copy_name):
        """Copies the contents of a playlist to a new playlist. Returns the id of the new playlist.

        :param playlist_id: id of the playlist to be copied.
        :param copy_name: the name of the new copied playlist.

        This is useful for making backups of playlists before modifications.
        """

        orig_tracks = self.get_playlist_songs(playlist_id)

        new_id = self.create_playlist(copy_name)
        self.add_songs_to_playlist(new_id, [t["id"] for t in orig_tracks])

        return new_id

    def change_playlist(self, playlist_id, desired_playlist, safe=True):
        """Changes the order and contents of an existing playlist.
        Returns the id of the playlist when finished -
        this may be the same as the argument in the case of a failure and recovery.

        :param playlist_id: the id of the playlist being modified.
        :param desired_playlist: the desired contents and order as a list of
          :ref:`song dictionaries <songdict-format>`, like is returned
          from :func:`get_playlist_songs`.

        :param safe: if ``True``, ensure playlists will not be lost if a problem occurs.
          This may slow down updates.

        The server only provides 3 basic playlist mutations: addition, deletion, and reordering.
        This function will use these to automagically apply the desired changes.

        However, this might involve multiple calls to the server, and if a call fails,
        the playlist will be left in an inconsistent state.
        The ``safe`` option makes a backup of the playlist before doing anything, so it can be
        rolled back if a problem occurs. This is enabled by default.
        This might slow down updates of very large playlists.

        There will always be a warning logged if a problem occurs, even if ``safe`` is ``False``.
        """

        #We'll be modifying the entries in the playlist, and need to copy it.
        #Copying ensures two things:
        # 1. the user won't see our changes
        # 2. changing a key for one entry won't change it for another - which would be the case
        #     if the user appended the same song twice, for example.
        desired_playlist = [copy.deepcopy(t) for t in desired_playlist]
        server_tracks = self.get_playlist_songs(playlist_id)

        if safe:
            #Make a backup.
            #The backup is stored on the server as a new playlist with "_gmusicapi_backup"
            # appended to the backed up name.
            names_to_ids = self.get_all_playlist_ids()['user']
            playlist_name = (ni_pair[0]
                             for ni_pair in names_to_ids.iteritems()
                             if playlist_id in ni_pair[1]).next()

            backup_id = self.copy_playlist(playlist_id, playlist_name + u"_gmusicapi_backup")

        try:
            #Counter, Counter, and set of id pairs to delete, add, and keep.
            to_del, to_add, to_keep = \
                tools.find_playlist_changes(server_tracks, desired_playlist)

            ##Delete unwanted entries.
            to_del_eids = [pair[1] for pair in to_del.elements()]
            if to_del_eids:
                self._remove_entries_from_playlist(playlist_id, to_del_eids)

            ##Add new entries.
            to_add_sids = [pair[0] for pair in to_add.elements()]
            if to_add_sids:
                new_pairs = self.add_songs_to_playlist(playlist_id, to_add_sids)

                ##Update desired tracks with added tracks server-given eids.
                #Map new sid -> [eids]
                new_sid_to_eids = {}
                for sid, eid in new_pairs:
                    if not sid in new_sid_to_eids:
                        new_sid_to_eids[sid] = []
                    new_sid_to_eids[sid].append(eid)

                for d_t in desired_playlist:
                    if d_t["id"] in new_sid_to_eids:
                        #Found a matching sid.
                        match = d_t
                        sid = match["id"]
                        eid = match.get("playlistEntryId")
                        pair = (sid, eid)

                        if pair in to_keep:
                            to_keep.remove(pair)  # only keep one of the to_keep eids.
                        else:
                            match["playlistEntryId"] = new_sid_to_eids[sid].pop()
                            if len(new_sid_to_eids[sid]) == 0:
                                del new_sid_to_eids[sid]

            ##Now, the right eids are in the playlist.
            ##Set the order of the tracks:

            #The web client has no way to dictate the order without block insertion,
            # but the api actually supports setting the order to a given list.
            #For whatever reason, though, it needs to be set backwards; might be
            # able to get around this by messing with afterEntry and beforeEntry parameters.
            if desired_playlist:
                #can't *-unpack an empty list
                sids, eids = zip(*tools.get_id_pairs(desired_playlist[::-1]))

                if sids:
                    self._make_call(webclient.ChangePlaylistOrder, playlist_id, sids, eids)

            ##Clean up the backup.
            if safe:
                self.delete_playlist(backup_id)

        except CallFailure:
            self.logger.info("a subcall of change_playlist failed - "
                             "playlist %s is in an inconsistent state", playlist_id)

            if not safe:
                raise  # there's nothing we can do
            else:  # try to revert to the backup
                self.logger.info("attempting to revert changes from playlist "
                                 "'%s_gmusicapi_backup'", playlist_name)

                try:
                    self.delete_playlist(playlist_id)
                    self.change_playlist_name(backup_id, playlist_name)
                except CallFailure:
                    self.logger.warning("failed to revert failed change_playlist call on '%s'",
                                        playlist_name)
                    raise
                else:
                    self.logger.info("reverted changes safely; playlist id of '%s' is now '%s'",
                                     playlist_name, backup_id)
                    playlist_id = backup_id

        return playlist_id

    @utils.accept_singleton(basestring, 2)
    @utils.empty_arg_shortcircuit(position=2)
    def add_songs_to_playlist(self, playlist_id, song_ids):
        """Appends songs to a playlist.
        Returns a list of (song id, playlistEntryId) tuples that were added.

        :param playlist_id: id of the playlist to add to.
        :param song_ids: a list of song ids, or a single song id.
        """

        res = self._make_call(webclient.AddToPlaylist, playlist_id, song_ids)
        new_entries = res['songIds']

        return [(e['songId'], e['playlistEntryId']) for e in new_entries]

    @utils.accept_singleton(basestring, 2)
    @utils.empty_arg_shortcircuit(position=2)
    def remove_songs_from_playlist(self, playlist_id, sids_to_match):
        """Removes all copies of the given song ids from a playlist.
        Returns a list of removed (sid, eid) pairs.

        :param playlist_id: id of the playlist to remove songs from.
        :param sids_to_match: a list of song ids to match, or a single song id.

        This does *not always* the inverse of a call to :func:`add_songs_to_playlist`,
        since multiple copies of the same song are removed. For more control in this case,
        get the playlist tracks with :func:`get_playlist_songs`, modify the list of tracks,
        then use :func:`change_playlist` to push changes to the server.
        """

        playlist_tracks = self.get_playlist_songs(playlist_id)
        sid_set = set(sids_to_match)

        matching_eids = [t["playlistEntryId"]
                         for t in playlist_tracks
                         if t["id"] in sid_set]

        if matching_eids:
            #Call returns "sid_eid" strings.
            sid_eids = self._remove_entries_from_playlist(playlist_id,
                                                          matching_eids)
            return [s.split("_") for s in sid_eids]
        else:
            return []

    @utils.accept_singleton(basestring, 2)
    @utils.empty_arg_shortcircuit(position=2)
    def _remove_entries_from_playlist(self, playlist_id, entry_ids_to_remove):
        """Removes entries from a playlist. Returns a list of removed "sid_eid" strings.

        :param playlist_id: the playlist to be modified.
        :param entry_ids: a list of entry ids, or a single entry id.
        """

        #GM requires the song ids in the call as well; find them.
        playlist_tracks = self.get_playlist_songs(playlist_id)
        remove_eid_set = set(entry_ids_to_remove)

        e_s_id_pairs = [(t["id"], t["playlistEntryId"])
                        for t in playlist_tracks
                        if t["playlistEntryId"] in remove_eid_set]

        num_not_found = len(entry_ids_to_remove) - len(e_s_id_pairs)
        if num_not_found > 0:
            self.logger.warning("when removing, %d entry ids could not be found in playlist id %s",
                                num_not_found, playlist_id)

        #Unzip the pairs.
        sids, eids = zip(*e_s_id_pairs)

        res = self._make_call(webclient.DeleteSongs, sids, playlist_id, eids)

        return res['deleteIds']

    def search(self, query):
        """Queries the server for songs and albums.

        **WARNING**: Google no longer uses this endpoint in their client;
        it may stop working or be removed from gmusicapi without warning.
        In addition, it is known to occasionally return unexpected results.
        See `#114
        <https://github.com/simon-weber/Unofficial-Google-Music-API/issues/114>`__
        for more information.

        Instead of using this call, retrieve all tracks with :func:`get_all_songs`
        and search them locally.  `This gist
        <https://gist.github.com/simon-weber/5007769>`__ has some examples of
        simple linear-time searches.

        :param query: a string keyword to search with. Capitalization and punctuation are ignored.

        The results are returned in a dictionary, arranged by how they were found.
        ``artist_hits`` and ``song_hits`` return a list of
        :ref:`song dictionaries <songdict-format>`, while ``album_hits`` entries
        have a different structure.

        For example, a search on ``'cat'`` could return::

            {
                "album_hits": [
                    {
                        "albumArtist": "The Cat Empire",
                        "albumName": "Cities: The Cat Empire Project",
                        "artistName": "The Cat Empire",
                        "imageUrl": "//ssl.gstatic.com/music/fe/[...].png"
                        # no more entries
                    },
                ],
                "artist_hits": [
                    {
                        "album": "Cinema",
                        "artist": "The Cat Empire",
                        "id": "c9214fc1-91fa-3bd2-b25d-693727a5f978",
                        "title": "Waiting"
                        # ... normal song dictionary
                    },
                ],
                "song_hits": [
                    {
                        "album": "Mandala",
                        "artist": "RX Bandits",
                        "id": "a7781438-8ec3-37ab-9c67-0ddb4115f60a",
                        "title": "Breakfast Cat",
                        # ... normal song dictionary
                    },
                ]
            }

        """

        res = self._make_call(webclient.Search, query)['results']

        return {"album_hits": res["albums"],
                "artist_hits": res["artists"],
                "song_hits": res["songs"]}

    @utils.accept_singleton(basestring)
    @utils.empty_arg_shortcircuit()
    def report_incorrect_match(self, song_ids):
        """Equivalent to the 'Fix Incorrect Match' button, this requests re-uploading of songs.
        Returns the song_ids provided.

        :param song_ids: a list of song ids to report, or a single song id.

        Note that if you uploaded a song through gmusicapi, it won't be reuploaded
        automatically - this currently only works for songs uploaded with the Music Manager.
        See issue `#89 <https://github.com/simon-weber/Unofficial-Google-Music-API/issues/89>`__.

        This should only be used on matched tracks (``song['type'] == 6``).
        """

        self._make_call(webclient.ReportBadSongMatch, song_ids)

        return song_ids

    @utils.accept_singleton(basestring)
    @utils.empty_arg_shortcircuit()
    def upload_album_art(self, song_ids, image_filepath):
        """Uploads an image and sets it as the album art for songs.

        :param song_ids: a list of song ids, or a single song id.
        :param image_filepath: filepath of the art to use. jpg and png are known to work.

        This function will *always* upload the provided image, even if it's already uploaded.
        If the art is already uploaded and set for another song, copy over the
        value of the ``'albumArtUrl'`` key using :func:`change_song_metadata` instead.
        """

        res = self._make_call(webclient.UploadImage, image_filepath)
        url = res['imageUrl']

        song_dicts = [dict((('id', id), ('albumArtUrl', url))) for id in song_ids]

        return self.change_song_metadata(song_dicts)
