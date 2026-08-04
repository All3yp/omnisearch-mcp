import argparse
import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from cloakbrowser import launch_async


async def run_login_flow(headless: bool = False):
    print("Iniciando fluxo de login CAFe...")
    
    # Try to get the existing proxy URL from .env, or use the Periodicos Capes portal as fallback
    env_path = Path(".env")
    env_content = ""
    if env_path.exists():
        env_content = env_path.read_text()
        
    match = re.search(r"^CAPES_PROXY_URL=[\"']?(.*?)[\"']?$", env_content, flags=re.MULTILINE)
    start_url = match.group(1).strip() if match and match.group(1).strip() else "https://www.periodicos.capes.gov.br/"
    
    print("Iniciando fluxo de login CAFe com CloakBrowser...")
    browser_path = os.getenv("PLAYWRIGHT_BROWSER_PATH")
    if browser_path and not os.path.exists(browser_path):
        browser_path = None

    browser = await launch_async(headless=headless, humanize=True)
    context = await browser.new_context()
    page = await context.new_page()

    print(f"Navegando para {start_url}")
    try:
        await page.goto(start_url)
    except Exception:
        print("Não foi possível acessar a URL inicial. Navegando para o portal da CAPES...")
        try:
            await page.goto("https://www.periodicos.capes.gov.br/")
        except Exception:
            pass

    # Aceita banner de cookie/LGPD inicial se visível (prioriza 'Aceitar todos' e 'Aceitar', evitando 'Definir')
    try:
        cookie_btn = page.locator('button:has-text("Aceitar todos"), button:has-text("Aceitar Cookies"), button:has-text("Aceitar"), button:has-text("Concordo"), a:has-text("Aceitar todos"), a:has-text("Aceitar")').first
        if await cookie_btn.is_visible():
            btn_text = (await cookie_btn.text_content() or "").lower()
            if "definir" not in btn_text and "configurar" not in btn_text:
                print("Banner de cookies/LGPD detectado. Clicando em aceitar...")
                await cookie_btn.click()
                await page.wait_for_timeout(1000)
    except Exception:
        pass

    # Se já estiver na URL do IEEE via capes, não precisa logar
    if "periodicos.capes.gov.br" in page.url and "ieeexplore" in page.url and "login" not in page.url.lower():
        print("Parece que a sessão já está ativa ou o IP já tem acesso.")
    else:
        cafe_inst = os.getenv("CAFE_INSTITUTION_ID")
        cafe_user = os.getenv("CAFE_USERNAME")
        cafe_pass = os.getenv("CAFE_PASSWORD")
        
        if cafe_inst or (cafe_user and cafe_pass):
            print("Modo de Automação Ativado. Monitorando telas de login do CAFe...")
            
            async def auto_fill():
                login_attempts = 0
                clicked_cafe = False
                try:
                    parsed_start = urlparse(start_url)
                    proxy_domain = parsed_start.netloc.replace("ieeexplore-ieee-org.", "")
                    
                    for i in range(120): # Monitora por até 4 minutos
                        # Pega sempre a aba mais recente caso uma nova aba tenha sido aberta
                        curr_page = context.pages[-1] if context.pages else page
                        current_url = curr_page.url.lower()

                        if "ieeexplore" in current_url and proxy_domain in current_url:
                            print("Sucesso! ieeexplore no proxy detectado.")
                            break
                        
                        if proxy_domain in current_url and "ieeexplore" not in current_url:
                            print(f"Login efetuado! Redirecionando para {start_url}")
                            try:
                                await curr_page.goto(start_url)
                                await curr_page.wait_for_timeout(3000)
                            except Exception:
                                pass

                        # Verifica e aceita banner de cookies se estiver bloqueando a tela
                        try:
                            c_btn = curr_page.get_by_role('button', name='Aceitar').first
                            if await c_btn.is_visible():
                                print("Fechando banner de cookies LGPD...")
                                await c_btn.click()
                                await curr_page.wait_for_timeout(1000)
                        except Exception:
                            pass

                        # Tela 0: Clica em 'Acesso CAFe' (botão do menu + link interno)
                        if cafe_inst and not clicked_cafe and ("periodicos.capes.gov.br" in current_url and "acesso-cafe" not in current_url and "ieeexplore" not in current_url):
                            try:
                                btn_menu = curr_page.get_by_role('button', name='Acesso CAFe').first
                                if await btn_menu.is_visible():
                                    print("Clicando no menu 'Acesso CAFe'...")
                                    await btn_menu.click()
                                    await curr_page.wait_for_timeout(1000)

                                link_item = curr_page.get_by_role('link', name=' Acesso CAFe').first
                                if await link_item.is_visible():
                                    print("Clicando no item do menu 'Acesso CAFe'...")
                                    clicked_cafe = True
                                    await link_item.click()
                                    await curr_page.wait_for_timeout(3000)
                                else:
                                    # Fallback genérico
                                    cafe_fallback = curr_page.locator('a:has-text("Acesso CAFe"), a[href*="acesso-cafe"]').first
                                    if await cafe_fallback.is_visible():
                                        clicked_cafe = True
                                        await cafe_fallback.click()
                                        await curr_page.wait_for_timeout(3000)
                            except Exception as e:
                                print(f"Tentativa de navegação Acesso CAFe: {e}")

                        # Tela 1: Seleção de Instituição CAFe
                        if cafe_inst and ("acesso-cafe" in current_url or "shibboleth" in current_url or "wayf" in current_url or "instituicao" in current_url or "periodicos.capes.gov.br" in current_url):
                            inst_input = curr_page.get_by_placeholder('Digite a sigla ou o nome da').first
                            if not await inst_input.is_visible():
                                inst_input = curr_page.locator('input[type="text"], input[name*="inst"], select[name*="inst"]').first

                            if await inst_input.is_visible():
                                try:
                                    print(f"Preenchendo instituição: {cafe_inst}...")
                                    await inst_input.click()
                                    await inst_input.fill(cafe_inst)
                                    await curr_page.wait_for_timeout(1000)
                                    
                                    # Seleciona o item da lista correspondente
                                    opt = curr_page.get_by_text(cafe_inst, exact=False).first
                                    if await opt.is_visible():
                                        await opt.click()
                                        await curr_page.wait_for_timeout(1000)
                                    
                                    sub_env = curr_page.get_by_role('button', name='Enviar').first
                                    if not await sub_env.is_visible():
                                        sub_env = curr_page.locator('button:has-text("Enviar"), input[type="submit"]').first
                                    
                                    if await sub_env.is_visible():
                                        await sub_env.click()
                                        await curr_page.wait_for_timeout(3000)
                                except Exception as e:
                                    print(f"Tentativa de seleção de instituição: {e}")

                        # Tela 2: Credenciais CAFe (Shibboleth/IdP)
                        if cafe_user and cafe_pass and login_attempts < 3:
                            user_field = curr_page.locator('input[name*="user" i], input[name*="username" i], input[id*="user" i]').first
                            pass_field = curr_page.locator('input[type="password"]').first
                            
                            if await user_field.is_visible() and await pass_field.is_visible():
                                current_user_val = await user_field.input_value()
                                if not current_user_val:
                                    print("Preenchendo usuário e senha no IdP...")
                                    await user_field.fill(cafe_user)
                                    await pass_field.fill(cafe_pass)
                                    login_attempts += 1
                                    
                                    sub_btn = curr_page.locator('button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Entrar")').first
                                    if await sub_btn.is_visible():
                                        await sub_btn.click()
                                        await curr_page.wait_for_timeout(3000)

                        await asyncio.sleep(2)
                except Exception as e:
                    print(f"Erro na automação do formulário: {e}")

            await auto_fill()
            print("Login detectado com sucesso!")

    cookies = await context.cookies()
    cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    
    parsed = urlparse(page.url)
    capes_proxy_url = f"{parsed.scheme}://{parsed.netloc}"
    
    await browser.close()

    if not cookie_string:
        print("Nenhum cookie capturado.")
        return

    print("Cookies capturados!")
    print(f"Proxy detectado: {capes_proxy_url}")
    
    if re.search(r"^IEEE_COOKIES=.*$", env_content, flags=re.MULTILINE):
        env_content = re.sub(r"^IEEE_COOKIES=.*$", f"IEEE_COOKIES=\"{cookie_string}\"", env_content, flags=re.MULTILINE)
    else:
        env_content += f"\nIEEE_COOKIES=\"{cookie_string}\"\n"
        
    if re.search(r"^CAPES_PROXY_URL=.*$", env_content, flags=re.MULTILINE):
        env_content = re.sub(r"^CAPES_PROXY_URL=.*$", f"CAPES_PROXY_URL=\"{capes_proxy_url}\"", env_content, flags=re.MULTILINE)
    else:
        env_content += f"\nCAPES_PROXY_URL=\"{capes_proxy_url}\"\n"
        
    env_path.write_text(env_content)
    print(f"Cookies e Proxy salvos com sucesso em {env_path.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="Realiza login no Portal Periódicos CAPES e salva cookies no .env")
    parser.add_argument("--headless", action="store_true", help="Executa o navegador em modo headless (sem janela visível)")
    args = parser.parse_args()

    asyncio.run(run_login_flow(headless=args.headless))


if __name__ == "__main__":
    main()
