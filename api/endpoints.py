"""API URL path constants for the Dispatcharr REST API.

Import this module and use these constants instead of inline strings so that
any API path changes only need to be updated in one place.
"""

AUTH              = "/api/accounts/token/"
M3U_REFRESH       = "/api/m3u/refresh/"
STREAMS           = "/api/channels/streams/"
CHANNELS          = "/api/channels/channels/"
CREATE_FROM_STREAM = "/api/channels/channels/from-stream/"
