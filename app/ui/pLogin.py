from nicegui import ui


@ui.page('/login')
def pLogin() -> None:
    """Pagina di login. Per ora nessuna validazione reale: serve solo
    a mostrare la struttura. La logica di autenticazione vera arriva
    quando aggiungiamo il secret manager e la sessione."""

    def handle_login() -> None:
        # TODO: qui in futuro chiameremo un service di autenticazione
        # e imposteremo lo stato di sessione (app.storage.user).
        # Per ora navighiamo semplicemente alla shell.
        ui.navigate.to('/')

    with ui.card().classes('absolute-center'):
        ui.label('Accedi').classes('text-h5')
        username = ui.input('Username')
        password = ui.input('Password', password=True)
        ui.button('Accedi', on_click=handle_login).classes('w-full')