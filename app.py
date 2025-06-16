import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import base64
import threading
import time
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)

AUTH_USERNAME = "admin"
AUTH_PASSWORD = "password123"

character_position = {'x': 50, 'y': 50}
camera_active = False # Track camera state on server
camera_thread = None
camera = None

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

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if data and data.get('username') == AUTH_USERNAME and data.get('password') == AUTH_PASSWORD:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

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
    
    if direction != 'jump': # Only emit for left/right immediately, jump handles its own emit
        socketio.emit('character_moved', character_position)
        
    return jsonify(character_position)

@app.route('/toggle_camera', methods=['POST'])
def toggle_camera():
    global camera_active # Access the global state
    action = request.json.get('action')
    if action == 'start':
        camera_active = True
        socketio.emit('start_camera') # Notify mobile to start camera
        print("Camera start requested from mobile.")
        return jsonify({'status': 'camera_expected_from_mobile'})
    elif action == 'stop':
        camera_active = False # Update server-side state
        socketio.emit('stop_camera') # <--- ADDED: Notify mobile to stop camera
        print("Camera stop requested.")
        return jsonify({'status': 'camera_stopped'})
    return jsonify({'error': 'Invalid action'}), 400

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    # When a client connects, send them the current character position
    socketio.emit('character_moved', character_position)
    # Also, if camera is already active, tell the new client to start it
    if camera_active:
        socketio.emit('start_camera')

@socketio.on('mobile_camera_frame')
def handle_mobile_camera_frame(data):
    # Forward the frame to all clients (e.g., laptop viewing control panel)
    socketio.emit('camera_feed', {'frame': data['frame']})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
