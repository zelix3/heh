from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
socketio = SocketIO(app, cors_allowed_origins="*")

# Storage
users = {}  # {username: {password_hash, is_online, socket_id}}
threads = []  # List of threads: {'id': str, 'title': str, 'description': str, 'created_by': str, 'message_count': int}
thread_messages = {}  # {thread_id: [messages]} message = {'id': str, 'username': str, 'message': str, 'timestamp': str, 'reactions': {}}
private_messages = {}
active_rooms = {}

@app.route('/')
def index():
    if 'username' in session:
        return render_template('chat.html', username=session['username'])
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    password = request.form['password']
    if username in users:
        return render_template('login.html', error='Username exists')
    users[username] = {'password_hash': generate_password_hash(password), 'is_online': False, 'socket_id': None}
    return render_template('login.html', success='Registered! Login now.')

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
    if 'username' not in session: return jsonify({'error': 'Unauthorized'})
    online = [u for u, d in users.items() if d['is_online'] and u != session['username']]
    return jsonify({'users': online})

@app.route('/threads')
def get_threads():
    if 'username' not in session: return jsonify({'error': 'Unauthorized'})
    return jsonify({'threads': threads})

def get_or_create_thread_messages(thread_id):
    if thread_id not in thread_messages:
        thread_messages[thread_id] = []
    return thread_messages[thread_id]

@socketio.on('connect')
def on_connect():
    if 'username' not in session: return False
    username = session['username']
    users[username]['socket_id'] = request.sid
    users[username]['is_online'] = True
    online_users = [u for u, d in users.items() if d['is_online']]
    emit('user_list_updated', {'users': online_users}, broadcast=True)
    emit('threads_updated', {'threads': threads}, broadcast=True)
    print(f"{username} connected")

@socketio.on('disconnect')
def on_disconnect():
    if 'username' in session:
        username = session['username']
        if username in users:
            users[username]['is_online'] = False
            users[username]['socket_id'] = None
        online_users = [u for u, d in users.items() if d['is_online']]
        emit('user_list_updated', {'users': online_users}, broadcast=True)
        print(f"{username} disconnected")

@socketio.on('create_thread')
def on_create_thread(data):
    if 'username' not in session: return
    username = session['username']
    thread_id = str(uuid.uuid4())
    new_thread = {
        'id': thread_id,
        'title': data['title'],
        'description': data.get('description', ''),
        'created_by': username,
        'message_count': 0
    }
    threads.append(new_thread)
    thread_messages[thread_id] = []
    emit('threads_updated', {'threads': threads}, broadcast=True)
    emit('thread_messages', {'thread_id': thread_id, 'messages': []}, room=request.sid)

@socketio.on('join_thread')
def on_join_thread(data):
    if 'username' not in session: return
    thread_id = data['thread_id']
    join_room(f'thread_{thread_id}')
    messages = get_or_create_thread_messages(thread_id)
    # Update message count
    if thread_id in [t['id'] for t in threads]:
        for t in threads:
            if t['id'] == thread_id:
                t['message_count'] = len(messages)
                break
    emit('threads_updated', {'threads': threads}, broadcast=True)
    emit('thread_messages', {'thread_id': thread_id, 'messages': messages})

@socketio.on('public_message')
def on_public_message(data):
    if 'username' not in session: return
    username = session['username']
    thread_id = data['thread_id']
    message = data['message']
    msg_id = str(uuid.uuid4())
    msg_data = {
        'id': msg_id,
        'username': username,
        'message': message,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'reactions': {}
    }
    get_or_create_thread_messages(thread_id).append(msg_data)
    emit('public_message_received', msg_data, room=f'thread_{thread_id}')
    # Update count
    for t in threads:
        if t['id'] == thread_id:
            t['message_count'] += 1
            break
    emit('threads_updated', {'threads': threads}, broadcast=True)

@socketio.on('react_message')
def on_react_message(data):
    if 'username' not in session: return
    thread_id = data['thread_id']
    msg_id = data['message_id']
    emoji = data['emoji']
    messages = get_or_create_thread_messages(thread_id)
    for msg in messages:
        if msg['id'] == msg_id:
            if emoji not in msg['reactions']:
                msg['reactions'][emoji] = []
            if session['username'] not in msg['reactions'][emoji]:
                msg['reactions'][emoji].append(session['username'])
            break
    emit('public_message_received', messages[-1] if messages else {}, room=f'thread_{thread_id}')  # Refresh last msg or handle better

# Private chat and screen sharing (mostly unchanged from original)
def get_private_room_id(user1, user2):
    return f"private_{min(user1, user2)}_{max(user1, user2)}"

@socketio.on('start_private_chat')
def on_start_private_chat(data):
    if 'username' not in session: return
    current_user = session['username']
    target_user = data['target_user']
    if target_user not in users or not users[target_user]['is_online']: 
        emit('error', {'message': 'User offline'})
        return
    room_id = get_private_room_id(current_user, target_user)
    join_room(room_id)
    target_sid = users[target_user]['socket_id']
    if target_sid:
        socketio.emit('private_chat_invitation', {'from_user': current_user, 'room_id': room_id}, room=target_sid)
    if room_id not in private_messages: private_messages[room_id] = []
    emit('private_chat_started', {'room_id': room_id, 'target_user': target_user, 'messages': private_messages[room_id]})

@socketio.on('join_private_chat')
def on_join_private_chat(data):
    if 'username' not in session: return
    username = session['username']
    room_id = data['room_id']
    join_room(room_id)
    emit('private_chat_messages', {'room_id': room_id, 'messages': private_messages.get(room_id, [])})

@socketio.on('private_message')
def on_private_message(data):
    if 'username' not in session: return
    username = session['username']
    room_id = data['room_id']
    message = data['message']
    if room_id not in private_messages: private_messages[room_id] = []
    msg_data = {'username': username, 'message': message, 'timestamp': datetime.now().strftime('%H:%M:%S')}
    private_messages[room_id].append(msg_data)
    emit('private_message_received', msg_data, room=room_id)

# Screen sharing events (unchanged)
@socketio.on('start_screen_share')
def on_start_screen_share(data):
    if 'username' not in session: return
    username = session['username']
    room_id = data['room_id']
    emit('screen_share_started', {'username': username, 'room_id': room_id}, room=room_id, include_self=False)

@socketio.on('stop_screen_share')
def on_stop_screen_share(data):
    if 'username' not in session: return
    username = session['username']
    room_id = data['room_id']
    emit('screen_share_stopped', {'username': username, 'room_id': room_id}, room=room_id, include_self=False)

@socketio.on('screen_share_offer')
def on_screen_share_offer(data):
    if 'username' not in session: return
    room_id = data['room_id']
    offer = data['offer']
    emit('screen_share_offer_received', {'offer': offer, 'from_user': session['username']}, room=room_id, include_self=False)

@socketio.on('screen_share_answer')
def on_screen_share_answer(data):
    if 'username' not in session: return
    room_id = data['room_id']
    answer = data['answer']
    target_user = data['target_user']
    if target_user in users and users[target_user]['socket_id']:
        emit('screen_share_answer_received', {'answer': answer}, room=users[target_user]['socket_id'])

@socketio.on('screen_share_ice_candidate')
def on_screen_share_ice_candidate(data):
    if 'username' not in session: return
    room_id = data['room_id']
    candidate = data['candidate']
    emit('screen_share_ice_candidate_received', {'candidate': candidate, 'from_user': session['username']}, room=room_id, include_self=False)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
