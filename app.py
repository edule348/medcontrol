import sqlite3
import os
import shutil
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

app = Flask(__name__)
app.secret_key = 'novo_sistema_secret_key'

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    primeiro_acesso INTEGER DEFAULT 1)''')
    try:
        conn.execute('ALTER TABLE usuarios ADD COLUMN primeiro_acesso INTEGER DEFAULT 1')
    except sqlite3.OperationalError:
        pass

    conn.execute('''CREATE TABLE IF NOT EXISTS pacientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    cpf TEXT,
                    telefone TEXT,
                    email TEXT,
                    cep TEXT,
                    rua TEXT,
                    numero TEXT,
                    bairro TEXT,
                    cidade_estado TEXT,
                    referencia TEXT)''')
    for col in ['cep', 'rua', 'numero', 'bairro', 'cidade_estado', 'referencia']:
        try:
            conn.execute(f'ALTER TABLE pacientes ADD COLUMN {col} TEXT')
        except sqlite3.OperationalError:
            pass

    conn.execute('''CREATE TABLE IF NOT EXISTS medicos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    especialidade TEXT NOT NULL,
                    telefone TEXT,
                    email TEXT,
                    tempo_consulta TEXT)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS especialidades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT UNIQUE NOT NULL,
                    descricao TEXT)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS medico_locais (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medico_id INTEGER,
                    local_atendimento TEXT,
                    dias_atendimento TEXT,
                    hora_inicio TEXT,
                    hora_fim TEXT,
                    FOREIGN KEY(medico_id) REFERENCES medicos(id))''')

    conn.execute('''CREATE TABLE IF NOT EXISTS hospitais (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT,
                    nome TEXT NOT NULL,
                    telefone TEXT,
                    email TEXT,
                    cep TEXT,
                    rua TEXT,
                    numero TEXT,
                    bairro TEXT,
                    cidade_estado TEXT)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS procedimentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paciente TEXT NOT NULL,
                    tipo_procedimento TEXT NOT NULL,
                    profissional TEXT,
                    data TEXT,
                    hora TEXT,
                    valor TEXT,
                    pagamento TEXT,
                    observacoes TEXT)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS agendamentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paciente TEXT NOT NULL,
                    cpf TEXT,
                    medico TEXT NOT NULL,
                    especialidade TEXT,
                    local_atendimento TEXT,
                    data_consulta TEXT,
                    hora_consulta TEXT,
                    status TEXT DEFAULT 'Agendado',
                    justificativa TEXT,
                    tipo_atendimento TEXT DEFAULT 'Consulta')''')

    for col, default in [('tipo_atendimento', '"Consulta"'), ('status', '"Agendado"')]:
        try:
            conn.execute(f'ALTER TABLE agendamentos ADD COLUMN {col} TEXT DEFAULT {default}')
        except sqlite3.OperationalError:
            pass

    admin = conn.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',)).fetchone()
    if not admin:
        conn.execute('INSERT INTO usuarios (username, password, role, primeiro_acesso) VALUES (?, ?, ?, ?)',
                     ('admin', 'admin123', 'admin', 0))
    conn.commit()
    conn.close()

init_db()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM usuarios WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['primeiro_acesso'] = user['primeiro_acesso']
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha inválidos!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/alterar-senha-primeiro-acesso', methods=['POST'])
def alterar_senha_primeiro_acesso():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    nova_senha = request.form.get('nova_senha')
    conn = get_db_connection()
    conn.execute('UPDATE usuarios SET password = ?, primeiro_acesso = 0 WHERE id = ?', (nova_senha, session['user_id']))
    conn.commit()
    conn.close()
    session['primeiro_acesso'] = 0
    flash('Senha alterada com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    pacientes = conn.execute('SELECT * FROM pacientes').fetchall()
    medicos = conn.execute('SELECT * FROM medicos').fetchall()
    especialidades = conn.execute('SELECT * FROM especialidades ORDER BY nome ASC').fetchall()
    agendamentos = conn.execute("SELECT * FROM agendamentos WHERE status NOT IN ('Atendido', 'Cancelado', 'Nao Compareceu') ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('index.html', pacientes=pacientes, medicos=medicos, especialidades=especialidades, agendamentos=agendamentos)

@app.route('/backup/executar', methods=['POST'])
def executar_backup():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        # Definir pasta Documentos (funciona no Linux Mint / Ubuntu / Windows)
        home_dir = os.path.expanduser('~')
        docs_dir = os.path.join(home_dir, 'Documentos')
        
        if not os.path.exists(docs_dir):
            docs_dir = os.path.join(home_dir, 'Documents') # Fallback inglês
            if not os.path.exists(docs_dir):
                os.makedirs(docs_dir)

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        nome_backup = f'medcontrol_backup_{timestamp}.db'
        caminho_destino = os.path.join(docs_dir, nome_backup)

        # Copiar banco de dados de forma segura
        shutil.copy('database.db', caminho_destino)
        flash(f'Backup salvo com sucesso na pasta Documentos: {nome_backup}', 'success')
    except Exception as e:
        flash(f'Erro ao realizar backup: {str(e)}', 'error')

    return redirect(url_for('admin_usuarios'))

@app.route('/especialidades', methods=['GET', 'POST'])
def especialidades():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form.get('nome').upper().strip()
        descricao = request.form.get('descricao', '').strip()
        if nome:
            try:
                conn.execute('INSERT INTO especialidades (nome, descricao) VALUES (?, ?)', (nome, descricao))
                conn.commit()
                flash('Especialidade cadastrada com sucesso!', 'success')
            except sqlite3.IntegrityError:
                flash('Esta especialidade já está cadastrada!', 'error')
        return redirect(url_for('especialidades'))
    
    lista = conn.execute('SELECT * FROM especialidades ORDER BY nome ASC').fetchall()
    conn.close()
    return render_template('especialidades.html', especialidades=lista)

@app.route('/especialidades/editar/<int:id>', methods=['POST'])
def editar_especialidade(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    nome = request.form.get('nome').upper().strip()
    descricao = request.form.get('descricao', '').strip()
    conn = get_db_connection()
    try:
        conn.execute('UPDATE especialidades SET nome = ?, descricao = ? WHERE id = ?', (nome, descricao, id))
        conn.commit()
        flash('Especialidade atualizada com sucesso!', 'success')
    except sqlite3.IntegrityError:
        flash('Já existe uma especialidade com esse nome!', 'error')
    conn.close()
    return redirect(url_for('especialidades'))

@app.route('/especialidades/excluir/<int:id>', methods=['POST'])
def excluir_especialidade(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM especialidades WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Especialidade excluída com sucesso!', 'success')
    return redirect(url_for('especialidades'))

@app.route('/api/pacientes')
def api_pacientes():
    if 'user_id' not in session:
        return jsonify([])
    conn = get_db_connection()
    termo = request.args.get('q', '').strip()
    if not termo:
        conn.close()
        return jsonify([])
    pacientes = conn.execute("SELECT nome FROM pacientes WHERE nome LIKE ? LIMIT 10", (termo + '%',)).fetchall()
    conn.close()
    return jsonify([p['nome'] for p in pacientes])

@app.route('/api/medicos')
def api_medicos():
    if 'user_id' not in session:
        return jsonify([])
    conn = get_db_connection()
    especialidade = request.args.get('especialidade', '').strip()
    if especialidade:
        medicos = conn.execute("SELECT nome FROM medicos WHERE LOWER(especialidade) LIKE LOWER(?)", ('%' + especialidade + '%',)).fetchall()
    else:
        medicos = []
    conn.close()
    return jsonify([m['nome'] for m in medicos])

@app.route('/api/medico_agenda')
def api_medico_agenda():
    if 'user_id' not in session:
        return jsonify({})
    nome_medico = request.args.get('medico', '').strip()
    conn = get_db_connection()
    medico = conn.execute("SELECT * FROM medicos WHERE nome = ?", (nome_medico,)).fetchone()
    if not medico:
        conn.close()
        return jsonify({})
    locais = conn.execute("SELECT * FROM medico_locais WHERE medico_id = ?", (medico['id'],)).fetchall()
    agendamentos = conn.execute("SELECT data_consulta, hora_consulta FROM agendamentos WHERE medico = ? AND status NOT IN ('Cancelado', 'Nao Compareceu')", (nome_medico,)).fetchall()
    conn.close()
    
    ocupados = [f"{ag['data_consulta']} {ag['hora_consulta']}" for ag in agendamentos]
    
    locais_lista = []
    for l in locais:
        locais_lista.append({
            'local': l['local_atendimento'],
            'dias': l['dias_atendimento'],
            'hora_inicio': l['hora_inicio'],
            'hora_fim': l['hora_fim']
        })
    
    tempo_val = 30
    if medico['tempo_consulta']:
        digits = "".join(filter(str.isdigit, medico['tempo_consulta']))
        if digits:
            tempo_val = int(digits)

    return jsonify({
        'nome': medico['nome'],
        'especialidade': medico['especialidade'],
        'tempo_consulta': tempo_val,
        'locais': locais_lista,
        'ocupados': ocupados
    })

@app.route('/agendar', methods=['POST'])
def agendar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    paciente = request.form.get('paciente')
    especialidade = request.form.get('especialidade')
    medico = request.form.get('medico')
    data = request.form.get('data')
    hora = request.form.get('hora')
    
    conn = get_db_connection()
    conn.execute('''INSERT INTO agendamentos (paciente, medico, especialidade, data_consulta, hora_consulta, status, tipo_atendimento)
                    VALUES (?, ?, ?, ?, ?, 'Agendado', 'Consulta')''', (paciente, medico, especialidade, data, hora))
    conn.commit()
    conn.close()
    flash('Consulta agendada com sucesso!', 'success')
    return redirect(url_for('crm'))

@app.route('/crm')
def crm():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    hoje_str = date.today().isoformat()
    amanha_str = (date.today() + timedelta(days=1)).isoformat()

    conn = get_db_connection()
    conn.execute("UPDATE agendamentos SET status = 'Em Confirmação' WHERE status = 'Agendado' AND data_consulta = ?", (amanha_str,))
    conn.execute("UPDATE agendamentos SET status = 'Paciente do Dia' WHERE status IN ('Confirmado', 'Em Confirmação', 'Agendado') AND data_consulta = ?", (hoje_str,))
    conn.commit()

    busca = request.args.get('busca', '').strip()
    if busca:
        if busca.startswith('Dr.') or busca.startswith('Dra.'):
            query = "SELECT * FROM agendamentos WHERE medico LIKE ?"
            agendamentos = conn.execute(query, ('%' + busca + '%',)).fetchall()
        else:
            query = "SELECT * FROM agendamentos WHERE paciente LIKE ? OR cpf LIKE ?"
            agendamentos = conn.execute(query, ('%' + busca + '%', '%' + busca + '%')).fetchall()
    else:
        agendamentos = conn.execute('SELECT * FROM agendamentos').fetchall()
    
    conn.close()
    return render_template('crm.html', agendamentos=agendamentos, busca=busca, hoje=hoje_str)

@app.route('/crm/atualizar_status/<int:id>/<path:status>', methods=['POST'])
def atualizar_status(id, status):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    justificativa = request.form.get('justificativa', '')
    conn = get_db_connection()
    if status == 'Cancelado':
        conn.execute('UPDATE agendamentos SET status = ?, justificativa = ? WHERE id = ?', (status, justificativa, id))
    else:
        conn.execute('UPDATE agendamentos SET status = ? WHERE id = ?', (status, id))
    conn.commit()
    conn.close()
    return redirect(url_for('crm'))

@app.route('/crm/reagendar/<int:id>', methods=['POST'])
def reagendar_consulta(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    nova_data = request.form.get('data')
    nova_hora = request.form.get('hora')
    conn = get_db_connection()
    conn.execute('UPDATE agendamentos SET data_consulta = ?, hora_consulta = ?, status = "Agendado" WHERE id = ?',
                 (nova_data, nova_hora, id))
    conn.commit()
    conn.close()
    flash('Consulta reagendada com sucesso!', 'success')
    return redirect(url_for('crm'))

@app.route('/crm/agendar_retorno/<int:id>', methods=['POST'])
def agendar_retorno(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    nova_data = request.form.get('data')
    nova_hora = request.form.get('hora')
    conn = get_db_connection()
    conn.execute('UPDATE agendamentos SET data_consulta = ?, hora_consulta = ?, status = "Retorno", tipo_atendimento = "Retorno" WHERE id = ?',
                 (nova_data, nova_hora, id))
    conn.commit()
    conn.close()
    flash('Retorno agendado com sucesso!', 'success')
    return redirect(url_for('crm'))

@app.route('/procedimentos', methods=['GET', 'POST'])
def procedimentos():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        conn.execute('''INSERT INTO procedimentos 
            (paciente, tipo_procedimento, profissional, data, hora, valor, pagamento, observacoes) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                request.form.get('paciente'),
                request.form.get('tipo_procedimento'),
                request.form.get('profissional'),
                request.form.get('data'),
                request.form.get('hora'),
                request.form.get('valor'),
                request.form.get('pagamento'),
                request.form.get('observacoes')
            ))
        conn.commit()
        flash('Procedimento agendado com sucesso!', 'success')
        return redirect(url_for('procedimentos'))
    lista_procedimentos = conn.execute('SELECT * FROM procedimentos').fetchall()
    pacientes = conn.execute('SELECT * FROM pacientes').fetchall()
    medicos = conn.execute('SELECT * FROM medicos').fetchall()
    conn.close()
    return render_template('agendar_procedimento.html', procedimentos=lista_procedimentos, pacientes=pacientes, medicos=medicos)

@app.route('/pacientes', methods=['GET', 'POST'])
def pacientes():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        conn = get_db_connection()
        conn.execute('''INSERT INTO pacientes 
            (nome, cpf, telefone, email, cep, rua, numero, bairro, cidade_estado, referencia) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                request.form.get('nome'),
                request.form.get('cpf'),
                request.form.get('telefone'),
                request.form.get('email'),
                request.form.get('cep'),
                request.form.get('rua'),
                request.form.get('numero'),
                request.form.get('bairro'),
                request.form.get('cidade_estado'),
                request.form.get('referencia')
            ))
        conn.commit()
        conn.close()
        flash('Paciente cadastrado com sucesso!', 'success')
        return redirect(url_for('pacientes'))
    conn = get_db_connection()
    lista_pacientes = conn.execute('SELECT * FROM pacientes').fetchall()
    conn.close()
    return render_template('cadastrar_paciente.html', pacientes=lista_pacientes)

@app.route('/pacientes/perfil/<int:id>')
def perfil_paciente(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    paciente = conn.execute('SELECT * FROM pacientes WHERE id = ?', (id,)).fetchone()
    if not paciente:
        conn.close()
        flash('Paciente não encontrado.', 'error')
        return redirect(url_for('cadastros'))
    agendamentos = conn.execute('SELECT * FROM agendamentos WHERE paciente = ?', (paciente['nome'],)).fetchall()
    conn.close()
    return render_template('perfil_paciente.html', paciente=paciente, agendamentos=agendamentos)

@app.route('/pacientes/agenda/<int:id>')
def agenda_paciente(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    paciente = conn.execute('SELECT * FROM pacientes WHERE id = ?', (id,)).fetchone()
    if not paciente:
        conn.close()
        flash('Paciente não encontrado.', 'error')
        return redirect(url_for('cadastros'))
    agendamentos = conn.execute('SELECT * FROM agendamentos WHERE paciente = ?', (paciente['nome'],)).fetchall()
    conn.close()
    return render_template('agenda_paciente.html', paciente=paciente, agendamentos=agendamentos)

@app.route('/medicos/cadastrar', methods=['GET', 'POST'])
def cadastrar_medico():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form.get('nome')
        especialidade = request.form.get('especialidade')
        telefone = request.form.get('telefone')
        email = request.form.get('email')
        tempo_consulta = request.form.get('tempo_consulta')
        cursor = conn.execute('''INSERT INTO medicos (nome, especialidade, telefone, email, tempo_consulta) 
                                 VALUES (?, ?, ?, ?, ?)''',
                              (nome, especialidade, telefone, email, tempo_consulta))
        medico_id = cursor.lastrowid
        locais = request.form.getlist('local_atendimento[]')
        for i in range(len(locais)):
            local = locais[i]
            if local.strip():
                dias = request.form.getlist(f'dias_{i}[]')
                dias_str = ", ".join(dias) if dias else "Nenhum"
                hora_inicio = request.form.getlist('hora_inicio[]')[i] if i < len(request.form.getlist('hora_inicio[]')) else ''
                hora_fim = request.form.getlist('hora_fim[]')[i] if i < len(request.form.getlist('hora_fim[]')) else ''
                conn.execute('''INSERT INTO medico_locais (medico_id, local_atendimento, dias_atendimento, hora_inicio, hora_fim)
                                VALUES (?, ?, ?, ?, ?)''',
                             (medico_id, local, dias_str, hora_inicio, hora_fim))
        conn.commit()
        conn.close()
        flash('Médico cadastrado com sucesso!', 'success')
        return redirect(url_for('cadastrar_medico'))
    medicos = conn.execute('SELECT * FROM medicos').fetchall()
    especialidades_lista = conn.execute('SELECT * FROM especialidades ORDER BY nome ASC').fetchall()
    conn.close()
    return render_template('cadastrar_medico.html', medicos=medicos, especialidades=especialidades_lista)

@app.route('/medicos/perfil/<int:id>')
def perfil_medico(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    medico = conn.execute('SELECT * FROM medicos WHERE id = ?', (id,)).fetchone()
    if not medico:
        conn.close()
        flash('Médico não encontrado.', 'error')
        return redirect(url_for('cadastros'))
    locais = conn.execute('SELECT * FROM medico_locais WHERE medico_id = ?', (id,)).fetchall()
    conn.close()
    return render_template('perfil_medico.html', medico=medico, locais=locais)

@app.route('/medicos/agenda/<int:id>')
def agenda_medico(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    medico = conn.execute('SELECT * FROM medicos WHERE id = ?', (id,)).fetchone()
    if not medico:
        conn.close()
        flash('Médico não encontrado.', 'error')
        return redirect(url_for('cadastros'))
    agendamentos = conn.execute('SELECT * FROM agendamentos WHERE medico = ?', (medico['nome'],)).fetchall()
    conn.close()
    return render_template('agenda_medico.html', medico=medico, agendamentos=agendamentos)

@app.route('/api/hospitais')
def api_hospitais():
    if 'user_id' not in session:
        return jsonify([])
    conn = get_db_connection()
    termo = request.args.get('q', '').strip()
    hospitais = conn.execute("SELECT nome FROM hospitais WHERE nome LIKE ? LIMIT 10", ('%' + termo + '%',)).fetchall()
    conn.close()
    return jsonify([h['nome'] for h in hospitais])

@app.route('/hospitais/cadastrar', methods=['GET', 'POST'])
def cadastrar_hospital():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        conn.execute('''INSERT INTO hospitais 
            (tipo, nome, telefone, email, cep, rua, numero, bairro, cidade_estado) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                request.form.get('tipo'),
                request.form.get('nome'),
                request.form.get('telefone'),
                request.form.get('email'),
                request.form.get('cep'),
                request.form.get('rua'),
                request.form.get('numero'),
                request.form.get('bairro'),
                request.form.get('cidade_estado')
            ))
        conn.commit()
        conn.close()
        flash('Hospital/Clínica cadastrado com sucesso!', 'success')
        return redirect(url_for('cadastrar_hospital'))
    hospitais = conn.execute('SELECT * FROM hospitais').fetchall()
    conn.close()
    return render_template('cadastrar_hospital.html', hospitais=hospitais)

@app.route('/hospitais/perfil/<int:id>')
def perfil_hospital(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    hospital = conn.execute('SELECT * FROM hospitais WHERE id = ?', (id,)).fetchone()
    if not hospital:
        conn.close()
        flash('Hospital ou clínica não encontrado.', 'error')
        return redirect(url_for('cadastrar_hospital'))
    medicos = conn.execute('''SELECT DISTINCT m.* FROM medicos m 
                              JOIN medico_locais ml ON m.id = ml.medico_id 
                              WHERE ml.local_atendimento LIKE ?''', ('%' + hospital['nome'] + '%',)).fetchall()
    conn.close()
    return render_template('perfil_hospital.html', hospital=hospital, medicos=medicos)

@app.route('/hospitais/agenda/<int:id>')
def agenda_hospital(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    hospital = conn.execute('SELECT * FROM hospitais WHERE id = ?', (id,)).fetchone()
    if not hospital:
        conn.close()
        flash('Hospital ou clínica não encontrado.', 'error')
        return redirect(url_for('cadastros'))
    agendamentos = conn.execute('SELECT * FROM agendamentos WHERE local_atendimento LIKE ?', ('%' + hospital['nome'] + '%',)).fetchall()
    conn.close()
    return render_template('agenda_hospital.html', hospital=hospital, agendamentos=agendamentos)

@app.route('/admin/usuarios', methods=['GET', 'POST'])
def admin_usuarios():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        try:
            conn.execute('INSERT INTO usuarios (username, password, role, primeiro_acesso) VALUES (?, ?, ?, 1)',
                         (username, password, role))
            conn.commit()
            flash('Usuário cadastrado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash('Nome de usuário já existe!', 'error')
        return redirect(url_for('admin_usuarios'))
    usuarios = conn.execute('SELECT * FROM usuarios').fetchall()
    conn.close()
    return render_template('admin_usuarios.html', usuarios=usuarios)

@app.route('/admin/usuarios/editar/<int:id>', methods=['POST'])
def editar_usuario(id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    conn = get_db_connection()
    if password:
        conn.execute('UPDATE usuarios SET username = ?, password = ?, role = ? WHERE id = ?', (username, password, role, id))
    else:
        conn.execute('UPDATE usuarios SET username = ?, role = ? WHERE id = ?', (username, role, id))
    conn.commit()
    conn.close()
    flash('Usuário atualizado com sucesso!', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/excluir/<int:id>', methods=['POST'])
def excluir_usuario(id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM usuarios WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Usuário excluído com sucesso!', 'success')
    return redirect(url_for('admin_usuarios'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
