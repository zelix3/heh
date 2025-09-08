from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room, rooms
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory storage (use a database in production)
users = {}  # {username: {password_hash: str, is_online: bool, socket_id: str}}
private_messages = {}  # {room_id: [messages]}
active_rooms = {}  # {room_id: [user1, user2]}

@app.route('/')
def index():
    if 'username' in session:
        return render_template('chat.html', username=session['username'])
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username in users:
            return render_template('login.html', error='Username already exists')
        
        users[username] = {
            'password_hash': generate_password_hash(password),
            'is_online': False,
            'socket_id': None
        }
        return render_template('login.html', success='Registration successful! Please login.')
    
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    
    if username in users and check_password_hash(users[username]['password_hash'], password):
        session['username'] = username
        users[username]['is_online'] = True
        return redirect(url_for('index'))
    
    return render_template('login.html', error='Invalid credentials')

@app.route('/logout')
def logout():
    if 'username' in session:
        username = session['username']
        if username in users:
            users[username]['is_online'] = False
            users[username]['socket_id'] = None
        session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/users')
def get_users():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'})
    
    online_users = [username for username, data in users.items() 
                   if data['is_online'] and username != session['username']]
    return jsonify({'users': online_users})

def get_private_room_id(user1, user2):
    """Generate consistent room ID for two users"""
    return f"private_{min(user1, user2)}_{max(user1, user2)}"

@socketio.on('connect')
def on_connect():
    if 'username' not in session:
        return False
    
    username = session['username']
    users[username]['socket_id'] = request.sid
    users[username]['is_online'] = True
    
    # Broadcast updated user list
    online_users = [u for u, data in users.items() if data['is_online']]
    emit('user_list_updated', {'users': online_users}, broadcast=True)
    
    print(f"{username} connected")

@socketio.on('disconnect')
def on_disconnect():
    if 'username' in session:
        username = session['username']
        if username in users:
            users[username]['is_online'] = False
            users[username]['socket_id'] = None
        
        # Broadcast updated user list
        online_users = [u for u, data in users.items() if data['is_online']]
        emit('user_list_updated', {'users': online_users}, broadcast=True)
        
        print(f"{username} disconnected")

@socketio.on('start_private_chat')
def on_start_private_chat(data):
    if 'username' not in session:
        return
    
    current_user = session['username']
    target_user = data['target_user']
    
    if target_user not in users or not users[target_user]['is_online']:
        emit('error', {'message': 'User not available'})
        return
    
    room_id = get_private_room_id(current_user, target_user)
    
    # Join both users to the private room
    join_room(room_id)
    
    # Notify target user
    target_socket_id = users[target_user]['socket_id']
    if target_socket_id:
        socketio.emit('private_chat_invitation', {
            'from_user': current_user,
            'room_id': room_id
        }, room=target_socket_id)
    
    # Initialize room if it doesn't exist
    if room_id not in private_messages:
        private_messages[room_id] = []
    
    if room_id not in active_rooms:
        active_rooms[room_id] = []
    
    if current_user not in active_rooms[room_id]:
        active_rooms[room_id].append(current_user)
    
    # Send chat history
    emit('private_chat_started', {
        'room_id': room_id,
        'target_user': target_user,
        'messages': private_messages[room_id]
    })

@socketio.on('join_private_chat')
def on_join_private_chat(data):
    if 'username' not in session:
        return
    
    username = session['username']
    room_id = data['room_id']
    
    join_room(room_id)
    
    if room_id not in active_rooms:
        active_rooms[room_id] = []
    
    if username not in active_rooms[room_id]:
        active_rooms[room_id].append(username)
    
    # Notify others in the room
    emit('user_joined_private_chat', {
        'username': username,
        'room_id': room_id
    }, room=room_id, include_self=False)
    
    # Send chat history to the joining user
    emit('private_chat_messages', {
        'room_id': room_id,
        'messages': private_messages.get(room_id, [])
    })

@socketio.on('private_message')
def on_private_message(data):
    if 'username' not in session:
        return
    
    username = session['username']
    room_id = data['room_id']
    message = data['message']
    
    # Store message
    if room_id not in private_messages:
        private_messages[room_id] = []
    
    message_data = {
        'username': username,
        'message': message,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    }
    
    private_messages[room_id].append(message_data)
    
    # Broadcast to room
    emit('private_message_received', message_data, room=room_id)

@socketio.on('start_screen_share')
def on_start_screen_share(data):
    if 'username' not in session:
        return
    
    username = session['username']
    room_id = data['room_id']
    
    # Notify others in the private room about screen sharing
    emit('screen_share_started', {
        'username': username,
        'room_id': room_id
    }, room=room_id, include_self=False)

@socketio.on('stop_screen_share')
def on_stop_screen_share(data):
    if 'username' not in session:
        return
    
    username = session['username']
    room_id = data['room_id']
    
    # Notify others in the private room
    emit('screen_share_stopped', {
        'username': username,
        'room_id': room_id
    }, room=room_id, include_self=False)

@socketio.on('screen_share_offer')
def on_screen_share_offer(data):
    if 'username' not in session:
        return
    
    room_id = data['room_id']
    offer = data['offer']
    
    # Forward the WebRTC offer to other users in the room
    emit('screen_share_offer_received', {
        'offer': offer,
        'from_user': session['username']
    }, room=room_id, include_self=False)

@socketio.on('screen_share_answer')
def on_screen_share_answer(data):
    if 'username' not in session:
        return
    
    room_id = data['room_id']
    answer = data['answer']
    target_user = data['target_user']
    
    # Forward the WebRTC answer to the specific user
    if target_user in users and users[target_user]['socket_id']:
        emit('screen_share_answer_received', {
            'answer': answer,
            'from_user': session['username']
        }, room=users[target_user]['socket_id'])

@socketio.on('screen_share_ice_candidate')
def on_screen_share_ice_candidate(data):
    if 'username' not in session:
        return
    
    room_id = data['room_id']
    candidate = data['candidate']
    
    # Forward ICE candidate to other users in the room
    emit('screen_share_ice_candidate_received', {
        'candidate': candidate,
        'from_user': session['username']
    }, room=room_id, include_self=False)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
