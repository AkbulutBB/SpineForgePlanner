from cx_Freeze import setup, Executable

setup(
    name="SpineForgePlanner",
    version="1.0",
    description="Spinal Alignment GUI Tool",
    executables=[Executable("FirstDraft.py", base="Win32GUI")]
)
