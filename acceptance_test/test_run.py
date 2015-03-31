# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014, Lars Asplund lars.anders.asplund@gmail.com

import unittest
from os.path import join, dirname, abspath
from vunit.ui import VUnit
from common import has_modelsim


@unittest.skipUnless(has_modelsim(), 'Requires modelsim')
class TestRun(unittest.TestCase):

    def run_sim(self, vhdl_standard):
        output_path = join(dirname(__file__), "run_out")
        ui = VUnit(clean=True, output_path=output_path,
                   vhdl_standard=vhdl_standard)
        ui.add_library("tb_run_lib")

        vhdl_path = join(dirname(abspath(__file__)), '..', 'vhdl', 'run')
        ui.add_source_files(join(vhdl_path, 'test', '*.vhd'),
                            "tb_run_lib")
        try:
            ui.main()
        except SystemExit as e:            
            self.assertEqual(e.code, 0)

    def test_run_vhdl_93(self):
        self.run_sim('93')

    def test_run_vhdl_2002(self):
        self.run_sim('2002')

    def test_run_vhdl_2008(self):
        self.run_sim('2008')