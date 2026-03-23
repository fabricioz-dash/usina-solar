"""
Scraper - PV Hub (weg.pv-hub.cloud)
Modos de uso:
  python scraper_pv_hub.py           → loop com agendamento diário às 20h
  python scraper_pv_hub.py --uma-vez → executa uma única coleta e sai (GitHub Actions)

Credenciais: variáveis de ambiente PV_USUARIO e PV_SENHA
  (ou edite USUARIO/SENHA abaixo para uso local)
"""

import csv
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import schedule
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ─────────────────────────────────────────────
# CONFIGURAÇÕES
# ─────────────────────────────────────────────
# Prioridade: variável de ambiente > valor fixo abaixo
USUARIO  = os.environ.get("PV_USUARIO", "seu_usuario_aqui")
SENHA    = os.environ.get("PV_SENHA",   "sua_senha_aqui")
HORARIO  = "20:00"

URL_LOGIN  = "https://weg.pv-hub.cloud/login"
URL_PLANTA = "https://weg.pv-hub.cloud/bus/plant/view"

CSV_PATH = Path(__file__).parent / "rendimento_diario.csv"
TIMEOUT  = 30
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

CAMPOS = {
    "rendimento_hoje":    "Rendimento de hoje",
    "rendimento_total":   "Rendimento total",
    "potencia_acumulada": "Potencia Acumulada",
}


def criar_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def fazer_login(driver, wait) -> bool:
    log.info("Acessando página de login...")
    driver.get(URL_LOGIN)
    campo_usuario = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[placeholder='Nome do usuário']")
        )
    )
    campo_usuario.clear()
    campo_usuario.send_keys(USUARIO)
    driver.find_element(By.CSS_SELECTOR, "input[placeholder='Senha']").send_keys(SENHA)
    driver.find_element(By.CSS_SELECTOR, "button.login-click").click()
    try:
        wait.until(EC.url_changes(URL_LOGIN))
        log.info("Login OK. URL atual: %s", driver.current_url)
        return True
    except Exception:
        log.error("Login falhou.")
        return False


def _valor_pelo_titulo(driver, titulo_parcial: str) -> str:
    """
    Localiza o div.plant-text pelo atributo title,
    sobe para o detail-box pai e retorna o span do div.plant-money irmão.
    """
    xpath = (
        f"//div[contains(@class,'plant-text') and contains(@title,'{titulo_parcial}')]"
        "/parent::div[contains(@class,'detail-box')]"
        "//div[contains(@class,'plant-money')]"
        "/span"
    )
    try:
        el = driver.find_element(By.XPATH, xpath)
        return el.text.strip()
    except Exception:
        return "NAO_ENCONTRADO"


def coletar_dados(driver, wait) -> dict:
    log.info("Navegando para %s", URL_PLANTA)
    driver.get(URL_PLANTA)
    wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.plant-money span"))
    )
    time.sleep(2)
    resultado = {}
    for chave, titulo in CAMPOS.items():
        valor = _valor_pelo_titulo(driver, titulo)
        resultado[chave] = valor
        log.info("  %-22s -> %s", chave, valor)
    return resultado


def salvar_csv(data: str, dados: dict) -> None:
    cabecalho = ["data"] + list(CAMPOS.keys())
    novo_arquivo = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        if novo_arquivo:
            writer.writerow(cabecalho)
        writer.writerow([data] + [dados.get(k, "") for k in CAMPOS])
    log.info("CSV atualizado -> %s", CSV_PATH)


def executar_coleta() -> None:
    log.info("=== Iniciando coleta ===")
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    driver = None
    try:
        driver = criar_driver()
        wait = WebDriverWait(driver, TIMEOUT)
        if not fazer_login(driver, wait):
            return
        time.sleep(3)
        dados = coletar_dados(driver, wait)
        salvar_csv(data_hoje, dados)
    except Exception as exc:
        log.exception("Erro inesperado: %s", exc)
        if driver:
            debug = Path(__file__).parent / "debug_page.html"
            debug.write_text(driver.page_source, encoding="utf-8")
        salvar_csv(data_hoje, {k: "ERRO" for k in CAMPOS})
    finally:
        if driver:
            driver.quit()
    log.info("=== Coleta finalizada ===")


def main() -> None:
    uma_vez = "--uma-vez" in sys.argv

    if uma_vez:
        # Modo GitHub Actions: executa e sai
        log.info("Modo: coleta única")
        executar_coleta()
    else:
        # Modo local: agenda e mantém em loop
        log.info("Agendador iniciado. Coleta diária às %s.", HORARIO)
        schedule.every().day.at(HORARIO).do(executar_coleta)
        log.info("Executando coleta inicial agora...")
        executar_coleta()
        while True:
            schedule.run_pending()
            time.sleep(60)


if __name__ == "__main__":
    main()
