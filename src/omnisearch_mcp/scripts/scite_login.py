import argparse
import asyncio
import os
from pathlib import Path

from cloakbrowser import launch_async

from .session_store import (
    context_options,
    cookie_header,
    save_storage_state,
    storage_summary,
    update_env_values,
)

LOGIN_URL = "https://scite.ai/login"
SUCCESS_URL = "https://scite.ai/dashboard"


async def run_login_flow(headless: bool = False):
    scite_email = os.getenv("SCITE_EMAIL")
    scite_password = os.getenv("SCITE_PASS")

    print("Iniciando fluxo de login Scite com CloakBrowser...")
    browser_path = os.getenv("PLAYWRIGHT_BROWSER_PATH")
    if browser_path and not os.path.exists(browser_path):
        browser_path = None

    browser = await launch_async(headless=headless, humanize=True)
    context = await browser.new_context(**context_options("scite"))
    page = await context.new_page()

    print("Navegando para https://scite.ai/")
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
            login_btn_home = page.locator('button:has-text("Log In"), a:has-text("Log In")').first
            if await login_btn_home.is_visible():
                await login_btn_home.click()
                await page.wait_for_timeout(800)

            # Preenche email
            email_input = page.locator('input[type="email"], input[name="email"], input[placeholder*="Email" i]').first
            if await email_input.is_visible():
                await email_input.fill(scite_email)

                # Clica em Next
                next_btn = page.locator('button:has-text("Next")').first
                if await next_btn.is_visible():
                    await next_btn.click()
                    await page.wait_for_timeout(800)

            # Preenche senha
            pass_input = page.locator('input[type="password"], input[name="password"]').first
            if await pass_input.is_visible():
                await pass_input.fill(scite_password)

                # Clica no botão final de login
                submit_btn = page.locator('button[type="submit"]:has-text("Log In"), button:has-text("Sign In")').first
                if await submit_btn.is_visible():
                    await submit_btn.click()
                    print("Formulário de login submetido!")
        except Exception as e:
            print(f"Não foi possível automatizar o login do Scite completamente: {e}")

    print("Aguardando login no Scite.ai...")

    # Monitoramento rápido dos cookies de sessão
    max_checks = 30 if (scite_email and scite_password) else 600
    success = False
    for _ in range(max_checks):
        await page.wait_for_timeout(500)
        cookies = await context.cookies()
        c_names = [c["name"] for c in cookies]
        if "userSession" in c_names or "connect.sid" in c_names or "dashboard" in page.url or "assistant" in page.url or "search" in page.url:
            print("Login no Scite detectado com sucesso!")
            success = True
            break

    if not success:
        print("Login no Scite não validado. Ação humana necessária: execute `uv run omnisearch-scite-login` em modo visível, conclua o login no navegador e tente a busca novamente uma vez.")
        await browser.close()
        return

    # Pega os cookies
    cookies = await context.cookies()
    cookie_string = cookie_header(cookies)

    await save_storage_state(context, "scite")
    await browser.close()

    if not cookie_string:
        print("Nenhum cookie capturado.")
        return

    print(f"Cookies do Scite capturados: {storage_summary(cookies)}")

    # Salva os cookies no .env
    env_path = Path(".env")
    update_env_values(env_path, {"SCITE_COOKIES": cookie_string})
    print(f"Sessão do navegador e cookies salvos com sucesso em {env_path.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="Realiza login no Scite.ai e salva cookies no .env")
    parser.add_argument("--headless", action="store_true", help="Executa o navegador em modo headless (sem janela visível)")
    args = parser.parse_args()

    asyncio.run(run_login_flow(headless=args.headless))


if __name__ == "__main__":
    main()
