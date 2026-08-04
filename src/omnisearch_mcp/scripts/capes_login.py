import argparse
import asyncio
import os
import re
from pathlib import Path

from urllib.parse import urlparse
from playwright.async_api import async_playwright

async def run_login_flow(headless: bool = False):
    print("Iniciando fluxo de login CAFe...")
    
    # Try to get the existing proxy URL from .env, or use the Periodicos Capes portal as fallback
    env_path = Path(".env")
    env_content = ""
    if env_path.exists():
        env_content = env_path.read_text()
        
    match = re.search(r"^CAPES_PROXY_URL=[\"']?(.*?)[\"']?$", env_content, flags=re.MULTILINE)
    start_url = match.group(1).strip() if match and match.group(1).strip() else "https://www.periodicos.capes.gov.br/"
    
    print("Iniciando fluxo de login CAFe...")
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

        print(f"Navegando para {start_url}")
        try:
            await page.goto(start_url)
        except Exception:
            print("Não foi possível acessar a URL inicial. Navegando para o portal da CAPES...")
            await page.goto("https://www.periodicos.capes.gov.br/")

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
                    try:
                        # Extrai o domínio do proxy (ex: ez138.periodicos.capes.gov.br)
                        parsed_start = urlparse(start_url)
                        proxy_domain = parsed_start.netloc.replace("ieeexplore-ieee-org.", "")
                        
                        for i in range(120): # Monitora por até 4 minutos (loops de 2s)
                            if "ieeexplore" in page.url and proxy_domain in page.url:
                                print("Sucesso! ieeexplore no proxy detectado.")
                                break
                            
                            # Se a URL contiver o domínio do proxy mas não estiver no IEEE Xplore,
                            # significa que o login foi bem sucedido e estamos no portal proxied.
                            # Redireciona automaticamente para o IEEE Xplore.
                            if proxy_domain in page.url and "ieeexplore" not in page.url:
                                print(f"Login efetuado! Redirecionando para {start_url}")
                                try:
                                    await page.goto(start_url)
                                    await page.wait_for_timeout(3000)
                                except Exception:
                                    pass
                                continue
                            
                            print(f"[Auto-Fill Loop {i}] URL atual: {page.url}")
                            
                            # Remove banners de cookies
                            try:
                                cookie_btn = page.locator("button:has-text('Concordo'), button:has-text('Aceitar'), button:has-text('Prosseguir'), button:has-text('Aceito'), .lgpd-btn").first
                                if await cookie_btn.is_visible():
                                    await cookie_btn.click()
                                    await page.wait_for_timeout(500)
                            except Exception:
                                pass

                            form = page.locator(".acesso-cafe-form, .form-padrao").first
                            
                            # Tenta clicar no Acesso CAFe caso estejamos na página principal da CAPES e o form não esteja aberto
                            # (O form pode demorar a aparecer, então checamos a URL também)
                            if not await form.is_visible():
                                if "periodicos.capes.gov.br" in page.url and "acesso-cafe" not in page.url.lower() and proxy_domain not in page.url:
                                    try:
                                        # Abre o dropdown
                                        dropdown = page.locator("#dropdownCafe").first
                                        if await dropdown.is_visible():
                                            await dropdown.click()
                                            await page.wait_for_timeout(1000)
                                            
                                        # Clica no link oficial do CAFe
                                        cafe_btn = page.locator("a[href*='acesso-cafe.html']").first
                                        if await cafe_btn.is_visible():
                                            print("Clicando no botão Acesso CAFe do portal...")
                                            await cafe_btn.click()
                                            await page.wait_for_timeout(3000)
                                    except Exception as e:
                                        print(f"Erro ao clicar Acesso CAFe: {e}")

                            # Tenta preencher instituição
                            if await form.is_visible() or await page.locator("#select-simple").is_visible():
                                if cafe_inst:
                                    trigger = page.locator('button[data-trigger], button[aria-label*="Exibir lista" i]').first
                                    if await trigger.is_visible():
                                        await trigger.click(force=True)
                                        await page.wait_for_timeout(500)
                                    inp = page.locator("#select-simple").first
                                    if await inp.is_visible():
                                        await inp.click(force=True)
                                        await inp.fill("")
                                        await inp.type(cafe_inst, delay=80)
                                        await page.wait_for_timeout(2000) # Aguarda a lista filtrar
                                        
                                        # Tenta clicar usando javascript
                                        print("Tentando selecionar a instituição via JS...")
                                        await page.evaluate("""() => {
                                            let items = document.querySelectorAll('.br-list .br-item');
                                            for (let item of items) {
                                                if (item.offsetParent !== null && !item.hasAttribute('hidden')) { 
                                                    let radio = item.querySelector('input[type="radio"]');
                                                    if (radio) { radio.click(); return; }
                                                    let label = item.querySelector('label');
                                                    if (label) { label.click(); return; }
                                                }
                                            }
                                        }""")
                                        await page.wait_for_timeout(1000)
                                            
                                    submit = page.locator("#enviarInstituicaoCafe").first
                                    if await submit.is_visible():
                                        print("Clicando no botão Enviar instituição...")
                                        await submit.click(force=True)
                                        await page.evaluate('document.querySelector("#enviarInstituicaoCafe")?.click()')
                                        await page.wait_for_timeout(2000)

                            # Tenta preencher login
                            if login_attempts < 3:
                                pass_field = page.locator('input#password, input[name="j_password"], input[name="password"]').first
                                if await pass_field.is_visible():
                                    if cafe_user and cafe_pass:
                                        user_field = page.locator('input[name="j_username"], input[name="username"], input[id="username"], input[name="uid"]').first
                                        if await user_field.is_visible():
                                            await user_field.fill(cafe_user)
                                            await pass_field.fill(cafe_pass)
                                            login_btn = page.locator('#btn-login, #login, input[type="submit"], button[type="submit"], button:has-text("Entrar"), button:has-text("Login"), input[value="Entrar"]').first
                                            if await login_btn.is_visible():
                                                print("Preenchendo e clicando em entrar no login...")
                                                await login_btn.click()
                                                login_attempts += 1
                                                await page.wait_for_timeout(3000)
                                                
                            # Tenta aceitar tela de consentimento do Shibboleth
                            try:
                                consent_btn = page.locator('button[name="_eventId_proceed"], button:has-text("Aceitar"), button:has-text("Concordar"), button:has-text("Accept")').first
                                if await consent_btn.is_visible():
                                    print("Clicando no consentimento do Shibboleth...")
                                    await consent_btn.click()
                                    await page.wait_for_timeout(2000)
                            except Exception as e:
                                print(f"Erro consentimento: {e}")

                            await asyncio.sleep(2)
                    except Exception as e:
                        pass
                
                asyncio.create_task(auto_fill())
            else:
                print("Nenhuma credencial automática configurada. Por favor, realize o login manualmente no navegador.")

            print("NOTA: Se a página não carregar ou ficar no portal da CAPES, acesse o IEEE Xplore manualmente pela busca para prosseguir.")
            print("Aguardando você acessar a página do IEEE Xplore pelo proxy da CAPES...")
            
            # Aguarda até que a URL contenha o proxy da CAPES novamente e pareça logado
            try:
                await page.wait_for_url("**ieeexplore*periodicos.capes.gov.br**", timeout=300000) # 5 minutos para logar
                print("Login detectado com sucesso!")
            except Exception as e:
                print(f"Erro aguardando o redirecionamento: {e}")
                await browser.close()
                return

        # Pega os cookies
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
        
        # Regex to replace or append IEEE_COOKIES
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
    parser = argparse.ArgumentParser(description="Realiza login no CAFe/CAPES e salva os cookies no .env")
    parser.add_argument("--headless", action="store_true", help="Rodar o navegador em modo invisível")
    args = parser.parse_args()
    
    asyncio.run(run_login_flow(args.headless))

if __name__ == "__main__":
    main()
