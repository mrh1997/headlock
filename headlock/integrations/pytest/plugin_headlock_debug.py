"""
This plugin creates a CMakeLists file, that contains all testsetups of the
first (failed) test.
To avoid overwriting this File the "--keep-first-failed-pytest" command line
option can be set.

The content of this file is used by testlibs/debug_failed.py
to run only one test.

In contrary to the builtin cache plugin, this plugin provides the option
--keep-first-failed-pytest. This option allows to avoid overwriting
'CMakeLists.tx' and this rerun a test again and again with
'debug_failed.py' (even if it passed in the last run).

A test is also marked as failed if its execution
stops with a crash (=no teardown executed)
"""
import os
from pathlib import Path
from collections import defaultdict
from headlock.buildsys_drvs import mingw
from .common import PYTEST_HEADLOCK_DIR


master_cmakelist = ''
keep_failed = False


def cmakelists_read_state():
    try:
        lines = open(master_cmakelist, 'r').readlines()
    except IOError:
        lines = []
    if len(lines) < 4:
        return '', 'UNDEFINED'
    else:
        comment1, comment2, first_line, *_, last_line = lines
        if first_line[0] != '#':
            return '', 'UNDEFINED'
        else:
            nodeid = first_line[1:].strip()
            if last_line.strip() not in ('# OK', '# FAILED'):
                return nodeid, 'UNDEFINED'
            else:
                return nodeid, last_line[1:].strip()

def cmakelists_reset(nodeid):
    try:
        with open(master_cmakelist, 'w') as cmfile:
            cmfile.write(f'# DO NOT MODIFY THIS FILE (CREATED BY '
                         f'pytest plugin headlock-cmake)\n')
            cmfile.write(f'#\n')
            cmfile.write(f'# {nodeid}\n')
            cmfile.write(f'cmake_minimum_required(VERSION 3.6)\n')
    except OSError:
        pass

def cmakelists_write_result(result):
    try:
        with open(master_cmakelist, 'a') as cmfile:
            cmfile.write('# ' + result)
    except OSError:
        pass

def initialize():
    try:
        os.remove(master_cmakelist)
    except OSError:
        pass

def start_test(nodeid):
    _, cur_state = cmakelists_read_state()
    if cur_state != 'FAILED':
        cmakelists_reset(nodeid)

def finish_test(nodeid, failed):
    cur_nodeid, cur_failed = cmakelists_read_state()
    if nodeid == cur_nodeid and cur_failed == 'UNDEFINED':
        cmakelists_write_result('FAILED' if failed else 'OK')



#--- PyTest specific interface: ---

def pytest_addoption(parser):
    parser.addoption('--keep-first-failed-pytest',
                     action='store_true', dest='KEEP_FAILED')

def pytest_configure(config):
    global abs_markerfile, master_cmakelist, keep_failed
    keep_failed = config.option.KEEP_FAILED
    if not keep_failed:
        master_cmakelist = os.path.join(config.rootdir,
                                        PYTEST_HEADLOCK_DIR, 'CMakeLists.txt')
        master_cmakelist_dir = os.path.dirname(master_cmakelist)
        if not os.path.exists(master_cmakelist_dir):
            os.mkdir(master_cmakelist_dir)
            gitignore_path = os.path.join(master_cmakelist_dir, '.gitignore')
            with open(gitignore_path, 'wt') as gitignore:
                gitignore.write('# created by pytest-headlock automatically, '
                                'do not change\n*')
        initialize()

def pytest_runtest_setup(item):
    if not keep_failed:
        start_test(item.nodeid)

def pytest_runtest_logreport(report):
    if not keep_failed and report.when == 'call':
        finish_test(report.nodeid, report.failed)


class CMakeFileGenerator(mingw.get_default_builddesc_cls()):

    @staticmethod
    def escape(str):
        if '"' in str or '(' in str or ')' in str:
            return '"' + str.replace('"', '\\"') + '"'
        else:
            return str

    def group_c_sources_by_paramset(self):
        param_sets = defaultdict(list)
        predef_macros = self.predef_macros()
        incl_dirs = self.incl_dirs()
        for c_src in self.c_sources():
            param_set = tuple(sorted(predef_macros[c_src].items())) + \
                        tuple(sorted(incl_dirs[c_src]))
            param_sets[param_set].append(c_src)
        return list(param_sets.values())

    def generate_cmakelists(self, additonal_c_sources):
        def add_lib_desc(lib_name, lib_type, c_srcs):
            yield f'add_library({lib_name} {lib_type}'
            for c_src in c_srcs:
                rel_c_src_path = os.path.relpath(c_src, self.build_dir)
                yield ' ' + rel_c_src_path.replace('\\', '/')
            yield ')\n'
            predef_macros = self.predef_macros()[c_srcs[0]]
            if predef_macros:
                yield f'target_compile_definitions({lib_name} PUBLIC'
                for mname, mval in predef_macros.items():
                    yield ' '
                    yield self.escape(mname +
                                      ('' if mval is None else f'={mval}'))
                yield ')\n'
            incl_dirs = self.incl_dirs()[c_srcs[0]]
            if incl_dirs:
                yield f'target_include_directories({lib_name} PUBLIC'
                for incl_dir in incl_dirs:
                    rel_incl_dir = os.path.relpath(incl_dir, self.build_dir)
                    yield ' ' + rel_incl_dir.replace('\\', '/')
                yield ')\n'
        main_lib_name = 'TS_' + self.name
        yield f'# This file was generated by CMakeToolChain ' \
              f'automaticially.\n' \
              f'# Do not modify it manually!\n' \
              f'\n' \
              f'cmake_minimum_required(VERSION 3.6)\n' \
              f'project({self.name} C)\n' \
              f'set(CMAKE_C_STANDARD 99)\n' \
              f'\n'
        grouped_c_sources = self.group_c_sources_by_paramset()
        if len(grouped_c_sources) == 1:
            c_srcs = grouped_c_sources[0]
            yield from add_lib_desc(main_lib_name, 'SHARED',
                                    c_srcs + additonal_c_sources)
        else:
            yield f'add_library({main_lib_name} SHARED'
            for cmod_ndx, c_srcs in enumerate(grouped_c_sources):
                yield f' $<TARGET_OBJECTS:CMOD_{self.name}_{cmod_ndx}>'
            if additonal_c_sources:
                yield f' $<TARGET_OBJECTS:CMOD_{self.name}'
            yield ')\n'
            if additonal_c_sources:
                yield from add_lib_desc('CMOD_' + self.name, 'OBJECT',
                                        additonal_c_sources)
        compile_opts = getattr(self, 'ADDITIONAL_COMPILE_OPTIONS', [])
        link_opts = getattr(self, 'ADDITIONAL_LINK_OPTIONS', [])
        lib_dirs = getattr(self, 'lib_dirs', [])
        req_libs = getattr(self, 'req_libs', [])
        if compile_opts:
            yield f"add_compile_options({' '.join(compile_opts)})\n"
        if link_opts:
            yield f"set(CMAKE_EXE_LINKER_FLAGS \"{' '.join(link_opts)}\")\n"
        if lib_dirs:
            yield f'link_directories({" ".join(lib_dirs)})\n'
        if req_libs:
            req_libs_str = ' '.join(req_libs)
            yield f'target_link_libraries({main_lib_name} {req_libs_str})\n'
        yield f'set_target_properties({main_lib_name} PROPERTIES\n' \
              f'                      RUNTIME_OUTPUT_DIRECTORY ${{CMAKE_CURRENT_SOURCE_DIR}}\n' \
              f'                      OUTPUT_NAME __headlock_dbg__\n' \
              f'                      PREFIX "")\n'
        yield '\n'
        if len(grouped_c_sources) > 1:
            for cmod_ndx, c_srcs in enumerate(grouped_c_sources):
                cmod_name = f'CMOD_{self.name}_{cmod_ndx}'
                yield from add_lib_desc(cmod_name, 'OBJECT', c_srcs)
                yield '\n'

    def build(self, additonal_c_sources=None):
        cmakelists_path = self.build_dir / 'CMakeLists.txt'
        cmakelists_path.write_text(
            ''.join(self.generate_cmakelists(additonal_c_sources or [])))

        if master_cmakelist:
            master_cmakelist_path = Path(master_cmakelist)
            master_cmakelist_dir = master_cmakelist_path.parent.resolve()
            rel_build_dir = os.path.relpath(self.build_dir,
                                            str(master_cmakelist_dir))
            rel_build_dir_str = str(rel_build_dir).replace('\\', '/')
            if master_cmakelist_path.exists():
                lines = master_cmakelist_path.open().readlines()
                if len(lines) >= 4:
                    lastline = lines[-1]
                    if len(lastline) > 0 and lastline[0] != '#':
                        with master_cmakelist_path.open('a') as cmfile:
                            cmfile.write(
                                f'add_subdirectory('
                                f'{rel_build_dir_str} {self.name})\n')

        super().build(additonal_c_sources)


mingw.get_default_builddesc_cls = lambda: CMakeFileGenerator
