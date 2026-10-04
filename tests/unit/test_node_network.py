"""Mac LAN addresses must advertise the actual selected connection port."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bilibili_ds.distributed.network import connection_urls


class NodeNetworkTests(unittest.TestCase):
    def test_mac_interface_ip_survives_failed_hostname_resolution(self):
        with patch('bilibili_ds.distributed.network.sys.platform', 'darwin'), \
             patch('bilibili_ds.distributed.network.socket.getaddrinfo', side_effect=OSError), \
             patch('bilibili_ds.distributed.network.socket.gethostname', return_value='Main.local'), \
             patch('bilibili_ds.distributed.network.subprocess.run', return_value=SimpleNamespace(stdout='lo0:\n inet 127.0.0.1\nen0:\n inet 192.168.3.149\nen1:\n inet 169.254.1.1\n')):
            urls = connection_urls(7988)
        self.assertEqual(urls[0], 'http://192.168.3.149:7988')
        self.assertNotIn('http://169.254.1.1:7988', urls)
        self.assertIn('http://127.0.0.1:7988', urls)

    def test_loopback_listener_does_not_advertise_remote_connections(self):
        self.assertEqual(connection_urls(7988, '127.0.0.1'), ['http://127.0.0.1:7988'])
