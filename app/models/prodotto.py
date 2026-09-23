from typing import Optional
from sqlmodel import Field, SQLModel


class Prodotto(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    quantita: int = Field(default=0)
    prezzo_unitario: float
    sku: str = Field(unique=True, index=True)