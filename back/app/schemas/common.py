from pydantic import BaseModel

class Source(BaseModel):
    titulo: str | None = None
    tipo: str | None = None
    fuente_archivo: str | None = None
    fuente_hoja: str | None = None
    fuente_fila: int | None = None
    periodo: str | None = None
