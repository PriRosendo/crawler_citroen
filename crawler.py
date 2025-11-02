# Crawler.py

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import json
import time
import re 
import os 
from supabase import create_client, Client 
from urllib.parse import urljoin

# --- LISTAS DE CLASSIFICAÇÃO (Mantidas) ---
TURBO_KEYWORDS_RAW = [
    'T', 'TC', 'TCI', 'TFSI', 'TSI', 'TGI', 'TGDI', 'GDI-T', 'T-GDI', 'GTDi', 'EcoBoost', 
    'TwinPower Turbo', 'TurboJet / MultiAir Turbo', 'THP', 'HDi', 'BlueHDi', 'CDTi', 'dCi', 
    'TDCi', 'CDI', 'd-4D', 'DTI', 'SDI', 'SDTI', 'IDTEC', 'CRDi', 'TD4', 'Di-D', 
    'Boosterjet / Booster Hybrid', 'TURBOJET', 'TURBODIESEL', 'TDI', 'TD', 'TURBOMAX',
    'TURBO'
]
TURBO_KEYWORDS_FLAT = []
for item in TURBO_KEYWORDS_RAW:
    parts = item.split(' / ')
    for part in parts:
        TURBO_KEYWORDS_FLAT.append(part.strip().upper())
TURBO_KEYWORDS_SORTED = sorted(list(set(TURBO_KEYWORDS_FLAT)), key=len, reverse=True)

FUEL_REGEX_LIST = [
    {"tipo": "Híbrido", "regex": r"\b(h[ií]brido|hybrid|phev|hev|mhev|plug[-\s]?in|48v)\b"},
    {"tipo": "Elétrico", "regex": r"\b(el[eé]trico|eléctrico|ev\b|bev\b|motor\s*el[eé]trico|bateria)\b"},
    {"tipo": "Flex", "regex": r"\b(flex|bi[-\s]?fuel|flex[-\s]?fuel|gasolina\/[aá]lcool|etanol\/gasolina)\b"},
    {"tipo": "Diesel", "regex": r"\b(diesel|dsl|gas[oó]leo|tdi|hdi|cdti|tdci|bluehdi|dci|crdi|ddi|di-d)\b"},
    {"tipo": "GNV", "regex": r"\b(gnv|cng|ngv|g[aá]s\s*natural|g[aá]s\s*veicular)\b"},
    {"tipo": "Gasolina", "regex": r"\b(gasolina|petrol|gasoline|nafta)\b"},
    {"tipo": "Etanol/Álcool", "regex": r"\b(et[aá]nol|[aá]lcool|ethanol)\b"},
    {"tipo": "Hidrogênio", "regex": r"\b(hidrog[eê]nio|hydrogen|fuel\s*cell|fcev)\b"}
]
# --- FIM DAS LISTAS ---

# --- MAPA DE FALLBACK DE MANUAIS (Mantido) ---
MANUAL_FALLBACK_MAP = {
    # Modelo C3
    ('C3', 'c3 you! t200'): "https://www.citroen.com.br/content/dam/citroen/products/ficha-t%C3%A9cnica/Ficha-T%C3%A9cnica-C3-You-CY25-PL8.pdf",
    ('C3', 'c3 feel'): "https://www.citroen.com.br/content/dam/citroen/products/ficha-t%C3%A9cnica/Ficha-T%C3%A9cnica-C3-Feel-CY25-PL8.pdf",
    ('C3', 'c3 live pack'): "https://www.citroen.com.br/content/dam/citroen/products/ficha-t%C3%A9cnica/Ficha-T%C3%A9cnica-C3-Live-Pack-CY25-PL8.pdf",
    ('C3', 'c3 live'): "https://www.citroen.com.br/content/dam/citroen/products/ficha-t%C3%A9cnica/Ficha-T%C3%A9cnica-C3-Live-CY25-PL8.pdf",

    # Modelo Aircross
    ('Aircross', 'shine'): "https://www.citroen.com.br/content/dam/citroen/products/ficha-t%C3%A9cnica/Ficha-Tecnica-Aircross-Shine-CY25-PL8.pdf",
    ('Aircross', 'feel pack'): "https://www.citroen.com.br/content/dam/citroen/products/ficha-t%C3%A9cnica/Ficha-Tecnica-Aircross-Feel-Pack-CY25-PL8.pdf", # "Feel 7"
    ('Aircross', 'feel'): "https://www.citroen.com.br/content/dam/citroen/products/ficha-t%C3%A9cnica/Ficha-Tecnica-Aircross-Feel-CY25-PL8.pdf", # "Feel 5"

    # Modelo Basalt
    ('Basalt', 'shine turbo'): "https://www.citroen.com.br/content/dam/citroen/paginas/showrooms/basalt/ficha-tecnica/Ficha-T%C3%A9cnica-Basalt-Shine-Turbo-AT-CY25.pdf",
    ('Basalt', 'feel turbo'): "https://www.citroen.com.br/content/dam/citroen/paginas/showrooms/basalt/ficha-tecnica/Ficha-T%C3%A9cnica-Basalt-Feel-Turbo-AT-CY25.pdf",
    ('Basalt', 'feel'): "https://www.citroen.com.br/content/dam/citroen/products/ficha-t%C3%A9cnica/Ficha-T%C3%A9cnica-Basalt-Feel-MT-CY25-1.pdf",
}
# --- FIM DO MAPA ---

# --- FUNÇÕES AUXILIARES (Mantidas) ---
def get_motor_value(motor_string):
    if not motor_string: return None
    try:
        match_displacement = re.search(r"\b(\d\.\d+)\b", motor_string) 
        match_electric_kw = re.search(r"(\d+\s*kW~\d+\s*cv)", motor_string, re.IGNORECASE)
        if match_displacement:
            return match_displacement.group(1)
        elif match_electric_kw:
            return match_electric_kw.group(1)
        elif "elétrico" in motor_string.lower():
            return "Elétrico"
    except Exception:
        pass
    return None

def get_turbo_value(motor_string):
    if not motor_string: return None
    try:
        motor_string_upper = motor_string.upper()
        motor_part_only = motor_string_upper.split("CÂMBIO")[0].split("AUTOMÁTICO")[0].split("MANUAL")[0]
        for term in TURBO_KEYWORDS_SORTED:
            if re.search(r'\b' + re.escape(term) + r'\b', motor_part_only):
                return "Sim"
    except Exception:
        pass
    return None

def get_fuel_value(motor_string):
    if not motor_string: return None
    try:
        for fuel in FUEL_REGEX_LIST:
            if re.search(fuel["regex"], motor_string, re.IGNORECASE):
                return fuel["tipo"]
    except Exception:
        pass
    return None
# --- FIM DAS FUNÇÕES ---

# --- CONEXÃO SUPABASE (Mantida) ---
try:
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        supabase = None
        print("⚠️ AVISO: SUPABASE_URL ou SUPABASE_KEY não definidos. A verificação de duplicatas está DESATIVADA.")
    else:
        supabase: Client = create_client(url, key)
        print("✔️ Conectado ao Supabase com sucesso.")
except Exception as e:
    print(f"❌ ERRO: Falha ao inicializar o Supabase: {e}")
    supabase = None
# --- FIM DA CONEXÃO ---


# --- CONFIG DO NAVEGADOR (MODO NUVEM) ---
chrome_options = Options()
chrome_options.add_argument("--headless=new")  
chrome_options.add_argument("--no-sandbox") 
chrome_options.add_argument("--disable-dev-shm-usage") 
chrome_options.add_argument("--window-size=1920,1080") 
chrome_options.add_argument("--start-maximized")

driver = webdriver.Chrome(service=Service(), options=chrome_options)
# --- FIM DA CONFIG ---

wait = WebDriverWait(driver, 30)
wait_short = WebDriverWait(driver, 10) 

driver.get("https://www.citroen.com.br/")

# === 1️⃣ CLICAR NO MENU PRINCIPAL ===
try:
    try:
        print("Aguardando o loader da página inicial desaparecer...")
        wait.until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, "div[data-testid='hub-loader']"))
        )
        print("✔️ Loader desapareceu.")
    except TimeoutException:
        print("⚠️ Loader não desapareceu a tempo, mas tentando continuar...")

    menu_button = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'li[title="Menu"] .menu-hamburger__cta'))
    )
    menu_button.click() 

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.menu-hamburger__options")))
    print("✔️ Menu principal aberto.")
    time.sleep(2.5) 

except Exception as e:
    print(f"Erro ao abrir menu principal: {e}")
    driver.quit()
    exit()

# === 2️⃣ CLICAR NO “+” DO ITEM CARROS ===
try:
    carros_expand = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//div[contains(@class,'menu-hamburger__options__item') and contains(.,'Carros')]//button[@title='Expand item']"
        ))
    )

    print("Botão 'Carros' pronto. Tentando clique normal...")
    carros_expand.click() 
    print("✔️ Clicou em '+' de Carros.")

    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.menu-hamburger__options__category")))
    time.sleep(2.5) 

except Exception as e:
    print(f"Erro ao expandir 'Carros': {e}")
    driver.quit()
    exit()

# === 3️⃣ EXTRAIR OS MODELOS ===
print("--- INICIANDO EXTRAÇÃO DE MODELOS (PASSO 3) ---")
categories = driver.find_elements(By.CSS_SELECTOR, "li.menu-hamburger__options__category")
result = {}

for cat in categories:
    try:
        tipo = cat.find_element(By.TAG_NAME, "span").text.strip(": ")
        try:
            wait_short.until(EC.visibility_of_all_elements_located((By.CSS_SELECTOR, "li.menu-hamburger__options__sub-item a")))
        except TimeoutException: print(f"      ⚠️ Links não ficaram visíveis a tempo para a categoria '{tipo}'. Pulando categoria."); continue
        links = cat.find_elements(By.CSS_SELECTOR, "li.menu-hamburger__options__sub-item a")
        for link in links:
            try:
                modelo_menu = link.get_attribute('textContent').strip()
                url = link.get_attribute("href")
                if not url: print(f"      ⚠️ Link com texto '{modelo_menu}' tem URL vazia. Pulando."); continue
                if "veiculos-passeio" in url or "veiculos-utilitarios" in url:
                    if modelo_menu: 
                        result[modelo_menu] = {"tipo_modelo": tipo, "site_url": url}
                        print(f"      ✔️ Modelo encontrado: {modelo_menu} ({tipo})")
                    else: print(f"      ⚠️ Modelo com nome vazio ignorado (textContent). URL: {url}")
                else:
                    if modelo_menu: print(f"      Ignorando link não-veículo: {modelo_menu} ({url})")
                    else: print(f"      Ignorando link não-veículo sem nome. URL: {url}")
            except StaleElementReferenceException: print("      ⚠️ Stale Element ao processar um link. Tentando continuar..."); continue
            except Exception as e_link: print(f"      ❌ Erro ao processar um link individual: {e_link}")
    except StaleElementReferenceException: print("      ⚠️ Stale Element ao processar uma categoria. Tentando continuar..."); continue
    except Exception as e: print(f"Erro geral ao processar categoria de menu: {e}")

# === 4️⃣ NAVEGAR EM CADA MODELO E EXTRAIR DADOS ===
print("\n--- INICIANDO EXTRAÇÃO DE VERSÕES (MÉTODO LÓGICA DUPLA) ---")

modelos_para_processar = list(result.keys())
if not modelos_para_processar: print("      ❌ ERRO: Nenhum modelo foi encontrado no Passo 3. Verifique o menu e os seletores.")

for modelo in modelos_para_processar:
    site_url = result[modelo]["site_url"]; print(f"\n➡️ Processando modelo: {modelo}"); print(f"      URL: {site_url}")
    lista_versoes = []
    
    nomes_vistos = set() 
    
    try:
        driver.get(site_url)
        titulo_versoes = None
        for _ in range(10):
            try:
                titulo_versoes = driver.find_element(By.XPATH, "//*[contains(translate(., 'VERSÕES', 'versões'), 'versão') and (self::h1 or self::h2 or self::h3 or contains(@class, 'font-h1') or contains(@class, 'font-h2') or contains(@class, 'font-h3'))]")
                if titulo_versoes: print("      ✔️ Título 'Versão(ões)' encontrado."); driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", titulo_versoes); time.sleep(1.5); break
            except NoSuchElementException: print("      ... Rolando para encontrar a seção 'versão(ões)' ..."); driver.execute_script("window.scrollBy(0, window.innerHeight * 0.8);"); time.sleep(1)
        if not titulo_versoes: print("      ⚠️  Não foi possível encontrar o título 'versão(ões)' após rolar a página. Tentando achar o componente mesmo assim.")
        try:
            carousel_element = driver.find_element(By.CSS_SELECTOR, "div.next-gen-carousel"); print("      ✔️ Encontrado 'next-gen-carousel'.")
            
            slides = carousel_element.find_elements(By.XPATH, ".//div[@data-testid='slide'] | .//div[@data-testid='next-gen-container-component' and @help-text='versão']")
            print(f"      ✔️ Encontrados {len(slides)} slides (buscando por data-testid='slide' ou help-text='versão'). Extraindo dados de cada um...")
            
            for slide in slides:
                try:
                    nome = driver.execute_script("return arguments[0].querySelector('h1.font-h1, h1, h2.font-h2, h2, h3.font-h3, h3, span.font-h1, span.font-h2, span.font-h3')?.textContent.trim()", slide)
                    
                    if nome and nome in nomes_vistos:
                        print(f"         - Aviso: Versão '{nome}' duplicada. Pulando.")
                        continue 
                    if nome:
                        nomes_vistos.add(nome) 
                    
                    if supabase and nome:
                        try:
                            response = supabase.table('veiculos').select('id', count='exact').eq('marca', 'citroen').eq('modelo', modelo).eq('versao', nome).execute()
                            if response.count > 0:
                                print(f"         - Aviso: Versão '{nome}' (Modelo: {modelo}) JÁ EXISTE no Supabase. Pulando.")
                                continue 
                        except Exception as e_supa:
                            print(f"         - ⚠️ ERRO ao consultar Supabase para '{nome}': {e_supa}. Continuando a coleta...")

                    preco = driver.execute_script("return arguments[0].querySelector('span.font-h2, p.font-h2, div.font-h2, span.font-h3, p.font-h3, div.font-h3, h1 b')?.textContent.trim()", slide)
                    imagem_url = driver.execute_script("return arguments[0].querySelector('img.next-gen-media, div.chameleon-image img')?.getAttribute('src')", slide)
                    
                    manual_url = None
                    try:
                        pdf_link_el = slide.find_element(By.XPATH, ".//a[contains(@href, '.pdf') and (contains(translate(., 'FICHA', 'ficha'), 'ficha'))]")
                        pdf_href = pdf_link_el.get_attribute('href');
                        if pdf_href and pdf_href != '#': manual_url = urljoin(driver.current_url, pdf_href); print(f"         - PDF Ficha Técnica encontrado DENTRO do slide para '{nome}'.")
                    except NoSuchElementException: pass
                    except Exception as e_pdf_slide: print(f"         - Erro ao procurar PDF no slide: {e_pdf_slide}")


                    motorizacao = None
                    motor = None
                    pneus = None
                    pneus_diametro = None
                    ar_condicionado = None 
                    turbo = None 
                    combustivel = None 
                    outras_caracteristicas = [] 

                    try:
                        spec_spans = slide.find_elements(By.XPATH, ".//div[contains(@class, 'image-wrapper')]/following-sibling::div[contains(@class, 'next-gen-text')]/span[contains(@class, 'font-body-sm') and @data-testid='next-gen-text-id']")
                        
                        for span in spec_spans:
                            spec_text = span.get_attribute('textContent').strip()
                            
                            if not spec_text:
                                continue
                            
                            spec_text_lower = spec_text.lower()
                            item_classificado = False 

                            if spec_text_lower.startswith("motor"):
                                motorizacao = spec_text
                                item_classificado = True 
                                motor = get_motor_value(spec_text)
                                turbo = get_turbo_value(spec_text)
                                combustivel = get_fuel_value(spec_text)
                            elif "rodas" in spec_text_lower or "pneu" in spec_text_lower:
                                pneus = spec_text
                                match = re.search(r"(\d+)[”\"]", spec_text) 
                                if not match:
                                    match = re.search(r"(\d+)\s*(em|de)", spec_text) 
                                if match:
                                    pneus_diametro = match.group(1)
                                item_classificado = True
                            elif spec_text_lower.startswith("ar-condicionado"):
                                valor_ar = spec_text.lower().replace("ar-condicionado", "").strip()
                                if "digital" in valor_ar:
                                    ar_condicionado = "Digital"
                                elif valor_ar: 
                                    ar_condicionado = valor_ar.capitalize()
                                else: 
                                    ar_condicionado = "Sim" 
                                item_classificado = True
                            if not item_classificado:
                                outras_caracteristicas.append(spec_text)

                    except NoSuchElementException:
                        pass 
                    except Exception as e_spec:
                        print(f"         - Erro ao processar itens de especificação (Motor, Rodas, etc.) para '{nome}': {e_spec}")

                    if not manual_url and nome:
                        try:
                            nome_normalizado = nome.lower().strip().replace('!', '')
                            key = (modelo, nome_normalizado)
                            fallback_url = MANUAL_FALLBACK_MAP.get(key)
                            if fallback_url:
                                manual_url = fallback_url
                                print(f"         - Info: Manual não encontrado no site. Usando URL de fallback para '{nome}'.")
                        except Exception as e_map:
                             print(f"         - Erro ao tentar aplicar fallback de manual: {e_map}")


                    if nome: 
                        print(f"         - Versão: {nome} (Preço: {preco or 'N/A'})")
                        
                        lista_versoes.append({
                            "marca": "citroen",
                            "modelo": modelo,
                            "versao": nome, 
                            "preco": preco or None, 
                            "imagem_url": imagem_url or None, 
                            "manual_url": manual_url,
                            "motorizacao": motorizacao,
                            "motor": motor,
                            "turbo": turbo,
                            "combustivel": combustivel, 
                            "pneus": pneus,
                            "pneus_diametro": pneus_diametro,
                            "ar_condicionado": ar_condicionado, 
                            "outras_caracteristicas": outras_caracteristicas 
                        })
                        
                    else: 
                        print("         - Aviso: Slide encontrado, mas sem nome. Pulando.")
                except Exception as e_inner: 
                    print(f"         - Erro ao processar um slide: {e_inner}")
        except NoSuchElementException:
            print("      ⚠️ 'next-gen-carousel' não encontrado. Procurando por 'hub-tabs-swiper'...")
            try:
                swiper_element = driver.find_element(By.CSS_SELECTOR, "div.hub-tabs-swiper"); print("      ✔️ Encontrado 'hub-tabs-swiper' (Padrão Jumpy).")
                tabs = swiper_element.find_elements(By.CSS_SELECTOR, "a.hub-button--tab-swiper")
                print(f"      ✔️ Encontradas {len(tabs)} abas (versões). Iterando e clicando...")
                for i in range(len(tabs)):
                    swiper_element_iter = driver.find_element(By.CSS_SELECTOR, "div.hub-tabs-swiper")
                    tabs_iter = swiper_element_iter.find_elements(By.CSS_SELECTOR, "a.hub-button--tab-swiper")
                    if i >= len(tabs_iter): print(f"         - Erro: Aba índice {i} não encontrada na re-busca."); continue
                    tab_to_click = tabs_iter[i]; tab_name = tab_to_click.text.strip()
                    print(f"           -> Clicando na aba: '{tab_name}'")
                    try:
                        driver.execute_script("arguments[0].click();", tab_to_click)
                        active_content_selector = f"div.tab-content-{i}.active"
                        active_content = wait_short.until(EC.visibility_of_element_located((By.CSS_SELECTOR, active_content_selector)))
                        wait_short.until(EC.presence_of_element_located((By.CSS_SELECTOR, f"{active_content_selector} div.hub-card-component")))
                        print(f"                ✔️ Conteúdo da aba '{tab_name}' está ativo.")
                        card = active_content.find_element(By.CSS_SELECTOR, "div.hub-card-component")
                        nome = driver.execute_script("return arguments[0].querySelector('h2.hub-card-title')?.textContent.trim()", card)
                        preco = None; imagem_url = driver.execute_script("return arguments[0].querySelector('div.hub-card-media img')?.getAttribute('src')", card)
                        manual_url = None
                        
                        if supabase and nome:
                            try:
                                response = supabase.table('veiculos').select('id', count='exact').eq('marca', 'citroen').eq('modelo', modelo).eq('versao', nome).execute()
                                if response.count > 0:
                                    print(f"         - Aviso: Versão '{nome}' (Modelo: {modelo}) JÁ EXISTE no Supabase. Pulando.")
                                    continue 
                            except Exception as e_supa:
                                print(f"         - ⚠️ ERRO ao consultar Supabase para '{nome}': {e_supa}. Continuando a coleta...")
                        
                        try:
                            pdf_link_el = card.find_element(By.XPATH, ".//a[.//span[contains(translate(., 'FICHA', 'ficha'), 'ficha')] or (self::a and contains(translate(., 'FICHA', 'ficha'), 'ficha'))]")
                            pdf_href = pdf_link_el.get_attribute('href')
                            if pdf_href and pdf_href.lower().endswith('.pdf') and pdf_href != '#':
                                manual_url = urljoin(driver.current_url, pdf_href)
                                print(f"                ✔️ PDF (href direto) encontrado para '{nome}'. URL: {manual_url}")
                            else:
                                print(f"                ... Link 'Ficha Técnica' encontrado para '{nome}'. Clicando para abrir PDF em nova aba...")
                                main_window = driver.current_window_handle
                                all_windows_before = set(driver.window_handles) 
                                try:
                                    driver.execute_script("arguments[0].click();", pdf_link_el)
                                    wait_short.until(EC.number_of_windows_to_be(len(all_windows_before) + 1))
                                    all_windows_after = set(driver.window_handles)
                                    new_window = list(all_windows_after - all_windows_before)[0] 
                                    driver.switch_to.window(new_window)
                                    time.sleep(2.5) 
                                    pdf_tab_url = driver.current_url
                                    if pdf_tab_url and (pdf_tab_url.lower().endswith('.pdf') or 'blob:' in pdf_tab_url.lower() or 'pdf' in pdf_tab_url.lower()):
                                        manual_url = pdf_tab_url 
                                        print(f"                ✔️ PDF (nova aba) capturado para '{nome}'. URL: {manual_url}")
                                    else:
                                        print(f"                ⚠️  Nova aba aberta, mas URL não parece PDF: {pdf_tab_url}")
                                    driver.close() 
                                    driver.switch_to.window(main_window) 
                                except TimeoutException:
                                    print(f"                ❌ Erro: Clicou em 'Ficha Técnica', mas nova aba não abriu a tempo.")
                                    if driver.current_window_handle != main_window:
                                        try: driver.switch_to.window(main_window)
                                        except Exception: pass 
                                except Exception as e_click:
                                    print(f"                ❌ Erro ao clicar e processar nova aba do PDF: {e_click}")
                                    if driver.current_window_handle != main_window:
                                        try: driver.switch_to.window(main_window)
                                        except Exception: pass
                        except NoSuchElementException: 
                            print(f"                - Aviso: Link 'Ficha técnica' não encontrado no card para '{nome}'.")
                        except Exception as e_pdf_card: 
                            print(f"                - Erro ao procurar PDF no card: {e_pdf_card}")
                        
                        if not manual_url and nome:
                            try:
                                nome_normalizado = nome.lower().strip().replace('!', '')
                                key = (modelo, nome_normalizado)
                                fallback_url = MANUAL_FALLBACK_MAP.get(key)
                                if fallback_url:
                                    manual_url = fallback_url
                                    print(f"         - Info: Manual não encontrado no site. Usando URL de fallback para '{nome}'.")
                            except Exception as e_map:
                                print(f"         - Erro ao tentar aplicar fallback de manual: {e_map}")

                        if nome: 
                            lista_versoes.append({
                                "marca": "citroen",
                                "modelo": modelo,
                                "versao": nome,
                                "preco": preco or None,
                                "imagem_url": imagem_url or None,
                                "manual_url": manual_url,
                                "motorizacao": None, 
                                "motor": None, 
                                "turbo": None,
                                "combustivel": None, 
                                "pneus": None, 
                                "pneus_diametro": None, 
                                "ar_condicionado": None, 
                                "outras_caracteristicas": [] 
                            })
                        else: 
                            print("                - Aviso: Card ativo, mas sem nome.")
                        time.sleep(0.5)
                    except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e_tab_content: print(f"         - Erro ao esperar/processar conteúdo da aba '{tab_name}': {type(e_tab_content).__name__}")
                    except Exception as e_inner_card: print(f"         - Erro geral ao processar aba/card '{tab_name}': {e_inner_card}")
            except NoSuchElementException: print(f"      ❌ Não foi possível encontrar 'hub-tabs-swiper'. Pulando modelo {modelo}.")
        comparativo_data = []
        try:
            print("      ... Procurando por botão de Comparativo ...")
            comparativo_button = None; possible_button_texts = ['COMPARATIVO ENTRE AS VERSÕES', 'Clique e compare as versões']
            button_xpath = " | ".join([f"//button[contains(., '{text}')]" for text in possible_button_texts])
            for _ in range(5):
                try:
                    comparativo_button = driver.find_element(By.XPATH, button_xpath)
                    if comparativo_button:
                        button_text_found = comparativo_button.text.strip(); print(f"      ✔️ Botão '{button_text_found}' encontrado.")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", comparativo_button); time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", comparativo_button); break
                except NoSuchElementException: driver.execute_script("window.scrollBy(0, window.innerHeight * 0.5);"); time.sleep(0.5)
            if not comparativo_button: print("      ⚠️  Botão de Comparativo não encontrado nesta página."); raise NoSuchElementException
            content_xpath = " | ".join([f"//button[contains(., '{text}')]/following-sibling::div[contains(@class, 'collapse-content')]" for text in possible_button_texts])
            content_area = wait.until(EC.visibility_of_element_located((By.XPATH, content_xpath))); print("      ✔️ Conteúdo do comparativo expandido.")
            try:
                table = content_area.find_element(By.TAG_NAME, "table"); print("      ✔️ Encontrado layout de Tabela no comparativo.")
                rows = table.find_elements(By.TAG_NAME, "tr")
                if not rows: raise NoSuchElementException("Tabela vazia")
                header_cells = rows[0].find_elements(By.XPATH, "./td | ./th"); version_names_table = [cell.text.strip() for cell in header_cells[1:]]; num_versions = len(version_names_table)
                if num_versions == 0: raise NoSuchElementException("Nenhuma versão no header da tabela")
                print(f"      ✔️ Encontradas {num_versions} versões na Tabela: {version_names_table}"); temp_comparativo_data = {name: {"versao_comparativo": name} for name in version_names_table}
                for data_row in rows[1:]:
                    cells = data_row.find_elements(By.TAG_NAME, "td");
                    if len(cells) < num_versions + 1: continue
                    spec_label = cells[0].text.strip().lower().replace('\n', ' '); spec_values = [cell.text.strip() for cell in cells[1:]]
                    for i in range(num_versions):
                        version_name = version_names_table[i]; spec_value = spec_values[i] if i < len(spec_values) else None
                        if not spec_value: continue
                        if "carga útil" in spec_label or "capacidade/carga" in spec_label: temp_comparativo_data[version_name]["carga_util"] = spec_value
                        
                        elif "motor" == spec_label or "motorização e câmbio" in spec_label:
                            temp_comparativo_data[version_name]["motorizacao"] = spec_value
                            temp_comparativo_data[version_name]["motor"] = get_motor_value(spec_value)
                            temp_comparativo_data[version_name]["turbo"] = get_turbo_value(spec_value)
                            temp_comparativo_data[version_name]["combustivel"] = get_fuel_value(spec_value)
                        
                        else: safe_label = spec_label.replace(' ', '_').replace('ç', 'c').replace('ã', 'a').replace('ê', 'e').replace('õ', 'o').replace('/','_'); temp_comparativo_data[version_name][safe_label] = spec_value
                comparativo_data = list(temp_comparativo_data.values())
                for v_data in comparativo_data: print(f"           - Comparativo (Tabela): {v_data.get('versao_comparativo')} (dados extraídos)")

                try:
                    print("         - Procurando PDFs no comparativo (Tabela)...")
                    last_row_cells = rows[-1].find_elements(By.TAG_NAME, "td")
                    if len(last_row_cells) == num_versions + 1: 
                        pdf_link_cells = last_row_cells[1:] 
                        for i in range(len(pdf_link_cells)):
                            version_name = version_names_table[i]
                            try:
                                pdf_link_el = pdf_link_cells[i].find_element(By.XPATH, ".//a[contains(translate(., 'FICHA', 'ficha'), 'ficha')]")
                                pdf_href = pdf_link_el.get_attribute('href')
                                if pdf_href and pdf_href != '#':
                                    pdf_url = urljoin(driver.current_url, pdf_href)
                                    temp_comparativo_data[version_name]["manual_url"] = pdf_url
                                    print(f"         - PDF (Tabela) encontrado para '{version_name}'.")
                            except NoSuchElementException:
                                print(f"         - PDF (Tabela) não encontrado para '{version_name}'.")
                    else:
                        print(f"         - Aviso (Tabela): Células da última linha ({len(last_row_cells)}) não batem com versões ({num_versions + 1}).")
                except Exception as e_pdf_table:
                    print(f"         - Erro ao buscar PDF no rodapé da tabela: {e_pdf_table}")

            except NoSuchElementException:
                print("      ⚠️ Layout de Tabela não encontrado. Procurando por layouts de Grid...")
                try:
                    grids_in_content = content_area.find_elements(By.CSS_SELECTOR, "div.next-gen-grid-container-vue"); num_grids = len(grids_in_content)
                    print(f"      ✔️ Encontrados {num_grids} grids dentro do comparativo.")
                    if num_grids == 1:
                        print("      ✔️ Detectado layout de Grid Único (Padrão Jumpy).")
                        grid = grids_in_content[0]; version_names_elements = grid.find_elements(By.CSS_SELECTOR, "h2.font-h2")
                        spec_columns = grid.find_elements(By.XPATH, "./div[.//span[contains(., 'Carga útil') or contains(., 'Motor')]]")
                        print(f"      ✔️ Encontradas {len(version_names_elements)} versões e {len(spec_columns)} colunas de dados (Grid Único).")
                        if len(version_names_elements) == len(spec_columns) and len(spec_columns) > 0:
                            for i in range(len(version_names_elements)):
                                name_el = version_names_elements[i]; col_el = spec_columns[i]; version_name = name_el.text.strip(); version_specs = {"versao_comparativo": version_name}
                                labels = col_el.find_elements(By.CSS_SELECTOR, "span.font-body-sm"); values = col_el.find_elements(By.CSS_SELECTOR, "p.font-body")
                                for label, value in zip(labels, values):
                                    spec_label = label.text.strip().lower().replace('\n', ' '); spec_value = value.text.strip()
                                    if "carga útil" in spec_label: version_specs["carga_util"] = spec_value
                                    
                                    elif "motor" == spec_label:
                                        version_specs["motorizacao"] = spec_value
                                        version_specs["motor"] = get_motor_value(spec_value)
                                        version_specs["turbo"] = get_turbo_value(spec_value)
                                        version_specs["combustivel"] = get_fuel_value(spec_value)
                                    
                                    else: safe_label = spec_label.replace(' ', '_').replace('ç', 'c').replace('ã', 'a').replace('ê', 'e').replace('õ', 'o'); version_specs[safe_label] = spec_value
                                print(f"           - Comparativo (Grid Único): {version_name} (dados extraídos)"); comparativo_data.append(version_specs)
                            
                            try:
                                print("         - Procurando PDFs no comparativo (Grid Único)...")
                                pdf_links_elements_grid = grid.find_elements(By.XPATH, ".//a[contains(translate(., 'FICHA', 'ficha'), 'ficha')]")
                                pdf_links_hrefs_grid = [urljoin(driver.current_url, el.get_attribute('href')) for el in pdf_links_elements_grid if el.get_attribute('href') and el.get_attribute('href') != '#']
                                
                                if len(pdf_links_hrefs_grid) == len(version_names_elements):
                                    for i in range(len(version_names_elements)):
                                        version_name = comparativo_data[i]["versao_comparativo"] 
                                        comparativo_data[i]["manual_url"] = pdf_links_hrefs_grid[i]
                                        print(f"         - PDF (Grid Único) encontrado para '{version_name}'.")
                                else:
                                    print(f"         - Aviso (Grid Único): Links PDF ({len(pdf_links_hrefs_grid)}) != Versões ({len(version_names_elements)}).")
                            except Exception as e_pdf_grid:
                                print(f"         - Erro ao buscar PDF no Grid Único: {e_pdf_grid}")

                        elif len(version_names_elements) != len(spec_columns): print(f"      ❌ Erro no comparativo (Grid Único): Nomes ({len(version_names_elements)}) e Colunas ({len(spec_columns)}) não batem.")
                    elif num_grids > 1:
                        print("      ✔️ Detectado layout de Múltiplos Grids (Padrão Jumper).")
                        first_grid = grids_in_content[0]; data_grids = grids_in_content[1:-1] 
                        button_grid = grids_in_content[-1] 
                        version_names_elements_jumper = first_grid.find_elements(By.CSS_SELECTOR, "h2.font-h2"); version_names_jumper = [name.text.strip() for name in version_names_elements_jumper]; num_versions_jumper = len(version_names_jumper)
                        if num_versions_jumper == 0: raise NoSuchElementException("Nenhuma versão no header (Múltiplos Grids)")
                        print(f"      ✔️ Encontradas {num_versions_jumper} versões (Múltiplos Grids): {version_names_jumper}")
                        temp_comparativo_data = {name: {"versao_comparativo": name} for name in version_names_jumper}
                        print(f"      ✔️ Encontrados {len(data_grids)} grids de dados para processar.")
                        if not data_grids: raise NoSuchElementException("Nenhum grid de dados após cabeçalho")
                        
                        pdf_links_elements_jumper = button_grid.find_elements(By.XPATH, ".//a[contains(translate(., 'FICHA', 'ficha'), 'ficha')]")
                        pdf_links_hrefs_jumper = [urljoin(driver.current_url, el.get_attribute('href')) for el in pdf_links_elements_jumper if el.get_attribute('href') and el.get_attribute('href') != '#']

                        for data_grid in data_grids:
                            cells = data_grid.find_elements(By.XPATH, "./div[contains(@class, 'next-gen-container-vue')]")
                            for i in range(0, len(cells), num_versions_jumper):
                                row_cells = cells[i:i+num_versions_jumper]
                                if not row_cells or len(row_cells) < num_versions_jumper : continue
                                try: label_element = row_cells[0].find_element(By.XPATH, ".//p/strong"); spec_label = label_element.text.strip().lower().replace('\n', ' ')
                                except NoSuchElementException: continue
                                spec_values = []
                                for k, cell in enumerate(row_cells):
                                    try:
                                        p_elements = cell.find_elements(By.TAG_NAME, "p"); cell_value_parts = []
                                        is_label_cell = (k == 0)
                                        for p_index, p_el in enumerate(p_elements):
                                            is_label_p = False
                                            if is_label_cell:
                                                try: p_el.find_element(By.TAG_NAME, "strong"); is_label_p = True
                                                except NoSuchElementException: pass
                                            if not is_label_p: cell_value_parts.append(p_el.text.strip())
                                        cell_value = " ".join(cell_value_parts).strip()
                                        if not cell_value and len(p_elements) >= 1: cell_value = p_elements[-1].text.strip()
                                        spec_values.append(cell_value if cell_value else None)
                                    except Exception: spec_values.append(None)
                                for j in range(num_versions_jumper):
                                    version_name = version_names_jumper[j]; spec_value = spec_values[j] if j < len(spec_values) else None
                                    if not spec_value: continue
                                    # Mapeamento
                                    if "carga útil" in spec_label or "capacidade/carga" in spec_label: temp_comparativo_data[version_name]["carga_util"] = spec_value
                                    
                                    elif "motor" == spec_label or "motorização e câmbio" in spec_label:
                                        temp_comparativo_data[version_name]["motorizacao"] = spec_value
                                        temp_comparativo_data[version_name]["motor"] = get_motor_value(spec_value)
                                        temp_comparativo_data[version_name]["turbo"] = get_turbo_value(spec_value)
                                        temp_comparativo_data[version_name]["combustivel"] = get_fuel_value(spec_value)
                                    
                                    else: safe_label = spec_label.replace(' ', '_').replace('ç', 'c').replace('ã', 'a').replace('ê', 'e').replace('õ', 'o').replace('/','_'); temp_comparativo_data[version_name][safe_label] = spec_value
                        
                        if len(pdf_links_hrefs_jumper) == num_versions_jumper:
                            for j in range(num_versions_jumper):
                                version_name = version_names_jumper[j]; temp_comparativo_data[version_name]["manual_url"] = pdf_links_hrefs_jumper[j]
                                print(f"           - PDF Ficha Técnica encontrado NO COMPARATIVO para '{version_name}'.")
                        else: print(f"           - Aviso: PDF do Jumper. Links({len(pdf_links_hrefs_jumper)}) != Versões({num_versions_jumper}).")
                        
                        comparativo_data = list(temp_comparativo_data.values())
                        for v_data in comparativo_data: print(f"           - Comparativo (Múltiplos Grids): {v_data.get('versao_comparativo')} (dados extraídos)")
                    else: raise NoSuchElementException("Nenhum grid no comparativo")
                except NoSuchElementException: print("      ❌ Erro: Layout desconhecido ou falha na extração dentro do comparativo.")
        except (NoSuchElementException, TimeoutException): print("      ⚠️  Nenhum componente de Comparativo encontrado ou falha ao expandir.")
        except Exception as e_comp: print(f"      ❌ Erro inesperado ao processar o processar o comparativo: {e_comp}")

        # === 4c. LÓGICA MERGE ===
        if comparativo_data:
            print("      ... Juntando dados do comparativo com os dados das versões...")
            for spec_dict in comparativo_data:
                spec_name = spec_dict.get("versao_comparativo")
                if not spec_name: continue
                found_match = False
                for versao_dict in lista_versoes:
                    versao_name = versao_dict.get("versao")
                    if not versao_name: continue
                    
                    if versao_name.upper().replace('Ë', 'E').replace('-', '').replace('.', '').replace('​', '').strip() == spec_name.upper().replace('Ë', 'E').replace('-', '').replace('.', '').replace('​', '').strip():
                        
                        comparator_pdf = spec_dict.get('manual_url')
                        card_pdf = versao_dict.get('manual_url')

                        if comparator_pdf:
                            if card_pdf and card_pdf != comparator_pdf:
                                print(f"         - PDF do Comparativo ({spec_name}) encontrado. Sobrescrevendo PDF do Card.")
                            pass 
                        
                        elif card_pdf:
                            print(f"         - Mantendo PDF do Card '{versao_name}' (Comparativo não tinha PDF).")
                            spec_dict.pop('manual_url', None)
                        
                        # (Lógica de fallback de manual PÓS-merge)
                        if not versao_dict.get('manual_url') and not spec_dict.get('manual_url'):
                            try:
                                nome_normalizado = versao_name.lower().strip().replace('!', '')
                                key = (modelo, nome_normalizado)
                                fallback_url = MANUAL_FALLBACK_MAP.get(key)
                                if fallback_url:
                                    spec_dict['manual_url'] = fallback_url
                                    print(f"         - Info: Manual não encontrado no site. Usando URL de fallback para '{versao_name}'.")
                            except Exception as e_map:
                                print(f"         - Erro ao tentar aplicar fallback de manual no merge: {e_map}")

                        versao_dict.update(spec_dict) # Merge
                        versao_dict.pop("versao_comparativo", None)
                        found_match = True; break

                if found_match: print(f"           - Dados de '{spec_name}' juntados.")
                else: print(f"           - Aviso: '{spec_name}' do comparativo não encontrou par na lista de versões.")

        result[modelo]["versoes"] = lista_versoes

    except Exception as e_outer:
        print(f"      ❌ ERRO GERAL ao processar o modelo {modelo} na URL {site_url}: {e_outer}")
        if "versoes" not in result[modelo]:
             result[modelo]["versoes"] = []

# === 5️⃣ FECHAR O NAVEGADOR ===
driver.quit()


# --- INÍCIO DA ALTERAÇÃO (PASSO 5 E 6) ---

# === 5️⃣ FORMATAR E ORDENAR A SAÍDA ===
print("\n--- INICIANDO FORMATAÇÃO E ORDENAÇÃO (PASSO 5) ---")
final_version_list = []

# Define a ordem exata das chaves conforme solicitado
key_order = [
    "marca", "modelo", "tipo_veiculo", "ano", "versao", "preco", "imagem_url", 
    "manual_url", "motorizacao", "motor", "turbo", "combustivel", "pneus", 
    "pneus_diametro", "ar_condicionado", "outras_caracteristicas"
]

# Itera sobre o dicionário 'result' que foi construído
for modelo_nome, modelo_data in result.items():
    
    for versao_dict in modelo_data.get("versoes", []):
        
        # Cria o novo dicionário
        ordered_dict = {}
        
        # 1. Adiciona as chaves fixas/novas com base no seu exemplo
        ordered_dict["marca"] = versao_dict.get("marca", "citroen")
        ordered_dict["modelo"] = versao_dict.get("modelo", modelo_nome)
        ordered_dict["tipo_veiculo"] = "TEXT"  # <-- Valor literal "TEXT"
        ordered_dict["ano"] = "INTEGER"   # <-- Valor literal "INTEGER"
        
        # 2. Adiciona as chaves principais na ordem certa
        for key in key_order:
            if key not in ordered_dict and key in versao_dict:
                ordered_dict[key] = versao_dict.get(key)
        
        # 3. Adiciona quaisquer chaves extras (ex: carga_util) no final
        for key, value in versao_dict.items():
            if key not in ordered_dict:
                ordered_dict[key] = value
                
        final_version_list.append(ordered_dict)

print(f"✔️ Formatação concluída. Total de {len(final_version_list)} versões processadas.")


# === 6️⃣ SALVAR RESULTADO FINAL ===
print("\n\n--- RESULTADO FINAL COMPLETO ---")
output_filename = "citroen_data.json"
try:
    # Salva a NOVA lista plana no arquivo
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(final_version_list, f, indent=2, ensure_ascii=False)
    print(f"✔️ Dados salvos com sucesso em {output_filename}")
except Exception as e:
    print(f"❌ Erro ao salvar o arquivo JSON: {e}")
    print(json.dumps(final_version_list, indent=2, ensure_ascii=False))
# --- FIM DA ALTERAÇÃO ---