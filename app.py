from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from functools import wraps
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'chave_secreta_super_segura_para_testes'
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
    # Apenas cria as tabelas se elas não existirem, preservando todos os dados gravados anteriormente
    conn.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_completo TEXT,
        cpf TEXT,
        telefone TEXT,
        email TEXT,
        rua TEXT,
        numero TEXT,
        complemento TEXT,
        bairro TEXT,
        cidade TEXT,
        cep TEXT,
        endereco TEXT,
        username TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        is_admin BOOLEAN NOT NULL,
        status TEXT DEFAULT 'ativo',
        primeiro_acesso BOOLEAN DEFAULT 1
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS clinicas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        telefone TEXT,
        email TEXT,
        rua TEXT,
        numero TEXT,
        complemento TEXT,
        bairro TEXT,
        cidade TEXT,
        cep TEXT,
        endereco TEXT,
        modalidade TEXT DEFAULT 'Particular'
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS medicos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        especialidade TEXT NOT NULL,
        telefone TEXT,
        tipo_atendimento TEXT NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS medico_locais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medico_id INTEGER,
        clinica_id INTEGER,
        dias TEXT,
        horario_inicio TEXT,
        horario_fim TEXT,
        duracao_minutos INTEGER DEFAULT 30
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS pacientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nome TEXT NOT NULL, 
        cpf TEXT, 
        telefones TEXT NOT NULL, 
        email TEXT, 
        rua TEXT,
        numero TEXT,
        complemento TEXT,
        bairro TEXT,
        cidade TEXT,
        cep TEXT,
        endereco TEXT
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS consultas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        paciente_id INTEGER, 
        medico_id INTEGER, 
        data_hora TEXT, 
        valor TEXT, 
        forma_pagamento TEXT, 
        comprovante TEXT, 
        status TEXT DEFAULT 'Agendado'
    )''')
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

    for col in ['nome_completo TEXT', 'cpf TEXT', 'telefone TEXT', 'email TEXT', 'rua TEXT', 'numero TEXT', 'complemento TEXT', 'bairro TEXT', 'cidade TEXT', 'cep TEXT', 'endereco TEXT']:
        try:
            conn.execute(f'ALTER TABLE usuarios ADD COLUMN {col}')
        except sqlite3.OperationalError:
            pass

    # Cria o admin padrão apenas se a tabela estiver totalmente vazia
    admin_existe = conn.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',)).fetchone()
    if not admin_existe:
        senha_hash = generate_password_hash('admin123')
        conn.execute('INSERT INTO usuarios (username, senha, is_admin, status, primeiro_acesso, nome_completo) VALUES (?, ?, 1, ?, 0, ?)', ('admin', senha_hash, 'ativo', 'Administrador Master'))
    
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM usuarios WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()

        if not user or user['status'] == 'bloqueado':
            session.clear()
            flash('Sua conta está bloqueada ou inativa.', 'danger')
            return redirect(url_for('login'))

        if user['primeiro_acesso'] and request.endpoint not in ['alterar_senha', 'logout']:
            return redirect(url_for('alterar_senha'))

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
            
            if user['primeiro_acesso']:
                return redirect(url_for('alterar_senha'))
            
            return redirect(url_for('index'))
        flash('Usuário ou senha inválidos.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/alterar-senha', methods=['GET', 'POST'])
@login_required
def alterar_senha():
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM usuarios WHERE id = ?', (session['user_id'],)).fetchone()
    
    if request.method == 'POST':
        nova_senha = request.form['nova_senha']
        confirma_senha = request.form['confirma_senha']
        
        if not nova_senha or nova_senha != confirma_senha:
            flash('As senhas não conferem ou estão vazias.', 'danger')
            conn.close()
            return render_template('alterar_senha.html', primeiro_acesso=user['primeiro_acesso'])
        
        senha_hash = generate_password_hash(nova_senha)
        conn.execute('UPDATE usuarios SET senha = ?, primeiro_acesso = 0 WHERE id = ?', (senha_hash, session['user_id']))
        conn.commit()
        conn.close()
        
        flash('Senha alterada com sucesso!', 'success')
        return redirect(url_for('index'))
        
    conn.close()
    return render_template('alterar_senha.html', primeiro_acesso=user['primeiro_acesso'])

@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    hoje_str = datetime.now().strftime('%d/%m/%Y')
    todas_consultas = conn.execute('SELECT c.*, p.nome as paciente_nome, m.nome as medico_nome FROM consultas c JOIN pacientes p ON c.paciente_id = p.id JOIN medicos m ON c.medico_id = m.id WHERE c.status != "Cancelado"').fetchall()
    consultas = [c for c in todas_consultas if hoje_str in c['data_hora']]
    conn.close()
    return render_template('index.html', consultas=consultas)

@app.route('/admin/usuarios', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_usuarios():
    conn = get_db_connection()
    if request.method == 'POST':
        nome_completo = request.form.get('nome_completo', '')
        cpf = request.form.get('cpf', '')
        telefone = request.form.get('telefone', '')
        email = request.form.get('email', '')
        rua = request.form.get('rua', '')
        numero = request.form.get('numero', '')
        complemento = request.form.get('complemento', '')
        bairro = request.form.get('bairro', '')
        cidade = request.form.get('cidade', '')
        cep = request.form.get('cep', '')
        
        comp_str = f", {complemento}" if complemento else ""
        endereco = f"{rua}, Nº {numero}{comp_str} - {bairro}, {cidade} - CEP: {cep}"

        username = request.form['username']
        senha_provisoria = request.form['senha']
        is_admin = 1 if 'is_admin' in request.form else 0
        
        existente = conn.execute('SELECT * FROM usuarios WHERE username = ?', (username,)).fetchone()
        if existente:
            flash('Este login de usuário já existe!', 'danger')
        else:
            senha_hash = generate_password_hash(senha_provisoria)
            conn.execute('''INSERT INTO usuarios (nome_completo, cpf, telefone, email, rua, numero, complemento, bairro, cidade, cep, endereco, username, senha, is_admin, status, primeiro_acesso) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "ativo", 1)''',
                         (nome_completo, cpf, telefone, email, rua, numero, complemento, bairro, cidade, cep, endereco, username, senha_hash, is_admin))
            conn.commit()
            flash('Usuário criado com sucesso! Ele deverá alterar a senha no primeiro acesso.', 'success')
        conn.close()
        return redirect(url_for('admin_usuarios'))
        
    usuarios = conn.execute('SELECT * FROM usuarios').fetchall()
    conn.close()
    return render_template('admin_usuarios.html', usuarios=usuarios)

@app.route('/admin/usuarios/editar-senha/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_editar_senha(id):
    nova_senha = request.form.get('nova_senha')
    if nova_senha:
        conn = get_db_connection()
        senha_hash = generate_password_hash(nova_senha)
        conn.execute('UPDATE usuarios SET senha = ?, primeiro_acesso = 1 WHERE id = ?', (senha_hash, id))
        conn.commit()
        conn.close()
        flash('Senha alterada com sucesso! O usuário deverá trocá-la no próximo acesso.', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/bloquear/<int:id>', methods=['POST'])
@login_required
@admin_required
def bloquear_usuario(id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM usuarios WHERE id = ?', (id,)).fetchone()
    if user:
        novo_status = 'ativo' if user['status'] == 'bloqueado' else 'bloqueado'
        conn.execute('UPDATE usuarios SET status = ? WHERE id = ?', (novo_status, id))
        conn.commit()
        flash(f'Status do usuário {user["username"]} alterado para {novo_status}.', 'success')
    conn.close()
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/excluir/<int:id>', methods=['POST'])
@login_required
@admin_required
def excluir_usuario(id):
    conn = get_db_connection()
    if id == session['user_id']:
        flash('Você não pode excluir sua própria conta de administrador.', 'danger')
    else:
        conn.execute('DELETE FROM usuarios WHERE id = ?', (id,))
        conn.commit()
        flash('Usuário excluído com sucesso.', 'success')
    conn.close()
    return redirect(url_for('admin_usuarios'))

@app.route('/api/buscar_paciente')
@login_required
def api_buscar_paciente():
    termo = request.args.get('termo', '').strip()
    conn = get_db_connection()
    pacientes = conn.execute('SELECT * FROM pacientes WHERE cpf LIKE ? OR nome LIKE ? LIMIT 10', (f'%{termo}%', f'%{termo}%')).fetchall()
    conn.close()
    return jsonify([dict(p) for p in pacientes])

@app.route('/api/buscar_medicos')
@login_required
def api_buscar_medicos():
    termo = request.args.get('termo', '').strip()
    conn = get_db_connection()
    medicos = conn.execute('SELECT * FROM medicos WHERE nome LIKE ? OR especialidade LIKE ? LIMIT 10', (f'%{termo}%', f'%{termo}%')).fetchall()
    conn.close()
    return jsonify([dict(m) for m in medicos])

@app.route('/api/horarios_medico')
@login_required
def api_horarios_medico():
    medico_id = request.args.get('medico_id')
    data_str = request.args.get('data')
    if not medico_id or not data_str:
        return jsonify([])

    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d')
        data_formatada_consulta = data_obj.strftime('%d/%m/%Y')
    except:
        return jsonify([])

    conn = get_db_connection()
    local_info = conn.execute('SELECT * FROM medico_locais WHERE medico_id = ? LIMIT 1', (medico_id,)).fetchone()
    consultas_existentes = conn.execute('SELECT data_hora FROM consultas WHERE medico_id = ? AND status != "Cancelado"', (medico_id,)).fetchall()
    conn.close()

    horarios_ocupados = [c['data_hora'] for c in consultas_existentes]

    inicio_str = local_info['horario_inicio'] if local_info and local_info['horario_inicio'] else '09:00'
    fim_str = local_info['horario_fim'] if local_info and local_info['horario_fim'] else '17:00'
    duracao_min = int(local_info['duracao_minutos']) if local_info and local_info['duracao_minutos'] else 30

    try:
        hora_atual = datetime.strptime(inicio_str, '%H:%M')
        hora_fim = datetime.strptime(fim_str, '%H:%M')
    except:
        hora_atual = datetime.strptime('09:00', '%H:%M')
        hora_fim = datetime.strptime('17:00', '%H:%M')
        duracao_min = 30

    grade_horarios = []
    delta = timedelta(minutes=duracao_min)

    while hora_atual <= hora_fim:
        h_fmt = hora_atual.strftime('%H:%M')
        string_completa = f"{data_formatada_consulta} {h_fmt}"
        ocupado = string_completa in horarios_ocupados

        grade_horarios.append({
            'horario': h_fmt,
            'data_hora_input': data_obj.strftime(f'%Y-%m-%dT%H:%M'),
            'ocupado': ocupado
        })
        hora_atual += delta

    return jsonify(grade_horarios)

@app.route('/cadastros')
@login_required
def cadastros():
    conn = get_db_connection()
    secao = request.args.get('secao', 'geral')
    
    pacientes = conn.execute('SELECT * FROM pacientes').fetchall()
    medicos_raw = conn.execute('SELECT * FROM medicos').fetchall()
    locais = conn.execute('SELECT * FROM clinicas').fetchall()
    conn.close()

    medicos_por_especialidade = {}
    for m in medicos_raw:
        especialidades = [e.strip() for e in m['especialidade'].split(',')]
        for esp in especialidades:
            if esp:
                esp_capitalizada = esp.capitalize()
                if esp_capitalizada not in medicos_por_especialidade:
                    medicos_por_especialidade[esp_capitalizada] = []
                medicos_por_especialidade[esp_capitalizada].append(m)

    hospitais = [l for l in locais if 'hospital' in l['nome'].lower()]
    clinicas = [l for l in locais if 'hospital' not in l['nome'].lower()]

    return render_template('cadastros.html', 
                           secao=secao,
                           pacientes=pacientes, 
                           medicos_por_especialidade=medicos_por_especialidade, 
                           hospitais=hospitais, 
                           clinicas=clinicas)

@app.route('/pacientes', methods=['GET', 'POST'])
@login_required
def pacientes():
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form.get('nome')
        cpf = request.form.get('cpf', '')
        
        telefones_list = request.form.getlist('telefones[]')
        contatos_list = request.form.getlist('contatos_tel[]')
        
        telefones_formatados = []
        for i in range(len(telefones_list)):
            if telefones_list[i].strip():
                contato_txt = f" ({contatos_list[i].strip()})" if i < len(contatos_list) and contatos_list[i].strip() else ""
                telefones_formatados.append(f"{telefones_list[i].strip()}{contato_txt}")
        telefones = ' | '.join(telefones_formatados)
        
        email = request.form.get('email', '')
        rua = request.form.get('rua', '')
        numero = request.form.get('numero', '')
        complemento = request.form.get('complemento', '')
        bairro = request.form.get('bairro', '')
        cidade = request.form.get('cidade', '')
        cep = request.form.get('cep', '')
        
        comp_str = f", {complemento}" if complemento else ""
        endereco_completo = f"{rua}, Nº {numero}{comp_str} - {bairro}, {cidade} - CEP: {cep}"
        
        conn.execute('''INSERT INTO pacientes (nome, cpf, telefones, email, rua, numero, complemento, bairro, cidade, cep, endereco) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                     (nome, cpf, telefones, email, rua, numero, complemento, bairro, cidade, cep, endereco_completo))
        conn.commit()
        conn.close()
        flash('Paciente cadastrado com sucesso!', 'success')
        return redirect(url_for('pacientes'))
        
    lista = conn.execute('SELECT * FROM pacientes').fetchall()
    conn.close()
    return render_template('pacientes.html', pacientes=lista)

@app.route('/editar/paciente/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_paciente(id):
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form.get('nome')
        cpf = request.form.get('cpf', '')
        
        telefones_list = request.form.getlist('telefones[]')
        contatos_list = request.form.getlist('contatos_tel[]')
        
        telefones_formatados = []
        for i in range(len(telefones_list)):
            if telefones_list[i].strip():
                contato_txt = f" ({contatos_list[i].strip()})" if i < len(contatos_list) and contatos_list[i].strip() else ""
                telefones_formatados.append(f"{telefones_list[i].strip()}{contato_txt}")
        telefones = ' | '.join(telefones_formatados)
        
        email = request.form.get('email', '')
        rua = request.form.get('rua', '')
        numero = request.form.get('numero', '')
        complemento = request.form.get('complemento', '')
        bairro = request.form.get('bairro', '')
        cidade = request.form.get('cidade', '')
        cep = request.form.get('cep', '')
        
        comp_str = f", {complemento}" if complemento else ""
        endereco_completo = f"{rua}, Nº {numero}{comp_str} - {bairro}, {cidade} - CEP: {cep}"
        
        conn.execute('''UPDATE pacientes SET nome=?, cpf=?, telefones=?, email=?, rua=?, numero=?, complemento=?, bairro=?, cidade=?, cep=?, endereco=? WHERE id=?''',
                     (nome, cpf, telefones, email, rua, numero, complemento, bairro, cidade, cep, endereco_completo, id))
        conn.commit()
        conn.close()
        flash('Paciente atualizado com sucesso!', 'success')
        return redirect(url_for('cadastros', secao='pacientes'))
        
    paciente = conn.execute('SELECT * FROM pacientes WHERE id = ?', (id,)).fetchone()
    conn.close()
    return render_template('editar_paciente.html', paciente=paciente)

@app.route('/medicos', methods=['GET', 'POST'])
@login_required
def medicos():
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form['nome']
        especialidades_list = request.form.getlist('especialidades[]')
        especialidade = ', '.join(especialidades_list) if especialidades_list else 'Geral'
        telefone = request.form.get('telefone', '')
        tipo_atendimento = request.form.get('tipo_atendimento', 'Particular')
        
        cursor = conn.execute('INSERT INTO medicos (nome, especialidade, telefone, tipo_atendimento) VALUES (?, ?, ?, ?)', 
                              (nome, especialidade, telefone, tipo_atendimento))
        medico_id = cursor.lastrowid
        
        clinicas_ids = request.form.getlist('clinica_id[]')
        inicios = request.form.getlist('horario_inicio[]')
        fins = request.form.getlist('horario_fim[]')
        duracoes = request.form.getlist('duracao_minutos[]')
        
        for i in range(len(clinicas_ids)):
            if clinicas_ids[i]:
                dias_selecionados = request.form.getlist(f'dias_{i}[]')
                dias_str = ', '.join(dias_selecionados)
                duracao = int(duracoes[i]) if i < len(duracoes) and duracoes[i].isdigit() else 30
                conn.execute('INSERT INTO medico_locais (medico_id, clinica_id, dias, horario_inicio, horario_fim, duracao_minutos) VALUES (?, ?, ?, ?, ?, ?)',
                             (medico_id, clinicas_ids[i], dias_str, inicios[i], fins[i], duracao))

        conn.commit()
        conn.close()
        flash('Médico e horários cadastrados com sucesso!', 'success')
        return redirect(url_for('medicos'))
        
    clinicas = conn.execute('SELECT * FROM clinicas').fetchall()
    conn.close()
    return render_template('medicos.html', clinicas=clinicas)

@app.route('/editar/medico/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_medico(id):
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form['nome']
        especialidades_list = request.form.getlist('especialidades[]')
        especialidade = ', '.join(especialidades_list) if especialidades_list else 'Geral'
        telefone = request.form.get('telefone', '')
        tipo_atendimento = request.form.get('tipo_atendimento', 'Particular')
        
        conn.execute('UPDATE medicos SET nome=?, especialidade=?, telefone=?, tipo_atendimento=? WHERE id=?', 
                     (nome, especialidade, telefone, tipo_atendimento, id))
        
        conn.execute('DELETE FROM medico_locais WHERE medico_id = ?', (id,))
        
        clinicas_ids = request.form.getlist('clinica_id[]')
        inicios = request.form.getlist('horario_inicio[]')
        fins = request.form.getlist('horario_fim[]')
        duracoes = request.form.getlist('duracao_minutos[]')
        
        for i in range(len(clinicas_ids)):
            if clinicas_ids[i]:
                dias_selecionados = request.form.getlist(f'dias_{i}[]')
                dias_str = ', '.join(dias_selecionados)
                duracao = int(duracoes[i]) if i < len(duracoes) and duracoes[i].isdigit() else 30
                conn.execute('INSERT INTO medico_locais (medico_id, clinica_id, dias, horario_inicio, horario_fim, duracao_minutos) VALUES (?, ?, ?, ?, ?, ?)',
                             (id, clinicas_ids[i], dias_str, inicios[i], fins[i], duracao))

        conn.commit()
        conn.close()
        flash('Médico atualizado com sucesso!', 'success')
        return redirect(url_for('cadastros', secao='medicos'))
        
    medico = conn.execute('SELECT * FROM medicos WHERE id = ?', (id,)).fetchone()
    locais = conn.execute('SELECT * FROM medico_locais WHERE medico_id = ?', (id,)).fetchall()
    clinicas = conn.execute('SELECT * FROM clinicas').fetchall()
    conn.close()
    return render_template('editar_medico.html', medico=medico, locais=locais, clinicas=clinicas)

@app.route('/clinicas', methods=['GET', 'POST'])
@login_required
def clinicas():
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form.get('email', '')
        
        telefones_list = request.form.getlist('telefones[]')
        contatos_list = request.form.getlist('contatos_tel[]')
        
        telefones_formatados = []
        for i in range(len(telefones_list)):
            if telefones_list[i].strip():
                contato_txt = f" ({contatos_list[i].strip()})" if i < len(contatos_list) and contatos_list[i].strip() else ""
                telefones_formatados.append(f"{telefones_list[i].strip()}{contato_txt}")
        telefone = ' | '.join(telefones_formatados)
        
        rua = request.form.get('rua', '')
        numero = request.form.get('numero', '')
        complemento = request.form.get('complemento', '')
        bairro = request.form.get('bairro', '')
        cidade = request.form.get('cidade', '')
        cep = request.form.get('cep', '')
        
        comp_str = f", {complemento}" if complemento else ""
        endereco = f"{rua}, Nº {numero}{comp_str} - {bairro}, {cidade} - CEP: {cep}"
        
        modalidades_list = request.form.getlist('modalidades[]')
        modalidade = ','.join(modalidades_list) if modalidades_list else 'Particular'
        
        conn.execute('''INSERT INTO clinicas (nome, telefone, email, rua, numero, complemento, bairro, cidade, cep, endereco, modalidade) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                     (nome, telefone, email, rua, numero, complemento, bairro, cidade, cep, endereco, modalidade))
        conn.commit()
        conn.close()
        flash('Clínica ou Hospital cadastrado com sucesso!', 'success')
        return redirect(url_for('clinicas'))
        
    lista = conn.execute('SELECT * FROM clinicas').fetchall()
    conn.close()
    return render_template('clinicas.html', clinicas=lista)

@app.route('/editar/clinica/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_clinica(id):
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form.get('email', '')
        
        telefones_list = request.form.getlist('telefones[]')
        contatos_list = request.form.getlist('contatos_tel[]')
        
        telefones_formatados = []
        for i in range(len(telefones_list)):
            if telefones_list[i].strip():
                contato_txt = f" ({contatos_list[i].strip()})" if i < len(contatos_list) and contatos_list[i].strip() else ""
                telefones_formatados.append(f"{telefones_list[i].strip()}{contato_txt}")
        telefone = ' | '.join(telefones_formatados)
        
        rua = request.form.get('rua', '')
        numero = request.form.get('numero', '')
        complemento = request.form.get('complemento', '')
        bairro = request.form.get('bairro', '')
        cidade = request.form.get('cidade', '')
        cep = request.form.get('cep', '')
        
        comp_str = f", {complemento}" if complemento else ""
        endereco = f"{rua}, Nº {numero}{comp_str} - {bairro}, {cidade} - CEP: {cep}"
        
        modalidades_list = request.form.getlist('modalidades[]')
        modalidade = ','.join(modalidades_list) if modalidades_list else 'Particular'
        
        conn.execute('''UPDATE clinicas SET nome=?, telefone=?, email=?, rua=?, numero=?, complemento=?, bairro=?, cidade=?, cep=?, endereco=?, modalidade=? WHERE id=?''', 
                     (nome, telefone, email, rua, numero, complemento, bairro, cidade, cep, endereco, modalidade, id))
        conn.commit()
        conn.close()
        flash('Clínica ou Hospital atualizado com sucesso!', 'success')
        return redirect(url_for('cadastros', secao='locais'))
        
    clinica = conn.execute('SELECT * FROM clinicas WHERE id = ?', (id,)).fetchone()
    conn.close()
    return render_template('editar_clinica.html', clinica=clinica)

@app.route('/crm')
@login_required
def crm():
    conn = get_db_connection()
    busca = request.args.get('busca', '')
    
    if busca:
        pacientes_kanban = conn.execute('SELECT * FROM pacientes WHERE nome LIKE ? OR cpf LIKE ? OR telefones LIKE ? OR email LIKE ?', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
        agendamentos_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Agendamentos" AND (nome_cliente LIKE ? OR documento LIKE ? OR telefones LIKE ? OR email LIKE ? OR medico LIKE ?)', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
        retorno_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Retorno" AND (nome_cliente LIKE ? OR documento LIKE ? OR telefones LIKE ? OR email LIKE ? OR medico LIKE ?)', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
        reagendamento_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Reagendamento" AND (nome_cliente LIKE ? OR documento LIKE ? OR telefones LIKE ? OR email LIKE ? OR medico LIKE ?)', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
        cancelados_kanban = conn.execute('SELECT * FROM crm_agendamentos WHERE status_etapa = "Cancelados" AND (nome_cliente LIKE ? OR documento LIKE ? OR telefones LIKE ? OR email LIKE ? OR medico LIKE ?)', (f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
    else:
        pacientes_kanban = conn.execute('SELECT * FROM pacientes').fetchall()
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

@app.route('/agendar', methods=['POST'])
@login_required
def agendar():
    conn = get_db_connection()
    data_bruta = request.form.get('data_hora', '')
    try:
        data_obj = datetime.strptime(data_bruta, '%Y-%m-%dT%H:%M')
        data_formatada = data_obj.strftime('%d/%m/%Y %H:%M')
        data_crm = data_obj.strftime('%d/%m/%Y')
        horario_crm = data_obj.strftime('%H:%M')
    except:
        data_formatada = data_bruta
        data_crm = ''
        horario_crm = ''

    paciente_id = request.form.get('paciente_id')
    medico_id = request.form.get('medico_id')
    
    conflito = conn.execute('SELECT * FROM consultas WHERE medico_id = ? AND data_hora = ? AND status != "Cancelado"', (medico_id, data_formatada)).fetchone()
    if conflito:
        conn.close()
        flash('Erro: Este horário já possui uma consulta agendada para este médico!', 'danger')
        return redirect(url_for('index'))

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
                 (paciente_id, medico_id, data_formatada, request.form.get('valor', 'R$ 0,00'), request.form.get('forma_pagamento', 'Dinheiro'), comprovante_nome, 'Agendado'))
    
    if paciente and medico:
        conn.execute('''INSERT INTO crm_agendamentos 
            (documento, nome_cliente, telefones, email, endereco, especialidade, medico, clinica_hospital, data_consulta, data_lembrete, horario, status_etapa, valor_consulta, tipo_pagamento, status_pagamento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (paciente['cpf'] if 'cpf' in paciente.keys() else '', 
             paciente['nome'], 
             paciente['telefones'], 
             paciente['email'] if 'email' in paciente.keys() else '', 
             paciente['endereco'] if 'endereco' in paciente.keys() else '', 
             medico['especialidade'], 
             medico['nome'], 
             'Principal', 
             data_crm, 
             data_crm, 
             horario_crm, 
             'Agendamentos', 
             request.form.get('valor', 'R$ 0,00'), 
             request.form.get('forma_pagamento', 'Dinheiro'), 
             'Pendente'))

    conn.commit()
    conn.close()
    flash('Consulta agendada com sucesso!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
