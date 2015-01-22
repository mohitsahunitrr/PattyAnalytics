import unittest
import pcl
import numpy as np
from patty_registration.conversions import loadLas, writeLas
from patty_registration.principalComponents import pcaRotate
from numpy.testing import assert_array_equal, assert_array_almost_equal

class TestPrincipalComponentRotation(unittest.TestCase):
    def testPCARotation(self):
        fileIn = 'data/footprints/162.las'
        fileOut = 'data/footprints/162_pca.las'
        pc = loadLas(fileIn)
        pc2 = pcaRotate(pc)
        writeLas(fileOut, pc2)
