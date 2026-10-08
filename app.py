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
    for col in ['cep', 'rua', 'numero', 'bairro', 'cidade_estado', 'referencia', 'telefones', 'endereco']:
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

@app.route('/cadastros')
def cadastros():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    pacientes = conn.execute('SELECT * FROM pacientes').fetchall()
    medicos = conn.execute('SELECT * FROM medicos').fetchall()
    hospitais = conn.execute('SELECT * FROM hospitais').fetchall()
    conn.close()
    return render_template('cadastros.html', pacientes=pacientes, medicos=medicos, hospitais=hospitais)

@app.route('/backup/executar', methods=['POST'])
def executar_backup():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        home_dir = os.path.expanduser('~')
        docs_dir = os.path.join(home_dir, 'Documentos')
        if not os.path.exists(docs_dir):
            docs_dir = os.path.join(home_dir, 'Documents')
            if not os.path.exists(docs_dir):
                os.makedirs(docs_dir)

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        nome_backup = f'medcontrol_backup_{timestamp}.db'
        caminho_destino = os.path.join(docs_dir, nome_backup)

        shutil.copy('database.db', caminho_destino)
        flash(f'Backup salvo com sucesso na pasta Documentos: {nome_backup}', 'success')
    except Exception as e:
        flash(f'Erro ao realizar backup: {str(e)}', 'error')

    return redirect(url_for('admin_usuarios'))

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
