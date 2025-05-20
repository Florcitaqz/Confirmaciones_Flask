from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
from tinydb import TinyDB, Query
import uuid
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configurar la base de datos
db_path = os.path.join(os.path.dirname(__file__), 'db.json')
db = TinyDB(db_path)
invitations_table = db.table('invitations')
events_table = db.table('events')

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

@app.route('/confirm/<token>')
def confirm_page(token):
    """Página de confirmación de asistencia"""
    # Buscar la invitación por token
    Invitation = Query()
    invitation = invitations_table.get(Invitation.token == token)
    
    if not invitation:
        return render_template('error.html', message="Invitación no encontrada")
    
    return render_template('confirm.html', 
                          invitation=invitation, 
                          event_name=invitation['event_name'],
                          event_date=invitation['event_date'],
                          event_time=invitation['event_time'],
                          participant_name=invitation['participant_name'])

@app.route('/confirm/<token>/response', methods=['POST'])
def confirm_response(token):
    """Procesar respuesta de confirmación"""
    response = request.form.get('response')
    
    if response not in ['confirmed', 'declined']:
        return render_template('error.html', message="Respuesta inválida")
    
    # Actualizar estado de la invitación
    Invitation = Query()
    invitation = invitations_table.get(Invitation.token == token)
    
    if not invitation:
        return render_template('error.html', message="Invitación no encontrada")
    
    # Actualizar la invitación
    invitations_table.update({'status': response, 'response_time': datetime.now().isoformat()}, 
                            Invitation.token == token)
    
    # Actualizar el evento
    Event = Query()
    event = events_table.get(Event.event_id == invitation['event_id'])
    
    if event:
        participants = event.get('participants', {})
        participants[invitation['participant_id']] = response
        events_table.update({'participants': participants}, Event.event_id == invitation['event_id'])
    else:
        # Crear el evento si no existe
        events_table.insert({
            'event_id': invitation['event_id'],
            'event_name': invitation['event_name'],
            'event_date': invitation['event_date'],
            'event_time': invitation['event_time'],
            'participants': {invitation['participant_id']: response}
        })
    
    return render_template('thank_you.html', 
                          response=response, 
                          event_name=invitation['event_name'])

# API Endpoints

@app.route('/api/create_invitation', methods=['POST'])
def create_invitation():
    """Crear una nueva invitación"""
    data = request.json
    
    # Validar datos requeridos
    required_fields = ['event_id', 'event_name', 'event_date', 'event_time', 
                      'participant_id', 'participant_name', 'participant_phone']
    
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Campo requerido: {field}'}), 400
    
    # Generar token único
    token = str(uuid.uuid4())
    
    # Crear invitación
    invitation = {
        'token': token,
        'event_id': data['event_id'],
        'event_name': data['event_name'],
        'event_date': data['event_date'],
        'event_time': data['event_time'],
        'participant_id': data['participant_id'],
        'participant_name': data['participant_name'],
        'participant_phone': data['participant_phone'],
        'status': 'pending',
        'created_at': datetime.now().isoformat()
    }
    
    # Guardar en la base de datos
    invitations_table.insert(invitation)
    
    return jsonify({'token': token})

@app.route('/api/check_status/<token>', methods=['GET'])
def check_status(token):
    """Verificar estado de una invitación"""
    Invitation = Query()
    invitation = invitations_table.get(Invitation.token == token)
    
    if not invitation:
        return jsonify({'error': 'Invitación no encontrada'}), 404
    
    return jsonify({'status': invitation['status']})

@app.route('/api/check_event_invitations/<event_id>', methods=['GET'])
def check_event_invitations(event_id):
    """Verificar todas las invitaciones de un evento"""
    Invitation = Query()
    invitations = invitations_table.search(Invitation.event_id == event_id)
    
    if not invitations:
        return jsonify({'participants': {}})
    
    # Crear mapa de participante_id -> estado
    participants = {}
    for invitation in invitations:
        participants[invitation['participant_id']] = invitation['status']
    
    return jsonify({'participants': participants})

if __name__ == '__main__':
    app.run(debug=True)
