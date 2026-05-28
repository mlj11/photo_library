from pydantic import BaseModel
from typing import Optional


class SessionCreate(BaseModel):
    name: str = ""
    input_dir: str
    output_dir: str = ""
    start_from: int = 0


class SessionUpdate(BaseModel):
    notes: Optional[str] = None


class PhotoUpdate(BaseModel):
    selected: Optional[bool] = None
    user_category: Optional[str] = None
    user_rating: Optional[int] = None
    notes: Optional[str] = None


class ExportRequest(BaseModel):
    dest_dir: str
    only_selected: bool = True
