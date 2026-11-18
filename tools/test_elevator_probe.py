"""Offline tests: these MUST never connect to a building or an EW11."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import elevator_probe as probe


class ElevatorProbeTests(unittest.TestCase):
    def test_management_addresses_are_blocked(self):
        for host in ("10.0.1.1", "10.0.1.10", "10.6.0.254"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                probe.ew11_endpoint(host, 8899)

    def test_local_ew11_is_accepted(self):
        self.assertEqual(probe.ew11_endpoint("192.168.0.75", 8899),
                         ("192.168.0.75", 8899))

    def test_ew11_dry_run_cannot_send(self):
        a = SimpleNamespace(host="192.168.0.75", port=8899,
                            hex="02 31 00 00 00", confirm="")
        with patch.object(probe.socket, "create_connection") as connect:
            probe.ew11_send(a)
            connect.assert_not_called()

    def test_ew11_non_frame_rejected(self):
        a = SimpleNamespace(host="192.168.0.75", port=8899,
                            hex="01 31 00 00 00", confirm=probe.CONFIRM)
        with patch.object(probe.socket, "create_connection") as connect:
            with self.assertRaises(ValueError):
                probe.ew11_send(a)
            connect.assert_not_called()

    def test_private_site_rejected(self):
        with self.assertRaises(ValueError):
            probe.site_host("10.6.0.254")

    def test_unverified_ipark_command_rejected(self):
        a = SimpleNamespace(path="/webapp/data/lights.php",
                            field=["device=light"], confirm=probe.CONFIRM)
        with self.assertRaises(ValueError):
            probe.ipark_send(a, object(), "example.com")

    def test_ipark_dry_run_no_post(self):
        a = SimpleNamespace(path="/webapp/data/elevator.php",
                            field=["device=elevator"], confirm="")
        with patch.object(probe, "http_request") as req:
            probe.ipark_send(a, object(), "example.com")
            req.assert_not_called()


if __name__ == "__main__":
    unittest.main()
