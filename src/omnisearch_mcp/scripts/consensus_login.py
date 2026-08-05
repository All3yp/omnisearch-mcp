import argparse
import asyncio
from pathlib import Path

import os
from cloakbrowser import launch_async

from .session_store import (
    context_options,
    cookie_header,
    save_storage_state,
    storage_summary,
    update_env_values,
)

LOGIN_URL = "https://consensus.app/sign-in/"
SUCCESS_URL = "https://consensus.app/search/"

async def run_login_flow(headless: bool = False):
    consensus_email = os.getenv("CONSENSUS_EMAIL")
    consensus_pass = os.getenv("CONSENSUS_PASS")

    print("Iniciando fluxo de login Consensus com CloakBrowser...")
    try:
        # Lança o CloakBrowser com humanização ativada para mitigar Cloudflare
        browser = await launch_async(headless=headless, humanize=True)
        context = await browser.new_context(**context_options("consensus"))
        page = await context.new_page()

        print(f"Navegando para {LOGIN_URL}")
        await page.goto(LOGIN_URL)

        # Automação do preenchimento das credenciais
        if consensus_email and consensus_pass:
            print("Modo de Automação Ativado. Tentando realizar login...")
            try:
                # Preenche email
                email_input = page.locator('input[type="email"], input[name="email"], input[placeholder*="Email" i]').first
                await email_input.fill(consensus_email)

                # Clica em Next
                next_btn = page.locator('button:has-text("Next")').first
                await next_btn.click()
                await page.wait_for_timeout(2000)

                # Clica em Use password
                use_pass_btn = page.locator('button:has-text("Use password")').first
                if await use_pass_btn.is_visible():
                    await use_pass_btn.click()
                    await page.wait_for_timeout(1000)

                # Preenche senha
                pass_input = page.locator('input[type="password"], input[name="password"]').first
                await pass_input.fill(consensus_pass)

                # Clica em Sign in
                signin_btn = page.get_by_test_id("sign-in").get_by_role("button", name="Sign in").first
                await signin_btn.click()
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"Falha na automação do login: {e}. Por favor, continue manualmente...")

        # Tenta resolver Cloudflare Turnstile se necessário (geralmente CloakBrowser faz isso sozinho)
        try:
            turnstile_iframe = page.locator('iframe[src*="challenges.cloudflare.com"]').first
            if await turnstile_iframe.is_visible():
                print("Cloudflare Turnstile detectado. Tentando clicar...")
                await turnstile_iframe.content_frame.locator('body').click()
                await page.wait_for_timeout(2000)
        except Exception:
            pass

        print("Por favor, realize o login no navegador aberto caso necessário.")
        print("Aguardando o redirecionamento pós login...")

        try:
            # Aguarda até que a URL mude e não contenha mais "sign-in" ou "login"
            success = False
            for _ in range(300): # loops de 500ms
                cookies = await context.cookies()
                c_names = [c["name"] for c in cookies]
                if "consensus_sess" in c_names or "__session" in c_names or ("consensus.app" in page.url and "sign-in" not in page.url and "login" not in page.url):
                    print(f"Login detectado com sucesso! URL atual: {page.url}")
                    success = True
                    break
                await page.wait_for_timeout(500)
            if not success:
                raise Exception("Timeout aguardando redirecionamento pós-login")
        except Exception as e:
            print(f"Erro aguardando o redirecionamento: {e}")
            await browser.close()
            return

        cookies = await context.cookies()
        cookie_string = cookie_header(cookies)

        await save_storage_state(context, "consensus")
        await browser.close()
    except Exception as e:
        print(f"Erro no fluxo do CloakBrowser: {e}")
        return

    if not cookie_string:
        print("Nenhum cookie capturado.")
        return

    print(f"Cookies capturados: {storage_summary(cookies)}")

    env_path = Path(".env")
    update_env_values(env_path, {"CONSENSUS_COOKIES": cookie_string})
    print(f"Sessão do navegador e cookies salvos com sucesso em {env_path.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="Realiza login no Consensus e salva os cookies no .env")
    parser.add_argument("--headless", action="store_true", help="Rodar o navegador em modo invisível")
    args = parser.parse_args()

    asyncio.run(run_login_flow(args.headless))

if __name__ == "__main__":
    main()
