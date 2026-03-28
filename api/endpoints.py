"""API URL path constants for the Dispatcharr REST API.

Import this module and use these constants instead of inline strings so that
any API path changes only need to be updated in one place.
"""

AUTH              = "/api/accounts/token/"
M3U_REFRESH       = "/api/m3u/refresh/"
M3U_ACCOUNTS      = "/api/m3u/accounts/"
STREAMS           = "/api/channels/streams/"
CHANNELS          = "/api/channels/channels/"
CHANNEL_GROUPS    = "/api/channels/channelgroups/"
CREATE_FROM_STREAM = "/api/channels/channels/from-stream/"
EPG_SOURCES       = "/api/epg/sources/"      # XMLTV source feeds
EPG_DATA          = "/api/epg/epgdata/"      # EPG channel entries (id, tvg_id, name, epg_source)
