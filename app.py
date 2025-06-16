import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS # <--- ADDED: Import CORS
import base64
import threading
import time
import os # <--- ADDED: Import os for secret key

app = Flask(__name__)
# Generate a strong secret key for production environments
# For development, you can use a fixed string, but for deployment, use a random one.
# If you deploy to Render, you should ideally set SECRET_KEY as an environment variable there.
app.config['SECRET_KEY'] = os.urandom(24) # <--- UPDATED: Stronger secret key
# Allow all origins for SocketIO and Flask routes for development/Render deployment
# IMPORTANT: In production, change "*" to your specific React frontend URL (e.g., "https://your-react-app.onrender.com")
socketio = SocketIO(app, cors_allowed_origins="*") # <--- UPDATED: Added cors_allowed_origins
CORS(app) # <--- ADDED: Enable CORS for Flask HTTP routes

# Authentication credentials (unchanged)
AUTH_USERNAME = "admin"
AUTH_PASSWORD = "password123"

# Character and camera state
character_position = {'x': 50, 'y': 50}
camera_active = False
camera_thread = None
camera = None

# --- Character Movement Configuration ---
MOVE_STEP_X = 50 # <--- UPDATED: Character moves 50 pixels left/right per press (increased from 10)
JUMP_HEIGHT = 100 # <--- UPDATED: Character jumps 100 pixels up (increased from 20)
JUMP_GRAVITY_DELAY_MS = 300 # How long character stays "up" before gravity pulls it down (matches client's setTimeout)
MAX_X_POSITION = 900 # <--- ADDED: Increased maximum X boundary for character movement
# --- End Configuration ---

# Helper function to apply gravity after a jump
def apply_gravity_after_jump(target_y):
    """
    Sets the character's Y position back to its 'ground' level after a jump,
    and emits a 'gravity' event to clients to trigger the fall animation.
    """
    global character_position
    character_position['y'] = target_y
    socketio.emit('gravity', {'y': target_y})
    print(f"Character fell back to Y: {character_position['y']}")

@app.route('/')
def index():
    """Renders the control panel HTML page."""
    return render_template('control_panel.html')

@app.route('/mobile')
def mobile():
    """Renders the mobile view HTML page."""
    return render_template('mobile_view.html')

@app.route('/login', methods=['POST'])
def login():
    """Handles user login for camera access."""
    data = request.get_json()
    if data and data.get('username') == AUTH_USERNAME and data.get('password') == AUTH_PASSWORD:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/move_character', methods=['POST'])
def move_character():
    """
    Handles character movement commands (left, right, jump).
    Updates server-side character_position and emits updates to clients.
    """
    global character_position
    direction = request.json.get('direction')

    if direction == 'left':
        # Move left, ensuring it doesn't go below 0 on the X axis
        character_position['x'] = max(0, character_position['x'] - MOVE_STEP_X) # <--- UPDATED
        print(f"Moved left to X: {character_position['x']}")
    elif direction == 'right':
        # Move right, ensuring it doesn't exceed the MAX_X_POSITION on the X axis
        character_position['x'] = min(MAX_X_POSITION, character_position['x'] + MOVE_STEP_X) # <--- UPDATED
        print(f"Moved right to X: {character_position['x']}")
    elif direction == 'jump':
        # Store the current 'ground' Y position before initiating the jump
        ground_y = character_position['y']
        
        # Move character immediately up to the peak of the jump
        character_position['y'] += JUMP_HEIGHT # <--- UPDATED
        
        # Notify all connected clients about the character's new, higher position
        socketio.emit('character_moved', character_position)
        print(f"Character jumped to Y: {character_position['y']}")
        
        # Schedule the character to "fall" back to its ground position after a delay.
        # This uses eventlet's non-blocking timer to simulate gravity after the jump.
        eventlet.spawn_after(JUMP_GRAVITY_DELAY_MS / 1000.0, apply_gravity_after_jump, ground_y)
        
    # For non-jump movements (left/right), emit the updated position immediately
    if direction != 'jump':
        socketio.emit('character_moved', character_position)
        
    return jsonify(character_position)

@app.route('/toggle_camera', methods=['POST'])
def toggle_camera():
    """Toggles camera streaming on/off based on action."""
    action = request.json.get('action')
    if action == 'start':
        socketio.emit('start_camera')  # Notify mobile to start camera
        print("Camera start requested from mobile.")
        return jsonify({'status': 'camera_expected_from_mobile'})
    elif action == 'stop':
        # In a real scenario, you'd send a stop signal to the mobile app
        print("Camera stop requested.")
        return jsonify({'status': 'camera_stopped'})
    return jsonify({'error': 'Invalid action'}), 400

@socketio.on('connect')
def handle_connect():
    """Handles new client connections to SocketIO."""
    print('Client connected')
    # Send the current character position to the newly connected client
    socketio.emit('character_moved', character_position)

@socketio.on('mobile_camera_frame')
def handle_mobile_camera_frame(data):
    """
    Receives camera frames from the mobile client and forwards them
    to all other connected clients (e.g., the laptop control panel).
    """
    # Forward the frame (base64 encoded image data) to all clients
    socketio.emit('camera_frame', {'frame': data['frame']})
    # print("Received and forwarded mobile camera frame.") # Uncomment for verbose debugging


if __name__ == '__main__':
    # When deploying to Render, the port is usually managed by Render itself.
    # debug=True provides auto-reloading and helpful error messages during development.
    socketio.run(app, debug=True, port=10000) # Use port 10000 as configured for Render
