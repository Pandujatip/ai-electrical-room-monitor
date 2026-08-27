import unittest
from unittest.mock import patch, MagicMock
from ptz import PTZController


class PTZControllerTests(unittest.TestCase):
    def setUp(self):
        self.ptz = PTZController("rtsp://admin:ELINSRM34@192.168.1.2:554/cam/realmonitor?channel=1&subtype=1")

    def test_parse_rtsp(self):
        self.assertEqual(self.ptz.ip, "192.168.1.2")
        self.assertEqual(self.ptz.user, "admin")
        self.assertEqual(self.ptz.password, "ELINSRM34")
        self.assertEqual(self.ptz.port, 80)

    @patch("requests.get")
    def test_move_left(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK\r\n"
        mock_get.return_value = mock_resp

        res = self.ptz.move("left", speed=5)
        self.assertTrue(res["ok"])
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["code"], "Left")
        self.assertEqual(kwargs["params"]["action"], "start")
        self.assertEqual(kwargs["params"]["arg1"], 5)

    @patch("requests.get")
    def test_continuous_scan_360(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK\r\n"
        mock_get.return_value = mock_resp

        res = self.ptz.continuous_scan_360("start")
        self.assertTrue(res["ok"])
        args, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["code"], "AutoScan")
        self.assertEqual(kwargs["params"]["action"], "start")

    @patch("requests.get")
    def test_goto_preset(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK\r\n"
        mock_get.return_value = mock_resp

        res = self.ptz.goto_preset(1)
        self.assertTrue(res["ok"])
        args, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["code"], "GotoPreset")
        self.assertEqual(kwargs["params"]["arg2"], 1)


if __name__ == "__main__":
    unittest.main()
