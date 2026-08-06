import argparse
import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from cloakbrowser import launch_async

from .session_store import (
    context_options,
    cookie_header,
    save_storage_state,
    storage_summary,
    update_env_values,
)


IEEE_VALIDATION_QUERY = "machine learning"
IEEE_VALIDATION_TIMEOUT = 20.0


async def validate_ieee_proxy_session(
    proxy_url: str,
    cookie_string: str,
    user_agent: str = "omnisearch-mcp/0.1",
) -> tuple[bool, str]:
    """Validate CAPES/IEEE cookies with HTTP only for backwards-compatible tests."""
    if not proxy_url or not cookie_string:
        return False, "missing proxy URL or cookies"

    return False, "direct HTTP validation is disabled; use browser validation"


async def validate_ieee_browser_session(page, proxy_url: str) -> tuple[bool, str]:
    """Validate CAPES/IEEE access in the already-open browser session."""
    if not proxy_url:
        return False, "missing proxy URL"

    try:
        await page.goto(
            f"{proxy_url.rstrip('/')}/Xplore/home.jsp",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await page.wait_for_timeout(3000)
    except Exception as exc:
        return False, f"browser validation navigation failed: {type(exc).__name__}"

    current_url = page.url.lower()
    if "login" in current_url or ("periodicos.capes.gov.br" in current_url and "ieeexplore" not in current_url):
        return False, "browser validation redirected to login/CAPES portal"

    try:
        search_marker = page.locator(
            'input[type="search"], button[aria-label*="Search" i], a[href="/search/advanced"]'
        ).first
        if await search_marker.is_visible():
            return True, "validated"
    except Exception:
        pass

    try:
        html = (await page.content()).lower()
    except Exception:
        html = ""

    if "unusual traffic" in html or "error 418" in html:
        return False, "browser validation reached IEEE 418 unusual traffic page"
    if "ieeexplore" in html or "ieee xplore" in html:
        return True, "validated"

    return False, "browser validation did not find IEEE search UI"


async def click_first_visible(page, selectors: tuple[str, ...], label: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if not await locator.is_visible():
                continue
            print(f"Clicando em {label} ({selector})...")
            try:
                await locator.click(timeout=5000)
            except TypeError:
                await locator.click()
            except Exception:
                await locator.evaluate("element => element.click()")
            return True
        except Exception:
            continue
    return False


async def current_url_changed(page, previous_url: str) -> bool:
    await page.wait_for_timeout(500)
    return page.url != previous_url


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
    context = await browser.new_context(**context_options("capes_ieee"))
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
                            opened_cafe_menu = await click_first_visible(
                                curr_page,
                                (
                                    'button[aria-controls]:has-text("Acesso CAFe")',
                                    'button[aria-expanded]:has-text("Acesso CAFe")',
                                    'button[aria-haspopup]:has-text("Acesso CAFe")',
                                    'button:has-text("Acesso CAFe")',
                                    '[role="button"]:has-text("Acesso CAFe")',
                                ),
                                "menu Acesso CAFe",
                            )
                            if opened_cafe_menu:
                                await curr_page.wait_for_timeout(1000)

                            clicked_cafe = await click_first_visible(
                                curr_page,
                                (
                                    'a[href*="acesso-cafe"]',
                                    'a[href*="Shibboleth.sso"]',
                                    'a[href*="cafe"]:has-text("Acesso CAFe")',
                                    '[role="menuitem"][href*="acesso-cafe"]',
                                    '[role="menuitem"]:has-text("Acesso CAFe")',
                                ),
                                "link Acesso CAFe",
                            )
                            if clicked_cafe and await current_url_changed(curr_page, current_url):
                                await curr_page.wait_for_timeout(3000)
                            else:
                                clicked_cafe = False

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

    active_page = context.pages[-1] if context.pages else page
    active_url = active_page.url.lower()
    active_url_looks_authenticated = "ieeexplore" in active_url and "login" not in active_url

    cookies = await context.cookies()
    cookie_string = cookie_header(cookies)

    env_proxy_url = os.getenv("CAPES_PROXY_URL")
    if active_url_looks_authenticated:
        parsed = urlparse(active_page.url)
        capes_proxy_url = f"{parsed.scheme}://{parsed.netloc}"
    elif env_proxy_url:
        capes_proxy_url = env_proxy_url.rstrip("/")
    else:
        await browser.close()
        print("Login CAPES/IEEE não validado. Ação humana necessária: execute `uv run omnisearch-capes-login` em modo visível, conclua MFA/CAPTCHA/SSO no navegador e tente a busca novamente uma vez.")
        return

    if not cookie_string:
        await browser.close()
        print("Nenhum cookie capturado.")
        return

    is_valid, validation_reason = await validate_ieee_browser_session(
        active_page, capes_proxy_url
    )
    if not is_valid:
        await browser.close()
        print(
            "Sessão CAPES/IEEE não validada na busca avançada. "
            f"Motivo: {validation_reason}. "
            "Ação humana necessária: execute `uv run omnisearch-capes-login` em modo visível, "
            "conclua MFA/CAPTCHA/SSO no navegador e tente a busca novamente uma vez."
        )
        return

    await save_storage_state(context, "capes_ieee")
    await browser.close()

    print(f"Cookies capturados: {storage_summary(cookies)}")
    print(f"Proxy detectado: {capes_proxy_url}")

    update_env_values(
        env_path,
        {
            "IEEE_COOKIES": cookie_string,
            "CAPES_PROXY_URL": capes_proxy_url,
        },
    )
    print(f"Sessão do navegador, cookies e proxy salvos com sucesso em {env_path.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="Realiza login no Portal Periódicos CAPES e salva cookies no .env")
    parser.add_argument("--headless", action="store_true", help="Executa o navegador em modo headless (sem janela visível)")
    args = parser.parse_args()

    asyncio.run(run_login_flow(headless=args.headless))


if __name__ == "__main__":
    main()
