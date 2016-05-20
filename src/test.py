#!@PYTHON@
 
# Work in progress to create unit tests

import sys
import unittest
import PyDataSource  

# See https://confluence.slac.stanford.edu/display/PSDM/Adding+Unit+Tests+to+an+Analysis+Release

# Test files to be used for unittest

ds = PyDataSource.DataSource('exp=xppi0815:run=102:dir=/reg/g/psdm/data_test/multifile/test_017_xppi0815')
ds = PyDataSource.DataSource('exp=xpph6015:run=155:idx:dir=/reg/g/psdm/data_test/multifile/test_016_xpph6015')
ds = PyDataSource.DataSource('exp=cxie9214:run=63:idx:dir=/reg/g/psdm/data_test/multifile/test_012_cxie9214')
ds = PyDataSource.DataSource('exp=xpptut15:run=54')

# returns psana.DataSource since Partition not in configStore
ds = PyDataSource.DataSource('exp=amo01509:run=125:dir=/reg/g/psdm/data_test/multifile/test_000_amo01509')

