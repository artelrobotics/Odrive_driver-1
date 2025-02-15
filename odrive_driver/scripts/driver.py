#!/usr/bin/env python3.8
import odrive
import rospy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import Int32MultiArray
from std_srvs.srv import SetBool, Empty,SetBoolResponse
import time
import math
from odrive_driver.msg import Channel_values, Status
import signal
import sys
import asyncio
from odrive.enums import AxisState 

class Odrive_Driver():

    def __init__(self) -> None:
        self.driver_alive = False
        rospy.loginfo("Finding an odrive...")
        self.my_drive = odrive.find_any()
        self.driver_alive = True
        # if (self.my_drive.axis0.requested_state != AxisState.CLOSED_LOOP_CONTROL and  self.my_drive.axis1.requested_state != AxisState.CLOSED_LOOP_CONTROL):
        #     self.calibration()
        rospy.loginfo("Succesfully found")
        self.wheelbase = rospy.get_param('~wheelbase', default = 0.365)
        self.radius = rospy.get_param('~wheel_radius', default = 0.085)
        self.max_rpm = rospy.get_param('~max_rpm', default = 260)
        rospy.Subscriber('cmd_vel', Twist, self.cmd_callback)
        self.shadow_counts = rospy.Publisher('shadow_counts', Channel_values, queue_size= 10)
        self.status_pub = rospy.Publisher('driver/status', Status, queue_size= 10)
        self.reboot = rospy.Service("reboot", Empty, self.reboot_callback)
        self.counts = Channel_values()
        self.status = Status()
        
        self.last_time = rospy.Time.now()
    def driver_status(self):
        """ Encoder ticks publishing"""
        try:
            self.counts.right = self.my_drive.axis1.encoder.shadow_count
            self.counts.left = - self.my_drive.axis0.encoder.shadow_count 
            self.shadow_counts.publish(self.counts)
        except AttributeError:
            self.recovery()
        
        except Exception as e:
            rospy.logerr(type(e))

        """ Driver Status publishing"""
        try:
            self.status.system_error = self.my_drive.error
            self.status.right_axis_error = self.my_drive.axis0.error
            self.status.right_motor_error = self.my_drive.axis0.motor.error
            self.status.right_sensorless_estimator_error = self.my_drive.axis0.sensorless_estimator.error
            self.status.right_encoder_error = self.my_drive.axis0.encoder.error
            self.status.right_controller_error = self.my_drive.axis0.controller.error
            self.status.left_axis_error = self.my_drive.axis1.error
            self.status.left_motor_error = self.my_drive.axis1.motor.error
            self.status.left_sensorless_estimator_error = self.my_drive.axis1.sensorless_estimator.error
            self.status.left_encoder_error = self.my_drive.axis1.encoder.error
            self.status.left_controller_error = self.my_drive.axis1.controller.error
            self.status.battery_voltage = self.my_drive.vbus_voltage
            self.status_pub.publish(self.status)
        except Exception as e:
            rospy.logerr(type(e))
        

    def cmd_stop(self):
        self.current_time = rospy.Time.now()
        elapsed = self.current_time.to_sec() - self.last_time.to_sec()
        if (elapsed > 1):
            try:
                self.my_drive.axis0.controller.input_vel = 0
                self.my_drive.axis1.controller.input_vel = 0 
            except Exception as e:
                rospy.logerr(type(e)) 
    

    def cmd_callback(self, msg):
        self.last_time = rospy.Time.now()
        try:
            self.my_drive.axis1.controller.input_vel = self.calculate_right_speed(msg.linear.x, msg.angular.z)   # turn/s
            self.my_drive.axis0.controller.input_vel = self.calculate_left_speed(msg.linear.x, msg.angular.z)    # turn/s
        
        except AttributeError:
            self.recovery()
        
        except Exception as e:
            rospy.logerr(type(e))
        
    def calculate_right_speed(self, x, z):
        speed = (2 * x + z * self.wheelbase) / (2 * self.radius * 2 * math.pi)
        return self.check_speed_limit(speed)

    def calculate_left_speed(self, x, z):
        speed = -(2 * x - z * self.wheelbase) / (2 * self.radius * 2 * math.pi) 
        return self.check_speed_limit(speed)
    
    def check_speed_limit(self, speed):
        if (abs(speed) > (self.max_rpm / 60)):
            speed = (self.max_rpm / 60) * (speed / abs(speed))
        
        return speed

    def reboot_callback(self, msg):
        try:
            rospy.logerr("Rebooting Odrive!")
            self.driver_alive = False
            Odrive.my_drive.reboot()
                   
        except:
            time.sleep(10)
            self.my_drive = odrive.find_any()
            self.driver_alive = True
            rospy.loginfo("Odrive found")
        
    def shutdown_hook(self):
        try:
            self.my_drive.axis0.controller.input_vel = 0
            self.my_drive.axis1.controller.input_vel = 0
            rospy.logwarn("Shuting down on hook")
            sys.exit(0)
        except Exception as e:
            rospy.logerr(type(e))
    
    def recovery(self):
        self.status.system_error = 1
        self.status_pub.publish(self.status)
        time.sleep(10)
        try:
            self.my_drive = odrive.find_any()
            self.driver_alive = True
            rospy.loginfo("Odrive found")
        except:
            rospy.loginfo("Odrive has been switched off")

    def calibration(self):
        self.my_drive.axis0.requested_state = AxisState.MOTOR_CALIBRATION
        time.sleep(5)
        self.my_drive.axis0.requested_state = AxisState.ENCODER_OFFSET_CALIBRATION
        time.sleep(10)
        self.my_drive.axis0.requested_state = AxisState.CLOSED_LOOP_CONTROL
        time.sleep(5)
        self.my_drive.axis1.requested_state = AxisState.MOTOR_CALIBRATION
        time.sleep(5)
        self.my_drive.axis1.requested_state = AxisState.ENCODER_OFFSET_CALIBRATION
        time.sleep(10)
        self.my_drive.axis1.requested_state = AxisState.CLOSED_LOOP_CONTROL
        time.sleep(5)
        rospy.loginfo("Calibration has been done")
        
    def signal_handler(self, num, frame):
        try:
            self.my_drive.axis0.controller.input_vel = 0
            self.my_drive.axis1.controller.input_vel = 0
            rospy.logwarn(f"Handle signal {num}")
            sys.exit(0)
        except Exception as e:
            rospy.logerr(type(e))
    
if __name__ == '__main__':
    # Initialize Node 
    rospy.init_node('Odrive_Driver_Node', anonymous=True)
    hz = rospy.get_param('~frequency', default = 50)
    r = rospy.Rate(hz)
    # Calling Class
    Odrive = Odrive_Driver()

    rospy.on_shutdown(Odrive.shutdown_hook)
    signal.signal(signal.SIGINT, Odrive.signal_handler)
    signal.signal(signal.SIGHUP, Odrive.signal_handler)
    signal.signal(signal.SIGTERM, Odrive.signal_handler)
    signal.signal(signal.SIGALRM, Odrive.signal_handler)
    signal.signal(signal.SIGSYS, Odrive.signal_handler)


    while not rospy.is_shutdown() and Odrive.driver_alive:
        try:
            Odrive.driver_status()
            Odrive.cmd_stop()
            r.sleep()
        except KeyboardInterrupt:
            break
       
    














