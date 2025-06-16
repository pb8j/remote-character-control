import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import base64
import threading
import time
import os # Import os for environment variables

app = Flask(__name__)
# Generate a strong secret key for production environments
app.config['SECRET_KEY'] = os.urandom(24)
# Allow all origins for SocketIO and Flask routes for development/Render deployment
# IMPORTANT: In production, change "*" to your specific React frontend URL (e.g., "https://your-react-app.onrender.com")
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app) # Enable CORS for Flask HTTP routes

# Authentication credentials
AUTH_USERNAME = "admin"
AUTH_PASSWORD = "password123"

# Character and camera state
character_position = {'x': 50, 'y': 50}
camera_active = False
camera_thread = None
camera = None

# --- Character Movement Configuration ---
MOVE_STEP_X = 50
JUMP_HEIGHT = 100
JUMP_GRAVITY_DELAY_MS = 300
MAX_X_POSITION = 900
# --- End Configuration ---

# Helper function to apply gravity after a jump
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
    
    if direction != 'jump':
        socketio.emit('character_moved', character_position)
        
    return jsonify(character_position)

@app.route('/toggle_camera', methods=['POST'])
def toggle_camera():
    action = request.json.get('action')
    if action == 'start':
        socketio.emit('start_camera')
        print("Camera start requested from mobile.")
        return jsonify({'status': 'camera_expected_from_mobile'})
    elif action == 'stop':
        print("Camera stop requested.")
        return jsonify({'status': 'camera_stopped'})
    return jsonify({'error': 'Invalid action'}), 400

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    socketio.emit('character_moved', character_position)

@socketio.on('mobile_camera_frame')
def handle_mobile_camera_frame(data):
    socketio.emit('camera_frame', {'frame': data['frame']})


if __name__ == '__main__':
    # Get the port from the environment variable provided by Render, default to 5000 for local development
    port = int(os.environ.get('PORT', 5000)) # <--- UPDATED: Get port from environment
    # Bind to '0.0.0.0' to be accessible externally (required by Render)
    socketio.run(app, host='0.0.0.0', port=port, debug=False) # <--- UPDATED: Bind to 0.0.0.0 and use dynamic port
