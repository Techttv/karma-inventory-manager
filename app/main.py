from nicegui import ui

from app.ui import pLogin  # noqa: F401  (side-effect: registra @ui.page('/login'))
from app.ui.shell import root

ui.header.default_classes('bg-black rounded-b-3xl')

@ui.page('/{_:path}')
def catch_all() -> None:
    """Route server-side per l'area applicativa (dashboard e sezioni
    collegate): la navigazione tra quelle sezioni avviene poi via
    ui.sub_pages() dentro root(), senza reload. Il login vive invece
    sulla propria route dedicata ('/login'), con un layout diverso."""
    root()


ui.run(title='Karma Inventory Manager')