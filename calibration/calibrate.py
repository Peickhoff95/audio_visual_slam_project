'''
camera calibration for distorted images with chess board samples
reads distorted images, calculates the calibration and write undistorted images
usage:
    calibrate.py [--debug <output path>] [--square_size] [<image mask>]
default values:
    --debug:    ./output/
    --square_size: 1.0
    <image mask> defaults to ../data/left*.bmp
'''
import os
import sys

import numpy as np
import cv2 as cv
import getopt
from glob import glob
import yaml


# CHESSBOARD SIZE
pattern_size = (11, 7)


def splitfn(fn):
    path, fn = os.path.split(fn)
    name, ext = os.path.splitext(fn)
    return path, name, ext

def processImage(fn):
    print('processing %s... ' % fn)
    img = cv.imread(fn, 0)
    if img is None:
        print("Failed to load", fn)
        return None

    assert w == img.shape[1] and h == img.shape[0], ("size: %d x %d ... " % (img.shape[1], img.shape[0]))
    found, corners = cv.findChessboardCorners(img, pattern_size)
    if found:
        term = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_COUNT, 30, 0.1)
        cv.cornerSubPix(img, corners, (5, 5), (-1, -1), term)

    if debug_dir:
        vis = cv.cvtColor(img, cv.COLOR_GRAY2BGR)
        cv.drawChessboardCorners(vis, pattern_size, corners, found)
        _path, name, _ext = splitfn(fn)
        outfile = os.path.join(debug_dir, name + '_chess.png')
        cv.imwrite(outfile, vis)

    if not found:
        print('chessboard not found')
        return None

    print('           %s... OK' % fn)
    return (corners.reshape(-1, 2), pattern_points)


def get_chessboard_info(h, w):
    # Get chessboard images:
    obj_points = []
    img_points = []

    threads_num = int(args.get('--threads'))
    if threads_num <= 1:
        chessboards = [processImage(fn) for fn in img_names]
    else:
        print("Run with %d threads..." % threads_num)
        from multiprocessing.dummy import Pool as ThreadPool
        pool = ThreadPool(threads_num)
        chessboards = pool.map(processImage, img_names)

    chessboards = [x for x in chessboards if x is not None]
    for (corners, pattern_points) in chessboards:
        img_points.append(corners)
        obj_points.append(pattern_points)

    return img_points, obj_points


def undistort_image(img, camera_matrix, dist_coefs):
    h, w = img.shape[:2]
    newcameramtx, roi = cv.getOptimalNewCameraMatrix(camera_matrix, dist_coefs, (w, h), 1, (w, h))

    dst = cv.undistort(img, camera_matrix, dist_coefs, None, newcameramtx)

    # crop the image
    #x, y, w, h = roi
    #dst = dst[y:y+h, x:x+w]
    return dst

def write_yaml_config(camera_matrix, dist_coefs):
    template_path = "./orbslam_config_template.yaml"
    save_path = "./orbslam_config.yaml"
    with open(template_path, "r") as f:
        _ = f.readline() #Skip first line for yaml loading
        orbslam_params = yaml.load(f, Loader=yaml.FullLoader)

    orbslam_params["Camera.fx"] = float(camera_matrix[0,0]) #Float cast to avoid yaml dump problems
    orbslam_params["Camera.fy"] = float(camera_matrix[1,1])
    orbslam_params["Camera.cx"] = float(camera_matrix[0,2])
    orbslam_params["Camera.cy"] = float(camera_matrix[1,2])
    orbslam_params["Camera.k1"] = float(dist_coefs[0])
    orbslam_params["Camera.k2"] = float(dist_coefs[1])
    orbslam_params["Camera.p1"] = float(dist_coefs[2])
    orbslam_params["Camera.p2"] = float(dist_coefs[3])
    orbslam_params["Camera.k3"] = float(dist_coefs[4])

    with open(save_path, 'w') as f:
        f.write("%YAML:1.0\n")
        yaml.dump(orbslam_params, f, )


if __name__ == '__main__':
    args, img_mask = getopt.getopt(sys.argv[1:], '', ['debug=', 'square_size=', 'threads='])
    args = dict(args)
    args.setdefault('--debug', './output/')
    args.setdefault('--square_size', 1.0)
    args.setdefault('--threads', 4)

    if not img_mask:
        img_mask = './calib_images/*.bmp'  # default
    else:
        img_mask = img_mask[0]
    print('img_mask: ', img_mask)

    img_names = glob(img_mask)
    debug_dir = args.get('--debug')
    if debug_dir and not os.path.isdir(debug_dir):
        os.mkdir(debug_dir)
    square_size = float(args.get('--square_size'))

    pattern_points = np.zeros((np.prod(pattern_size), 3), np.float32)
    pattern_points[:, :2] = np.indices(pattern_size).T.reshape(-1, 2)
    pattern_points *= square_size

    h, w = cv.imread(img_names[0], cv.IMREAD_GRAYSCALE).shape[:2]  # TODO: use imquery call to retrieve results

    img_points, obj_points = get_chessboard_info(h, w)

    print("\ncomputing camera parameters...")

    # calculate camera distortion
    rms, camera_matrix, dist_coefs, rvecs, tvecs = cv.calibrateCamera(obj_points, img_points, (w, h), None, None)

    print("\nRMS:", rms)
    print("camera matrix:\n", camera_matrix)
    print("distortion coefficients: ", dist_coefs.ravel())
    np.save("camera_matrix", camera_matrix)
    np.save("dist_coefs", dist_coefs)

    # undistort the image with the calibration
    print('')
    for fn in img_names if debug_dir else []:
        path, name, ext = splitfn(fn)
        img_found = os.path.join(debug_dir, name + '_chess.png')
        outfile = os.path.join(debug_dir, name + '_undistorted.png')

        img = cv.imread(img_found)
        if img is None:
            continue

        undistorted = undistort_image(img, camera_matrix, dist_coefs)

        print('Undistorted image written to: %s' % outfile)
        cv.imwrite(outfile, undistorted)

    cv.destroyAllWindows()
