"""Connection addresses from local interfaces, without probing the internet."""

import ipaddress
import re
import socket
import subprocess
import sys


def connection_urls(port, host='0.0.0.0'):
    if host in {'127.0.0.1', 'localhost'}:
        return [f'http://127.0.0.1:{port}']
    addresses = set()
    if sys.platform == 'darwin':
        try:
            output = subprocess.run(['/sbin/ifconfig'], capture_output=True, text=True, check=True, timeout=3).stdout
            addresses.update(re.findall(r'^\s+inet\s+(\d+\.\d+\.\d+\.\d+)\b', output, re.MULTILINE))
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        addresses.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    valid = [address for address in addresses if not (ipaddress.ip_address(address).is_loopback
            or ipaddress.ip_address(address).is_unspecified or ipaddress.ip_address(address).is_link_local)]
    return [f'http://{address}:{port}' for address in sorted(valid)] + [f'http://{socket.gethostname()}:{port}', f'http://127.0.0.1:{port}']
