import psutil
from time import sleep,time
import json
from socket import gethostname
from platform import system
from os import getenv, path
from dotenv import load_dotenv
from boto3 import Session
from datetime import datetime
from mysql.connector import connect
from atlassian import Jira
from requests import HTTPError
load_dotenv()

jira = Jira(
    url = getenv('URL_JIRA'), 
    username = getenv('EMAIL_JIRA'),
    password = getenv('TOKEN_JIRA')
)

mydb = connect(
    user=getenv('USUARIO_BANCO'), 
    password=getenv('SENHA_BANCO'), 
    host=getenv('HOST_BANCO'),
    database=getenv('NOME_BANCO'),
    port=getenv('PORTA_BANCO')
)

session = Session(
    aws_access_key_id=getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=getenv('AWS_SECRET_ACCESS_KEY'),
    aws_session_token=getenv('AWS_SESSION_TOKEN'),
    region_name=getenv('AWS_REGION')
)

cursor = mydb.cursor()
s3_client = session.client('s3')

nomeMaquina = gethostname()
sistemaOperacional = system()

freqTotalProcessador = round(psutil.cpu_freq().max, 2)
memortiaTotal = round(psutil.virtual_memory().total/pow(10, 9),0)

if(sistemaOperacional == "Windows"):
    disco = psutil.disk_usage('C:\\')
else:
    disco = psutil.disk_usage('/')

discoTotal = round(disco.total/pow(10, 9), 0)

cursor.execute(f"SELECT * FROM CaixaEletronico WHERE nomeEquipamento = '{nomeMaquina}'")
for i in cursor.fetchall():
    print(i)

if cursor.rowcount < 1: 
    cursor.execute(f"INSERT INTO CaixaEletronico VALUES (default, '{nomeMaquina}', '{sistemaOperacional}', {memortiaTotal}, {discoTotal}, {freqTotalProcessador}, 1)") 
    mydb.commit()
    idEquipamento = cursor.lastrowid
else: 
    cursor.execute(f"SELECT idCaixa FROM CaixaEletronico WHERE nomeEquipamento LIKE '{nomeMaquina}'")
    idEquipamento_tupla = cursor.fetchone()
    idEquipamento = idEquipamento_tupla[0]


def get_network_transfer_rate(interval=1):
    net_io_start = psutil.net_io_counters()
    bytes_sent_start = net_io_start.bytes_sent
    bytes_recv_start = net_io_start.bytes_recv
    
    sleep(interval)
    
    net_io_end = psutil.net_io_counters()
    bytes_sent_end = net_io_end.bytes_sent
    bytes_recv_end = net_io_end.bytes_recv
    
    bytes_sent_per_sec = (bytes_sent_end - bytes_sent_start) / interval
    bytes_recv_per_sec = (bytes_recv_end - bytes_recv_start) / interval
    
    return bytes_sent_per_sec, bytes_recv_per_sec

def upload_to_s3(file_name, bucket, s3_client):
    try:
        s3_client.upload_file(file_name, bucket, file_name)
        print(f"Arquivo '{file_name}' enviado com sucesso para o bucket '{bucket}'!")
    except FileNotFoundError:
        print(f"Arquivo '{file_name}' não encontrado.")
    except Exception as e:
        print(f"Erro ao enviar o arquivo para o S3: {e}")

def ler_json_existente(file_name):
    if path.exists(file_name):
        with open(file_name, 'r') as json_file:
            try:
                return json.load(json_file)
            except json.JSONDecodeError:
                return []  # Retorna uma lista vazia se o JSON estiver malformado
    return []

def adicionar_ao_json(file_name, novos_dados):
    dados_existentes = ler_json_existente(file_name)  
    dados_existentes.append(novos_dados) 
    
    with open(file_name, 'w') as json_file:
        json.dump(dados_existentes, json_file, indent=4)

def main():
    i = 0
    intervalo = 10
    upload_interval = 300
    file_name = '/home/presilli/Documentos/ProjetoGrupo/dados.json'
    
    while True:
        i += 1
        porcent_cpu = psutil.cpu_percent()
        memoria = psutil.virtual_memory()
        freq_cpu = psutil.cpu_freq().current
        tempo_atividade = psutil.boot_time()
        upload_rate, download_rate = get_network_transfer_rate()
        dataHora = datetime.now()
        data_e_hora_em_texto = dataHora.strftime('%d/%m/%Y %H:%M:%S')


        upload_kbps = (upload_rate * 8) / 1024  # de bytes para kilobits
        download_kbps = (download_rate * 8) / 1024  # de bytes para kilobits

        tempo_atual = time()
        uptime_s = tempo_atual - tempo_atividade

        if sistemaOperacional == "Windows":
            disco = psutil.disk_usage('C:\\')
        else:
            disco = psutil.disk_usage('/')

        if(round(porcent_cpu, 2) > 80 and round(memoria.percent, 2) > 80):
            cursor.execute(f"INSERT INTO Alerta VALUES (DEFAULT, 'Memória e CPU', 'Ambos acima de 80%', {idRegistro}, {idEquipamento})")
            mydb.commit()
            repeticao_CPU_RAM+=1

            if(repeticao_CPU_RAM >= 5):
                    
                jira.issue_create(
                    fields={
                        'project': {
                            'key': 'VAULT' #SIGLA DO PROJETO
                        },
                        'summary': 'Alerta de CPU e RAM',
                        'description': 'CPU e RAM acima da média, necessario olhar com atenção esse Caixa em específico caso precise de manutenção em breve',
                        'issuetype': {
                            "name": "Task"
                        },
                    }
                )
                repeticao_CPU_RAM=0

        elif (round(memoria.percent, 2) > 80):
            cursor.execute(f"INSERT INTO Alerta VALUES (DEFAULT, 'Memória', 'Memória RAM acima de 80%', {idRegistro}, {idEquipamento})")
            mydb.commit()
            repeticao_RAM+=1

            if(repeticao_RAM >= 5):
                try:
                    jira.issue_create(
                        fields={
                        'project': {
                            'key': 'VAULT' #SIGLA DO PROJETO
                        },
                        'summary': 'Alerta de RAM',
                        'description': 'Memória RAM acima da média, analisar comportamento estranho e verificar se é frequente',
                        'issuetype': {
                            "name": "Task"
                        },
                    }
                )
                except HTTPError as e:
                    print(e.response.text)

                repeticao_RAM=0

        elif(round(porcent_cpu, 2) > 80):
            cursor.execute(f"INSERT INTO Alerta VALUES (DEFAULT, 'CPU', 'CPU acima de 80%', {idRegistro}, {idEquipamento})")
            mydb.commit()
            repeticao_CPU+=1

            if(repeticao_CPU >= 5):
                        
                jira.issue_create(
                    fields={
                        'project': {
                            'key': 'VAULT' #SIGLA DO PROJETO
                        },
                        'summary': 'Alerta de CPU',
                        'description': 'Processador acima da média, possível ataque no Caixa ou erro de Hardware.',
                        'issuetype': {
                            "name": "Task"
                        },
                    }
                )
            repeticao_CPU=0

        captura = {
            "idCaixaEletronico": idEquipamento,
            "dataHora": data_e_hora_em_texto,
            "tempo_atividade": round(uptime_s, 2),
            "intervalo": intervalo,
            "porcCPU": porcent_cpu,
            "freqCpu": round(freq_cpu, 2) ,
            "totalMEM": round(memoria.total / (1024 ** 3), 2),
            "usadaMEM": round(memoria.used / (1024 ** 3), 2),
            "porcMEM": memoria.percent,
            "totalDisc": round(disco.total / (1024 ** 3), 2),
            "usadoDisc": round(disco.used / (1024 ** 3), 2),
            "usoDisc": disco.percent,
            "upload_kbps": round(upload_kbps, 2),
            "download_kbps": round(download_kbps, 2)
        }

        # Adiciona a captura ao arquivo JSON sem sobrescrever os dados existentes
        adicionar_ao_json(file_name, captura)
        
        current_time = time.time()
        if current_time - last_upload_time >= upload_interval:
            upload_to_s3(file_name, getenv('AWS_BUCKET_NAME'), s3_client)
            last_upload_time = current_time

        print(f"Captura {i} realizada com sucesso.")
        sleep(intervalo)

if __name__ == "__main__":
    main()
