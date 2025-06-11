from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Character position
character_pos = {'x': 50, 'y': 50}

@app.route('/')
def control_panel():
    return render_template('control_panel.html')

@app.route('/mobile')
def mobile_view():
    return render_template('mobile.html')

@socketio.on('move')
def handle_move(direction):
    if direction == 'left':
        character_pos['x'] = max(0, character_pos['x'] - 10)
    elif direction == 'right':
        character_pos['x'] = min(300, character_pos['x'] + 10)
    elif direction == 'jump':
        character_pos['y'] = max(0, character_pos['y'] - 20)
        # Simulate gravity
        socketio.emit('gravity', {'y': character_pos['y'] + 20})
    
    emit('character_moved', character_pos, broadcast=True)

# Receive video frames from phone
@socketio.on('video_frame')
def handle_frame(data):
    # Broadcast to all control panel clients
    emit('phone_camera_feed', data, broadcast=True, include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)