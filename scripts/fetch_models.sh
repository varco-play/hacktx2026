#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../models"
Z=https://github.com/opencv/opencv_zoo/raw/main/models
M=https://storage.googleapis.com/mediapipe-models
curl -fsSL -o face_detection_yunet_2023mar.onnx "$Z/face_detection_yunet/face_detection_yunet_2023mar.onnx"
curl -fsSL -o face_recognition_sface_2021dec.onnx "$Z/face_recognition_sface/face_recognition_sface_2021dec.onnx"
curl -fsSL -o face_landmarker.task "$M/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
curl -fsSL -o hand_landmarker.task "$M/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
shasum -a 256 -c <<SUMS
8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4  face_detection_yunet_2023mar.onnx
0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79  face_recognition_sface_2021dec.onnx
64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff  face_landmarker.task
fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1  hand_landmarker.task
SUMS
