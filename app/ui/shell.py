from nicegui import ui

from app.ui.pages.pAdmin import pAdmin
from app.ui.pages.pFatture import pFatture
from app.ui.pages.pProdotti import pProdotti


def home() -> None:
    ui.label('Benvenuto nella dashboard.')


def root() -> None:
    """Layout dell'area principale dell'app (post-login).
    Per ora nessun controllo di autenticazione: chiunque visita
    una qualsiasi sotto-pagina vede questo header/drawer.
    Lo aggiungeremo insieme alla sessione."""

    with ui.header().classes('items-center justify-between'):
        ui.label('Karma Inventory Manager').classes('text-h6')
        ui.button('Logout', on_click=lambda: ui.navigate.to('/login'))

    with ui.left_drawer():
        ui.label('Navigazione').classes('text-subtitle2')
        ui.separator()
        # TODO: qui aggiungeremo i link alle sezioni reali
        # (Magazzino, Fornitori, Ordini...) quando esisteranno.

    ui.sub_pages({
        '/': home,
        '/prodotti': pProdotti,
        '/fatture': pFatture,
        '/admin': pAdmin,
    })