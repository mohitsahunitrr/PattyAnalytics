#!/usr/bin/env python

import pcl
import argparse
from patty.segmentation.segRedStick import getReds

def getInputPoinCloudAsArray(sourcePath):
    pc = pcl.load(sourcePath, loadRGB=True)
    return pc.to_array()

def saveArrayAsPointCloud(array):
    pc = pcl.PointCloudXYZRGB()
    pc.from_array(array)
    pcl.save(pc, args.outFile)

if __name__=='__main__':
    """Segment points by colour from a pcd file and saves all reddish points into a pcd of ply file."""
    parser = argparse.ArgumentParser(description='Segment points by colour from a ply or pcd file and saves all reddish points into a pcd of ply file.')
    parser.add_argument('-i','--inFile', required=True, type=str, help='Input PLY/PCD file')
    parser.add_argument('-o','--outFile',required=True, type=str, help='Output PLY/PCD file')
    args = parser.parse_args()

    ar = getInputPoinCloudAsArray(args.inFile)
    redsAr = getReds(ar)
    saveArrayAsPointCloud(redsAr)
