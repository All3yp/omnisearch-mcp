import argparse
import asyncio

from omnisearch_mcp.scripts import capes_login, scite_login, consensus_login


async def run_all_logins(headless: bool = False):
    print("=" * 60)
    print(" [1/3] Autenticando CAPES / IEEE Xplore via CloakBrowser...")
    print("=" * 60)
    try:
        await capes_login.run_login_flow(headless=headless)
    except Exception as e:
        print(f"[-] Erro ao realizar login CAPES: {e}")

    print("\n" + "=" * 60)
    print(" [2/3] Autenticando Scite.ai via CloakBrowser...")
    print("=" * 60)
    try:
        await scite_login.run_login_flow(headless=headless)
    except Exception as e:
        print(f"[-] Erro ao realizar login Scite: {e}")

    print("\n" + "=" * 60)
    print(" [3/3] Autenticando Consensus.app via CloakBrowser...")
    print("=" * 60)
    try:
        await consensus_login.run_login_flow(headless=headless)
    except Exception as e:
        print(f"[-] Erro ao realizar login Consensus: {e}")

    print("\n" + "=" * 60)
    print(" [✔] Processo de login concluído para todas as plataformas!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Realiza login em todas as plataformas (CAPES, Scite, Consensus) e salva cookies no .env")
    parser.add_argument("--headless", action="store_true", help="Executa os navegadores em modo headless")
    args = parser.parse_args()

    asyncio.run(run_all_logins(headless=args.headless))


if __name__ == "__main__":
    main()
