import pytest
from unittest.mock import Mock
from pathlib import Path

from headlock.buildsys_drvs import BuildDescription


class TestBuildDescription:

    def test_init_onUniqueNamedObj(self):
        builddesc = BuildDescription('PrjName', Path('path/to/prj'))
        assert builddesc.name == 'PrjName'
        assert builddesc.build_dir == Path('path/to/prj')

    def test_init_onNonUniqueNamedObj_addsId(self):
        builddesc = BuildDescription('PrjName', Path('path/to/prj'),
                                     unique_name=False)
        builddesc.c_sources = Mock(return_value=[Path('src.c')])
        builddesc.incl_dirs = Mock(return_value={Path('src.c'): [Path('dir')]})
        builddesc.predef_macros = Mock(return_value={Path('src.c'): {'m': 'v'}})
        assert builddesc.name == 'PrjName'
        assert builddesc.build_dir.parent == Path('path/to')
        assert builddesc.build_dir.name[:-8] == 'prj_'
        assert all(c.isalnum() for c in builddesc.build_dir.name[-8:])
