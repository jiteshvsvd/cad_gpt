import os
import uuid
import base64
import traceback
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class CadRequest(BaseModel):
    code: str

class CadResponse(BaseModel):
    ok: bool
    stl_base64: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/generate_stl", response_model=CadResponse)
def generate_stl(req: CadRequest):
    try:
        import cadquery as cq
        # Execute the generated code
        ns = {"cq": cq}
        exec(req.code, ns)
        result = ns.get("result")

        if result is None:
            return CadResponse(ok=False, error="No 'result' variable found in code.")

        # Export to STL
        filename = f"cad_{uuid.uuid4().hex[:8]}.stl"
        cq.exporters.export(result, filename)

        with open(filename, "rb") as f:
            stl_bytes = f.read()

        # Cleanup file after reading
        if os.path.exists(filename):
            os.remove(filename)

        return CadResponse(
            ok=True,
            filename=filename,
            stl_base64=base64.b64encode(stl_bytes).decode("utf-8")
        )
    except Exception:
        return CadResponse(ok=False, error=traceback.format_exc())