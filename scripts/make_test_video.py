"""Build a TEST INPUT video from two face images: A and B visible, A leaves, A returns on the other side.

Usage: python scripts/make_test_video.py faceA.jpg faceB.jpg out.mp4
Output is for development only and must be labeled TEST INPUT when replayed.
"""
import sys
import cv2
import numpy as np

a, b = cv2.imread(sys.argv[1]), cv2.imread(sys.argv[2])
A = cv2.resize(a[150:420, 180:390], (150, 190))          # lena face crop
B = cv2.resize(b[60:170, 190:290], (150, 165))           # messi face crop
out = cv2.VideoWriter(sys.argv[3], cv2.VideoWriter_fourcc(*"mp4v"), 15, (640, 480))
for i in range(15 * 14):
    f = np.full((480, 640, 3), 70, np.uint8)
    f[:, :, 1] = (np.arange(640) // 3 % 255).astype(np.uint8)[None, :]
    f[300:480, 380:640] = (60, 90, 120)                   # background clutter
    f[150:315, 440:590] = B                               # B always on right
    t = i / 15
    if t < 5:                                             # A on left
        f[120:310, 60:210] = A
    elif t < 8:                                           # A gone
        pass
    else:                                                 # A returns lower-middle
        f[260:450, 220:370] = A
    out.write(f)
out.release()
