from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import cv2
import base64
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

# Authentication credentials
AUTH_USERNAME = "admin"
AUTH_PASSWORD = "password123"

# Character and camera state
character_position = {'x': 50, 'y': 50}
camera_active = False
camera_thread = None
camera = None

# Camera streaming function

@app.route('/')
def index():
    return render_template('control_panel.html')  # No forced login

@app.route('/mobile')
def mobile():
    return render_template('mobile_view.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if data['username'] == AUTH_USERNAME and data['password'] == AUTH_PASSWORD:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/move_character', methods=['POST'])
def move_character():
    direction = request.json.get('direction')
    if direction == 'left':
        character_position['x'] = max(0, character_position['x'] - 10)
    elif direction == 'right':
        character_position['x'] = min(300, character_position['x'] + 10)
    elif direction == 'jump':
        character_position['y'] = max(0, character_position['y'] - 20)
        socketio.emit('gravity', {'y': character_position['y'] + 20})
    
    socketio.emit('character_moved', character_position)
    return jsonify(character_position)

@app.route('/toggle_camera', methods=['POST'])
def toggle_camera():
    action = request.json.get('action')
    if action == 'start':
        socketio.emit('start_camera')  # Notify mobile to start
        return jsonify({'status': 'camera_expected_from_mobile'})
    elif action == 'stop':
        return jsonify({'status': 'camera_stopped'})
    return jsonify({'error': 'Invalid action'}), 400



@socketio.on('connect')
def handle_connect():
    socketio.emit('character_moved', character_position)

@socketio.on('mobile_camera_frame')
def handle_mobile_camera_frame(data):
    # Forward the frame to all clients (e.g., laptop viewing control panel)
    socketio.emit('camera_frame', {'frame': data['frame']})


# if __name__ == '__main__':
#     socketio.run(app, host='0.0.0.0', port=5000, debug=True)

if __name__ == '__main__':
    import eventlet
    import eventlet.wsgi
    eventlet.monkey_patch()

    socketio.run(app, host='0.0.0.0', port=10000)  # Port will be overridden by Render
