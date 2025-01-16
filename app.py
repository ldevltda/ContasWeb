from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta, date
import sqlite3
import bcrypt
import re


app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_para_sessoes'


def db_connection():
    conn = sqlite3.connect('contas.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def login():
    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
def processar_login():
    data = request.form
    cpf = data.get('cpf')
    senha = data.get('senha')

    conn = db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM usuarios WHERE cpf = ?', (cpf,))
    usuario = cursor.fetchone()

    if usuario and bcrypt.checkpw(senha.encode('utf-8'), usuario['senha']):
        session['usuario_id'] = usuario['id']
        return redirect(url_for('home'))
    else:
        return render_template('login.html', error='CPF ou senha inválidos!')


@app.route('/home')
def home():
    if 'usuario_id' not in session:
        return redirect('/')

    conn = db_connection()
    cursor = conn.cursor()

    try:
        # Total Não Pago
        cursor.execute('SELECT COALESCE(SUM(valor), 0) AS total_nao_pago FROM contas WHERE status = "não pago"')
        total_nao_pago = cursor.fetchone()["total_nao_pago"]

        # Limite Restante
        cursor.execute('''
            SELECT COALESCE(SUM(limite_total - limite_utilizado), 0) AS limite_restante
            FROM cartoes_credito
        ''')
        limite_restante = cursor.fetchone()["limite_restante"]

        conn.close()

        return render_template(
            'index.html',
            title="Resumo Geral",
            total_nao_pago=total_nao_pago,
            limite_restante=limite_restante
        )
    except Exception as e:
        print(f"Erro na rota /home: {e}")
        return "Erro ao carregar a página inicial.", 500
    finally:
        conn.close()


@app.route('/resumo')
def resumo():
    if 'usuario_id' not in session:
        return redirect('/')

    try:
        data_atual = datetime.now()
        mes = int(request.args.get('mes', data_atual.month))
        ano = int(request.args.get('ano', data_atual.year))

        # Obtém a data de hoje
        hoje = datetime.now()

        # Subtrai 1 dia para obter a data de ontem
        ontem = hoje - timedelta(days=1)

        # Define os limites do mês atual no resumo
        primeiro_dia_mes = f"{ano}-{mes:02d}-01"
        ultimo_dia_mes = (datetime(ano, mes, 1) + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        ultimo_dia_mes = ultimo_dia_mes.strftime('%Y-%m-%d')

        conn = db_connection()
        cursor = conn.cursor()

        # Resumo das contas no mês atual
        cursor.execute('''
            SELECT 
                COUNT(*) as total_contas,
                COALESCE(SUM(valor), 0) as total_valor,
                COALESCE(SUM(CASE WHEN status = "pago" THEN valor ELSE 0 END), 0) as total_pago,
                COALESCE(SUM(CASE WHEN status = "não pago" THEN valor ELSE 0 END), 0) as total_nao_pago
            FROM contas
            WHERE (vencimento >= ?
              AND vencimento <= ?)
                OR (vencimento <= ? and status = 'não pago' and vencimento < ?)
        ''', (primeiro_dia_mes, ultimo_dia_mes, ontem, primeiro_dia_mes))
        resumo = cursor.fetchone()

        # Total Vencido: Contas não pagas vencidas até o último dia do mês atual
        cursor.execute('''
            SELECT COALESCE(SUM(valor), 0) as total_vencido
            FROM contas
            WHERE status = "não pago"
            AND vencimento <= ?
            and vencimento <= ?
        ''', (ontem, ultimo_dia_mes))
        total_vencido = cursor.fetchone()["total_vencido"]

        # Contas no Grid:
        # 1. Contas do mês em questão (independente do status)
        # 2. Contas não pagas vencidas dos meses anteriores até o mês atual
        cursor.execute('''
            SELECT * FROM contas
            WHERE (strftime('%Y-%m', vencimento) = strftime('%Y-%m', ?))
               OR (status = "não pago" AND vencimento < ? and vencimento <= ?)
            ORDER BY vencimento
        ''', (primeiro_dia_mes, ontem, ultimo_dia_mes))
        contas = cursor.fetchall()

        conn.close()

        return render_template(
            'resumo_contas.html',
            title='Contas a Pagar',
            mes=mes,
            ano=ano,
            total_contas=resumo['total_contas'] if resumo else 0,
            total_valor=resumo['total_valor'] if resumo else 0.0,
            total_pago=resumo['total_pago'] if resumo else 0.0,
            total_nao_pago=resumo['total_nao_pago'] if resumo else 0.0,
            total_vencido=total_vencido if total_vencido else 0.0,
            contas=contas
        )
    except Exception as e:
        print(f"Erro na rota /resumo: {e}")
        return "Erro ao carregar a página inicial.", 500


@app.route('/incluir', methods=['GET', 'POST'])
def incluir_conta():
    if 'usuario_id' not in session:
        return redirect('/')

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        valor = request.form.get('valor')
        vencimento = request.form.get('vencimento')
        usuario_id = session['usuario_id']

        # Verifique se os campos obrigatórios foram preenchidos
        if not descricao or not valor or not vencimento:
            return render_template('incluir.html', title='Incluir Conta', error='Todos os campos são obrigatórios!')

        conn = db_connection()
        cursor = conn.cursor()

        try:
            # Define o status como 'não pago' por padrão
            cursor.execute('''
                INSERT INTO contas (descricao, valor, vencimento, status, usuario_id)
                VALUES (?, ?, ?, 'não pago', ?)
            ''', (descricao, float(valor), vencimento, usuario_id))
            conn.commit()
            return redirect('/home')
        except Exception as e:
            conn.rollback()
            return render_template('incluir.html', title='Incluir Conta', error=f'Erro ao criar conta: {str(e)}')
        finally:
            conn.close()

    return render_template('incluir.html', title='Incluir Conta')


@app.route('/logout')
def logout():
    session.pop('usuario_id', None)
    return redirect('/')

@app.template_filter('format_currency')
def format_currency(value):
    """Format numbers in Brazilian currency style."""
    if value is None:
        return "R$ 0,00"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@app.route('/confirmar_exclusao/<int:id>', methods=['GET', 'POST'])
def confirmar_exclusao(id):
    if 'usuario_id' not in session:
        return redirect('/')

    conn = db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        try:
            cursor.execute('DELETE FROM contas WHERE id = ?', (id,))
            conn.commit()
            return redirect('/home')
        except Exception as e:
            conn.rollback()
            return render_template('confirmar_exclusao.html', title="Excluir Conta", error=f'Erro ao excluir conta: {str(e)}')
        finally:
            conn.close()

    try:
        cursor.execute('SELECT * FROM contas WHERE id = ?', (id,))
        conta = cursor.fetchone()
        if conta:
            return render_template('confirmar_exclusao.html', conta=conta)
        else:
            return redirect('/home')
    finally:
        conn.close()


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar_conta(id):
    if 'usuario_id' not in session:
        return redirect('/')

    conn = db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        valor = request.form.get('valor')
        vencimento = request.form.get('vencimento')

        try:
            cursor.execute('''
                UPDATE contas
                SET descricao = ?, valor = ?, vencimento = ?
                WHERE id = ?
            ''', (descricao, valor, vencimento, id))
            conn.commit()
            return redirect('/home')
        except Exception as e:
            conn.rollback()
            return render_template('editar.html', id=id, error=f'Erro ao editar conta: {str(e)}')
        finally:
            conn.close()

    try:
        cursor.execute('SELECT * FROM contas WHERE id = ?', (id,))
        conta = cursor.fetchone()
        if conta:
            return render_template('editar.html', conta=conta)
        else:
            return redirect('/home')
    finally:
        conn.close()


@app.route('/marcar/<int:id>', methods=['POST'])
def marcar_status(id):
    if 'usuario_id' not in session:
        return jsonify({'message': 'Usuário não autenticado!'}), 401

    conn = db_connection()
    cursor = conn.cursor()

    try:
        # Alternar o status com base no atual
        cursor.execute('SELECT status FROM contas WHERE id = ?', (id,))
        conta = cursor.fetchone()

        if not conta:
            return jsonify({'message': 'Conta não encontrada!'}), 404

        novo_status = 'não pago' if conta['status'] == 'pago' else 'pago'
        cursor.execute('UPDATE contas SET status = ? WHERE id = ?', (novo_status, id))
        conn.commit()

        return jsonify({'message': 'Status atualizado com sucesso!', 'novo_status': novo_status}), 200
    except Exception as e:
        conn.rollback()
        print(f"Erro no back-end: {str(e)}")  # Log para debug
        return jsonify({'message': f'Erro ao atualizar status: {str(e)}'}), 500
    finally:
        conn.close()


@app.route('/api/atualizar_resumo', methods=['GET'])
def atualizar_resumo():
    if 'usuario_id' not in session:
        return jsonify({'message': 'Usuário não autenticado!'}), 401

    conn = db_connection()
    cursor = conn.cursor()

    try:
        data_ontem = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        # Resumo
        cursor.execute('''
            SELECT 
                COUNT(*) as total_contas,
                COALESCE(SUM(valor), 0) as total_valor,
                COALESCE(SUM(CASE WHEN status = "pago" THEN valor ELSE 0 END), 0) as total_pago,
                COALESCE(SUM(CASE WHEN status = "não pago" THEN valor ELSE 0 END), 0) as total_nao_pago,
                COALESCE(SUM(CASE WHEN status = "não pago" AND vencimento <= ? THEN valor ELSE 0 END), 0) as total_vencido
            FROM contas
        ''', (data_ontem,))
        resumo = cursor.fetchone()

        # Grid
        cursor.execute('SELECT * FROM contas ORDER BY vencimento')
        contas = [dict(row) for row in cursor.fetchall()]

        return jsonify({'resumo': resumo, 'contas': contas}), 200
    except Exception as e:
        return jsonify({'message': f'Erro ao atualizar resumo: {str(e)}'}), 500
    finally:
        conn.close()


@app.route('/cartoes')
def cartoes():
    if 'usuario_id' not in session:
        return redirect('/')

    conn = db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT 
            id, nome, 
            limite_total, 
            limite_utilizado, 
            (limite_total - limite_utilizado) as limite_restante
        FROM cartoes_credito
    ''')
    cartoes = cursor.fetchall()

    total_limite = sum(c['limite_total'] for c in cartoes)
    limite_utilizado = sum(c['limite_utilizado'] for c in cartoes)
    limite_restante = total_limite - limite_utilizado

    return render_template(
        'cartoes.html',
        title='Cartões de Crédito',
        mes=datetime.now().month,
        ano=datetime.now().year,
        total_limite=total_limite,
        limite_utilizado=limite_utilizado,
        limite_restante=limite_restante,
        cartoes=cartoes
    )


@app.route('/faturas/<int:cartao_id>')
def faturas(cartao_id):
    if 'usuario_id' not in session:
        return redirect('/')

    conn = db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT nome, limite_total FROM cartoes_credito WHERE id = ?', (cartao_id,))
        cartao = cursor.fetchone()
        if not cartao:
            return "Cartão não encontrado.", 404

        nome_cartao = cartao['nome']
        limite_total = cartao['limite_total']

        cursor.execute('SELECT * FROM fatura WHERE cartao_id = ?', (cartao_id,))
        faturas = cursor.fetchall()

        return render_template(
            'faturas.html',
            title='Faturas do Cartão',
            cartao_id=cartao_id,
            nome_cartao=nome_cartao,
            limite_total=limite_total,
            faturas=faturas
        )
    except Exception as e:
        return f"Erro: {e}"
    finally:
        conn.close()


@app.route('/editar_fatura/<int:fatura_id>', methods=['GET', 'POST'])
def editar_fatura(fatura_id):
    if 'usuario_id' not in session:
        return redirect('/')

    conn = db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        dia_vencimento = request.form.get('dia_vencimento')
        valor = request.form.get('valor')
        cartao_id = request.form.get('cartao_id')  # Certifique-se de enviar o cartao_id no formulário

        try:
            cursor.execute(
                '''
                UPDATE fatura
                SET dia_vencimento = ?, valor = ?
                WHERE id = ?
                ''',
                (dia_vencimento, valor, fatura_id)
            )
            conn.commit()
            return redirect(url_for('faturas', cartao_id=cartao_id))
        except Exception as e:
            conn.rollback()
            return f"Erro ao editar fatura: {e}"
        finally:
            conn.close()

    try:
        cursor.execute('SELECT * FROM fatura WHERE id = ?', (fatura_id,))
        fatura = cursor.fetchone()
        if not fatura:
            return "Fatura não encontrada.", 404

        return render_template('editar_fatura.html', fatura=fatura)
    finally:
        conn.close()


@app.route('/incluir_fatura/<int:cartao_id>', methods=['GET', 'POST'])
def incluir_fatura(cartao_id):
    if 'usuario_id' not in session:
        return redirect('/')

    if request.method == 'POST':
        mes = int(request.form.get('mes'))  # Garantindo que mes é inteiro
        ano = int(request.form.get('ano'))  # Garantindo que ano é inteiro
        dia_vencimento = int(request.form.get('dia_vencimento'))  # Garantindo que dia_vencimento é inteiro
        valor = request.form.get('valor')

        conn = db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO fatura (cartao_id, mes, ano, dia_vencimento, valor)
                VALUES (?, ?, ?, ?, ?)
            ''', (cartao_id, mes, ano, dia_vencimento, valor))
            conn.commit()
            fatura_id = cursor.lastrowid

            cursor.execute("SELECT nome FROM cartoes_credito WHERE id = ?", (cartao_id,))
            cartao = cursor.fetchone()
            nome_cartao = cartao[0] if cartao else 'Desconhecido'

            # Criar objeto date com os valores convertidos
            data_vencimento = date(ano, mes, dia_vencimento)
            descricao = f"Fatura {nome_cartao} {mes:02}/{ano}"

            # Chamar a função incluir_contas_a_pagar
            incluir_contas_a_pagar(fatura_id, descricao, data_vencimento, valor)

            return redirect(f'/faturas/{cartao_id}')
        except Exception as e:
            conn.rollback()
            return f"Erro ao inserir fatura: {e}"
        finally:
            conn.close()

    return render_template('incluir_fatura.html', title="Incluir Fatura", cartao_id=cartao_id)


@app.route('/atualizar_limite/<int:cartao_id>', methods=['POST'])
def atualizar_limite(cartao_id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))  # Caso o usuário não esteja autenticado

    limite_total = request.form.get('limite_total')

    if not limite_total or float(limite_total) <= 0:
        return "Erro: O limite do cartão deve ser maior que zero.", 400

    conn = db_connection()
    cursor = conn.cursor()

    try:
        # Atualiza o limite do cartão
        cursor.execute('''
            UPDATE cartoes_credito
            SET limite_total = ?
            WHERE id = ?
        ''', (float(limite_total), cartao_id))
        conn.commit()
        # Redireciona corretamente para a rota de faturas usando url_for
        return redirect(url_for('cartoes'))
    except Exception as e:
        conn.rollback()
        return f"Erro ao atualizar limite: {e}"
    finally:
        conn.close()

def incluir_contas_a_pagar(fatura_id, descricao, data_vencimento, valor_fatura):

    if 'usuario_id' not in session:
        return redirect('/')
    
    # Conectar ao banco de dados
    db_path = 'contas.db'  # Substitua pelo caminho correto
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        usuario_id = session['usuario_id']
        
        print(f'fatura_id:{fatura_id}, descricao: {descricao}, valor: {valor_fatura}, vencimento: {data_vencimento}, status: não pago, usuario_id: {usuario_id}')

        # Inserir na tabela contas
        cursor.execute('''
            INSERT INTO contas (fatura_id, descricao, valor, vencimento, status, usuario_id)
            VALUES (?, ?, ?, ?, 'não pago', 1)
        ''', (int(fatura_id), descricao, float(valor_fatura), data_vencimento))

        # Commitar transacao
        conn.commit()
        print("Contas a pagar inserido com sucesso!")
    
    except Exception as e:
        print(f"Erro ao inserir contas a pagar: {e}")
        conn.rollback()
    
    finally:
        conn.close()


def validar_cpf(cpf):
    """ Validação simples do CPF """
    cpf = re.sub(r'[^0-9]', '', cpf)  # Remove caracteres não numéricos
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    return True  # Adicione a lógica completa, se necessário

@app.route('/cadastro_usuario', methods=['GET', 'POST'])
def cadastro_usuario():
    if request.method == 'POST':
        cpf = request.form.get('cpf')
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')

        # Verificar campos obrigatórios
        if not cpf or not nome or not email or not senha:
            return render_template('cadastro_usuario.html', error="Todos os campos são obrigatórios!")

        # Validar CPF
        if not validar_cpf(cpf):
            return render_template('cadastro_usuario.html', error="CPF inválido!")

        # Gerar hash da senha
        senha_hash = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt())

        try:
            conn = db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO usuarios (cpf, nome, email, senha) VALUES (?, ?, ?, ?)",
                (cpf, nome, email, senha_hash)
            )
            conn.commit()
            return redirect('/?success=1')
        except Exception as e:
            print(f"Erro ao inserir na tabela usuarios: {e}")
            return render_template('cadastro_usuario.html', error="Erro ao cadastrar o usuário. CPF ou Email já existente.")
        finally:
            conn.close()

    return render_template('cadastro_usuario.html')


if __name__ == '__main__':
    app.run(debug=True)
