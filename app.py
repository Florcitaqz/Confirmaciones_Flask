from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
from tinydb import TinyDB, Query
import uuid
import os
import logging
from datetime import datetime, timedelta
import threading
import time
import schedule

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
reminders_table = db.table('reminders')

# Variable global para controlar el hilo de recordatorios
reminder_thread = None
stop_reminder_thread = False

def send_reminder(invitation_token):
    """
    Envía un recordatorio para una invitación específica.
    Esta función simula el envío de un recordatorio.
    En una implementación real, aquí se enviaría un mensaje de WhatsApp.
    """
    try:
        Invitation = Query()
        invitation = invitations_table.get(Invitation.token == invitation_token)
        
        if not invitation:
            logger.warning(f"No se encontró la invitación para el token: {invitation_token}")
            return False
        
        if invitation['status'] != 'pending':
            logger.info(f"No se envía recordatorio para {invitation_token} porque el estado es {invitation['status']}")
            return False
        
        # Registrar el recordatorio
        reminder = {
            'invitation_token': invitation_token,
            'event_id': invitation['event_id'],
            'participant_id': invitation['participant_id'],
            'sent_at': datetime.now().isoformat()
        }
        reminders_table.insert(reminder)
        
        logger.info(f"Recordatorio enviado para la invitación {invitation_token}")
        return True
    except Exception as e:
        logger.error(f"Error al enviar recordatorio: {str(e)}", exc_info=True)
        return False

def check_pending_invitations():
    """
    Verifica las invitaciones pendientes y envía recordatorios si es necesario.
    """
    try:
        logger.info("Verificando invitaciones pendientes para enviar recordatorios...")
        
        # Obtener todas las invitaciones pendientes
        Invitation = Query()
        pending_invitations = invitations_table.search(Invitation.status == 'pending')
        
        if not pending_invitations:
            logger.info("No hay invitaciones pendientes para enviar recordatorios")
            return
        
        # Obtener la fecha actual
        now = datetime.now()
        
        # Verificar cada invitación pendiente
        for invitation in pending_invitations:
            try:
                # Verificar si el evento ya pasó
                event_date_str = invitation.get('event_date', '')
                if not event_date_str:
                    continue
                
                # Convertir la fecha del evento a objeto datetime
                # Formato esperado: YYYY-MM-DD
                event_date = datetime.strptime(event_date_str, "%Y-%m-%d")
                
                # Si el evento ya pasó, no enviar recordatorio
                if event_date.date() < now.date():
                    logger.info(f"No se envía recordatorio para evento pasado: {invitation['event_id']}")
                    continue
                
                # Verificar si ya se envió un recordatorio hoy
                Reminder = Query()
                today_start = datetime(now.year, now.month, now.day, 0, 0, 0).isoformat()
                today_reminders = reminders_table.search(
                    (Reminder.invitation_token == invitation['token']) & 
                    (Reminder.sent_at >= today_start)
                )
                
                if today_reminders:
                    logger.info(f"Ya se envió un recordatorio hoy para {invitation['token']}")
                    continue
                
                # Verificar si el evento es pronto (en los próximos 3 días)
                days_until_event = (event_date.date() - now.date()).days
                
                if days_until_event <= 3:
                    # Enviar recordatorio
                    send_reminder(invitation['token'])
                    logger.info(f"Recordatorio enviado para evento en {days_until_event} días: {invitation['event_id']}")
                
            except Exception as e:
                logger.error(f"Error al procesar invitación para recordatorio: {str(e)}", exc_info=True)
                continue
        
    except Exception as e:
        logger.error(f"Error al verificar invitaciones pendientes: {str(e)}", exc_info=True)

def reminder_scheduler():
    """
    Función que se ejecuta en un hilo separado para programar y enviar recordatorios.
    """
    global stop_reminder_thread
    
    logger.info("Iniciando programador de recordatorios...")
    
    # Programar la verificación de invitaciones pendientes todos los días a las 10:00 AM
    schedule.every().day.at("10:00").do(check_pending_invitations)
    
    # También programar una verificación cada hora para eventos que están muy próximos
    schedule.every(1).hours.do(check_pending_invitations)
    
    while not stop_reminder_thread:
        schedule.run_pending()
        time.sleep(60)  # Dormir por 60 segundos
    
    logger.info("Deteniendo programador de recordatorios...")

def start_reminder_thread():
    """
    Inicia el hilo para el programador de recordatorios.
    """
    global reminder_thread, stop_reminder_thread
    
    if reminder_thread is None or not reminder_thread.is_alive():
        stop_reminder_thread = False
        reminder_thread = threading.Thread(target=reminder_scheduler)
        reminder_thread.daemon = True
        reminder_thread.start()
        logger.info("Hilo de recordatorios iniciado")
    else:
        logger.info("El hilo de recordatorios ya está en ejecución")

def stop_reminder_thread_func():
    """
    Detiene el hilo del programador de recordatorios.
    """
    global stop_reminder_thread
    stop_reminder_thread = True
    logger.info("Solicitud para detener el hilo de recordatorios")

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

# Endpoints para recordatorios

@app.route('/api/send_reminder/<token>', methods=['POST'])
def api_send_reminder(token):
    """Enviar un recordatorio manualmente para una invitación específica"""
    try:
        logger.debug(f"Solicitud para enviar recordatorio manual para token: {token}")
        
        # Verificar si la invitación existe
        Invitation = Query()
        invitation = invitations_table.get(Invitation.token == token)
        
        if not invitation:
            logger.warning(f"Invitación no encontrada para token: {token}")
            return jsonify({'error': 'Invitación no encontrada'}), 404
        
        # Verificar si la invitación ya fue respondida
        if invitation['status'] != 'pending':
            logger.warning(f"No se puede enviar recordatorio para invitación con estado: {invitation['status']}")
            return jsonify({'error': 'La invitación ya fue respondida'}), 400
        
        # Enviar recordatorio
        success = send_reminder(token)
        
        if success:
            return jsonify({'success': True, 'message': 'Recordatorio enviado correctamente'})
        else:
            return jsonify({'error': 'Error al enviar recordatorio'}), 500
    except Exception as e:
        logger.error(f"Error en api_send_reminder: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/send_event_reminders/<event_id>', methods=['POST'])
def api_send_event_reminders(event_id):
    """Enviar recordatorios a todos los participantes pendientes de un evento"""
    try:
        logger.debug(f"Solicitud para enviar recordatorios para evento: {event_id}")
        
        # Verificar si el evento existe
        Event = Query()
        event = events_table.get(Event.event_id == event_id)
        
        if not event:
            logger.warning(f"Evento no encontrado: {event_id}")
            return jsonify({'error': 'Evento no encontrado'}), 404
        
        # Obtener todas las invitaciones pendientes para este evento
        Invitation = Query()
        pending_invitations = invitations_table.search(
            (Invitation.event_id == event_id) & 
            (Invitation.status == 'pending')
        )
        
        if not pending_invitations:
            logger.info(f"No hay invitaciones pendientes para el evento: {event_id}")
            return jsonify({'message': 'No hay invitaciones pendientes para enviar recordatorios'})
        
        # Enviar recordatorios
        sent_count = 0
        for invitation in pending_invitations:
            if send_reminder(invitation['token']):
                sent_count += 1
        
        return jsonify({
            'success': True,
            'total_pending': len(pending_invitations),
            'reminders_sent': sent_count
        })
    except Exception as e:
        logger.error(f"Error en api_send_event_reminders: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_reminder_settings', methods=['GET'])
def get_reminder_settings():
    """Obtener la configuración actual de recordatorios"""
    try:
        # En una implementación real, esto vendría de una tabla de configuración
        settings = {
            'automatic_reminders_enabled': True,
            'days_before_event': 3,
            'reminder_hour': 10,
            'max_reminders_per_invitation': 3
        }
        
        return jsonify(settings)
    except Exception as e:
        logger.error(f"Error en get_reminder_settings: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_reminder_settings', methods=['POST'])
def update_reminder_settings():
    """Actualizar la configuración de recordatorios"""
    try:
        data = request.json
        logger.debug(f"Actualizando configuración de recordatorios: {data}")
        
        # En una implementación real, esto se guardaría en una tabla de configuración
        # Por ahora, simplemente devolvemos los datos recibidos
        
        return jsonify({
            'success': True,
            'settings': data
        })
    except Exception as e:
        logger.error(f"Error en update_reminder_settings: {str(e)}", exc_info=True)
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

@app.route('/debug/reminders')
def debug_reminders():
    """Ver todos los recordatorios enviados (solo para depuración)"""
    try:
        reminders = reminders_table.all()
        return jsonify(reminders)
    except Exception as e:
        logger.error(f"Error en debug_reminders: {str(e)}", exc_info=True)
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
            'event_count': len(events_table.all()),
            'reminder_count': len(reminders_table.all())
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

@app.route('/debug/start_reminder_thread')
def debug_start_reminder_thread():
    """Iniciar el hilo de recordatorios (solo para depuración)"""
    try:
        start_reminder_thread()
        return jsonify({'success': True, 'message': 'Hilo de recordatorios iniciado'})
    except Exception as e:
        logger.error(f"Error al iniciar hilo de recordatorios: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/debug/stop_reminder_thread')
def debug_stop_reminder_thread():
    """Detener el hilo de recordatorios (solo para depuración)"""
    try:
        stop_reminder_thread_func()
        return jsonify({'success': True, 'message': 'Solicitud para detener hilo de recordatorios enviada'})
    except Exception as e:
        logger.error(f"Error al detener hilo de recordatorios: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/debug/check_pending_now')
def debug_check_pending_now():
    """Ejecutar la verificación de invitaciones pendientes ahora (solo para depuración)"""
    try:
        check_pending_invitations()
        return jsonify({'success': True, 'message': 'Verificación de invitaciones pendientes ejecutada'})
    except Exception as e:
        logger.error(f"Error al verificar invitaciones pendientes: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Iniciar el hilo de recordatorios cuando se inicia la aplicación
@app.before_first_request
def before_first_request():
    """Se ejecuta antes de la primera solicitud"""
    start_reminder_thread()

if __name__ == '__main__':
    app.run(debug=True)
