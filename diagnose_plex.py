"""Read-only connection diagnostics; never prints Plex tokens or library titles."""
import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import app


def main():
    state = app.read_state()
    servers = app.plex_servers(state, private=True)
    print('Discovered servers:', len(servers), flush=True)
    for index, server in enumerate(servers, 1):
        print('Server', index, 'owned:', server.get('owned'), flush=True)
        for connection in server.get('connections', []):
            print('Connection:', connection.get('uri'), 'local:', connection.get('local'), 'relay:', connection.get('relay'), flush=True)
            for path in ('/', '/identity', '/library/sections'):
                request = urllib.request.Request(connection['uri'].rstrip('/') + path, headers={'Accept': 'application/xml', 'X-Plex-Token': server['accessToken']})
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        root = ET.fromstring(response.read())
                        print(path, 'HTTP', response.status, 'identity matches:', root.get('machineIdentifier') == server['clientIdentifier'], 'attribute names:', ','.join(root.attrib), flush=True)
                except urllib.error.HTTPError as exc:
                    print(path, 'HTTP', exc.code, flush=True)
                    exc.close()
                except urllib.error.URLError as exc:
                    print(path, type(exc.reason).__name__, str(exc.reason), flush=True)
                except Exception as exc:
                    print(path, type(exc).__name__, str(exc), flush=True)


if __name__ == '__main__':
    main()
