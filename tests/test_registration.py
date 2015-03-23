import os.path
import shutil
from tempfile import mkdtemp

import numpy as np
import pcl

from patty import center_boundingbox, conversions
from patty.registration import (point_in_polygon2d, downsample_voxel,
                                scale_points, intersect_polygon2d,
                                get_pointcloud_boundaries, is_upside_down)
from patty.conversions import BoundingBox
from scripts.registration import registration_pipeline

from helpers import make_tri_pyramid_with_base
from nose.tools import (assert_equal, assert_greater, assert_less,
                        assert_true, assert_false)
from numpy.testing import (assert_array_equal, assert_array_almost_equal,
                           assert_array_less)
from sklearn.utils.extmath import cartesian
import unittest


class TestPolygon(unittest.TestCase):

    def setUp(self):
        self.poly = [[0., 0.], [1., 0.], [0.4, 0.4], [1., 1.], [0., 1.]]
        self.points = [[0., 0.], [0.5, 0.2], [1.1, 1.1], [0.2, 1.1]]

    def test_in_polygon(self):
        ''' Test whether the point_in_polygon2d behaves as expected. '''
        in_polygon = point_in_polygon2d(self.points, self.poly)
        assert_array_equal(in_polygon, [False, True, False, False],
                           "points expected in polygon not matched")

    def test_scale_polygon(self):
        ''' Test whether scaling up the polygon works '''
        newpoly = scale_points(self.poly, 1.3)
        assert_equal(len(newpoly), len(self.poly),
                     "number of polygon points is altered when scaling")
        assert_array_equal(self.poly[0], [.0, .0],
                           "original polygon is altered when scaling")
        assert_array_less(newpoly[0], self.poly[0],
                          "small polygon points do not shrink when scaling up")
        assert_array_less(self.poly[3], newpoly[3],
                          "large polygon points do not grow when scaling up")
        in_scaled_polygon = point_in_polygon2d(self.points, newpoly)
        assert_true(np.all(in_scaled_polygon),
                    "not all points are in polygon when scaling up")


class TestCutoutPointCloud(unittest.TestCase):

    def setUp(self):
        self.footprint = [[0., 0.], [1., 0.], [0.4, 0.4], [1., 1.], [0., 1.]]
        self.offset = [-0.01, -0.01, -0.01]
        points = np.array([[0., 0.], [0.5, 0.2], [1.1, 1.1], [0.2, 1.1]])
        data = np.zeros((4, 6), dtype=np.float32)
        data[:, :2] = points
        self.pc = pcl.PointCloudXYZRGB(data)
        conversions.set_registration(self.pc, offset=self.offset)

    def test_cutout_from_footprint(self):
        ''' Test whether a cutout from a pointcloud gets the right points '''
        pc_fp = intersect_polygon2d(self.pc, self.footprint)
        assert_equal(pc_fp.size, 1,
                     "number of points expected in polygon not matched")
        err_msg = "point that should be matched was modified"
        assert_array_almost_equal(pc_fp[0], [0.5, 0.2, 0., 0., 0., 0.],
                                  err_msg=err_msg)
        err_msg = "offset changed by intersection with polygon"
        assert_array_equal(pc_fp.offset, self.offset, err_msg=err_msg)


class TestCenter(unittest.TestCase):

    def setUp(self):
        data = np.array(
            [[1, 1, 1, 1, 1, 1], [3, 3, 3, 1, 1, 1]], dtype=np.float32)
        self.pc = pcl.PointCloudXYZRGB(data)

    def test_center(self):
        '''test whether pointcloud can be centered around zero'''
        # Baseline: original center
        bb = BoundingBox(points=np.asarray(self.pc))
        assert_array_equal(bb.center, [2., 2., 2.],
                           "original bounding box center"
                           " is not center of input")

        # New center
        center_boundingbox(self.pc)
        bb_new = BoundingBox(points=np.asarray(self.pc))
        assert_array_equal(bb_new.center, np.zeros(3),
                           "after centering, BoundingBox center not in origin")
        assert_array_equal(self.pc.offset, bb.center,
                           "offset of centering operation not equal to"
                           " original center")
        assert_array_equal(bb.size, bb_new.size,
                           "bounding box size changed due to translation")


def array_in_margin(target, actual, margin, msg):
    assert_array_less(target, actual + np.asarray(margin), msg)
    assert_array_less(actual, target + np.asarray(margin), msg)


class TestBoundary(unittest.TestCase):

    def setUp(self):
        self.num_rows = 50
        self.max = 0.1
        self.num_points = self.num_rows * self.num_rows
        grid = np.zeros((self.num_points, 6))
        row = np.linspace(start=0.0, stop=self.max, num=self.num_rows)
        grid[:, 0:2] = cartesian((row, row))
        self.pc = pcl.PointCloudXYZRGB(grid.astype(np.float32))
        conversions.set_registration(self.pc)
        self.footprint_boundary = np.array(
            [[0.0, 0.0], [0.0, self.max],
             [self.max, self.max], [self.max, 0.0]])

    def test_boundaries(self):
        boundary = get_pointcloud_boundaries(self.pc, search_radius=0.02)
        assert_equal(self.pc.size, self.num_points)
        assert_less(boundary.size, self.num_points)
        assert_greater(boundary.size, 0)

        small_footprint = scale_points(self.footprint_boundary, 0.9)
        large_footprint = scale_points(self.footprint_boundary, 1.1)

        assert_equal(np.sum(point_in_polygon2d(boundary, small_footprint)), 0)
        assert_equal(np.sum(point_in_polygon2d(boundary, large_footprint)),
                     boundary.size)
        assert_greater(np.sum(point_in_polygon2d(self.pc, small_footprint)), 0)
        assert_equal(np.sum(point_in_polygon2d(self.pc, large_footprint)),
                     self.pc.size)

    def test_boundaries_too_small_radius(self):
        boundary = get_pointcloud_boundaries(
            self.pc, search_radius=0.0001, normal_search_radius=0.0001)
        assert_equal(boundary.size, 0)


class TestRegistrationPipeline(unittest.TestCase):

    def setUp(self):
        self.useLocal = True

        if self.useLocal:
            self.tempdir = tempdir = '.'
        else:
            self.tempdir = tempdir = mkdtemp(prefix='patty-analytics')

        self.drivemapLas = os.path.join(tempdir, 'testDriveMap.las')
        self.sourcelas = os.path.join(tempdir, 'testSource.las')
        self.footprint_csv = os.path.join(tempdir, 'testFootprint.csv')
        self.foutlas = os.path.join(tempdir, 'testOutput.las')

        self.min = -10
        self.max = 10
        self.num_rows = 1000

        # Create plane with a pyramid
        dm_pct = 0.5
        dm_rows = np.round(self.num_rows * dm_pct)
        dm_min = self.min * dm_pct
        dm_max = self.max * dm_pct

        delta = dm_max / dm_rows
        shape_side = dm_max - dm_min

        dm_offset = [0, 0, 0]
        self.dense_obj_offset = [3, 2, -(1 + shape_side / 2)]

        # make drivemap
        plane_row = np.linspace(
            start=self.min, stop=self.max, num=self.num_rows)
        plane_points = cartesian((plane_row, plane_row, [0]))

        shape_points, footprint = make_tri_pyramid_with_base(
            shape_side, delta, dm_offset)
        np.savetxt(self.footprint_csv, footprint, fmt='%.3f', delimiter=',')

        dm_points = np.vstack([plane_points, shape_points])
        plane_grid = np.zeros((dm_points.shape[0], 6), dtype=np.float32)
        plane_grid[:, 0:3] = dm_points

        self.drivemap_pc = pcl.PointCloudXYZRGB(plane_grid)
        self.drivemap_pc = downsample_voxel(self.drivemap_pc,
                                            voxel_size=delta * 20)
        conversions.set_registration(self.drivemap_pc)
        conversions.save(self.drivemap_pc, self.drivemapLas)

        # Create a simple pyramid
        dense_grid = np.zeros((shape_points.shape[0], 6), dtype=np.float32)
        dense_grid[:, 0:3] = shape_points + self.dense_obj_offset

        self.source_pc = pcl.PointCloudXYZRGB(dense_grid)
        self.source_pc = downsample_voxel(self.source_pc, voxel_size=delta * 5)
        conversions.set_registration(self.source_pc)
        conversions.save(self.source_pc, self.sourcelas)

    def tearDown(self):
        if not self.useLocal:
            shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_pipeline(self):
        # TODO: should just use shutil to run the registration.py script, and load the result

        # Register box on surface
        pc = conversions.load(self.sourcelas)
        dm = conversions.load(self.drivemapLas)
        fp = conversions.load_csv_polygon(self.footprint_csv)
        
        registration_pipeline(pc, dm, fp)
        registered_pc = pc 

        conversions.save(registered_pc, self.foutlas )

        target = np.asarray(self.source_pc) + self.source_pc.offset
        target -= np.array(self.dense_obj_offset)
        actual = np.asarray(registered_pc) + registered_pc.offset

        array_in_margin(target.min(axis=0), actual.min(axis=0), [1, 1, 1],
                        "Lower bound of registered cloud does not"
                        " match expectation")
        array_in_margin(target.max(axis=0), actual.max(axis=0), [2.5, 5.5, 2],
                        "Upper bound of registered cloud does not"
                        " match expectation")
        array_in_margin(target.mean(axis=0), actual.mean(axis=0), [1, 1, 1],
                        "Middle point of registered cloud does not"
                        " match expectation")


class TestUpsideDown(unittest.TestCase):
    def setUp(self):
        testdir = 'tests'
        self.down = os.path.join(testdir, 'testdownfile.json')
        self.up = os.path.join(testdir, 'testupfile.json')
        self.rotate = np.array([[1., 0., 0.], [0., -1., 0.], [0., 0., -1.]])

    def test_no_file(self):
        '''Without up file path, should return false.'''
        assert_false(is_upside_down(None, np.identity(3)))

    def test_non_existent_file(self):
        '''Without existing up file, should return false.'''
        assert_false(is_upside_down('nonexisting1234.json', np.identity(3)))

    def test_empty_file(self):
        '''With empty up file path, should return false.'''
        assert_false(is_upside_down('', np.identity(3)))

    def test_down(self):
        '''With down vector, should return true.'''
        assert_true(is_upside_down(self.down, np.identity(3)))

    def test_up(self):
        '''With up vector, should return false.'''
        assert_false(is_upside_down(self.up, np.identity(3)))

    def test_rotated_up(self):
        '''With up vector rotated 180, should return true.'''
        assert_true(is_upside_down(self.up, self.rotate))

    def test_rotated_down(self):
        '''With down vector rotated 180, should return false.'''
        assert_false(is_upside_down(self.down, self.rotate))
