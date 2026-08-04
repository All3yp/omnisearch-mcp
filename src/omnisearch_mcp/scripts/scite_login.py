import argparse
import asyncio
import os
import re
from pathlib import Path

from playwright.async_api import async_playwright

LOGIN_URL = "https://scite.ai/login"
SUCCESS_URL = "https://scite.ai/dashboard"

async def run_login_flow(headless: bool = False):
    scite_email = os.getenv("SCITE_EMAIL")
    scite_password = os.getenv("SCITE_PASS")
    
    print("Iniciando fluxo de login Scite...")
    async with async_playwright() as p:
        # Usa o browser customizado se configurado no .env, senão usa o padrão do Playwright
        browser_path = os.getenv("PLAYWRIGHT_BROWSER_PATH")
        if browser_path and not os.path.exists(browser_path):
            browser_path = None
            
        browser = await p.chromium.launch(
            headless=headless,
            executable_path=browser_path,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        context = await browser.new_context()
        page = await context.new_page()

        print(f"Navegando para https://scite.ai/")
        await page.goto("https://scite.ai/")

        # Aceita cookies se o banner aparecer
        try:
            cookie_btn = page.locator('button:has-text("Allow All"), button:has-text("Concordo"), button:has-text("Aceitar")').first
            if await cookie_btn.is_visible():
                await cookie_btn.click()
        except Exception:
            pass

        if scite_email and scite_password:
            print("Modo de Automação Ativado. Tentando realizar login...")
            try:
                # Clica em Log In
                login_btn_home = page.locator('button:has-text("Log In"), a:has-text("Log In")').first
                await login_btn_home.click()
                await page.wait_for_timeout(2000)
                
                # Preenche email
                email_input = page.locator('input[type="email"], input[name="email"], input[placeholder*="Email" i]').first
                await email_input.fill(scite_email)
                
                # Clica em Next
                next_btn = page.locator('button:has-text("Next")').first
                await next_btn.click()
                await page.wait_for_timeout(2000)
                
                # Preenche senha
                pass_input = page.locator('input[type="password"], input[name="password"]').first
                await pass_input.fill(scite_password)
                
                # Clica em Log in
                login_btn_submit = page.locator('button:has-text("Log in")').first
                await login_btn_submit.click()
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"Falha na automação do login: {e}. Continue manualmente...")

        print("Aguardando o redirecionamento para o dashboard...")
        
        try:
            # Aguarda a caixa de pergunta (indica login bem sucedido) ou a URL de dashboard
            try:
                await page.wait_for_selector('textarea[placeholder*="Ask a question" i], textbox[name="Ask a question"]', timeout=30000)
                print("Login detectado com sucesso via seletor do dashboard!")
            except Exception:
                await page.wait_for_url(f"**{SUCCESS_URL}**", timeout=270000)
                print("Login detectado com sucesso via URL!")
        except Exception as e:
            print(f"Erro aguardando o redirecionamento: {e}")
            await browser.close()
            return

        cookies = await context.cookies()
        cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        await browser.close()

        if not cookie_string:
            print("Nenhum cookie capturado.")
            return

        print("Cookies capturados!")
        
        env_path = Path(".env")
        env_content = ""
        if env_path.exists():
            env_content = env_path.read_text()
            
        if re.search(r"^SCITE_COOKIES=.*$", env_content, flags=re.MULTILINE):
            env_content = re.sub(r"^SCITE_COOKIES=.*$", f"SCITE_COOKIES=\"{cookie_string}\"", env_content, flags=re.MULTILINE)
        else:
            env_content += f"\nSCITE_COOKIES=\"{cookie_string}\"\n"
            
        env_path.write_text(env_content)
        print(f"Cookies salvos com sucesso em {env_path.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="Realiza login no Scite e salva os cookies no .env")
    parser.add_argument("--headless", action="store_true", help="Rodar o navegador em modo invisível")
    args = parser.parse_args()
    
    asyncio.run(run_login_flow(args.headless))

if __name__ == "__main__":
    main()
