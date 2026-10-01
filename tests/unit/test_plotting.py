"""Axis formatting and bounded, memory-only plot snapshots."""

from collections import OrderedDict
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from bilibili_ds import plotting
from bilibili_ds.web import plots


class PlottingTests(unittest.TestCase):
    def test_round_zero_based_axes(self):
        for values, expected in [([0], (1, 0.2)), ([10000, 30000], (40000, 10000)),
                                 ([100000], (150000, 50000))]:
            # Tick intervals are restricted to powers of ten times 1, 2, or 5.
            upper, step = plotting.nice_y_axis(values)
            self.assertGreater(upper, max(values))
            self.assertGreater(step, 0)
            self.assertEqual((upper, step), expected)
        upper, step = plotting.nice_y_axis([0.001, 0.002])
        self.assertAlmostEqual(upper, 0.0025)
        self.assertAlmostEqual(step, 0.0005)

    def test_png_axis_formatter_uses_commas_without_unnecessary_decimals(self):
        figure, axis = plotting.plt.subplots()
        self.addCleanup(plotting.plt.close, figure)
        plotting.configure_y_axis(axis, [10000, 30000])
        self.assertEqual(axis.get_ylim(), (0, 40000))
        formatter = axis.yaxis.get_major_formatter()
        self.assertEqual(formatter(10000, 0), "10,000")
        self.assertEqual(formatter(1000000, 0), "1,000,000")
        self.assertEqual(formatter(0.001, 0), "0.001")
        self.assertEqual(formatter(0, 0), "0")

    def test_snapshot_limit_empty_data_and_copy_isolation(self):
        with ExitStack() as stack:
            pending = OrderedDict()
            stack.enter_context(patch.object(plots, "_pending_plots", pending))
            stack.enter_context(patch.object(plots, "PENDING_PLOT_LIMIT", 2))
            save = stack.enter_context(patch.object(plots, "save_web_plot_png", return_value="sample.png"))
            selected = {"name": "Original", "uid": "42"}
            points = [{"label": "2026-09-01 00:00:00", "value": 0, "title": "Original"}]
            self.assertIsNone(plots.prepare_plot(selected, "all", "Views", "Views", []))
            first = plots.prepare_plot(selected, "all", "Views", "Views", points)
            second = plots.prepare_plot(selected, "all", "Views", "Views", points)
            selected["name"] = "Changed"
            points[0]["value"] = 100
            self.assertEqual(pending[second]["selected"]["name"], "Original")
            self.assertEqual(pending[second]["points"][0]["value"], 0)
            plots.prepare_plot(selected, "all", "Views", "Views", points)
            self.assertEqual(len(pending), 2)
            with self.assertRaisesRegex(ValueError, "expired"):
                plots.save_prepared_plot(first)
            save.assert_not_called()
