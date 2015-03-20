# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2015, Lars Asplund lars.anders.asplund@gmail.com
# Copyright (c) 2014-2015, Oystein Svendsen, Norbit ODM AS, osv@norbit.com

from __future__ import print_function

from vunit.ostools import Process, write_file, file_exists
import re
from os.path import join, dirname, abspath
import os

from vunit.exceptions import CompileError
import logging
logger = logging.getLogger(__name__)

class RivieraProInterface:
    def __init__(self, library_cfg="library.cfg", persistent=False, gui=False):
        self._library_cfg = library_cfg

        # Workarround for Microsemi 10.3a which does not 
        # respect riviera environment variable when set within .do script
        # Microsemi bug reference id: dvt64978 
        os.environ["riviera"] = self._library_cfg

        self._create_library_cfg()
        self._asim_process = None
        self._gui = gui
        assert not (persistent and gui)

        if persistent:
            self._create_asim_process()

    def _teardown(self):
        if self._asim_process is not None:
            self._send_command("quit")
            self._asim_process.terminate()
            self._asim_process = None


    def __del__(self):
        self._teardown()

    def _create_asim_process(self):
        """
        Create the asim process
        """

        self._asim_process = Process(["vsim", "-c",
                                      "-l", join(dirname(self._library_cfg), "transcript")])
        self._asim_process.write("#VUNIT_RETURN\n")
        self._asim_process.consume_output(OutputConsumer(silent=True))

    def _create_library_cfg(self):
        if not file_exists(self._library_cfg):
            proc = Process(args=['vmap'], cwd=dirname(self._library_cfg))
            proc.consume_output(callback=None)

    def compile_project(self, project, vhdl_standard):
        for library in project.get_libraries():
            self.create_library(library.name, library.directory)

        for source_file in project.get_files_in_compile_order():
            print('Compiling ' + source_file.name + ' ...')

            if source_file.file_type == 'vhdl':
                success = self.compile_vhdl_file(source_file.name, source_file.library.name, vhdl_standard)
            elif source_file.file_type == 'verilog':
                success = self.compile_verilog_file(source_file.name, source_file.library.name)
            else:
                raise RuntimeError("Unkown file type: " + source_file.file_type)

            if not success:
                raise CompileError("Failed to compile '%s'" % source_file.name)
            project.update(source_file)

    def compile_vhdl_file(self, source_file_name, library_name, vhdl_standard):
        try:
            proc = Process(['vcom', '-quiet', '-O3',
                            '-' + vhdl_standard, '-work', library_name, source_file_name])
            proc.consume_output()
        except Process.NonZeroExitCode:
            return False
        return True

    def compile_verilog_file(self, source_file_name, library_name):
        try:
            proc = Process(['vlog', '-quiet', self._library_cfg,
                            '-work', library_name, source_file_name])
            proc.consume_output()
        except Process.NonZeroExitCode:
            return False
        return True


    
    _vmap_pattern = re.compile('(?P<lib>.*?) = (?P<path>.+)')
    def create_library(self, library_name, path):
        logger.debug('create_library %s %s', library_name, path)

        #if not file_exists(dirname(path)):
        #    os.makedirs(dirname(path))
        logging.debug(os.getcwd())
        #if not file_exists(path + '/' + library_name +'.lib'):
        proc = Process(['vlib', path])
        proc.consume_output(callback=None)

        try:
            proc = Process(['vmap', library_name])
            proc.consume_output(callback=None)
        except Process.NonZeroExitCode:
            pass

        match = self._vmap_pattern.search(proc.output)
        
        if match:
            do_vmap = False
        else:
            do_vmap = True
            
        if 'AMAP: Error: Logical library does not exist' in proc.output:
            do_vmap = True

        if do_vmap:
            proc = Process(['vmap', library_name, path + "/" + library_name + ".lib"])
            proc.consume_output(callback=None)

    def _create_load_function(self, library_name, entity_name, architecture_name, generics, pli, output_path):
        set_generic_str = "".join(('    set vunit_generic_%s {%s}\n' % (name, value) for name, value in generics.items()))
        set_generic_name_str = " ".join(('-g%s="${vunit_generic_%s}"' % (name, name) for name in generics))
        #pli_str = " ".join("-pli {%s}" %  fix_path(name) for name in pli)
        if architecture_name is None:
            architecture_suffix = ""
        else:
            architecture_suffix = "%s" % architecture_name

        tcl = """
proc vunit_load {{}} {{
    {set_generic_str}

    asim -quiet -t 0 {set_generic_name_str} {library_name}.{entity_name} {library_name}.{architecture_suffix}
    set no_finished_signal [catch {{examine {{vunit_finished}}}}]
    set no_test_runner_exit [catch {{examine {{/vunit_lib.run_base_pkg/runner.exit_without_errors}}}}]

    if {{${{no_finished_signal}} && ${{no_test_runner_exit}}}}  {{
        echo {{Error: Found none of either simulation shutdown mechanisms}}
        echo {{Error: 1) No vunit_finished signal on test bench top level}}
        echo {{Error: 2) No vunit test runner package used}}
        return 1
    }}
    return 0
}}
""".format(rivieraini=fix_path(self._library_cfg),           
           set_generic_str=set_generic_str,
           set_generic_name_str=set_generic_name_str,
           library_name=library_name,
           entity_name=entity_name,
           architecture_suffix=architecture_suffix,
           wlf_file_name=fix_path(join(output_path, "asim.wlf")))

        return tcl

    def _create_run_function(self, fail_on_warning=False):
        return """
        
proc vunit_run {} {
    global BreakOnAssertion

    # Break on error
    set BreakOnAssertion %i

    proc on_break {} {
        resume
    }
    onbreak {on_break}

    set no_finished_signal [catch {examine {vunit_finished}}]
    
    set aldec_no_finished_signal [catch {exa {runner.exit_without_errors}}]
    
    if {${aldec_no_finished_signal} == 0} {
        set exit_boolean {runner.exit_without_errors}
    } elseif {${no_finished_signal}} {
        set exit_boolean {/vunit_lib.run_base_pkg/runner.exit_without_errors}
    } {
        set exit_boolean {vunit_finished}
    }

    when "${exit_boolean} = true" {
        echo "Finished"
        stop
        resume
    }

    run -all
    set failed [expr [examine ${exit_boolean}]!=true]
    if {$failed} {
        catch {
            # tb command can fail when error comes from pli
            echo
            echo "Stack trace result from 'tb' command"
            echo [null tb]
            echo
            echo "Surrounding code from 'see' command"
            echo [null see]
        }
    }
    return $failed
}
""" % (1 if fail_on_warning else 2)


    def _create_common_script(self, library_name, entity_name, architecture_name, generics, pli, fail_on_warning, output_path):
        """
        Create tcl script with functions common to interactive and batch modes
        """
        tcl = """
proc vunit_help {} {
    echo {vunit_help - Prints this help}
    echo {vunit_load - Load design with correct generics for the test}
    echo {vunit_run  - Run test, must do vunit_load first}
}
"""
        tcl += self._create_load_function(library_name, entity_name, architecture_name, generics, pli, output_path)
        tcl += self._create_run_function(fail_on_warning)
        return tcl

    def _create_batch_script(self, common_file_name, load_only=False):
        """
        Create tcl script to run in batch mode
        """
        batch_do = "do " + fix_path(common_file_name) + "\n"
        batch_do += "null [set failed [vunit_load]]\n"
        batch_do += "if {$failed} {quit -force -code 1}\n"
        if not load_only:
            batch_do += "null [set failed [vunit_run]]\n"
            batch_do += "if {$failed} {quit -force -code 1}\n"
        batch_do += "exit\n"
        return batch_do

    def _create_user_script(self, common_file_name):
        tcl = "do %s\n" % fix_path(common_file_name)
        tcl += "vunit_help\n"
        return tcl

    def _run_batch_file(self, batch_file_name, gui=False):
        try:
            args = ['vsim', '-quiet',
                    "-l", join(dirname(batch_file_name), "transcript"),
                    '-do', "do %s" % fix_path(batch_file_name)]
            
            if gui:
                args.append('-gui')
            else:
                args.append('-c')

            proc = Process(args)
            proc.consume_output()
        except Process.NonZeroExitCode:
            return False
        return True

    def _send_command(self, cmd):
        self._asim_process.write("%s\n" % cmd)
        self._asim_process._next()
        self._asim_process.write("#VUNIT_RETURN\n")
        self._asim_process.consume_output(OutputConsumer())

    def _read_var(self, varname):
        self._asim_process.write("echo $%s #VUNIT_READVAR\n" % varname)
        self._asim_process._next()
        self._asim_process.write("#VUNIT_RETURN\n")
        consumer = OutputConsumer(silent=True)
        self._asim_process.consume_output(consumer)
        return consumer.var

    def _run_persistent(self, common_file_name, load_only=False):
        try:
            self._send_command("quit -sim")
            self._send_command("do " + fix_path(common_file_name))
            self._send_command("quietly set failed [vunit_load]")
            if self._read_var("failed") == '1':
                return False

            if not load_only:
                self._send_command("quietly set failed [vunit_run]")
                if self._read_var("failed") == '1':
                    return False

            return True
        except Process.NonZeroExitCode:
            self._create_asim_process()
            return False

    def simulate(self, output_path, library_name, entity_name, architecture_name=None, generics=None, pli=None, load_only=None, fail_on_warning=False):
        generics = {} if generics is None else generics
        pli = [] if pli is None else pli
        asim_output_path = abspath(join(output_path, "asim"))
        common_file_name = join(asim_output_path, "common.do")
        user_file_name = join(asim_output_path, "user.do")
        batch_file_name = join(asim_output_path, "batch.do")

        common_do = self._create_common_script(library_name, entity_name, architecture_name, generics, pli,
                                               fail_on_warning=fail_on_warning,
                                               output_path=asim_output_path)
        user_do = self._create_user_script(common_file_name)
        batch_do = self._create_batch_script(common_file_name, load_only)
        write_file(common_file_name, common_do)
        write_file(user_file_name, user_do)
        write_file(batch_file_name, batch_do)

        if self._gui:
            success = self._run_batch_file(user_file_name, gui=True)
        elif self._asim_process is None:
            success = self._run_batch_file(batch_file_name)
        else:
            success = self._run_persistent(common_file_name, load_only)

        return success

    def load(self, output_path, library_name, entity_name, architecture_name=None, generics=None, pli=None):
        return self.simulate(output_path, library_name, entity_name, architecture_name, generics, pli, load_only=True)

    def __del__(self):
        if self._asim_process is not None:
            del self._asim_process

class OutputConsumer:
    """
    Consume output from riviera and print with indentation
    """
    def __init__(self, silent=False):
        self.var = None
        self.silent = silent

    def __call__(self, line):
        stripline = line.strip()

        if stripline.endswith("#VUNIT_RETURN"):
            return True

        if stripline.endswith("#VUNIT_READVAR"):
            self.var = line.split("#VUNIT_READVAR")[0][1:].strip()
            return

        if not self.silent:
            print(line)

def fix_path(path):
    """ riviera does not like backslash """
    return path.replace("\\", "/").replace(" ", "\\ ")
