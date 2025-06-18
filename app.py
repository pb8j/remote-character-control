import eventlet
eventlet.monkey_patch() # Patch standard library for async operations
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import base64
import os
import random # For generating random device IDs for phones

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24) # Generate a random secret key for Flask sessions
socketio = SocketIO(app, cors_allowed_origins="*") # Enable SocketIO with CORS for all origins
CORS(app) # Enable Flask CORS for all origins

# Global state to keep track of connected devices and their socket IDs
# This acts as a simple registry for WebRTC signaling
connected_laptops = {} # {laptop_socket_id: laptop_socket_object}
connected_phones = {} # {phone_device_id: phone_socket_object}

# Global state for robot joint angles (Robotiq 85 gripper specific)
# These initial values are based on common defaults or the provided image's context.
robot_joint_angles = {
    'finger_joint': 0.0, # Main joint for the Robotiq 85 gripper (0 = open, 0.725 = closed)
    # Other joints might be mimicked in the URDF, so we primarily control this one
    'shoulder_yaw': 0.95, # Example from hexapod, not directly used by gripper
    'shoulder_pitch': 1.44, # Example from hexapod, not directly used by gripper
    'elbow_pitch': -0.20, # Example from hexapod, not directly used by gripper
    'wrist_pitch': 1.31, # Example from hexapod, not directly used by gripper
    'wrist_roll': -2.94, # Example from hexapod, not directly used by gripper
    'finger_joint_2': 0.0 # Example from hexapod, not directly used by gripper
}

@app.route('/')
def index():
    """Renders the control panel HTML page."""
    return render_template('control_panel.html')

@app.route('/mobile')
def mobile():
    """Renders the mobile view HTML page."""
    return render_template('mobile_view.html')

@app.route('/toggle_camera', methods=['POST'])
def toggle_camera():
    """
    Handles camera start/stop requests.
    This is for direct camera frame streaming (base64) as a fallback/alternative,
    but the primary streaming will be WebRTC controlled by socket events.
    """
    action = request.json.get('action')
    phone_device_id = request.json.get('phoneDeviceId') # Get target phone ID

    if phone_device_id not in connected_phones:
        print(f"Error: Target phone {phone_device_id} not connected.")
        return jsonify({'error': f'Phone device {phone_device_id} not found.'}), 404

    target_socket = connected_phones[phone_device_id]

    if action == 'start':
        socketio.emit('start_camera', room=target_socket.sid) # Emit to specific phone
        print(f"Camera start requested for phone: {phone_device_id}")
        return jsonify({'status': 'camera_start_requested'})
    elif action == 'stop':
        socketio.emit('stop_camera', room=target_socket.sid) # Emit to specific phone
        print(f"Camera stop requested for phone: {phone_device_id}")
        return jsonify({'status': 'camera_stopped'})
    else:
        return jsonify({'error': 'Invalid action'}), 400

# --- Socket.IO Event Handlers ---

@socketio.on('connect')
def handle_connect():
    """Handles new client connections."""
    print(f'Client connected: {request.sid}')
    # Immediately send initial joint states to any newly connected client
    socketio.emit('initial_joint_states', robot_joint_angles, room=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    """Handles client disconnections."""
    print(f'Client disconnected: {request.sid}')
    # Remove disconnected laptops
    laptop_id_to_remove = None
    for laptop_id, sock_obj in connected_laptops.items():
        if sock_obj.sid == request.sid:
            laptop_id_to_remove = laptop_id
            break
    if laptop_id_to_remove:
        del connected_laptops[laptop_id_to_remove]
        print(f"Laptop {laptop_id_to_remove} removed from connected list.")
        # Notify other laptops about the change
        socketio.emit('available_phones', list(connected_phones.keys()))

    # Remove disconnected phones
    phone_id_to_remove = None
    for phone_id, sock_obj in connected_phones.items():
        if sock_obj.sid == request.sid:
            phone_id_to_remove = phone_id
            break
    if phone_id_to_remove:
        del connected_phones[phone_id_to_remove]
        print(f"Phone {phone_id_to_remove} removed from connected list.")
        # Notify all laptops about the updated list of available phones
        socketio.emit('available_phones', list(connected_phones.keys()))

@socketio.on('register_laptop')
def handle_register_laptop():
    """Registers a laptop client."""
    laptop_socket_id = request.sid
    connected_laptops[laptop_socket_id] = request
    print(f"Laptop registered: {laptop_socket_id}")
    # Send the current list of available phones to the newly registered laptop
    socketio.emit('available_phones', list(connected_phones.keys()), room=laptop_socket_id)

@socketio.on('register_phone')
def handle_register_phone(phone_device_id):
    """Registers a phone client with a unique device ID."""
    connected_phones[phone_device_id] = request
    print(f"Phone registered: {phone_device_id} (socket ID: {request.sid})")
    # Notify all registered laptops about the new phone
    socketio.emit('available_phones', list(connected_phones.keys()))

@socketio.on('get_available_phones')
def handle_get_available_phones():
    """Sends the list of available phones to the requesting laptop."""
    socketio.emit('available_phones', list(connected_phones.keys()), room=request.sid)
    print(f"Sent available phones to {request.sid}")

@socketio.on('request_stream')
def handle_request_stream(data):
    """
    Initiates WebRTC offer creation on the target phone.
    Sent from laptop to server, then forwarded to phone.
    """
    phone_device_id = data.get('phoneDeviceId')
    laptop_socket_id = data.get('laptopSocketId')

    if phone_device_id in connected_phones:
        target_phone_socket = connected_phones[phone_device_id]
        print(f"Requesting stream from {phone_device_id} for laptop {laptop_socket_id}")
        socketio.emit('start_webrtc_offer', {
            'requestingLaptopSocketId': laptop_socket_id
        }, room=target_phone_socket.sid)
    else:
        print(f"Error: Phone {phone_device_id} not found for stream request.")

@socketio.on('sdp_offer_from_phone')
def handle_sdp_offer_from_phone(data):
    """
    Forwards SDP offer from phone to the requesting laptop.
    Sent from phone to server, then forwarded to laptop.
    """
    sdp_offer = data.get('sdpOffer')
    phone_device_id = data.get('phoneDeviceId')
    requesting_laptop_socket_id = data.get('requestingLaptopSocketId')

    if requesting_laptop_socket_id in connected_laptops:
        print(f"Forwarding SDP Offer from {phone_device_id} to laptop {requesting_laptop_socket_id}")
        socketio.emit('sdp_offer_from_phone', {
            'sdpOffer': sdp_offer,
            'phoneDeviceId': phone_device_id
        }, room=requesting_laptop_socket_id)
    else:
        print(f"Error: Requesting laptop {requesting_laptop_socket_id} not found for SDP offer.")

@socketio.on('sdp_answer_from_laptop')
def handle_sdp_answer_from_laptop(data):
    """
    Forwards SDP answer from laptop to the phone that sent the offer.
    Sent from laptop to server, then forwarded to phone.
    """
    sdp_answer = data.get('sdpAnswer')
    phone_device_id = data.get('phoneDeviceId')

    if phone_device_id in connected_phones:
        target_phone_socket = connected_phones[phone_device_id]
        print(f"Forwarding SDP Answer from laptop {request.sid} to phone {phone_device_id}")
        socketio.emit('sdp_answer_from_laptop', sdp_answer, room=target_phone_socket.sid)
    else:
        print(f"Error: Phone {phone_device_id} not found for SDP answer.")

@socketio.on('ice_candidate_from_phone')
def handle_ice_candidate_from_phone(data):
    """
    Forwards ICE candidate from phone to the requesting laptop.
    Sent from phone to server, then forwarded to laptop.
    """
    candidate = data.get('candidate')
    phone_device_id = data.get('phoneDeviceId')
    requesting_laptop_socket_id = data.get('requestingLaptopSocketId')

    if requesting_laptop_socket_id in connected_laptops:
        print(f"Forwarding ICE candidate from {phone_device_id} to laptop {requesting_laptop_socket_id}")
        socketio.emit('ice_candidate_from_phone', candidate, room=requesting_laptop_socket_id)
    else:
        print(f"Error: Requesting laptop {requesting_laptop_socket_id} not found for ICE candidate.")

@socketio.on('ice_candidate_from_laptop')
def handle_ice_candidate_from_laptop(data):
    """
    Forwards ICE candidate from laptop to the phone.
    Sent from laptop to server, then forwarded to phone.
    """
    candidate = data.get('candidate')
    phone_device_id = data.get('phoneDeviceId')

    if phone_device_id in connected_phones:
        target_phone_socket = connected_phones[phone_device_id]
        print(f"Forwarding ICE candidate from laptop {request.sid} to phone {phone_device_id}")
        socketio.emit('ice_candidate_from_laptop', candidate, room=target_phone_socket.sid)
    else:
        print(f"Error: Phone {phone_device_id} not found for ICE candidate.")

@socketio.on('set_joint_angle')
def handle_set_joint_angle(data):
    """
    Handles joint angle updates from the control panel and broadcasts to all clients.
    The 'finger_joint' is specifically for the Robotiq 85 gripper.
    """
    joint_name = data.get('joint_name')
    angle = data.get('angle')

    if joint_name in robot_joint_angles:
        robot_joint_angles[joint_name] = angle
        print(f"Joint '{joint_name}' set to angle: {angle} radians")
        # Broadcast the updated joint angle to all connected clients (laptops and phones)
        socketio.emit('joint_angle_updated', {'joint_name': joint_name, 'angle': angle})
    else:
        print(f"Warning: Attempted to set unknown joint: {joint_name}")
        # For the hexapod, general movement commands are sent via 'control' event

@socketio.on('control')
def handle_control_command(data):
    """
    Handles general control commands (e.g., for hexapod movement).
    Broadcasts the command to all connected clients.
    """
    cmd = data.get('cmd')
    target_phone_id = data.get('targetPhoneId')

    print(f"Received control command '{cmd}' for phone {target_phone_id}")

    # For hexapod movement, we want the mobile client (phone) to apply it locally
    # and potentially other control panels to visualize it.
    if target_phone_id in connected_phones:
        socketio.emit('control', cmd, room=connected_phones[target_phone_id].sid) # Send only to the target phone
        print(f"Forwarded control command '{cmd}' to target phone {target_phone_id}")
    else:
        print(f"Error: Target phone {target_phone_id} not found for control command.")


@socketio.on('mobile_camera_frame')
def handle_mobile_camera_frame(data):
    """
    Handles camera frames (base64) from mobile and broadcasts to control panel.
    This is for the non-WebRTC fallback/alternative.
    """
    socketio.emit('camera_feed', {'frame': data['frame']})
    # print("Camera frame received from mobile and broadcasted (base64)") # Commented out to reduce log spam

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # It's crucial to specify host='0.0.0.0' for deployment on platforms like Render
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
