from gmusicapi.api import Api

MUSIC_PREFIX = '/music/googlemusic'

NAME = L('Title')

ART = 'art-default.jpg'
ICON = 'icon-default.png'

api = Api()
################################################################################

def Start():
    Plugin.AddPrefixHandler(MUSIC_PREFIX, MusicMainMenu, NAME, ICON, ART)

    Plugin.AddViewGroup("InfoList", viewMode="InfoList", mediaType="items")
    Plugin.AddViewGroup("List", viewMode = "List", mediaType = "items")

    ObjectContainer.art = R(ART)
    ObjectContainer.title1 = NAME
    DirectoryObject.thumb = R(ICON)
    
    #MediaContainer.title1 = NAME
    #MediaContainer.viewGroup = "List"
    #MediaContainer.art = R(ART)
    #DirectoryItem.thumb = R(ICON)

def ValidatePrefs():
    return True

def MusicMainMenu():
    dir = MediaContainer(viewGroup="InfoList")

    # Borrowed menu display based on prefs/auth from Pandora plugin
    # https://github.com/plexinc-plugins/Pandora.bundle/
    if 'GMusicConnection' not in Dict:
        Dict['GMusicConnection'] = {}

    if not Prefs['email'] or not Prefs['password']:
        dir.Append(PrefsItem(title=L('Prefs Title')))
        return dir
    elif 'authed' in Dict['GMusicConnection']:
        if Dict['GMusicConnection']['authed']:
            authed = Dict['GMusicConnection']['authed']
        else:
            authed = GMusic_Authenticate()
    else:
        authed = GMusic_Authenticate()

    if not authed:
        dir.Append(PrefsItem(title=L('Prefs Title'), summary=L('Bad Password')))
    else:
        dir.Append(Function(DirectoryItem(PlaylistList, L('Playlists'))))
        dir.Append(Function(DirectoryItem(ArtistList, L('Artists'))))
        dir.Append(Function(DirectoryItem(AlbumList, L('Albums'))))
        dir.Append(Function(DirectoryItem(SongList, L('Songs'))))
        dir.Append(Function(InputDirectoryItem(SearchResults, L('Search'), L('Search'), summary=L('Search Prompt'), thumb=R(ICON), art=R(ART))))
        dir.Append(PrefsItem(title=L('Prefs Title Change')))

    return dir

def GMusic_Authenticate():
    global api
    authed = api.login(Prefs['email'], Prefs['password'])

    if authed:
        return True
    else:
        return False

def PlaylistList(sender):
    dir = MediaContainer(viewGroup="InfoList")

    playlists = api.get_all_playlist_ids()

    for k, v in playlists['user'].iteritems():
        dir.Append(Function(DirectoryItem(Playlist, k), id=v))

    return dir

def Playlist(sender, id=None):
    dir = MediaContainer(viewGroup="InfoList")
    
    songs = api.get_playlist_songs(id)

    for song in songs:
        if song.has_key('artist'):
            s = song['artist']
        if not s == None:
            s += " - "
        if song.has_key('title'):
            s += song['title']
        dir.Append(Function(DirectoryItem(PlayAudio, s), song=song))

    return dir

def ArtistList(sender):
    return

def AlbumList(sender):
    return

def SongList(sender):
    return

def PlayAudio(sender, song=None):
    if song:
        song_url = api.get_stream_url(song['id'])

    oc = ObjectContainer()
    oc.add(TrackObject(key=song_url, rating_key=0, title=song['title']))

    return oc

def SearchResults(sender, query=None):
    return
