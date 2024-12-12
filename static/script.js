document.addEventListener('DOMContentLoaded', function () {
    const tabela = document.getElementById('tabela-contas');
    const mesAnoSpan = document.getElementById('mes-ano');
    const totalContas = document.getElementById('total-contas');
    const totalValor = document.getElementById('total-valor');
    const totalPago = document.getElementById('total-pago');
    const totalNaoPago = document.getElementById('total-nao-pago');
    const modal = document.getElementById('modal-incluir');
    const btnIncluir = document.getElementById('btn-incluir');
    const fecharModal = document.getElementById('fechar-modal');
    const formIncluir = document.getElementById('form-incluir');

    let mesAtual = new Date().getMonth() + 1;
    let anoAtual = new Date().getFullYear();

    function nomeMes(mes) {
        const meses = [
            'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
            'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
        ];
        return meses[mes - 1];
    }

    function carregarResumo(mes = mesAtual, ano = anoAtual) {
        mesAtual = mes;
        anoAtual = ano;

        const mesFormatado = String(mesAtual).padStart(2, '0');
        console.log(`Carregando resumo para ${mesFormatado}/${anoAtual}`);

        fetch(`/api/resumo?mes=${mesFormatado}&ano=${anoAtual}`)
            .then(res => res.json())
            .then(data => {
                const { resumo, contas } = data;

                mesAnoSpan.textContent = `${nomeMes(mesAtual)} / ${anoAtual}`;
                totalContas.textContent = resumo.total_contas || 0;
                totalValor.textContent = resumo.total_valor?.toFixed(2) || '0.00';
                totalPago.textContent = resumo.total_pago?.toFixed(2) || '0.00';
                totalNaoPago.textContent = resumo.total_nao_pago?.toFixed(2) || '0.00';

                tabela.innerHTML = '';
                contas.forEach(conta => {
                    const hoje = new Date().toISOString().split('T')[0];
                    const isVencida = new Date(conta.vencimento) < new Date(hoje) && conta.status === "não pago";
                    tabela.innerHTML += `
                        <tr style="color: ${isVencida ? 'red' : 'black'};">
                            <td>${conta.descricao}</td>
                            <td>R$ ${conta.valor.toFixed(2)}</td>
                            <td>${conta.vencimento}</td>
                            <td>${conta.status}</td>
                        </tr>
                    `;
                });
            });
    }

    function mudarMes(direcao) {
        if (direcao === 'proximo') {
            if (mesAtual === 12) {
                mesAtual = 1;
                anoAtual += 1;
            } else {
                mesAtual += 1;
            }
        } else if (direcao === 'anterior') {
            if (mesAtual === 1) {
                mesAtual = 12;
                anoAtual -= 1;
            } else {
                mesAtual -= 1;
            }
        }
        carregarResumo();
    }

    document.getElementById('prev-mes').addEventListener('click', function () {
        mudarMes('anterior');
    });

    document.getElementById('next-mes').addEventListener('click', function () {
        mudarMes('proximo');
    });

    // Abrir o modal
    btnIncluir.addEventListener('click', function () {
        modal.style.display = 'flex';
    });

    // Fechar o modal
    fecharModal.addEventListener('click', function () {
        modal.style.display = 'none';
    });

    // Fechar o modal clicando fora do conteúdo
    window.addEventListener('click', function (e) {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });

    // Salvar a nova conta
    formIncluir.addEventListener('submit', function (e) {
        e.preventDefault();
        const descricao = document.getElementById('descricao').value;
        const valor = parseFloat(document.getElementById('valor').value);
        const vencimento = document.getElementById('vencimento').value;

        fetch('/api/contas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ descricao, valor, vencimento })
        })
            .then(res => res.json())
            .then(data => {
                alert(data.message);
                modal.style.display = 'none';
                carregarResumo(); // Atualiza a lista de contas
            });
    });

    carregarResumo(); // Inicializa com o mês atual
});