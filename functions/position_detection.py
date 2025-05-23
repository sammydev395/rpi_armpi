#!/usr/bin/python3
# coding=utf8
import sys
import cv2
import time
import math
import threading
import numpy as np
import common.misc as Misc
import common.yaml_handle as yaml_handle

# 6.AI视觉学习课程/第3课 目标位置检测(6.AI Vision Learning/Lesson 3 Position Detection)

if sys.version_info.major == 2:
    print('Please run this program with python3!')
    sys.exit(0)
    
# 夹持器夹取时闭合的角度(the closing angle of the gripper while grasping an object)
servo1 = 1500

# 初始位置(initial position)
def initMove():
    board.pwm_servo_set_position(0.3, [[1, servo1]])
    AK.setPitchRangeMoving((0, 8, 10), -90,-90, 0,1500)

# 设置颜色的RGB值(set the color of the RGB value)
range_rgb = {
    'red': (0, 0, 255),
    'blue': (255, 0, 0),
    'green': (0, 255, 0),
    'black': (0, 0, 0),
    'white': (255, 255, 255),
}

# 读取颜色阈值文件(read color threshold file)
lab_data = None
def load_config():
    global lab_data
    
    lab_data = yaml_handle.get_yaml_data(yaml_handle.lab_file_path)


# 找出面积最大的轮廓(find the contour with the largest area)
# 参数为要比较的轮廓的列表(parameter is the listing of contours to be compared)
def getAreaMaxContour(contours):
    contour_area_temp = 0
    contour_area_max = 0
    areaMaxContour = None

    for c in contours:  # 历遍所有轮廓(iterate through all contours)
        contour_area_temp = math.fabs(cv2.contourArea(c))  # 计算轮廓面积(calculate the contour area)
        if contour_area_temp > contour_area_max:
            contour_area_max = contour_area_temp
            if contour_area_temp > 300:  # 只有在面积大于300时，最大面积的轮廓才是有效的，以过滤干扰(Only the contour with the area larger than 300, which is greater than 300, is considered valid to filter out disturbance.)
                areaMaxContour = c

    return areaMaxContour, contour_area_max  # 返回最大的轮廓(return the largest contour)


size = (320, 240)
__isRunning = False
__target_color = ('red',)

# 图像处理及追踪控制(image processing and tracking control)
def run(img):
    global lab_data
    global __isRunning
   
    img_copy = img.copy()
    img_h, img_w = img.shape[:2]
    
    if not __isRunning:
        return img
     
    area_max = 0
    areaMaxContour = 0
    frame_resize = cv2.resize(img_copy, size)
    frame_gb = cv2.GaussianBlur(frame_resize, (3, 3), 3)
    frame_lab = cv2.cvtColor(frame_gb, cv2.COLOR_BGR2LAB)  # 将图像转换到LAB空间(convert the image to LAB space)
        
    for i in __target_color:
        if i in lab_data:
            detect_color = i
            frame_mask = cv2.inRange(frame_lab,
                                         (lab_data[detect_color]['min'][0],
                                          lab_data[detect_color]['min'][1],
                                          lab_data[detect_color]['min'][2]),
                                         (lab_data[detect_color]['max'][0],
                                          lab_data[detect_color]['max'][1],
                                          lab_data[detect_color]['max'][2]))  #对原图像和掩模进行位运算(perform bitwise operation on the original image and the mask)
            opened = cv2.morphologyEx(frame_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))  # 开运算(opening operation)
            closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))  # 闭运算(closing operation)
            contours = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[-2]  # 找出轮廓(find contours)
            areaMaxContour, area_max = getAreaMaxContour(contours)  # 找出最大轮廓(find the largest contour)
    if area_max > 300:  # 有找到最大面积(the maximum area has been found)
        (center_x, center_y), radius = cv2.minEnclosingCircle(areaMaxContour)  # 获取最小外接圆中心坐标和半径(get the center coordinate and radius of the minimum circumscribed circle)
        center_x = int(Misc.map(center_x, 0, size[0], 0, img_w)) # 坐标和半径映射到实际显示大小(map the coordinate and the radius to actual size for displaying)
        center_y = int(Misc.map(center_y, 0, size[1], 0, img_h))
        radius = int(Misc.map(radius, 0, size[0], 0, img_w))
        print('Center_x: ',center_x,' Center_y: ',center_y) # 打印中心坐标(print center coordinate)
        cv2.circle(img, (int(center_x), int(center_y)), int(radius), range_rgb[detect_color], 2) # 在画面标记出目标(mark the target on the image)
        cv2.putText(img, 'X:'+str(center_x)+' Y:'+str(center_y), (center_x-65, center_y+100 ), cv2.FONT_HERSHEY_SIMPLEX, 0.65, range_rgb[detect_color], 2) # 在画面显示中心坐标
                    
    return img

if __name__ == '__main__':
    from kinematics.arm_move_ik import *
    from common.ros_robot_controller_sdk import Board
    board = Board()
    # 实例化逆运动学库(instantiate the inverse kinematics library)
    AK = ArmIK()
    AK.board = board
    
    initMove()
    load_config()
    __isRunning = True
    __target_color = ('red',)
    cap = cv2.VideoCapture('http://127.0.0.1:8080?action=stream')
    #cap = cv2.VideoCapture(0)
    while True:
        ret,img = cap.read()
        if ret:
            frame = img.copy()
            Frame = run(frame)
            frame_resize = cv2.resize(Frame, size)
            cv2.imshow('frame', frame_resize)
            key = cv2.waitKey(1)
            if key == 27:
                break
        else:
            time.sleep(0.01)
    cv2.destroyAllWindows()
