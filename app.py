from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
from tinydb import TinyDB, Query
import uuid
import os
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
    try:
        logger.debug(f"Accediendo a confirmación con token: {token}")
        
        # Buscar la invitación por token
        Invitation = Query()
        invitation = invitations_table.get(Invitation.token == token)
        
        if not invitation:
            logger.warning(f"Invitación no encontrada para token: {token}")
            return render_template('error.html', message="Invitación no encontrada. El token puede ser inválido o haber expirado.")
        
        logger.debug(f"Invitación encontrada: {invitation}")
        
        # Asegurarse de que todos los campos necesarios estén presentes
        event_name = invitation.get('event_name', 'Evento')
        event_date = invitation.get('event_date', 'Fecha no especificada')
        event_time = invitation.get('event_time', 'Hora no especificada')
        participant_name = invitation.get('participant_name', 'Invitado')
        
        return render_template('confirm.html', 
                              invitation=invitation, 
                              event_name=event_name,
                              event_date=event_date,
                              event_time=event_time,
                              participant_name=participant_name,
                              token=token)  # Asegurarse de pasar el token
    except Exception as e:
        logger.error(f"Error en confirm_page: {str(e)}", exc_info=True)
        return render_template('error.html', message=f"Error del servidor: {str(e)}")

@app.route('/confirm/<token>/response', methods=['POST'])
def confirm_response(token):
    """Procesar respuesta de confirmación"""
    try:
        logger.debug(f"Procesando respuesta para token: {token}")
        
        response = request.form.get('response')
        logger.debug(f"Respuesta recibida: {response}")
        
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
                              event_name=invitation.get('event_name', 'Evento'))
    except Exception as e:
        logger.error(f"Error en confirm_response: {str(e)}", exc_info=True)
        return render_template('error.html', message=f"Error del servidor: {str(e)}")

# API Endpoints

@app.route('/api/create_invitation', methods=['POST'])
def create_invitation():
    """Crear una nueva invitación"""
    try:
        logger.debug("Recibida solicitud para crear invitación")
        data = request.json
        logger.debug(f"Datos recibidos: {data}")
        
        # Validar datos requeridos
        required_fields = ['event_id', 'event_name', 'event_date', 'event_time', 
                          'participant_id', 'participant_name', 'participant_phone']
        
        for field in required_fields:
            if field not in data:
                logger.warning(f"Campo requerido faltante: {field}")
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
        logger.debug(f"Invitación creada con token: {token}")
        
        return jsonify({'token': token})
    except Exception as e:
        logger.error(f"Error en create_invitation: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/check_status/<token>', methods=['GET'])
def check_status(token):
    """Verificar estado de una invitación"""
    try:
        logger.debug(f"Verificando estado para token: {token}")
        
        Invitation = Query()
        invitation = invitations_table.get(Invitation.token == token)
        
        if not invitation:
            logger.warning(f"Invitación no encontrada para token: {token}")
            return jsonify({'error': 'Invitación no encontrada'}), 404
        
        logger.debug(f"Estado de invitación: {invitation['status']}")
        return jsonify({'status': invitation['status']})
    except Exception as e:
        logger.error(f"Error en check_status: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/check_event_invitations/<event_id>', methods=['GET'])
def check_event_invitations(event_id):
    """Verificar todas las invitaciones de un evento"""
    try:
        logger.debug(f"Verificando invitaciones para evento: {event_id}")
        
        Invitation = Query()
        invitations = invitations_table.search(Invitation.event_id == event_id)
        
        if not invitations:
            logger.debug(f"No se encontraron invitaciones para el evento: {event_id}")
            return jsonify({'participants': {}})
        
        # Crear mapa de participante_id -> estado
        participants = {}
        for invitation in invitations:
            participants[invitation['participant_id']] = invitation['status']
        
        logger.debug(f"Estados de participantes: {participants}")
        return jsonify({'participants': participants})
    except Exception as e:
        logger.error(f"Error en check_event_invitations: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Endpoint de depuración
@app.route('/debug/invitations')
def debug_invitations():
    """Ver todas las invitaciones (solo para depuración)"""
    try:
        invitations = invitations_table.all()
        return jsonify(invitations)
    except Exception as e:
        logger.error(f"Error en debug_invitations: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/debug/db_info')
def debug_db_info():
    """Ver información de la base de datos (solo para depuración)"""
    try:
        db_info = {
            'db_path': db_path,
            'db_exists': os.path.exists(db_path),
            'db_size': os.path.getsize(db_path) if os.path.exists(db_path) else 0,
            'invitation_count': len(invitations_table.all()),
            'event_count': len(events_table.all())
        }
        return jsonify(db_info)
    except Exception as e:
        logger.error(f"Error en debug_db_info: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/debug/test')
def debug_test():
    """Página de prueba para verificar que el servidor está funcionando"""
    return "El servidor está funcionando correctamente"

@app.route('/debug/templates')
def debug_templates():
    """Listar todas las plantillas disponibles"""
    try:
        template_dir = os.path.join(app.root_path, 'templates')
        templates = os.listdir(template_dir)
        return jsonify({
            'template_dir': template_dir,
            'templates': templates,
            'exists': os.path.exists(template_dir)
        })
    except Exception as e:
        logger.error(f"Error en debug_templates: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
