import sqlite3
import os

# Caminho do banco compartilhado
db_path = r"C:\Users\prisc\OneDrive - tce.mg.gov.br\Projeto_Manuais_Automotivos_IA\data_output\FichasTecnicas\dados.db"

# Cria a pasta se não existir
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# Conecta ao SQLite
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Cria tabela de veículos
cursor.execute('''
CREATE TABLE IF NOT EXISTS veiculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marca TEXT,
    modelo TEXT,
    ano INTEGER,
    manual_url TEXT,
    site_url TEXT,
    imagem_urls TEXT,  -- várias URLs separadas por '|'
    preco REAL
    criado_data DATETIME DEFAULT (datetime('now','localtime'))
)
''')

conn.commit()
conn.close()