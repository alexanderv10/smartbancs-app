import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "http://localhost:8000"


def print_title(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def request_json(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        f"{API_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(
            "No pude conectar con la API. Verifica que docker compose este corriendo."
        ) from exc


def read_int(prompt: str) -> int:
    while True:
        value = input(prompt).strip()
        try:
            return int(value)
        except ValueError:
            print("Ingresa un numero entero.")


def read_amount(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        try:
            amount = float(value)
        except ValueError:
            print("Ingresa un monto valido.")
            continue
        if amount <= 0:
            print("El monto debe ser mayor que cero.")
            continue
        return value


def option_get_account() -> None:
    print_title("Consultar cuenta")
    account_id = read_int("account_id: ")
    print_json(request_json("GET", f"/accounts/{account_id}"))


def option_create_transaction() -> None:
    print_title("Crear transferencia")
    from_account_id = read_int("Cuenta origen: ")
    to_account_id = read_int("Cuenta destino: ")
    amount = read_amount("Monto: ")
    response = request_json(
        "POST",
        "/transactions",
        {
            "from_account_id": from_account_id,
            "to_account_id": to_account_id,
            "amount": amount,
        },
    )
    print_json(response)
    print("\nPuedes usar transaction_id para consultar esta transferencia en Swagger.")
    print("Puedes usar trace_id para buscar el recorrido tecnico en logs.")


def show_menu() -> None:
    print(
        """
SmartBancs Menu

1. Consultar cuenta por ID
2. Crear transferencia
0. Salir
"""
    )


def main() -> int:
    actions = {
        "1": option_get_account,
        "2": option_create_transaction,
    }

    while True:
        show_menu()
        choice = input("Elige una opcion: ").strip()
        if choice == "0":
            print("Saliendo.")
            return 0
        action = actions.get(choice)
        if action is None:
            print("Opcion invalida.")
            continue
        try:
            action()
        except RuntimeError as exc:
            print(f"Error: {exc}")
        input("\nEnter para continuar...")


if __name__ == "__main__":
    sys.exit(main())
