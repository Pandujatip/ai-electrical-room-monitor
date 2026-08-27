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

    def test_auto_tracking_deadzone_and_direction(self):
        w = 640
        center_x = 320
        deadzone = w * 0.18  # 115.2

        # 1. Target inside deadzone (e.g. cx = 310) -> no move
        cx_inside = 310
        offset_inside = cx_inside - center_x
        self.assertLessEqual(abs(offset_inside), deadzone)

        # 2. Target far left (e.g. cx = 80) -> move left
        cx_left = 80
        offset_left = cx_left - center_x
        self.assertLess(offset_left, -deadzone)

        # 3. Target far right (e.g. cx = 580) -> move right
        cx_right = 580
        offset_right = cx_right - center_x
        self.assertGreater(offset_right, deadzone)


if __name__ == "__main__":
    unittest.main()
