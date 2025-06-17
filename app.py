import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import base64 # Still import, but not used for camera frames
import threading # Still import, but not used for camera threads
import time # Still import, but not used for camera delays
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)

AUTH_USERNAME = "admin"
AUTH_PASSWORD = "password123"

# Global state for character base position (still used for overall movement)
character_position = {'x': 50, 'y': 50}
# camera_active = False # Removed camera state
# camera_thread = None  # Removed camera thread
# camera = None         # Removed camera object

# --- Global state for joint angles ---
# Store the current angle for each relevant joint.
# These values will be sent to mobile_view.html to update the 3D robot's pose.
# Initialize with default/starting angles (e.g., 0 radians)
robot_joint_angles = {
    'shoulder_yaw': 0.0,
    'shoulder_pitch': 0.0,
    'elbow_pitch': 0.0,
    'wrist_pitch': 0.0,
    'wrist_roll': 0.0,
    'finger_joint': 0.0, # Prismatic, but we can simulate a linear motion with this "angle"
    'finger_joint_2': 0.0 # Mimics finger_joint
}

# --- Character Movement Configuration ---
MOVE_STEP_X = 50
JUMP_HEIGHT = 100
JUMP_GRAVITY_DELAY_MS = 300
MAX_X_POSITION = 900

def apply_gravity_after_jump(target_y):
    global character_position
    character_position['y'] = target_y
    socketio.emit('gravity', {'y': target_y})
    print(f"Character fell back to Y: {character_position['y']}")

@app.route('/')
def index():
    return render_template('control_panel.html')

@app.route('/mobile')
def mobile():
    return render_template('mobile_view.html')

# Removed login route as it was only for camera access
# @app.route('/login', methods=['POST'])
# def login():
#     data = request.get_json()
#     if data and data.get('username') == AUTH_USERNAME and data.get('password') == AUTH_PASSWORD:
#         return jsonify({'success': True})
#     return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/move_character', methods=['POST'])
def move_character():
    global character_position
    direction = request.json.get('direction')

    if direction == 'left':
        character_position['x'] = max(0, character_position['x'] - MOVE_STEP_X)
        print(f"Moved left to X: {character_position['x']}")
    elif direction == 'right':
        character_position['x'] = min(MAX_X_POSITION, character_position['x'] + MOVE_STEP_X)
        print(f"Moved right to X: {character_position['x']}")
    elif direction == 'jump':
        ground_y = character_position['y']
        character_position['y'] += JUMP_HEIGHT
        socketio.emit('character_moved', character_position)
        print(f"Character jumped to Y: {character_position['y']}")
        eventlet.spawn_after(JUMP_GRAVITY_DELAY_MS / 1000.0, apply_gravity_after_jump, ground_y)
    
    if direction != 'jump':
        socketio.emit('character_moved', character_position)
        
    return jsonify(character_position)

# Removed toggle_camera route
# @app.route('/toggle_camera', methods=['POST'])
# def toggle_camera():
#     global camera_active
#     action = request.json.get('action')
#     if action == 'start':
#         camera_active = True
#         socketio.emit('start_camera')
#         print("Camera start requested from mobile.")
#         return jsonify({'status': 'camera_expected_from_mobile'})
#     elif action == 'stop':
#         camera_active = False
#         socketio.emit('stop_camera')
#         print("Camera stop requested.")
#         return jsonify({'status': 'camera_stopped'})\
#     return jsonify({'error': 'Invalid action'}), 400

@socketio.on('set_joint_angle')
def handle_set_joint_angle(data):
    joint_name = data.get('joint_name')
    angle = data.get('angle')
    
    if joint_name in robot_joint_angles:
        robot_joint_angles[joint_name] = angle
        print(f"Joint '{joint_name}' set to angle: {angle} radians")
        socketio.emit('joint_angle_updated', {'joint_name': joint_name, 'angle': angle})
    else:
        print(f"Warning: Attempted to set unknown joint: {joint_name}")

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    socketio.emit('character_moved', character_position)
    socketio.emit('initial_joint_states', robot_joint_angles)
    # Removed camera active check and emit
    # if camera_active:
    #     socketio.emit('start_camera')

# Removed mobile_camera_frame event handler
# @socketio.on('mobile_camera_frame')
# def handle_mobile_camera_frame(data):
#     socketio.emit('camera_feed', {'frame': data['frame']})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
