#!/usr/bin/python3
# coding=utf8
import time
import numpy as np
from my_kinematics.arm_move_ik import ArmIK
from common.ros_robot_controller_sdk import Board
import math

# Servo number constants (based on hardware mapping and provided image)
SERVO_GRIPPER = 1   # 1: Gripper (Claw)
SERVO_ELBOW   = 3   # 3: Elbow
SERVO_SHOULDER= 4   # 4: Shoulder
SERVO_LIFT    = 5   # 5: Base Lift/Rotate
SERVO_BASE    = 6   # 6: Base Rotation
# (If you have a wrist servo, add SERVO_WRIST = 2)

class ArmController:
    """
    Controls the robotic arm movements and operations.
    """
    def __init__(self):
        self.board = Board()
        self.AK = ArmIK()
        self.AK.board = self.board
        self.number = 0  # Counter for stacking
        
        # Load deviation data for smooth motion
        try:
            import common.yaml_handle as yaml_handle
            self.deviation_data = yaml_handle.get_yaml_data(yaml_handle.deviation_file_path)
        except:
            self.deviation_data = {'1': 0, '3': 0, '4': 0, '5': 0, '6': 0}
        
        # Define scan positions in polar coordinates (r, theta, z)
        # r: distance from base (cm)
        # theta: angle relative to forward direction (degrees)
        # z: height above table (cm)
        
        # Adjust scan radius based on angle:
        # - At 0° (forward), we can reach further
        # - At ±90° and beyond, we need shorter reach
        self.min_radius = 8
        self.max_radius_forward = 16  # Maximum reach when facing forward
        self.max_radius_side = 12    # Maximum reach at ±90°
        self.scan_heights = [18]     # Increased height for safety
        
        # Define coordinates
        self.coordinates = {
            'capture': (0, 0, 0),  # Will be set from yaml
            'place': (12, 0, 0.5),  # Placing coordinate
        }

        # Base rotation tracking
        self.current_base_angle = 0   # degrees, 0 = forward
        self.current_base_pos = 1500  # PWM signal for base servo
        self.base_rotation_angle = 0  # Track absolute base rotation
        # Add current joint angles for jogging
        self.current_lift_angle = 0
        self.current_shoulder_angle = 0
        self.current_elbow_angle = 0
        self.current_gripper_pos = 1500  # Track gripper position

    def get_max_radius(self, base_angle):
        """Calculate maximum safe radius based on base angle."""
        # Convert angle to absolute value (symmetrical workspace)
        abs_angle = abs(base_angle)
        
        # Linear interpolation between forward and side max radius
        # As angle goes from 0° to 90°, max radius goes from forward to side
        if abs_angle <= 90:
            fraction = abs_angle / 90.0
            return self.max_radius_forward * (1 - fraction) + self.max_radius_side * fraction
        else:
            # Beyond ±90°, use an even shorter radius
            over_90 = (abs_angle - 90) / 30.0  # How far past 90° we are
            return max(self.min_radius, self.max_radius_side * (1 - over_90 * 0.25))

    def get_scan_positions(self, base_angle):
        """
        Get safe scan positions for this base angle.
        Adjust max radius based on angle to avoid overextending.
        """
        scan_positions = []
        max_r = self.get_max_radius(base_angle)
        
        # Use 3 radial positions between min and max radius
        radii = np.linspace(self.min_radius, max_r, num=3)
        
        # Convert base angle to radians
        base_rad = math.radians(base_angle)
        
        # Always use safe Z height (e.g., 18cm)
        safe_z = 18
        
        for r in radii:
            x = r * math.cos(base_rad)
            y = r * math.sin(base_rad)
            scan_positions.append((x, y, safe_z))
        
        return scan_positions

    def init_move(self):
        """Initialize arm to starting position (match Hiwonder sample)."""
        self.board.pwm_servo_set_position(0.3, [[SERVO_GRIPPER, 1500]])
        self.current_gripper_pos = 1500  # Track gripper position
        res = self.AK.setPitchRangeMoving((0, 8, 10), -90, -90, 90, 1500)
        if res and res[0] is not False:  # Check if we got valid results
            servos, alpha, movetime, angles = res
            self.current_elbow_angle = angles['theta3']
            self.current_shoulder_angle = angles['theta4']
            # The IK angle for the lift joint (theta5) is relative to the horizontal plane,
            # while the jogging angle is a direct servo angle. We adjust it by 90 degrees.
            self.current_lift_angle = 90 - angles['theta5']
            self.current_base_angle = angles['theta6']
            # Also update base PWM position tracker
            self.current_base_pos = servos['servo6']
        else:
            # Fallback values if IK calculation fails
            print("[WARNING] IK calculation failed, using default angles")
            self.current_elbow_angle = 0
            self.current_shoulder_angle = 0
            self.current_lift_angle = 0
            self.current_base_angle = 0
            self.current_base_pos = 1500
    
    def set_rgb(self, color):
        """Set RGB LED color."""
        if color == "red":
            self.board.set_rgb([[1, 255, 0, 0], [2, 255, 0, 0]])
        elif color == "green":
            self.board.set_rgb([[1, 0, 255, 0], [2, 0, 255, 0]])
        elif color == "blue":
            self.board.set_rgb([[1, 0, 0, 255], [2, 0, 0, 255]])
        else:
            self.board.set_rgb([[1, 0, 0, 0], [2, 0, 0, 0]])
    
    def set_coordinates(self, x, y, z):
        """Set the capture coordinates."""
        self.coordinates['capture'] = (x, y, z)
    
    def open_gripper(self):
        """Open the gripper."""
        print("[Arm] Opening gripper")
        self.board.pwm_servo_set_position(0.5, [[SERVO_GRIPPER, 1900]])
        time.sleep(0.5)

    def close_gripper(self):
        """Close the gripper."""
        print("[Arm] Closing gripper")
        self.board.pwm_servo_set_position(0.5, [[SERVO_GRIPPER, 1500]])
        time.sleep(0.5)

    def move_to_position(self, pos, pitch=-90, movetime=1000):
        """
        Move arm to position with specified pitch angle.
        Returns True if movement successful, False otherwise.
        """
        print(f"[Arm] Moving to position {pos} with pitch {pitch}°")
        result = self.AK.setPitchRangeMoving(pos, pitch, pitch, pitch, movetime)
        if not result:
            print(f"[WARNING] Could not reach position: {pos} with pitch {pitch}")
            return False
        else:
            time.sleep(result[2] / 1000)  # Wait for movement to complete
            return True

    def pick_up_block(self, x, y, z):
        """
        Pick up block at (x, y, z).
        Uses a sequence of coordinated movements with error checking.
        """
        # Open gripper before approaching
        self.open_gripper()

        # Move to pickup position
        pickup_z = z - 2.75  # Offset for pickup
        print(f"[Arm] Lowering to pickup at ({x}, {y}, {pickup_z})")
        if not self.move_to_position((x, y, pickup_z), pitch=-60):
            print("[Arm] Failed to reach pickup position")
            return False

        # Close gripper on block
        self.close_gripper()

        # Lift block up to safe height
        if not self.move_to_position((0, 6, 18), pitch=-45):
            print("[Arm] Failed to lift block")
            return False

        return True

    def place_block(self):
        """
        Place block at stacking location.
        Uses a sequence of coordinated movements with error checking.
        """
        stacking_x, stacking_y, stacking_z = 12, 0, 0.5  # Default stacking location
        place_z = stacking_z + self.number * self.block_height - 2  # Drop height

        # Move above stacking location
        if not self.move_to_position((stacking_x, stacking_y, 12), pitch=-45):
            print("[Arm] Failed to move above stacking location")
            return False

        # Lower to place position
        print(f"[Arm] Placing block {self.number} at ({stacking_x}, {stacking_y}, {place_z})")
        if not self.move_to_position((stacking_x, stacking_y, place_z), pitch=-60):
            print("[Arm] Failed to reach place position")
            return False

        # Release block
        self.open_gripper()

        # Lift up after placing
        if not self.move_to_position((6, 0, 18), pitch=-45):
            print("[Arm] Failed to lift after placing")
            return False

        # Return to ready position
        if not self.move_to_position((0, 8, 10), pitch=-45):
            print("[Arm] Failed to return to ready position")
            return False

        # Update block count and signal completion
        self.number = (self.number + 1) % 3
        if self.number == 0:
            self.board.set_buzzer(1900, 0.1, 0.9, 1)
            self.set_rgb('white')
            time.sleep(0.5)

        return True
    
    def scan_position(self, position, pitch_angle=-10):
        """
        Move to a scan position with a fixed pitch angle to avoid "lifting".
        """
        print(f"[Arm] Moving to scan position: {position} with pitch {pitch_angle}° (base angle {self.current_base_angle})")
        self.board.pwm_servo_set_position(0.5, [[SERVO_BASE, self.current_base_pos]])
        # Use fixed pitch angle and scan position
        self.AK.setPitchRangeMoving(position, pitch_angle, pitch_angle, pitch_angle, 500)
        time.sleep(0.25)
    
    def rotate_base(self, angle):
        """
        Rotate the base by a given angle (degrees). Positive for CW, negative for CCW.
        """
        self.current_base_angle += angle
        self.current_base_angle = max(-180, min(180, self.current_base_angle))  # Expand to ±180°
        units_per_degree = 2000 / 180  # Corrected scaling: 2000 pulse range / 180 degrees
        self.current_base_pos = 1500 + int(self.current_base_angle * units_per_degree)
        self.current_base_pos = max(500, min(2500, self.current_base_pos))
        print(f"[Arm] Rotating base to servo pos {self.current_base_pos} for angle {self.current_base_angle}")
        self.board.pwm_servo_set_position(0.5, [[SERVO_BASE, self.current_base_pos]])
        self.base_rotation_angle = self.current_base_angle  # 💡 Always track absolute base rotation
        time.sleep(1)

    def move_lift(self, delta_angle):
        """Jog the lift axis by delta_angle degrees."""
        self.current_lift_angle += delta_angle
        self.current_lift_angle = max(-120, min(120, self.current_lift_angle))  # adjust limits as needed
        pos = 1500 + int(self.current_lift_angle * (2000 / 180)) # Corrected scaling
        pos = max(500, min(2500, pos))
        # Use WonderPi smooth motion: 20ms movement time + deviation compensation
        self.board.pwm_servo_set_position(0.02, [[SERVO_LIFT, pos + self.deviation_data[str(SERVO_LIFT)]]])

    def move_shoulder(self, delta_angle):
        """Jog the shoulder axis by delta_angle degrees."""
        self.current_shoulder_angle += delta_angle
        self.current_shoulder_angle = max(-120, min(120, self.current_shoulder_angle))
        pos = 1500 + int(self.current_shoulder_angle * (2000 / 180)) # Corrected scaling
        pos = max(500, min(2500, pos))
        # Use WonderPi smooth motion: 20ms movement time + deviation compensation
        self.board.pwm_servo_set_position(0.02, [[SERVO_SHOULDER, pos + self.deviation_data[str(SERVO_SHOULDER)]]])

    def move_elbow(self, delta_angle):
        """Jog the elbow axis by delta_angle degrees."""
        self.current_elbow_angle += delta_angle
        self.current_elbow_angle = max(-120, min(120, self.current_elbow_angle))
        pos = 1500 + int(self.current_elbow_angle * (2000 / 180)) # Corrected scaling
        pos = max(500, min(2500, pos))
        # Use WonderPi smooth motion: 20ms movement time + deviation compensation
        final_pos = pos + self.deviation_data[str(SERVO_ELBOW)]
        self.board.pwm_servo_set_position(0.02, [[SERVO_ELBOW, final_pos]])

    def move_base(self, delta_angle):
        """Jog the base axis by delta_angle degrees."""
        self.current_base_angle += delta_angle
        self.current_base_angle = max(-180, min(180, self.current_base_angle))
        pos = 1500 + int(self.current_base_angle * (2000 / 180)) # Corrected scaling
        pos = max(500, min(2500, pos))
        # Use WonderPi smooth motion: 20ms movement time + deviation compensation
        self.board.pwm_servo_set_position(0.02, [[SERVO_BASE, pos + self.deviation_data[str(SERVO_BASE)]]])
        self.current_base_pos = pos

    def move_gripper(self, delta_pos):
        """Jog the gripper by delta_pos PWM units."""
        self.current_gripper_pos += delta_pos
        self.current_gripper_pos = max(500, min(2500, self.current_gripper_pos))  # PWM limits
        # Use WonderPi smooth motion: 20ms movement time + deviation compensation
        self.board.pwm_servo_set_position(0.02, [[SERVO_GRIPPER, self.current_gripper_pos + self.deviation_data[str(SERVO_GRIPPER)]]])

    def get_arm_position(self):
        """Get current arm position using forward kinematics."""
        # Convert joint angles to radians
        lift_rad = math.radians(self.current_lift_angle)
        shoulder_rad = math.radians(self.current_shoulder_angle)
        elbow_rad = math.radians(self.current_elbow_angle)
        base_rad = math.radians(self.current_base_angle)
        
        # Simplified forward kinematics (you may need to adjust these parameters)
        # This is a basic approximation - replace with your actual FK
        L1 = 10.5  # Base to shoulder length (cm)
        L2 = 10.5  # Shoulder to elbow length (cm)
        L3 = 10.5  # Elbow to gripper length (cm)
        
        # Calculate end effector position
        x = L1 * math.cos(base_rad) * math.cos(shoulder_rad) + \
            L2 * math.cos(base_rad) * math.cos(shoulder_rad + elbow_rad) + \
            L3 * math.cos(base_rad) * math.cos(shoulder_rad + elbow_rad)
        
        y = L1 * math.sin(base_rad) * math.cos(shoulder_rad) + \
            L2 * math.sin(base_rad) * math.cos(shoulder_rad + elbow_rad) + \
            L3 * math.sin(base_rad) * math.cos(shoulder_rad + elbow_rad)
        
        z = L1 * math.sin(shoulder_rad) + L2 * math.sin(shoulder_rad + elbow_rad) + \
            L3 * math.sin(shoulder_rad + elbow_rad) + self.current_lift_angle * 0.1
        
        return (x, y, z)
