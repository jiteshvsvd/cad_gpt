import os
import uuid
import traceback
import streamlit as st
os.environ["PYOPENGL_PLATFORM"] = "osmesa"
os.environ["MESA_GL_VERSION_OVERRIDE"] = "4.5"
os.environ["MESA_GLSL_VERSION_OVERRIDE"] = "450"
os.environ["OCP_VERBOSE"] = "0"
os.environ["DISPLAY"] = ":99"  # Virtual display
import requests
import base64

from groq import Groq
CAD_BACKEND_URL = st.secrets.get("CAD_BACKEND_URL", "")

# Optional STL viewer component (install: pip install streamlit-stl)
# If not installed, app still works with download only.
try:
    from streamlit_stl import stl_from_file
    HAS_STL_VIEWER = True
except Exception:
    HAS_STL_VIEWER = False

st.set_page_config(page_title="Groq CAD Chat", page_icon="🧩", layout="wide")
st.title("🧩 Groq CAD Chat (CadQuery + Streamlit)")

# ---------------------------
# Config
# ---------------------------
api_key = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY", ""))
if not api_key:
    st.error("GROQ_API_KEY not found. Set it in Streamlit secrets or environment variable.")
    st.stop()

client = Groq(api_key=api_key)

SYSTEM_PROMPT = """
You are an expert mechanical CAD engineer and Python CadQuery programmer.

Return ONLY valid Python code (no markdown fences).
Rules:
1) Use: import cadquery as cq
2) Define parameters at top
3) Create final object in variable: result
4) Do not call show(), display(), exporters, or print()
5) Keep code concise and runnable
"""

MODEL_OPTIONS = [
    "llama-3.3-70b-versatile",
    "qwen/qwen3-7b"
]

with st.sidebar:
    st.header("Settings")
    model_name = st.selectbox("Model", MODEL_OPTIONS, index=0)
    temperature = st.slider("Temperature", 0.0, 1.0, 0.2, 0.1)
    st.caption("Install optional STL viewer: pip install streamlit-stl")
    if st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()

# ---------------------------
# Session state
# ---------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # list of dicts: role/content/type/meta

def clean_code(text: str) -> str:
    lines = text.splitlines()
    cleaned = [ln for ln in lines if not ln.strip().startswith("```")]
    return "\n".join(cleaned).strip()

def generate_cad_code(user_request: str) -> str:
    resp = client.chat.completions.create(
        model=model_name,
        temperature=temperature,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Generate CadQuery Python code for:\n{user_request}"}
        ]
    )
    return resp.choices[0].message.content or ""

# def run_cad_code_and_export_stl(code: str) -> tuple[str, str]:
#     """
#     Returns (stl_path, error_message)
#     """
#     import cadquery as cq
#     try:
#         namespace = {"cq": cq}
#         exec(code, namespace)
#         result = namespace.get("result", None)
#         if result is None:
#             return "", "No variable named `result` found in generated code."

#         file_name = f"cad_{uuid.uuid4().hex[:8]}.stl"
#         # CadQuery export
#         cq.exporters.export(result, file_name)
#         return file_name, ""
#     except Exception:
#         return "", traceback.format_exc()



def run_cad_via_backend(code: str) -> tuple[str, str]:
    """
    Sends code to Render backend and gets back an STL file.
    Returns: (stl_path, error_message)
    """
    if not CAD_BACKEND_URL:
        return "", "CAD_BACKEND_URL is not configured in Streamlit Secrets."

    try:
        # 1. Send the request to Render
        response = requests.post(
            f"{CAD_BACKEND_URL}/generate_stl",
            json={"code": code},
            timeout=120
        )
        
        # 2. Check if the request was successful
        if response.status_code != 200:
            return "", f"Backend Error (Status {response.status_code}): {response.text}"
            
        data = response.json()
        
        if not data.get("ok"):
            return "", data.get("error", "Unknown error from backend.")

        # 3. Decode the STL file sent by the backend
        stl_bytes = base64.b64decode(data["stl_base64"])
        filename = f"cad_{uuid.uuid4().hex[:8]}.stl"
        
        # 4. Save it locally on Streamlit Cloud so the user can download/view it
        with open(filename, "wb") as f:
            f.write(stl_bytes)
            
        return filename, ""
        
    except Exception as e:
        return "", f"Failed to connect to backend: {str(e)}"

# ---------------------------
# Render existing chat
# ---------------------------
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m.get("type") == "text":
            st.markdown(m["content"])
        elif m.get("type") == "code":
            st.code(m["content"], language="python")
        elif m.get("type") == "cad":
            st.markdown("✅ CAD model generated.")
            st.caption(f"STL file: {m['content']}")
            if HAS_STL_VIEWER:
                stl_from_file(
                    file_path=m["content"],
                    color="#87CEEB",
                    material="material",
                    auto_rotate=False,
                    opacity=1.0,
                    height=500,
                    shininess=50,
                    key=f"viewer_{m['content']}"
                )
            with open(m["content"], "rb") as f:
                st.download_button(
                    "Download STL",
                    data=f,
                    file_name=m["content"],
                    mime="model/stl",
                    key=f"dl_{m['content']}"
                )
        elif m.get("type") == "error":
            st.error(m["content"])

# ---------------------------
# Chat input
# ---------------------------
user_msg = st.chat_input("Describe CAD model (example: cylinder radius 5mm, height 10mm, hole radius 2mm)")

if user_msg:
    # store + show user message
    st.session_state.messages.append({"role": "user", "type": "text", "content": user_msg})
    with st.chat_message("user"):
        st.markdown(user_msg)

    # assistant processing
    with st.chat_message("assistant"):
        with st.spinner("Generating CadQuery code..."):
            raw = generate_cad_code(user_msg)
            code = clean_code(raw)

        st.markdown("Here is the generated CadQuery code:")
        st.code(code, language="python")

        st.session_state.messages.append({"role": "assistant", "type": "code", "content": code})

        with st.spinner("Building CAD model..."):
            stl_path, err = run_cad_via_backend(code)

        if err:
            st.error("CAD build failed.")
            st.code(err, language="text")
            st.session_state.messages.append({"role": "assistant", "type": "error", "content": err})
        else:
            st.success("CAD model created successfully.")
            if HAS_STL_VIEWER:
                stl_from_file(
                    file_path=stl_path,
                    color="#87CEEB",
                    material="material",
                    auto_rotate=False,
                    opacity=1.0,
                    height=500,
                    shininess=50,
                    key=f"viewer_new_{stl_path}"
                )

            with open(stl_path, "rb") as f:
                st.download_button(
                    "Download STL",
                    data=f,
                    file_name=stl_path,
                    mime="model/stl",
                    key=f"dl_new_{stl_path}"
                )

            st.session_state.messages.append({"role": "assistant", "type": "cad", "content": stl_path})
