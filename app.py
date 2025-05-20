from flask import Flask, request, render_template, jsonify
from tinydb import TinyDB, Query
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Permitir conexiones desde otras apps (Android)

db = TinyDB("confirmaciones.json")

@app.route("/")
def home():
    return "Servidor Flask de confirmaciones activo 🚀"

@app.route("/confirmar")
def confirmar():
    evento_id = request.args.get("id")
    contacto = request.args.get("contacto")
    if not evento_id or not contacto:
        return "Faltan parámetros", 400
    return render_template("confirmar.html", evento_id=evento_id, contacto=contacto)

@app.route("/respuesta", methods=["POST"])
def respuesta():
    data = request.form
    evento_id = data.get("evento_id")
    contacto = data.get("contacto")
    respuesta = data.get("respuesta")
    if not evento_id or not contacto or not respuesta:
        return "Faltan datos en el formulario", 400

    # Guarda o actualiza la respuesta
    query = Query()
    existentes = db.search((query.evento_id == evento_id) & (query.contacto == contacto))
    if existentes:
        db.update({"asiste": respuesta}, (query.evento_id == evento_id) & (query.contacto == contacto))
    else:
        db.insert({"evento_id": evento_id, "contacto": contacto, "asiste": respuesta})

    return "¡Gracias por confirmar! 🎉"

@app.route("/confirmaciones")
def confirmaciones():
    evento_id = request.args.get("idEvento")
    if not evento_id:
        return jsonify({"error": "Falta idEvento"}), 400
    query = Query()
    resultados = db.search(query.evento_id == evento_id)
    return jsonify(resultados)

if __name__ == "__main__":
    app.run(debug=True)
