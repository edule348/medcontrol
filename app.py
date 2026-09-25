from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, senha TEXT NOT NULL, is_admin BOOLEAN NOT NULL, status TEXT DEFAULT "ativo")')
    conn.execute('CREATE TABLE IF NOT EXISTS clinicas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, telefone TEXT, endereco TEXT, modalidade TEXT DEFAULT "Particular")')
    conn.execute('CREATE TABLE IF NOT EXISTS medicos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, especialidade TEXT NOT NULL, telefone TEXT, tipo_atendimento TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS medico_locais (id INTEGER PRIMARY KEY AUTOINCREMENT, medico_id INTEGER, clinica_id INTEGER, dias TEXT, horario_inicio TEXT, horario_fim TEXT, duracao_minutos TEXT)')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS pacientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nome TEXT NOT NULL, 
        cpf TEXT, 
        telefones TEXT NOT NULL, 
        email TEXT, 
        rua TEXT, 
        numero TEXT, 
        bairro TEXT, 
        cidade TEXT, 
        estado TEXT, 
        cep TEXT, 
        endereco TEXT
    )''')
    
    conn.execute('CREATE TABLE IF NOT EXISTS consultas (id INTEGER PRIMARY KEY AUTOINCREMENT, paciente_id INTEGER, medico_id INTEGER, clinica_id INTEGER, data_hora TEXT, valor TEXT, forma_pagamento TEXT, comprovante TEXT, status TEXT DEFAULT "Agendado")')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS crm_agendamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        documento TEXT,
        nome_cliente TEXT,
        telefones TEXT,
        email TEXT,
        endereco TEXT,
        especialidade TEXT,
        medico TEXT,
        clinica_hospital TEXT,
        data_consulta TEXT,
        data_lembrete TEXT,
        horario TEXT,
        status_etapa TEXT DEFAULT 'Agendamentos',
        valor_consulta TEXT,
        tipo_pagamento TEXT,
        status_pagamento TEXT DEFAULT 'Pendente'
    )''')
    
    for col_def in [('clinicas', 'modalidade TEXT DEFAULT "Particular"'), 
                    ('pacientes', 'cpf TEXT'), 
                    ('consultas', 'status TEXT DEFAULT "Agendado"'),
                    ('crm_agendamentos', 'status_etapa TEXT DEFAULT "Agendamentos"')]:
        try:
            conn.execute(f'ALTER TABLE {col_def[0]} ADD COLUMN {col_def[1]}')
        except sqlite3.OperationalError:
            pass

    admin = conn.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',)).fetchone()
    if not admin:
        senha_hash = generate_password_hash('admin123')
        conn.execute('INSERT INTO usuarios (username, senha, is_admin, status) VALUES (?, ?, 1, ?)', ('admin', senha_hash, 'ativo'))
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Acesso restrito ao Administrador!', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        senha = request.form['senha']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM usuarios WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['senha'], senha):
            if user['status'] == 'bloqueado':
                flash('Sua conta está bloqueada.', 'danger')
                return redirect(url_for('login'))
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            return redirect(url_for('index'))
        flash('Usuário ou senha inválidos.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    pacientes = conn.execute('SELECT * FROM pacientes').fetchall()
    medicos = conn.execute('SELECT * FROM medicos').fetchall()
    clinicas = conn.execute('SELECT * FROM clinicas').fetchall()
    
    hoje_str = datetime.now().strftime('%d/%m/%Y')
    todas_consultas = conn.execute('SELECT c.*, p.nome as paciente_nome, m.nome as medico_nome FROM consultas c JOIN pacientes p ON c.paciente_id = p.id JOIN medicos m ON c.medico_id = m.id WHERE c.status != "Cancelado"').fetchall()
    consultas = [c for c in todas_consultas if hoje_str in c['data_hora']]
    
    conn.close()
    return render_template('index.html', pacientes=pacientes, medicos=medicos, clinicas=clinicas, consultas=consultas)

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/proximo_horario/<int:medico_id>')
@login_required
def api_proximo_horario(medico_id):
    conn = get_db_connection()
    locais = conn.execute('SELECT * FROM medico_locais WHERE medico_id = ?', (medico_id,)).fetchall()
    conn.close()
    
    if not locais:
        return jsonify({'horario': 'Nenhum local/horário cadastrado'})
    
    dias_map = {'Monday': 'Segunda', 'Tuesday': 'Terça', 'Wednesday': 'Quarta', 'Thursday': 'Quinta', 'Friday': 'Sexta', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
    agora = datetime.now()
    for i in range(1, 11):
        dia_futuro = agora + timedelta(days=i)
        dia_nome = dias_map.get(dia_futuro.strftime('%A'))
        for local in locais:
            dias_atendimento = [d.strip() for d in local['dias'].split(',')] if local['dias'] else []
            if dia_nome in dias_atendimento:
                horario_ini = local['horario_inicio'] or '09:00'
                duracao = local['duracao_minutos'] or '30'
                return jsonify({'horario': f"{dia_futuro.strftime('%d/%m/%Y')} às {horario_ini} (Cons. {duracao} min)"})
                
    return jsonify({'horario': 'Nenhum horário vago nos próximos 10 dias'})

@app.route('/crm')
@login_required
def crm():
    conn = get_db_connection()
    busca = request.args.get('busca', '')
    
    if busca:
        pacientes_kanban = conn.execute('SELECT * FROM pacientes WHERE (nome LIKE ? OR cpf LIKE ? OR telefones LIKE ? OR email LIKE ?) AND id NOT IN (SELECT p.id FROM pacientes p JOIN crm_agendamentos c ON p.cpf = c.documento WHERE c.status_etapa != "Cancelados")', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
        agendamentos_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Agendamentos" AND (nome_cliente LIKE ? OR documento LIKE ? OR telefones LIKE ? OR email LIKE ? OR medico LIKE ?)', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
        retorno_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Retorno" AND (nome_cliente LIKE ? OR documento LIKE ? OR telefones LIKE ? OR email LIKE ? OR medico LIKE ?)', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
        reagendamento_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Reagendamento" AND (nome_cliente LIKE ? OR documento LIKE ? OR telefones LIKE ? OR email LIKE ? OR medico LIKE ?)', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
        cancelados_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Cancelados" AND (nome_cliente LIKE ? OR documento LIKE ? OR telefones LIKE ? OR email LIKE ? OR medico LIKE ?)', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
    else:
        pacientes_kanban = conn.execute('SELECT * FROM pacientes WHERE id NOT IN (SELECT p.id FROM pacientes p JOIN crm_agendamentos c ON p.cpf = c.documento WHERE c.status_etapa != "Cancelados")').fetchall()
        agendamentos_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Agendamentos"').fetchall()
        retorno_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Retorno"').fetchall()
        reagendamento_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Reagendamento"').fetchall()
        cancelados_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Cancelados"').fetchall()
        
    conn.close()
    return render_template('crm.html', 
                           pacientes=pacientes_kanban, 
                           agendamentos=agendamentos_kanban, 
                           retorno=retorno_kanban, 
                           reagendamento=reagendamento_kanban, 
                           cancelados=cancelados_kanban, 
                           busca=busca)

@app.route('/crm/mover/<int:id>/<etapa>')
@login_required
def crm_mover(id, etapa):
    etapas_validas = ['Agendamentos', 'Retorno', 'Reagendamento', 'Cancelados']
    if etapa in etapas_validas:
        conn = get_db_connection()
        conn.execute('UPDATE crm_agendamentos SET status_etapa = ? WHERE id = ?', (etapa, id))
        if etapa == 'Cancelados':
            registro = conn.execute('SELECT * FROM crm_agendamentos WHERE id = ?', (id,)).fetchone()
            if registro:
                conn.execute('UPDATE consultas SET status = "Cancelado" WHERE data_hora LIKE ?', 
                             (f"%{registro['data_consulta']}%",))
        conn.commit()
        conn.close()
        flash(f'Cartão movido para {etapa} com sucesso!', 'success')
    return redirect(url_for('crm'))

@app.route('/crm/retorno/<int:crm_id>')
@login_required
def crm_retorno_form(crm_id):
    conn = get_db_connection()
    crm_item = conn.execute('SELECT * FROM crm_agendamentos WHERE id = ?', (crm_id,)).fetchone()
    if not crm_item:
        conn.close()
        flash('Registro não encontrado.', 'danger')
        return redirect(url_for('crm'))
    
    medico = conn.execute('SELECT * FROM medicos WHERE nome = ?', (crm_item['medico'],)).fetchone()
    if not medico:
        medico = conn.execute('SELECT * FROM medicos LIMIT 1').fetchone()
    
    medico_locais = conn.execute('SELECT * FROM medico_locais WHERE medico_id = ?', (medico['id'],)).fetchall() if medico else []
    conn.close()
    return render_template('retorno.html', crm_item=crm_item, medico=medico, medico_locais=medico_locais)

@app.route('/crm/retorno/salvar/<int:crm_id>', methods=['POST'])
@login_required
def crm_retorno_salvar(crm_id):
    conn = get_db_connection()
    crm_item = conn.execute('SELECT * FROM crm_agendamentos WHERE id = ?', (crm_id,)).fetchone()
    if not crm_item:
        conn.close()
        flash('Registro não encontrado.', 'danger')
        return redirect(url_for('crm'))
    
    data_bruta = request.form.get('data_hora', '')
    try:
        data_obj = datetime.strptime(data_bruta, '%Y-%m-%dT%H:%M')
        data_formatada = data_obj.strftime('%d/%m/%Y %H:%M')
        data_crm = data_obj.strftime('%d/%m/%Y')
        horario_crm = data_obj.strftime('%H:%M')
    except:
        data_formatada = data_bruta
        data_crm = data_bruta
        horario_crm = ''

    valor = request.form.get('valor', 'R$ 0,00')
    forma_pagamento = request.form.get('forma_pagamento', 'Sem pagamento')

    conn.execute('UPDATE crm_agendamentos SET status_etapa = "Agendamentos", data_consulta = ?, horario = ?, valor_consulta = ?, tipo_pagamento = ? WHERE id = ?',
                 (data_crm, horario_crm, valor, forma_pagamento, crm_id))

    conn.commit()
    conn.close()
    flash('Consulta agendada com sucesso e movida para Agendamentos!', 'success')
    return redirect(url_for('crm'))

@app.route('/cliente/perfil/<int:id>')
@login_required
def cliente_perfil(id):
    conn = get_db_connection()
    # Tenta buscar pelo ID do CRM ou ID do paciente
    cliente = conn.execute('SELECT * FROM crm_agendamentos WHERE id = ?', (id,)).fetchone()
    if not cliente:
        paciente = conn.execute('SELECT * FROM pacientes WHERE id = ?', (id,)).fetchone()
        if paciente:
            cliente = {
                'id': paciente['id'],
                'nome_cliente': paciente['nome'],
                'telefones': paciente['telefones'],
                'email': paciente['email'],
                'documento': paciente['cpf'],
                'endereco': paciente['endereco'],
                'especialidade': 'Geral',
                'medico': 'Não atribuído',
                'clinica_hospital': 'Principal',
                'data_consulta': 'Pendente',
                'horario': '-',
                'status_etapa': 'Pacientes',
                'valor_consulta': 'R$ 0,00',
                'tipo_pagamento': '-'
            }
    
    # Buscar histórico completo de movimentações deste cliente pelo documento ou nome
    historico = []
    if cliente:
        doc = cliente['documento'] if 'documento' in cliente else None
        nome = cliente['nome_cliente'] if 'nome_cliente' in cliente else None
        if doc:
            historico = conn.execute('SELECT * FROM crm_agendamentos WHERE documento = ?', (doc,)).fetchall()
        elif nome:
            historico = conn.execute('SELECT * FROM crm_agendamentos WHERE nome_cliente = ?', (nome,)).fetchall()

    conn.close()
    return render_template('cliente_perfil.html', cliente=cliente, historico=historico)

@app.route('/pacientes', methods=['GET', 'POST'])
@login_required
def pacientes():
    if request.method == 'POST':
        nome = request.form['nome']
        cpf = request.form['cpf']
        telefones = ', '.join(request.form.getlist('telefones[]'))
        email = request.form['email']
        rua = request.form['rua']
        numero = request.form['numero']
        bairro = request.form['bairro']
        cidade = request.form['cidade']
        estado = request.form['estado']
        cep = request.form['cep']
        endereco = f"Rua: {rua}, Nº: {numero}, Bairro: {bairro}, Cidade: {cidade}-{estado}, CEP: {cep}"
        
        conn = get_db_connection()
        conn.execute('INSERT INTO pacientes (nome, cpf, telefones, email, rua, numero, bairro, cidade, estado, cep, endereco) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                     (nome, cpf, telefones, email, rua, numero, bairro, cidade, estado, cep, endereco))
        conn.commit()
        conn.close()
        flash('Paciente cadastrado com sucesso!', 'success')
        return redirect(url_for('pacientes'))
    return render_template('pacientes.html')

@app.route('/medicos', methods=['GET', 'POST'])
@login_required
def medicos():
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form['nome']
        especialidades_lista = request.form.getlist('especialidades[]')
        especialidade = ', '.join([e.strip() for e in especialidades_lista if e.strip()])
        telefone = request.form['telefone']
        tipo_atendimento = request.form['tipo_atendimento']
        
        cursor = conn.execute('INSERT INTO medicos (nome, especialidade, telefone, tipo_atendimento) VALUES (?, ?, ?, ?)', (nome, especialidade, telefone, tipo_atendimento))
        medico_id = cursor.lastrowid
        
        clinicas_ids = request.form.getlist('clinica_id[]')
        inicios = request.form.getlist('horario_inicio[]')
        fins = request.form.getlist('horario_fim[]')
        duracoes = request.form.getlist('duracao_minutos[]')
        
        for i in range(len(clinicas_ids)):
            if clinicas_ids[i]:
                dias_selecionados = request.form.getlist(f'dias_{i}[]')
                dias_str = ', '.join(dias_selecionados)
                duracao = duracoes[i] if i < len(duracoes) else ''
                conn.execute('INSERT INTO medico_locais (medico_id, clinica_id, dias, horario_inicio, horario_fim, duracao_minutos) VALUES (?, ?, ?, ?, ?, ?)',
                             (medico_id, clinicas_ids[i], dias_str, inicios[i], fins[i], duracao))
        
        conn.commit()
        flash('Médico e horários cadastrados com sucesso!', 'success')
        conn.close()
        return redirect(url_for('medicos'))
        
    clinicas = conn.execute('SELECT * FROM clinicas').fetchall()
    conn.close()
    return render_template('medicos.html', clinicas=clinicas)

@app.route('/clinicas', methods=['GET', 'POST'])
@login_required
def clinicas():
    if request.method == 'POST':
        nome = request.form['nome']
        telefone = request.form['telefone']
        endereco = request.form['endereco']
        modalidades_lista = request.form.getlist('modalidades[]')
        modalidade = ', '.join(modalidades_lista)
        
        conn = get_db_connection()
        conn.execute('INSERT INTO clinicas (nome, telefone, endereco, modalidade) VALUES (?, ?, ?, ?)', (nome, telefone, endereco, modalidade))
        conn.commit()
        conn.close()
        flash('Clínica/Hospital cadastrado com sucesso!', 'success')
        return redirect(url_for('clinicas'))
    return render_template('clinicas.html')

@app.route('/cadastros/pacientes')
@login_required
def cadastros_pacientes():
    conn = get_db_connection()
    busca = request.args.get('busca', '')
    if busca:
        pacientes = conn.execute('SELECT * FROM pacientes WHERE nome LIKE ? OR cpf LIKE ? OR telefones LIKE ?', (f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
    else:
        pacientes = conn.execute('SELECT * FROM pacientes').fetchall()
    conn.close()
    return render_template('cadastros_pacientes.html', pacientes=pacientes, busca=busca)

@app.route('/cadastros/medicos')
@login_required
def cadastros_medicos():
    conn = get_db_connection()
    busca = request.args.get('busca', '')
    if busca:
        medicos = conn.execute('SELECT * FROM medicos WHERE nome LIKE ? OR especialidade LIKE ?', (f'%{busca}%', f'%{busca}%')).fetchall()
    else:
        medicos = conn.execute('SELECT * FROM medicos').fetchall()
    conn.close()
    return render_template('cadastros_medicos.html', medicos=medicos, busca=busca)

@app.route('/cadastros/clinicas')
@login_required
def cadastros_clinicas():
    conn = get_db_connection()
    busca = request.args.get('busca', '')
    if busca:
        clinicas = conn.execute('SELECT * FROM clinicas WHERE nome LIKE ? OR modalidade LIKE ? OR endereco LIKE ?', (f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
    else:
        clinicas = conn.execute('SELECT * FROM clinicas').fetchall()
    conn.close()
    return render_template('cadastros_clinicas.html', clinicas=clinicas, busca=busca)

@app.route('/cadastros')
@login_required
def ver_cadastros():
    return render_template('cadastros_geral.html')

@app.route('/agendar', methods=['POST'])
@login_required
def agendar():
    conn = get_db_connection()
    data_bruta = request.form['data_hora']
    try:
        data_obj = datetime.strptime(data_bruta, '%Y-%m-%dT%H:%M')
        data_formatada = data_obj.strftime('%d/%m/%Y %H:%M')
        data_crm = data_obj.strftime('%d/%m/%Y')
        horario_crm = data_obj.strftime('%H:%M')
    except:
        data_formatada = data_bruta
        data_crm = ''
        horario_crm = ''

    paciente_id = request.form['paciente_id']
    medico_id = request.form['medico_id']
    
    paciente = conn.execute('SELECT * FROM pacientes WHERE id = ?', (paciente_id,)).fetchone()
    medico = conn.execute('SELECT * FROM medicos WHERE id = ?', (medico_id,)).fetchone()
    
    comprovante_nome = ''
    if 'comprovante' in request.files:
        file = request.files['comprovante']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            comprovante_nome = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], comprovante_nome))

    conn.execute('INSERT INTO consultas (paciente_id, medico_id, data_hora, valor, forma_pagamento, comprovante, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                 (paciente_id, medico_id, data_formatada, request.form.get('valor'), request.form.get('forma_pagamento'), comprovante_nome, 'Agendado'))
    
    if paciente and medico:
        conn.execute('''INSERT INTO crm_agendamentos 
            (documento, nome_cliente, telefones, email, endereco, especialidade, medico, clinica_hospital, data_consulta, data_lembrete, horario, status_etapa, valor_consulta, tipo_pagamento, status_pagamento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (paciente['cpf'], paciente['nome'], paciente['telefones'], paciente['email'], paciente['endereco'], 
             medico['especialidade'], medico['nome'], 'Principal', data_crm, data_crm, horario_crm, 'Agendamentos', 
             request.form.get('valor', 'R$ 0,00'), request.form.get('forma_pagamento', 'Dinheiro'), 'Pendente'))

    conn.commit()
    conn.close()
    flash('Consulta agendada com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/admin/usuarios', methods=['GET', 'POST'])
@admin_required
def admin_usuarios():
    conn = get_db_connection()
    if request.method == 'POST':
        username = request.form['username']
        senha = generate_password_hash(request.form['senha'])
        is_admin = 1 if 'is_admin' in request.form else 0
        conn.execute('INSERT INTO usuarios (username, senha, is_admin) VALUES (?, ?, ?)', (username, senha, is_admin))
        conn.commit()
        flash('Usuário criado com sucesso!', 'success')
        return redirect(url_for('admin_usuarios'))
    usuarios = conn.execute('SELECT * FROM usuarios').fetchall()
    conn.close()
    return render_template('admin_usuarios.html', usuarios=usuarios)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
